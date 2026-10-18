#!/usr/bin/env python3
"""Capture first-league-match XI/bench/formation evidence for English-92 2015/16.

This is deliberately a source-capture step, not a PM99 writer.  It resolves
each club's Transfermarkt team and season schedule, selects its first 2015/16
league fixture from the known division competition code, and records the
published formation grid, eleven, full substitute bench and source URLs.

The resulting local ledger must be reconciled to the factual squad ledger
before a season compiler changes a roster.  A missing or unexpected source
shape is therefore an error rather than a reason to insert a generic 4-4-2.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.transfermarkt.co.uk"
USER_AGENT = "PM99 historical database research (local source capture)"
DIVISION_COMPETITIONS = {
    "Premier League": "GB1",
    "Championship": "GB2",
    "League One": "GB3",
    "League Two": "GB4",
}
# Search names can collide with a foreign club. Each override is a deliberate,
# reviewable English team id rather than a position-dependent "first result".
TEAM_ID_OVERRIDES = {
    "Arsenal": 11,
    "Brighton & Hove Albion": 1237,
    "Dagenham & Redbridge": 3696,
    "Southend United": 2793,
}
TEAM_SEARCH_NAMES = {
    "Bournemouth": "AFC Bournemouth",
    "Brighton & Hove Albion": "Brighton and Hove Albion",
    "Dagenham & Redbridge": "Dagenham",
    "Rochdale": "Rochdale AFC",
    "Sunderland": "Sunderland AFC",
}


@dataclass(frozen=True)
class TeamRef:
    club: str
    transfermarkt_name: str
    club_id: int
    club_path: str


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def _club_key(value: str) -> str:
    key = _normalise(value)
    for suffix in ("footballclub", "fc"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return key


def _get(url: str, cache_dir: Path, key: str, *, delay: float) -> bytes:
    cache_path = cache_dir / key
    if cache_path.is_file():
        return cache_path.read_bytes()
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"})
    with urlopen(request, timeout=30) as response:  # nosec B310: fixed public source host
        payload = response.read()
    if len(payload) < 1_000:
        raise RuntimeError(f"Source response is implausibly small for {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(payload)
    if delay:
        time.sleep(delay)
    return payload


def _team_ref(club: str, cache_dir: Path, *, delay: float) -> TeamRef:
    search_name = TEAM_SEARCH_NAMES.get(club, club)
    url = f"{BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={quote(search_name)}"
    page = BeautifulSoup(_get(url, cache_dir, f"search/{_normalise(search_name)}.html", delay=delay), "html.parser")
    candidates: list[tuple[str, str, int]] = []
    for link in page.select('a[href*="/startseite/verein/"]'):
        name = link.get_text(" ", strip=True)
        match = re.search(r"^/([^/]+)/startseite/verein/(\d+)", str(link.get("href") or ""))
        if name and match:
            candidates.append((name, match.group(1), int(match.group(2))))
    unique_candidates = {(name, slug, club_id) for name, slug, club_id in candidates}
    override = TEAM_ID_OVERRIDES.get(club)
    if override is not None:
        exact = [candidate for candidate in unique_candidates if candidate[2] == override]
    else:
        exact_name = [candidate for candidate in unique_candidates if _normalise(candidate[0]) == _normalise(search_name)]
        exact = exact_name if len(exact_name) == 1 else [candidate for candidate in unique_candidates if _club_key(candidate[0]) == _club_key(search_name)]
    if len(exact) != 1:
        raise ValueError(f"Could not resolve one Transfermarkt club for {club!r}: {[row[0] for row in candidates[:8]]}")
    name, slug, club_id = exact[0]
    return TeamRef(club=club, transfermarkt_name=name, club_id=club_id, club_path=f"/{slug}/startseite/verein/{club_id}")


def _first_league_fixture(ref: TeamRef, division: str, cache_dir: Path, *, delay: float) -> dict[str, str]:
    expected_competition = DIVISION_COMPETITIONS.get(division)
    if expected_competition is None:
        raise ValueError(f"No Transfermarkt competition mapping for {division!r}")
    slug = ref.club_path.split("/")[1]
    url = f"{BASE_URL}/{slug}/spielplan/verein/{ref.club_id}/saison_id/2015"
    page = BeautifulSoup(_get(url, cache_dir, f"schedule/{ref.club_id}.html", delay=delay), "html.parser")
    matches: list[dict[str, str]] = []
    for row in page.select("tr"):
        report = row.select_one('a[href*="/spielbericht/index/spielbericht/"]')
        competition = row.select_one('a[href*="/test/spieltag/wettbewerb/"]')
        if report is None or competition is None:
            continue
        comp_match = re.search(r"/wettbewerb/([^/]+)/", str(competition.get("href") or ""))
        date_match = re.search(r"\b(\d{2}/\d{2}/2015)\b", row.get_text(" ", strip=True))
        report_match = re.search(r"/spielbericht/(\d+)", str(report.get("href") or ""))
        if not comp_match or not date_match or not report_match:
            continue
        matches.append({
            "competition": comp_match.group(1),
            "date": date_match.group(1),
            "match_id": report_match.group(1),
            "report_url": urljoin(BASE_URL, str(report.get("href"))),
            "schedule_url": url,
        })
    league_matches = [row for row in matches if row["competition"] == expected_competition]
    if not league_matches:
        raise ValueError(f"{ref.club}: no {division} fixture found on its 2015/16 schedule")
    # The schedule is chronological, but make the source invariant explicit.
    league_matches.sort(key=lambda row: tuple(int(part) for part in row["date"].split("/")[::-1]))
    return league_matches[0]


def _percent(style: str, field: str) -> float:
    match = re.search(rf"{field}:\s*([0-9.]+)%", style or "")
    if not match:
        raise ValueError(f"formation player has no {field} percentage")
    return float(match.group(1))


def _team_box_for_ref(page: BeautifulSoup, ref: TeamRef) -> Any:
    for heading in page.select(".formation-subtitle"):
        box = heading.find_parent("div", class_="large-6")
        if box is None:
            continue
        club_links = box.select(f'a[href*="/startseite/verein/{ref.club_id}"]')
        if club_links:
            return box
    raise ValueError(f"{ref.club}: match report has no formation box for Transfermarkt club {ref.club_id}")


def _player_from_link(link: Any) -> dict[str, str]:
    href = str(link.get("href") or "")
    match = re.search(r"^/([^/]+)/profil/spieler/(\d+)", href)
    if not match:
        raise ValueError(f"unexpected Transfermarkt player link {href!r}")
    return {
        "display_name": link.get_text(" ", strip=True),
        "source_slug": match.group(1),
        "source_player_id": match.group(2),
        "source_url": urljoin(BASE_URL, href),
    }


def _lineup_from_report(ref: TeamRef, fixture: dict[str, str], cache_dir: Path, *, delay: float) -> dict[str, Any]:
    page = BeautifulSoup(_get(fixture["report_url"], cache_dir, f"report/{fixture['match_id']}.html", delay=delay), "html.parser")
    box = _team_box_for_ref(page, ref)
    subtitle = box.select_one(".formation-subtitle")
    if subtitle is None:
        raise ValueError(f"{ref.club}: no published starting formation in {fixture['report_url']}")
    formation_match = re.search(r"Starting Line-up:\s*([0-9-]+)", subtitle.get_text(" ", strip=True))
    if formation_match is None:
        raise ValueError(f"{ref.club}: could not parse formation label {subtitle.get_text(' ', strip=True)!r}")
    starters: list[dict[str, Any]] = []
    for container in box.select(".formation-player-container"):
        link = container.select_one('a[href*="/profil/spieler/"]')
        if link is None:
            continue
        player = _player_from_link(link)
        style = str(container.get("style") or "")
        player.update({"pitch_top_percent": _percent(style, "top"), "pitch_left_percent": _percent(style, "left")})
        shirt = container.select_one(".tm-shirt-number")
        shirt_text = shirt.get_text(" ", strip=True) if shirt is not None else ""
        if not shirt_text.isdigit():
            raise ValueError(f"{ref.club}: starter {player['display_name']} has no numeric published shirt number")
        player["source_shirt_number"] = int(shirt_text)
        starters.append(player)
    if len(starters) != 11:
        raise ValueError(f"{ref.club}: expected eleven starters, found {len(starters)}")
    bench_box = box.select_one(".aufstellung-ersatzbank-box")
    if bench_box is None:
        raise ValueError(f"{ref.club}: match report has no substitute bench")
    bench: list[dict[str, Any]] = []
    for row in bench_box.select("tr"):
        link = row.select_one('a[href*="/profil/spieler/"]')
        if link is None:
            continue
        player = _player_from_link(link)
        shirt = row.select_one(".tm-shirt-number")
        shirt_text = shirt.get_text(" ", strip=True) if shirt is not None else ""
        if not shirt_text.isdigit():
            raise ValueError(f"{ref.club}: substitute {player['display_name']} has no numeric published shirt number")
        cells = row.select("td")
        player["source_shirt_number"] = int(shirt_text)
        player["source_position_label"] = cells[-1].get_text(" ", strip=True) if len(cells) >= 3 else ""
        bench.append(player)
    if len(bench) < 5:
        raise ValueError(f"{ref.club}: match report has fewer than five substitutes")
    club_name = next((link.get_text(" ", strip=True) for link in box.select(f'a[href*="/startseite/verein/{ref.club_id}"]') if link.get_text(" ", strip=True)), ref.transfermarkt_name)
    return {
        "club": ref.club,
        "transfermarkt_club_name": club_name,
        "transfermarkt_club_id": ref.club_id,
        "first_league_fixture_date": fixture["date"],
        "schedule_url": fixture["schedule_url"],
        "lineup_source_url": fixture["report_url"],
        "source_match_id": fixture["match_id"],
        "formation": formation_match.group(1),
        "starting_xi": starters,
        "substitutes": bench,
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", type=Path, default=ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".local/season-2015-16/transfermarkt-opening-lineups-cache")
    parser.add_argument("--limit", type=int, help="capture only the first N source-ledger clubs; development probe only")
    parser.add_argument("--delay", type=float, default=0.25, help="delay after a cache miss in seconds (default: 0.25)")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.delay < 0 or args.delay > 5:
        raise SystemExit("--delay must be between 0 and 5 seconds")
    source = json.loads(args.source_ledger.read_text(encoding="utf-8"))
    clubs = list(source.get("clubs") or [])
    if len(clubs) != 92:
        raise SystemExit("source ledger must contain exactly 92 clubs")
    if args.limit is not None:
        if not 1 <= args.limit <= len(clubs):
            raise SystemExit("--limit must be between 1 and 92")
        clubs = clubs[:args.limit]
    rows = []
    for source_club in clubs:
        club = str(source_club["club"])
        division = str(source_club["division"])
        ref = _team_ref(club, args.cache_dir, delay=args.delay)
        fixture = _first_league_fixture(ref, division, args.cache_dir, delay=args.delay)
        rows.append(_lineup_from_report(ref, fixture, args.cache_dir, delay=args.delay))
        print(f"captured {club}: {rows[-1]['first_league_fixture_date']} {rows[-1]['formation']}")
    output = {
        "schema_version": "pm99-2015-16-opening-lineup-source-v1",
        "season": "2015/16",
        "snapshot_policy": "Kick-off of each club's first 2015/16 league fixture.",
        "source": "Transfermarkt published schedule and match-report formation grids",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "clubs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
