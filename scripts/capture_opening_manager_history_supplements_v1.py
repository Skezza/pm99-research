#!/usr/bin/env python3
"""Capture dated opening managers from cached Transfermarkt club histories.

This supplements only clubs whose first-match receipt has no declared manager.
Club identity is resolved inside the exact season competition (or by an
explicit reviewed identity alias), and the manager must uniquely cover the
club's first league fixture date.  No native/current-manager fallback exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_opening_lineups_v1 as opening


SCHEMA = "pm99-opening-manager-supplement-v1"


class ManagerHistoryError(ValueError):
    """Manager-history evidence is malformed or ambiguous."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerHistoryError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ManagerHistoryError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise ManagerHistoryError("club selector is incomplete")
    return result  # type: ignore[return-value]


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ManagerHistoryError(f"manager history has invalid date {text!r}") from exc


def manager_at_date(payload: bytes, fixture_date: date) -> tuple[str, str]:
    page = BeautifulSoup(payload, "html.parser")
    matches: list[tuple[str, str]] = []
    for row in page.select("table.items tbody tr"):
        cells = row.select(":scope > td")
        links = row.select('a[href*="/profil/trainer/"]')
        link = next(
            (candidate for candidate in links if str(candidate.get("title") or candidate.get_text(" ", strip=True)).strip()),
            None,
        )
        if link is None or len(cells) < 4:
            continue
        appointed = _parse_date(cells[2].get_text(" ", strip=True))
        ended = _parse_date(cells[3].get_text(" ", strip=True))
        if appointed is None or fixture_date < appointed or (ended is not None and fixture_date > ended):
            continue
        href = str(link.get("href") or "")
        manager_id = re.search(r"/profil/trainer/(\d+)", href)
        name = str(link.get("title") or link.get_text(" ", strip=True)).strip()
        if name and manager_id is not None:
            matches.append((name, manager_id.group(1)))
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise ManagerHistoryError(f"manager history has {len(unique)} managers covering {fixture_date.isoformat()}")
    return unique[0]


def capture(
    *, source_capture: Mapping[str, Any], source_capture_sha256: str,
    lineups: Mapping[str, Any], lineup_sha256: str,
    lineup_source_selection: Mapping[str, Any] | None,
    lineup_source_selection_sha256: str | None,
    competition_map: Mapping[tuple[str, str], str], competition_map_sha256: str,
    aliases: Mapping[tuple[str, str, str], Mapping[str, Any]], aliases_sha256: str | None,
    cache: opening.SnapshotCache,
) -> dict[str, Any]:
    lineup_source = lineups.get("source") or {}
    expected_capture_sha = lineup_source.get("source_capture_sha256")
    expected_selection_sha = lineup_source.get("lineup_source_selection_sha256")
    selected_club_keys: set[tuple[str, str, str]] | None = None
    if not isinstance(expected_capture_sha, str) or not expected_capture_sha:
        raise ManagerHistoryError("opening lineups have no source capture or selector projection hash")
    if expected_selection_sha is not None:
        # Composed receipts declare both links: full current squad capture and
        # the narrower club-selector projection used for opening fixtures.
        if expected_capture_sha != source_capture_sha256:
            raise ManagerHistoryError("opening lineups target a different source capture")
        if not isinstance(expected_selection_sha, str) or not expected_selection_sha:
            raise ManagerHistoryError("opening lineups have an invalid selector projection hash")
        required_selection_sha = expected_selection_sha
    else:
        # Older direct Transfermarkt receipts used source_capture_sha256 for
        # their selector file.  The supplied full source remains necessary to
        # validate that projection is a subset of the current season capture.
        required_selection_sha = expected_capture_sha
    if required_selection_sha:
        if lineup_source_selection is None or lineup_source_selection_sha256 != required_selection_sha:
            raise ManagerHistoryError("opening lineups target a different selector projection")
        selection_rows = lineup_source_selection.get("clubs")
        if not isinstance(selection_rows, list):
            raise ManagerHistoryError("selector projection has no club list")
        selected_club_keys = set()
        for row in selection_rows:
            if not isinstance(row, Mapping):
                raise ManagerHistoryError("selector projection has a malformed club")
            selector = _selector(row)
            if selector in selected_club_keys:
                raise ManagerHistoryError("selector projection has a duplicate club")
            selected_club_keys.add(selector)
    year = lineups.get("season_start_year")
    if not isinstance(year, int):
        raise ManagerHistoryError("opening lineups have no season start year")
    lineup_by_club = {_selector(row["source_selector"]): row for row in lineups.get("clubs") or []}
    source_clubs = source_capture.get("clubs")
    if not isinstance(source_clubs, list):
        raise ManagerHistoryError("source capture has no club list")
    source_club_keys = {_selector(row) for row in source_clubs}
    if selected_club_keys is not None:
        missing = sorted(selected_club_keys - source_club_keys)
        if missing:
            raise ManagerHistoryError("selector projection contains clubs absent from source capture")
        source_clubs = [row for row in source_clubs if _selector(row) in selected_club_keys]
    clubs = sorted(source_clubs, key=lambda row: _selector(row))
    team_indexes: dict[str, list[opening.TeamRef]] = {}
    managers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for club in clubs:
        selector = _selector(club)
        selector_object = dict(zip(("country_catalog", "competition_catalog", "club_name"), selector))
        lineup = lineup_by_club.get(selector)
        if str((lineup or {}).get("declared_manager") or "").strip():
            continue
        try:
            code = competition_map.get(selector[:2])
            if code is None:
                raise ManagerHistoryError("no-explicit-transfermarkt-competition-map")
            lineup_selector = (lineup or {}).get("source_selector") or {}
            lineup_club_id = lineup_selector.get("transfermarkt_club_id")
            schedule_url = str((lineup or {}).get("schedule_url") or "")
            fixture_date_value = str((lineup or {}).get("first_league_fixture_date") or "")
            if lineup_club_id is not None and schedule_url and fixture_date_value:
                club_id = int(lineup_club_id)
                slug_match = re.search(r"transfermarkt\.co\.uk/([^/]+)/spielplan/", schedule_url)
                if slug_match is None:
                    raise ManagerHistoryError("captured lineup has no reusable Transfermarkt club slug")
                ref = opening.TeamRef(str(selector[2]), str(lineup_selector.get("transfermarkt_club_name") or selector[2]), club_id, f"/{slug_match.group(1)}/startseite/verein/{club_id}", "opening-lineup-receipt")
                fixture = {"date": fixture_date_value, "schedule_url": schedule_url}
            else:
                if code not in team_indexes:
                    team_indexes[code] = opening._competition_teams(season_start_year=year, competition_code=code, cache=cache)
                alias = aliases.get(selector)
                ref = opening._team_ref_alias(selector[2], alias, team_indexes[code]) if alias is not None else opening._team_ref(selector[2], team_indexes[code])
                fixture = opening._first_fixture(ref, season_start_year=year, competition_code=code, cache=cache)
            fixture_date = date.fromisoformat(str(fixture["date"]))
            slug = ref.club_path.split("/")[1]
            url = f"{opening.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{ref.club_id}"
            key = f"manager-history/{ref.club_id}.html"
            payload = cache.get(url, key)
            manager_name, manager_id = manager_at_date(payload, fixture_date)
            snapshot = cache.used[key]
            managers.append({
                "source_selector": selector_object,
                "opening_fixture_date": fixture_date.isoformat(),
                "manager_name": manager_name,
                "source_name": "Transfermarkt published club manager history",
                "source_url": url,
                "source_snapshot_sha256": snapshot["sha256"],
                "reason": f"manager id {manager_id} uniquely covers the sourced first-league-fixture date",
            })
        except (KeyError, OSError, ValueError, opening.CaptureError, ManagerHistoryError) as exc:
            gaps.append({"source_selector": selector_object, "reason": str(exc)})
    return {
        "schema_version": SCHEMA,
        "season_start_year": year,
        "sources": {
            "full_source_capture_sha256": source_capture_sha256,
            "lineup_source_capture_or_selector_sha256": expected_capture_sha,
            "opening_lineup_sha256": lineup_sha256,
            "lineup_source_selection_sha256": lineup_source_selection_sha256,
            "competition_map_sha256": competition_map_sha256,
            "club_identity_aliases_sha256": aliases_sha256,
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "summary": {"supplemented_manager_count": len(managers), "unresolved_manager_count": len(gaps)},
        "managers": sorted(managers, key=lambda row: _selector(row["source_selector"])),
        "gaps": sorted(gaps, key=lambda row: _selector(row["source_selector"])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--opening-lineups", required=True, type=Path)
    parser.add_argument("--lineup-source-selection", type=Path)
    parser.add_argument("--competition-map", required=True, type=Path)
    parser.add_argument("--club-identity-aliases", type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        source, source_sha = _load(args.source_capture, "source capture")
        lineups, lineup_sha = _load(args.opening_lineups, "opening lineups")
        selection: dict[str, Any] | None = None
        selection_sha: str | None = None
        if args.lineup_source_selection is not None:
            selection, selection_sha = _load(args.lineup_source_selection, "lineup source selection")
        competition_map, competition_map_sha = opening.load_competition_map(args.competition_map)
        aliases, aliases_sha = opening.load_club_identity_aliases(args.club_identity_aliases)
        result = capture(
            source_capture=source, source_capture_sha256=source_sha, lineups=lineups, lineup_sha256=lineup_sha,
            lineup_source_selection=selection, lineup_source_selection_sha256=selection_sha,
            competition_map=competition_map, competition_map_sha256=competition_map_sha,
            aliases=aliases, aliases_sha256=aliases_sha,
            cache=opening.SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay),
        )
    except (OSError, ManagerHistoryError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
