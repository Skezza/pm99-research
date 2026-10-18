#!/usr/bin/env python3
"""Fill English opening-lineup gaps from cached Soccerbase match records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


BASE_URL = "https://www.soccerbase.com"
SCHEMA = "pm99-composed-opening-lineup-source-v1"
PRIMARY_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
COMPETITION_LABELS = {
    "faprem": {"premier league"}, "prem": {"premier league"},
    "d1": {"football league div 1"}, "d2": {"football league div 2"},
    "d3": {"football league div 3"}, "flcham": {"championship"},
    "flone": {"football league one", "league one"},
    "fltwo": {"football league two", "league two"},
}


class SoccerbaseCaptureError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    # Soccerbase headings commonly abbreviate United as ``Utd`` while the
    # frozen squad source spells it out. This is an explicit lexical alias,
    # not a fuzzy identity match.
    text = re.sub(r"\bUtd\b", "United", text, flags=re.I)
    return "".join(char.casefold() for char in text if char.isalnum() and not unicodedata.combining(char))


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(key) or "").strip() for key in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise SoccerbaseCaptureError("source selector is incomplete")
    return result  # type: ignore[return-value]


class Cache:
    def __init__(self, root: Path, *, offline: bool, delay: float) -> None:
        self.root, self.offline, self.delay = root, offline, delay
        self.used: dict[str, dict[str, str]] = {}

    def get(self, url: str, key: str) -> bytes:
        path = self.root / key
        if path.is_file():
            payload = path.read_bytes()
        elif self.offline:
            raise SoccerbaseCaptureError(f"offline snapshot is missing: {path}")
        else:
            request = Request(url, headers={"User-Agent": "PM99 historical database research (local source capture)", "Accept-Language": "en-GB,en;q=0.9"})
            with urlopen(request, timeout=30) as response:  # nosec B310: fixed source host
                payload = response.read()
            if self.delay:
                time.sleep(self.delay)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        sample = payload[:100_000].decode("utf-8", errors="ignore").casefold()
        if len(payload) < 1000 or "just a moment..." in sample or "cf-chl-" in sample:
            raise SoccerbaseCaptureError(f"source response is not a usable Soccerbase document: {url}")
        self.used[key] = {"cache_path": f"soccerbase/{key}", "sha256": hashlib.sha256(payload).hexdigest(), "url": url}
        return payload


def _team_candidates(club_name: str, cache: Cache) -> list[tuple[int, str]]:
    queries = [club_name]
    if "&" in club_name:
        queries.append(club_name.split("&", 1)[0].strip())
    candidates: set[tuple[int, str]] = set()
    for query in queries:
        url = f"{BASE_URL}/teams/search_results.sd?type=team&search={quote_plus(query)}"
        page = BeautifulSoup(cache.get(url, f"team-search/{hashlib.sha256(query.encode()).hexdigest()}.html"), "html.parser")
        canonical = page.select_one('link[rel="canonical"][href*="team_id="]')
        heading = page.select_one("h1")
        published = re.sub(r"\s+Club details\s*$", "", heading.get_text(" ", strip=True) if heading else "")
        links = [canonical] if canonical is not None else page.select('a[href*="/teams/team.sd?team_id="]')
        for link in links:
            match = re.search(r"team_id=(\d+)", str(link.get("href") or ""))
            name = published if canonical is not None else link.get_text(" ", strip=True)
            if match and name and (_normalise(name) in _normalise(club_name) or _normalise(club_name) in _normalise(name)):
                candidates.add((int(match.group(1)), name))
    return sorted(candidates)


def _team_identity(club_name: str, cache: Cache) -> tuple[int, str]:
    candidates = _team_candidates(club_name, cache)
    if len(candidates) != 1:
        raise SoccerbaseCaptureError(f"{club_name}: exact Soccerbase team search resolved {len(candidates)} compatible clubs")
    return candidates[0]


def _first_fixture(club_name: str, team_id: int, competition_catalog: str, season_start_year: int, cache: Cache) -> dict[str, Any]:
    season_id = season_start_year - 1870
    url = f"{BASE_URL}/teams/team.sd?team_id={team_id}&teamTabs=results&season_id={season_id}"
    page = BeautifulSoup(cache.get(url, f"team-season/{season_start_year}/{team_id}.html"), "html.parser")
    expected_season = f"{season_start_year}/{season_start_year + 1}"
    if not any(option.get_text(" ", strip=True) == expected_season and str(option.get("value")) == str(season_id) for option in page.select("select#seasonSelect option")):
        raise SoccerbaseCaptureError(f"{club_name}: Soccerbase season selector does not verify {expected_season}")
    labels = COMPETITION_LABELS.get(competition_catalog)
    if labels is None:
        raise SoccerbaseCaptureError(f"{club_name}: no reviewed Soccerbase competition label for {competition_catalog}")
    candidates = []
    for row in page.select("tr.match[id^=tgc]"):
        competition_link = row.select_one("td.tournament a")
        competition = _normalise(competition_link.get_text(" ", strip=True) if competition_link else "")
        if competition not in {_normalise(label) for label in labels}:
            continue
        target = row.select_one(f'a[href*="team_id={team_id}"]')
        hidden_date = row.select_one("td.dateTime span.hide")
        if target is None or hidden_date is None:
            continue
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", hidden_date.get_text(" ", strip=True))
        game_match = re.fullmatch(r"tgc(\d+)", str(row.get("id") or ""))
        teams = row.select("td.team")
        if not date_match or not game_match or len(teams) != 2:
            continue
        candidates.append({"date": date_match.group(0), "game_id": game_match.group(1), "side": 0 if target.find_parent("td") is teams[0] else 1, "schedule_url": url})
    if not candidates:
        raise SoccerbaseCaptureError(f"{club_name}: no exact {competition_catalog} fixture in Soccerbase season results")
    return min(candidates, key=lambda row: (row["date"], int(row["game_id"])))


def _profile_name(player_id: str, short_name: str, cache: Cache) -> str:
    url = f"{BASE_URL}/players/player.sd?player_id={player_id}"
    page = BeautifulSoup(cache.get(url, f"player/{player_id}.html"), "html.parser")
    heading = page.select_one("h1")
    name = heading.get_text(" ", strip=True) if heading else ""
    if not name:
        raise SoccerbaseCaptureError(f"player {player_id}: profile has no published full name")
    surname = _normalise(short_name.split()[-1] if short_name.split() else "")
    if surname and not _normalise(name).endswith(surname):
        raise SoccerbaseCaptureError(f"player {player_id}: profile name does not corroborate match name")
    return name


def _lineup(club_name: str, team_id: int, published_team_name: str, fixture: Mapping[str, Any], cache: Cache) -> dict[str, Any]:
    url = f"{BASE_URL}/matches/additional_information.sd?id_game={fixture['game_id']}"
    page = BeautifulSoup(cache.get(url, f"match/{fixture['game_id']}.html"), "html.parser")
    tables = [table for table in page.select("table") if len(table.select('a[href*="/players/player.sd?player_id="]')) >= 11]
    if len(tables) != 2:
        raise SoccerbaseCaptureError(f"{club_name}: Soccerbase game {fixture['game_id']} has {len(tables)} lineup tables")
    table = tables[int(fixture["side"])]
    starters, substitutes = [], []
    unknown_starter_roles = 0
    after_separator = False
    for row in table.select("tr"):
        if row.select_one("td.separator") is not None:
            after_separator = True
            continue
        link = row.select_one('a[href*="/players/player.sd?player_id="]')
        if link is None:
            continue
        match = re.search(r"player_id=(\d+)", str(link.get("href") or ""))
        role_match = re.search(r"\(([GDMF])\)", row.get_text(" ", strip=True))
        if not match:
            raise SoccerbaseCaptureError(f"{club_name}: malformed Soccerbase lineup player row")
        player_id = match.group(1)
        short_name = link.get_text(" ", strip=True)
        full_name = _profile_name(player_id, short_name, cache)
        role = role_match.group(1) if role_match else None
        if role is None and not after_separator:
            unknown_starter_roles += 1
        player = {
            "display_name": full_name, "source_player_id": f"soccerbase:{player_id}",
            "source_slug": "-".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode().casefold())),
            "source_url": f"{BASE_URL}/players/player.sd?player_id={player_id}",
        }
        if role is not None:
            player.update({"source_position": role, "source_position_group": {"G": "Goalkeeper", "D": "Defenders", "M": "Midfielders", "F": "Forwards"}[role]})
        (substitutes if after_separator else starters).append(player)
    if len(starters) != 11:
        raise SoccerbaseCaptureError(f"{club_name}: Soccerbase game has {len(starters)} starters, not eleven")
    selector = {"country_catalog": "eng", "competition_catalog": "", "club_name": club_name, "soccerbase_team_id": team_id, "soccerbase_team_name": published_team_name, "soccerbase_identity_match_method": "exact-search-redirect-plus-compatible-published-name"}
    blockers = ["no-published-formation-grid", "no-published-manager"]
    if unknown_starter_roles:
        blockers.append(f"{unknown_starter_roles}-starter-roles-not-published")
    return {"source_selector": selector, "first_league_fixture_date": fixture["date"], "formation": None, "lineup_source_style": "soccerbase-published-role-groups", "lineup_source_url": url, "schedule_url": fixture["schedule_url"], "source_match_id": f"soccerbase:{fixture['game_id']}", "starting_xi": starters, "substitutes": substitutes, "declared_manager": None, "source_status": "source-qualified-with-explicit-gaps", "source_blockers": blockers}


def supplement(
    *, source_capture: Mapping[str, Any], source_capture_sha256: str,
    primary: Mapping[str, Any], primary_sha256: str, season_start_year: int, cache: Cache,
    lineup_source_selection: Mapping[str, Any] | None = None,
    lineup_source_selection_sha256: str | None = None,
    source_intake: Mapping[str, Any] | None = None,
    source_intake_sha256: str | None = None,
) -> dict[str, Any]:
    if primary.get("schema_version") != PRIMARY_SCHEMA:
        raise SoccerbaseCaptureError(f"primary lineup receipt must have schema {PRIMARY_SCHEMA}")
    primary_source_sha = (primary.get("source") or {}).get("source_capture_sha256")
    selected_keys: set[tuple[str, str, str]] | None = None
    if primary_source_sha != source_capture_sha256:
        if lineup_source_selection is None or primary_source_sha != lineup_source_selection_sha256:
            raise SoccerbaseCaptureError("primary lineup receipt targets a different squad source")
        if (
            source_intake is None
            or lineup_source_selection.get("source_intake_sha256") != source_intake_sha256
            or source_intake.get("source_capture_sha256") != source_capture_sha256
        ):
            raise SoccerbaseCaptureError("lineup source selection is not bound through the exact source intake")
        selected_keys = {_selector(row) for row in lineup_source_selection.get("clubs") or []}
    captured = {_selector(row["source_selector"]): dict(row) for row in primary.get("clubs") or []}
    source_clubs = {_selector(row): row for row in source_capture.get("clubs") or []}
    if selected_keys is not None:
        missing = selected_keys - set(source_clubs)
        if missing:
            raise SoccerbaseCaptureError(f"lineup source selection is absent from squad source: {sorted(missing)[:3]}")
        source_clubs = {key: source_clubs[key] for key in sorted(selected_keys)}
        if not set(captured) <= selected_keys:
            raise SoccerbaseCaptureError("primary lineup receipt contains a club outside its source selection")
    failures = []
    supplemented = 0
    for key, source_club in sorted(source_clubs.items()):
        if key in captured or key[0] != "eng":
            continue
        try:
            viable = []
            for team_id, published in _team_candidates(key[2], cache):
                try:
                    viable.append((team_id, published, _first_fixture(key[2], team_id, key[1], season_start_year, cache)))
                except SoccerbaseCaptureError:
                    continue
            if len(viable) != 1:
                raise SoccerbaseCaptureError(f"{key[2]}: {len(viable)} compatible Soccerbase identities have an exact season/competition fixture")
            team_id, published, fixture = viable[0]
            row = _lineup(key[2], team_id, published, fixture, cache)
            row["source_selector"]["competition_catalog"] = key[1]
            captured[key] = row
            supplemented += 1
        except (OSError, ValueError, SoccerbaseCaptureError) as exc:
            failures.append({"country_catalog": key[0], "competition_catalog": key[1], "club_name": key[2], "reason": str(exc)})
    failure_keys = {
        (row["country_catalog"], row["competition_catalog"], row["club_name"])
        for row in failures
    }
    for failure in primary.get("failures") or []:
        if failure.get("club_name") == "<competition-source>":
            continue
        key = (str(failure.get("country_catalog") or ""), str(failure.get("competition_catalog") or ""), str(failure.get("club_name") or ""))
        if key not in captured and key in source_clubs and key not in failure_keys:
            failures.append(dict(failure))
            failure_keys.add(key)
    for key in sorted(set(source_clubs) - set(captured) - failure_keys):
        failures.append({
            "country_catalog": key[0],
            "competition_catalog": key[1],
            "club_name": key[2],
            "reason": "selected club is uncaptured by the primary receipt and has no applicable exact Soccerbase supplement",
        })
    cache_files = list((primary.get("source") or {}).get("cache_files") or []) + [cache.used[key] for key in sorted(cache.used)]
    return {"schema_version": SCHEMA, "season_start_year": season_start_year, "snapshot_policy": primary.get("snapshot_policy"), "source": {"name": "Composed Transfermarkt and Soccerbase published schedules/match reports", "source_capture_sha256": source_capture_sha256, "lineup_source_selection_sha256": lineup_source_selection_sha256, "primary_lineup_sha256": primary_sha256, "cache_files": cache_files, "credits": ["Transfermarkt", "Soccerbase"]}, "summary": {"source_club_count": len(source_clubs), "captured_club_count": len(captured), "soccerbase-supplemented-club-count": supplemented, "failed-club-count": len(failures)}, "clubs": [captured[key] for key in sorted(captured)], "failures": sorted(failures, key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"]))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--primary-lineups", type=Path, required=True)
    parser.add_argument("--lineup-source-selection", type=Path)
    parser.add_argument("--source-intake", type=Path,
                        help="exact immutable intake required when the primary used a selector projection")
    parser.add_argument("--season-start-year", type=int, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    source_raw, primary_raw = args.source_capture.read_bytes(), args.primary_lineups.read_bytes()
    selection, selection_sha = None, None
    if args.lineup_source_selection is not None:
        selection_raw = args.lineup_source_selection.read_bytes()
        selection, selection_sha = json.loads(selection_raw), hashlib.sha256(selection_raw).hexdigest()
    intake, intake_sha = None, None
    if args.source_intake is not None:
        intake_raw = args.source_intake.read_bytes()
        intake, intake_sha = json.loads(intake_raw), hashlib.sha256(intake_raw).hexdigest()
    result = supplement(source_capture=json.loads(source_raw), source_capture_sha256=hashlib.sha256(source_raw).hexdigest(), primary=json.loads(primary_raw), primary_sha256=hashlib.sha256(primary_raw).hexdigest(), season_start_year=args.season_start_year, cache=Cache(args.cache_dir, offline=args.offline, delay=args.delay), lineup_source_selection=selection, lineup_source_selection_sha256=selection_sha, source_intake=intake, source_intake_sha256=intake_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
