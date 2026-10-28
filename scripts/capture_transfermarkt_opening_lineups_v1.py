#!/usr/bin/env python3
"""Capture first-domestic-fixture XI facts from cached Transfermarkt pages.

This is a reusable source stage, not a PM99 database writer.  It consumes one
hashable squad capture plus an explicit competition-code map, resolves every
selected club deterministically, and records its first league match's
published starting XI.  Modern formation-grid reports retain their formation
and bench; older position-group reports retain the XI but explicitly report
the missing formation/bench facts.  No fallback formation or invented bench
is ever emitted.

The first online pass saves every response in ``--cache-dir``.  Subsequent
``--offline`` runs use only those byte-identical snapshots, so changing an
unrelated aspect of a later database build cannot alter lineup evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup



ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import transfermarkt_calendar_year_policy_v1 as calendar_year_policy  # noqa: E402


BASE_URL = "https://www.transfermarkt.co.uk"
USER_AGENT = "PM99 historical database research (local source capture)"
SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
COMPETITION_MAP_SCHEMA = "pm99-transfermarkt-opening-lineup-competition-map-v1"
CLUB_IDENTITY_ALIAS_SCHEMA = "pm99-transfermarkt-opening-lineup-club-identity-aliases-v1"


class CaptureError(ValueError):
    """A source input or source response cannot support a safe capture."""


def _validate_snapshot_payload(payload: bytes, url: str) -> None:
    """Reject access-control interstitials before they become evidence cache.

    A challenge document can be many kilobytes, so the old size-only guard was
    insufficient. Treat it as a failed acquisition both on first fetch and
    when replaying an existing cache: a byte-identical access-control page is
    not a byte-identical source page.
    """

    if len(payload) < 1_000:
        raise CaptureError(f"source response is implausibly small for {url}")
    sample = payload[:200_000].decode("utf-8", errors="ignore").casefold()
    access_markers = (
        "cf-chl-",
        "challenge-platform",
        "performing security verification",
        "just a moment...",
        "access denied",
    )
    if any(marker in sample for marker in access_markers):
        raise CaptureError(f"source response is an access-control page, not a source document: {url}")


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def _club_key(value: object) -> str:
    """Compare structural club-label variants without changing an identity.

    This intentionally handles only designation words (``FC``, ``AC``) and
    language connectors/numbers.  It does *not* decide that different club
    names such as Inter and Internazionale are equivalent; those require an
    explicit reviewed identity map.
    """

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    words = re.findall(r"[A-Za-z0-9]+", text.casefold())
    ignored = {"a", "ac", "afc", "as", "ca", "cd", "cf", "de", "fc", "la", "le", "rcd", "sc", "ssv", "vfb"}
    return "".join(word for word in words if word not in ignored and not word.isdigit())


@dataclass(frozen=True)
class TeamRef:
    source_club_name: str
    transfermarkt_name: str
    club_id: int
    club_path: str
    identity_match_method: str


class SnapshotCache:
    """A local immutable-by-convention snapshot cache with per-file hashes."""

    def __init__(
        self, directory: Path, *, offline: bool, delay: float,
        validator: Callable[[bytes, str], None] = _validate_snapshot_payload,
    ) -> None:
        self.directory = directory
        self.offline = offline
        self.delay = delay
        self.validator = validator
        self.used: dict[str, dict[str, str]] = {}

    def get(self, url: str, key: str) -> bytes:
        path = self.directory / key
        if path.is_file():
            payload = path.read_bytes()
        elif self.offline:
            raise CaptureError(f"offline snapshot is missing: {path}")
        else:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"})
            with urlopen(request, timeout=30) as response:  # nosec B310: fixed public source host
                payload = response.read()
            self.validator(payload, url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            if self.delay:
                time.sleep(self.delay)
        self.validator(payload, url)
        self.used[key] = {"cache_path": key, "sha256": _sha256_bytes(payload), "url": url}
        return payload


def load_competition_map(path: Path) -> tuple[dict[tuple[str, str], str], str]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read competition map: {path}") from exc
    if not isinstance(document, dict) or raw != _canonical_json_bytes(document):
        raise CaptureError("competition map must be canonical JSON")
    if document.get("schema_version") != COMPETITION_MAP_SCHEMA:
        raise CaptureError(f"competition map must have schema {COMPETITION_MAP_SCHEMA}")
    rows = document.get("competitions")
    if not isinstance(rows, list) or not rows:
        raise CaptureError("competition map needs a non-empty competitions list")
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"competition_catalog", "country_catalog", "source_competition_code"}:
            raise CaptureError("each competition map row must contain country_catalog, competition_catalog and source_competition_code")
        country, competition, code = (row["country_catalog"], row["competition_catalog"], row["source_competition_code"])
        if not all(isinstance(value, str) and value.strip() for value in (country, competition, code)):
            raise CaptureError("competition map values must be non-empty strings")
        key = (country, competition)
        if key in result:
            raise CaptureError(f"competition map duplicates {country}/{competition}")
        result[key] = code
    return dict(sorted(result.items())), _sha256_bytes(raw)


def load_source_capture(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read squad source capture: {path}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("clubs"), list):
        raise CaptureError("squad source capture must contain a clubs list")
    clubs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_club in document["clubs"]:
        if not isinstance(raw_club, dict):
            raise CaptureError("squad source capture contains a non-object club")
        values = {field: raw_club.get(field) for field in ("club_name", "country_catalog", "competition_catalog")}
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise CaptureError("squad source club lacks a country, competition or name")
        key = (str(values["country_catalog"]), str(values["competition_catalog"]), str(values["club_name"]))
        if key in seen:
            raise CaptureError(f"squad source capture duplicates {key}")
        seen.add(key)
        clubs.append(dict(raw_club))
    return sorted(clubs, key=lambda row: (str(row["country_catalog"]), str(row["competition_catalog"]), str(row["club_name"]))), _sha256_bytes(raw)


def _source_selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    key = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise CaptureError("club identity alias selector lacks country_catalog, competition_catalog or club_name")
    return key  # type: ignore[return-value]


def load_club_identity_aliases(path: Path | None) -> tuple[dict[tuple[str, str, str], dict[str, Any]], str | None]:
    """Load reviewed season-competition team IDs; no site-wide name fallback."""

    if path is None:
        return {}, None
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read club identity aliases: {path}") from exc
    if not isinstance(document, dict) or raw != _canonical_json_bytes(document):
        raise CaptureError("club identity aliases must be canonical JSON")
    if document.get("schema_version") != CLUB_IDENTITY_ALIAS_SCHEMA or not isinstance(document.get("aliases"), list):
        raise CaptureError(f"club identity aliases must have schema {CLUB_IDENTITY_ALIAS_SCHEMA} and an aliases list")
    aliases: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in document["aliases"]:
        if not isinstance(entry, dict) or set(entry) != {"reason", "source_selector", "transfermarkt_club_id"}:
            raise CaptureError("each club identity alias needs source_selector, transfermarkt_club_id and reason")
        if not isinstance(entry["source_selector"], dict) or not isinstance(entry["transfermarkt_club_id"], int):
            raise CaptureError("club identity alias has an invalid selector or Transfermarkt club id")
        selector = _source_selector(entry["source_selector"])
        reason = str(entry["reason"] or "").strip()
        if not reason or entry["transfermarkt_club_id"] <= 0:
            raise CaptureError("club identity alias has a blank reason or invalid Transfermarkt club id")
        if selector in aliases:
            raise CaptureError(f"club identity aliases duplicate {selector}")
        aliases[selector] = {"club_id": entry["transfermarkt_club_id"], "reason": reason}
    return aliases, _sha256_bytes(raw)


def _competition_teams(*, season_start_year: int, competition_code: str, cache: SnapshotCache,
                       target_season_start_year: int | None = None) -> list[TeamRef]:
    """Return first-team identities from the exact season's competition page."""

    # Transfermarkt currently ignores the legacy ``?saison_id=`` query on
    # competition start pages and silently serves the current season.  The
    # path-shaped season selector is stable and exposes hash-verifiable links
    # carrying the requested ``/saison_id/<year>`` value.
    url = f"{BASE_URL}/wettbewerb/startseite/wettbewerb/{competition_code}/saison_id/{season_start_year}"
    target_year = season_start_year if target_season_start_year is None else target_season_start_year
    key = calendar_year_policy.cache_key(kind="competition", target_year=target_year,
        provider_year=season_start_year, code=competition_code)
    page = BeautifulSoup(cache.get(url, key), "html.parser")
    candidates: set[tuple[str, str, int]] = set()
    for link in page.select(f'a[href*="/startseite/verein/"][href*="/saison_id/{season_start_year}"]'):
        match = re.search(r"^/([^/]+)/startseite/verein/(\d+)/saison_id/\d+", str(link.get("href") or ""))
        name = str(link.get("title") or link.get_text(" ", strip=True)).strip()
        if match and name:
            candidates.add((name, match.group(1), int(match.group(2))))
    if not candidates:
        raise CaptureError(f"competition {competition_code} has no season-team identities in source page")
    return [TeamRef(source_club_name="", transfermarkt_name=name, club_id=club_id, club_path=f"/{slug}/startseite/verein/{club_id}", identity_match_method="competition-season-roster") for name, slug, club_id in sorted(candidates)]


def _team_ref(club: str, candidates: list[TeamRef]) -> TeamRef:
    exact = [row for row in candidates if _normalise(row.transfermarkt_name) == _normalise(club)]
    method = "exact-season-competition-club-name"
    if len(exact) != 1:
        exact = [row for row in candidates if _club_key(row.transfermarkt_name) == _club_key(club)]
        method = "normalised-season-competition-club-name"
    if len(exact) != 1:
        raw_key = _club_key(club)
        exact = [row for row in candidates if raw_key and (raw_key in _club_key(row.transfermarkt_name) or _club_key(row.transfermarkt_name) in raw_key)]
        method = "unique-containment-within-season-competition"
    if len(exact) != 1:
        names = sorted(row.transfermarkt_name for row in candidates)
        raise CaptureError(f"could not resolve exactly one season-competition club for {club!r}: {names[:12]}")
    selected = exact[0]
    return TeamRef(source_club_name=club, transfermarkt_name=selected.transfermarkt_name, club_id=selected.club_id, club_path=selected.club_path, identity_match_method=method)


def _team_ref_alias(club: str, alias: Mapping[str, Any], candidates: list[TeamRef]) -> TeamRef:
    matches = [row for row in candidates if row.club_id == alias["club_id"]]
    if len(matches) != 1:
        raise CaptureError(f"explicit club identity alias for {club!r} is absent from its declared season competition roster")
    selected = matches[0]
    return TeamRef(
        source_club_name=club, transfermarkt_name=selected.transfermarkt_name, club_id=selected.club_id,
        club_path=selected.club_path, identity_match_method=f"explicit-season-competition-id-alias:{alias['reason']}",
    )


def _first_fixture(ref: TeamRef, *, season_start_year: int, competition_code: str,
                   cache: SnapshotCache, country_catalog: str | None = None) -> dict[str, Any]:
    target_year = season_start_year
    route = calendar_year_policy.route_provider_year(target_year, competition_code, country_catalog)
    provider_year = route.provider_season_id
    slug = ref.club_path.split("/")[1]
    url = f"{BASE_URL}/{slug}/spielplan/verein/{ref.club_id}/saison_id/{provider_year}"
    key = calendar_year_policy.cache_key(kind="schedule", target_year=target_year,
        provider_year=provider_year, code=competition_code, club_id=ref.club_id)
    page_bytes = cache.get(url, key)
    page = BeautifulSoup(page_bytes, "html.parser")
    if provider_year != target_year:
        try:
            calendar_year_policy.require_source_title(page_bytes, provider_year=provider_year,
                target_year=target_year, label="schedule")
        except calendar_year_policy.RoutingError as exc:
            raise CaptureError(str(exc)) from exc
    matches: list[dict[str, Any]] = []
    for row in page.select("tr"):
        report = row.select_one('a[href*="/spielbericht/index/spielbericht/"]')
        competition = row.select_one('a[href*="/test/spieltag/wettbewerb/"]')
        if report is None or competition is None:
            continue
        competition_match = re.search(r"/wettbewerb/([^/]+)", str(competition.get("href") or ""))
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", row.get_text(" ", strip=True))
        report_match = re.search(r"/spielbericht/(\d+)", str(report.get("href") or ""))
        if not competition_match or not date_match or not report_match:
            continue
        if competition_match.group(1) != competition_code:
            continue
        parsed_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
        matches.append({
            "date": parsed_date.isoformat(),
            "match_id": report_match.group(1),
            "report_url": urljoin(BASE_URL, str(report.get("href"))),
            "schedule_url": url,
        })
    if not matches:
        raise CaptureError(f"{ref.source_club_name}: no {competition_code} fixture found in provider season {provider_year}")
    if provider_year != target_year:
        matches = [row for row in matches if datetime.strptime(row["date"], "%Y-%m-%d").year == target_year]
        if not matches:
            raise CaptureError(
                f"{ref.source_club_name}: provider season {provider_year} has no actual fixture in target calendar year {target_year}"
            )
    selected = min(matches, key=lambda row: (row["date"], int(row["match_id"])))
    if provider_year != target_year:
        selected["calendar_year_routing"] = route.document()
        selected["provider_season_id"] = provider_year
        selected["target_calendar_year"] = target_year
    return selected


def _player_from_link(link: Any, *, position_group: str | None = None) -> dict[str, Any]:
    href = str(link.get("href") or "")
    match = re.search(r"^/([^/]+)/profil/spieler/(\d+)", href)
    if not match:
        raise CaptureError(f"unexpected Transfermarkt player link {href!r}")
    result: dict[str, Any] = {
        "display_name": link.get_text(" ", strip=True),
        "source_player_id": match.group(2),
        "source_slug": match.group(1),
        "source_url": urljoin(BASE_URL, href),
    }
    if position_group is not None:
        result["source_position_group"] = position_group
    return result


def _classic_lineup(box: Any) -> tuple[list[dict[str, Any]], str | None]:
    tables = [table for table in box.select('table')
              if 'ersatzbank' not in table.get('class', []) and
              table.find_parent(class_='aufstellung-ersatzbank-box') is None]
    table = tables[0] if len(tables) == 1 else None
    if table is None:
        raise CaptureError("classic lineup box has no lineup table")
    players: list[dict[str, Any]] = []
    manager: str | None = None
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True)
        if label.casefold() == "manager":
            manager = cells[1].get_text(" ", strip=True) or None
            continue
        for link in cells[1].select('a[href*="/profil/spieler/"]'):
            players.append(_player_from_link(link, position_group=label))
    if len(players) != 11:
        raise CaptureError(f"classic match report has {len(players)} starting players, not eleven")
    return players, manager


def _modern_lineup(box: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str | None]:
    subtitle = box.select_one(".formation-subtitle")
    if subtitle is None:
        raise CaptureError("modern lineup box has no formation subtitle")
    formation_match = re.search(r"Starting Line-up:\s*([0-9-]+)", subtitle.get_text(" ", strip=True))
    if formation_match is None:
        raise CaptureError("modern lineup box has no published formation label")
    starters: list[dict[str, Any]] = []
    for container in box.select(".formation-player-container"):
        link = container.select_one('a[href*="/profil/spieler/"]')
        if link is None:
            continue
        starters.append(_player_from_link(link))
    # Some older reports retain the modern published formation heading and
    # pitch, but render anonymous position markers on the pitch.  The same
    # team box still publishes the eleven named starters in its position-group
    # table.  Treat that table as the identity-bearing representation instead
    # of discarding otherwise complete source evidence.
    table_manager: str | None = None
    if not starters and box.select_one("table") is not None:
        starters, table_manager = _classic_lineup(box)
    if len(starters) != 11:
        raise CaptureError(f"modern match report has {len(starters)} starting players, not eleven")
    bench: list[dict[str, Any]] = []
    bench_box = box.select_one(".aufstellung-ersatzbank-box")
    if bench_box is not None:
        for row in bench_box.select("tr"):
            link = row.select_one('a[href*="/profil/spieler/"]')
            if link is not None:
                bench.append(_player_from_link(link))
    manager_link = box.select_one('a[href*="/profil/trainer/"]')
    manager = manager_link.get_text(" ", strip=True) if manager_link is not None else None
    if manager is None:
        manager = table_manager
    return starters, bench, formation_match.group(1), manager or None


def _lineup_from_report(ref: TeamRef, fixture: Mapping[str, Any], cache: SnapshotCache) -> dict[str, Any]:
    route_doc = fixture.get("calendar_year_routing")
    report_key = (calendar_year_policy.cache_key(kind="report",
        target_year=int(fixture["target_calendar_year"]),
        provider_year=int(fixture["provider_season_id"]),
        code=str(route_doc["source_competition_code"]), club_id=int(fixture["match_id"]))
        if route_doc else f"report/{fixture['match_id']}.html")
    page = BeautifulSoup(cache.get(str(fixture["report_url"]), report_key), "html.parser")
    def is_requested_team(box):
        ids = {int(match.group(1)) for a in box.select('a[href]')
               if (match := re.search(r'/startseite/verein/(\d+)(?:/|$)', str(a.get('href') or '')))}
        return ids == {ref.club_id}
    team_boxes = [
        box for box in page.select(".aufstellung-box")
        if is_requested_team(box)
    ]
    if not team_boxes:
        team_boxes = [
            box for box in page.select(".large-6")
            if is_requested_team(box)
        ]
    if len(team_boxes) != 1:
        raise CaptureError(f"{ref.source_club_name}: source report has {len(team_boxes)} candidate lineup boxes")
    box = team_boxes[0]
    if box.select_one(".formation-subtitle") is not None:
        starters, bench, formation, manager = _modern_lineup(box)
        source_style = "published-formation-grid"
        blockers: list[str] = []
        if len(bench) < 5:
            blockers.append("fewer-than-five-published-bench-players")
    else:
        starters, manager = _classic_lineup(box)
        bench, formation = [], None
        source_style = "published-position-groups"
        blockers = ["no-published-formation-grid", "no-published-bench"]
    if manager is None:
        blockers.append("no-published-manager")
    return {
        "source_selector": {
            "club_name": ref.source_club_name,
            "transfermarkt_club_id": ref.club_id,
            "transfermarkt_club_name": ref.transfermarkt_name,
            "transfermarkt_identity_match_method": ref.identity_match_method,
        },
        "first_league_fixture_date": fixture["date"],
        "formation": formation,
        "lineup_source_style": source_style,
        "lineup_source_url": fixture["report_url"],
        "schedule_url": fixture["schedule_url"],
        "source_match_id": fixture["match_id"],
        "starting_xi": starters,
        "substitutes": bench,
        "declared_manager": manager,
        "source_status": "source-qualified" if not blockers else "source-qualified-with-explicit-gaps",
        "source_blockers": blockers,
    }


def _reject_duplicate_club_identities(rows):
    """Do not certify two source club selectors as one provider club.

    A unique substring match can otherwise map Olympiakos to Olympiakos Volos.
    Keep the original failure explicit; do not guess which selector is wrong.
    """
    groups = {}
    for row in rows:
        selector = row['source_selector']
        key = selector['transfermarkt_club_id']
        groups.setdefault(key, []).append(row)
    accepted, failures = [], []
    for group in groups.values():
        selectors = {(r['source_selector']['country_catalog'],
                      r['source_selector']['competition_catalog'],
                      r['source_selector']['club_name']) for r in group}
        if len(selectors) <= 1:
            accepted.extend(group)
            continue
        names = sorted(f'{country}/{competition}/{club}' for country, competition, club in selectors)
        for row in group:
            selector = row['source_selector']
            failures.append({key: selector[key] for key in
                             ('club_name', 'competition_catalog', 'country_catalog')} |
                            {'reason': 'duplicate-provider-club-identity: ' + ', '.join(names)})
    return accepted, failures


def capture(
    *,
    clubs: list[dict[str, Any]],
    source_capture_sha256: str,
    season_start_year: int,
    competition_map: Mapping[tuple[str, str], str],
    competition_map_sha256: str,
    club_identity_aliases: Mapping[tuple[str, str, str], Mapping[str, Any]],
    club_identity_aliases_sha256: str | None,
    cache: SnapshotCache,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    if any(str(competition_map.get((str(row.get("country_catalog")), str(row.get("competition_catalog"))), ""))
           in {*calendar_year_policy.CALENDAR_CODE_COUNTRY, "RU1"} for row in clubs):
        calendar_year_policy.verify_audit(ROOT)
    team_indexes: dict[tuple[str, str], list[TeamRef]] = {}
    route_by_pair: dict[tuple[str, str], calendar_year_policy.YearRoute] = {}
    pairs = sorted({(str(row["country_catalog"]), str(row["competition_catalog"]))
        for row in clubs if (str(row["country_catalog"]), str(row["competition_catalog"])) in competition_map})
    for country, competition in pairs:
        code = competition_map[(country, competition)]
        try:
            route = calendar_year_policy.route_provider_year(season_start_year, code, country)
            route_by_pair[(country, competition)] = route
            team_indexes[(country, competition)] = _competition_teams(
                season_start_year=route.provider_season_id, target_season_start_year=season_start_year,
                competition_code=code, cache=cache,
            )
        except (CaptureError, OSError, ValueError) as exc:
            team_indexes[(country, competition)] = []
            failures.append({"club_name": "<competition-source>", "competition_catalog": competition,
                "country_catalog": country, "reason": f"{code}: {exc}"})
    for source_club in clubs:
        club_name = str(source_club["club_name"])
        country = str(source_club["country_catalog"])
        competition = str(source_club["competition_catalog"])
        code = competition_map.get((country, competition))
        selector = {"club_name": club_name, "competition_catalog": competition, "country_catalog": country}
        if code is None:
            failures.append({**selector, "reason": "no-explicit-transfermarkt-competition-map"})
            continue
        try:
            alias = club_identity_aliases.get((country, competition, club_name))
            candidates = team_indexes[(country, competition)]
            ref = _team_ref_alias(club_name, alias, candidates) if alias is not None else _team_ref(club_name, candidates)
            fixture = _first_fixture(ref, season_start_year=season_start_year, competition_code=code,
                cache=cache, country_catalog=country)
            row = _lineup_from_report(ref, fixture, cache)
            if "calendar_year_routing" in fixture:
                row["calendar_year_routing"] = fixture["calendar_year_routing"]
                row["provider_season_id"] = fixture["provider_season_id"]
                row["target_calendar_year"] = fixture["target_calendar_year"]
            row["source_selector"].update({"competition_catalog": competition, "country_catalog": country})
            row["source_competition_code"] = code
            rows.append(row)
        except (CaptureError, OSError, ValueError) as exc:
            failures.append({**selector, "reason": str(exc)})
    rows, collisions = _reject_duplicate_club_identities(rows)
    failures.extend(collisions)
    rows.sort(key=lambda row: (str(row["source_selector"]["country_catalog"]), str(row["source_selector"]["competition_catalog"]), str(row["source_selector"]["club_name"])))
    failures.sort(key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"]))
    qualified = sum(row["source_status"] == "source-qualified" for row in rows)
    return {
        "schema_version": SCHEMA,
        "season_start_year": season_start_year,
        "snapshot_policy": "first domestic-league fixture per club, ordered by published fixture date then source match id; cached source bytes are hash-bound",
        "source": {
            "name": "Transfermarkt published schedules and match reports",
            "base_url": BASE_URL,
            "source_capture_sha256": source_capture_sha256,
            "competition_map_schema": COMPETITION_MAP_SCHEMA,
            "competition_map_sha256": competition_map_sha256,
            "club_identity_alias_schema": CLUB_IDENTITY_ALIAS_SCHEMA if club_identity_aliases_sha256 is not None else None,
            "club_identity_aliases_sha256": club_identity_aliases_sha256,
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
            **({"calendar_year_routing_audit": calendar_year_policy.verify_audit(ROOT)}
               if any(route.provider_season_id != route.target_year for route in route_by_pair.values()) else {}),
        },
        "summary": {
            "source_club_count": len(clubs),
            "captured_club_count": len(rows),
            "fully-qualified-club-count": qualified,
            "captured-with-explicit-gaps-club-count": len(rows) - qualified,
            "failed-club-count": len(failures),
        },
        "clubs": rows,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--competition-map", required=True, type=Path)
    parser.add_argument("--club-identity-aliases", type=Path, help="canonical reviewed season-competition team IDs")
    parser.add_argument("--season-start-year", required=True, type=int)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--club", action="append", help="capture only this exact source-club name; repeatable development probe")
    parser.add_argument("--offline", action="store_true", help="forbid network access and require cached snapshots")
    parser.add_argument("--delay", type=float, default=0.25, help="delay in seconds after cache misses (default: 0.25)")
    parser.add_argument("--strict", action="store_true", help="return non-zero if any source club is not captured")
    args = parser.parse_args(argv)
    if not 0 <= args.delay <= 5:
        parser.error("--delay must be between 0 and 5 seconds")
    try:
        clubs, source_capture_sha256 = load_source_capture(args.source_capture)
        competition_map, competition_map_sha256 = load_competition_map(args.competition_map)
        club_identity_aliases, club_identity_aliases_sha256 = load_club_identity_aliases(args.club_identity_aliases)
        if args.club:
            wanted = set(args.club)
            clubs = [row for row in clubs if str(row["club_name"]) in wanted]
            if wanted != {str(row["club_name"]) for row in clubs}:
                missing = sorted(wanted - {str(row["club_name"]) for row in clubs})
                raise CaptureError(f"requested source club is absent: {', '.join(missing)}")
        cache = SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay)
        receipt = capture(
            clubs=clubs, source_capture_sha256=source_capture_sha256, season_start_year=args.season_start_year,
            competition_map=competition_map, competition_map_sha256=competition_map_sha256, cache=cache,
            club_identity_aliases=club_identity_aliases, club_identity_aliases_sha256=club_identity_aliases_sha256,
        )
    except (OSError, CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(receipt))
    print(json.dumps(receipt["summary"], sort_keys=True))
    return 1 if args.strict and receipt["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
