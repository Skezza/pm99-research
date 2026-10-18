#!/usr/bin/env python3
"""Capture dated managers for the exact fixed carriers missing lineup receipts.

Unlike the opening-lineup supplement, this worker is scoped by the immutable
carrier allocation.  It derives each allocated club's first league fixture
from the declared season competition, then uses the dated Transfermarkt club
manager history.  It writes a compatible manager supplement plus an explicit
gap list; no native/current-manager fallback or name guessing is permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_opening_manager_history_supplements_v1 as history  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-opening-manager-supplement-v1"
ALLOCATION_SCHEMA = "pm99-season-carrier-allocation-v1"


class AllocatedManagerHistoryError(ValueError):
    """An allocated-club manager capture cannot be tied to exact inputs."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllocatedManagerHistoryError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise AllocatedManagerHistoryError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(assignment: Mapping[str, Any]) -> tuple[str, str, str]:
    source = assignment.get("source_selector")
    if not isinstance(source, Mapping):
        raise AllocatedManagerHistoryError("carrier allocation has no source selector")
    values = (
        str(source.get("country_catalog") or "").strip(),
        str(source.get("competition_catalog") or "").strip(),
        str(assignment.get("club_name") or "").strip(),
    )
    if not all(values):
        raise AllocatedManagerHistoryError("carrier allocation has an incomplete source selector")
    return values


def _selector_object(selector: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("country_catalog", "competition_catalog", "club_name"), selector))


def _season_start_year(allocation: Mapping[str, Any]) -> int:
    """Read the explicit allocation season, including legacy catalog-only receipts."""
    season = allocation.get("season")
    if not isinstance(season, Mapping):
        raise AllocatedManagerHistoryError("carrier allocation has no season")
    direct = season.get("start_year")
    if isinstance(direct, int):
        return direct
    # The legacy immutable allocation contract declares e.g. ``2007-2008``.
    # It is a date identifier, not a guessed season conversion.
    catalog = season.get("catalog")
    if isinstance(catalog, str) and len(catalog) == 9 and catalog[4] == "-" and catalog[:4].isdigit() and catalog[5:].isdigit():
        return int(catalog[:4])
    raise AllocatedManagerHistoryError("carrier allocation has no season start year")


def _valid_known_manager(row: Mapping[str, Any]) -> bool:
    """Return whether an existing ledger row is safe to retain without a fetch."""
    evidence = row.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    name = str(row.get("manager_name") or "").strip()
    fixture_date = str(row.get("opening_fixture_date") or "").strip()
    snapshot_sha = str(evidence.get("source_snapshot_sha256") or "").strip()
    source_url = str(evidence.get("source_url") or "").strip()
    try:
        date.fromisoformat(fixture_date)
    except ValueError:
        return False
    return bool(name and source_url and len(snapshot_sha) == 64 and all(char in "0123456789abcdef" for char in snapshot_sha.lower()))


def _manager_selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    selector = row.get("source_selector")
    if not isinstance(selector, Mapping):
        raise AllocatedManagerHistoryError("known manager ledger row has no source selector")
    try:
        return history._selector(selector)
    except history.ManagerHistoryError as exc:
        raise AllocatedManagerHistoryError(str(exc)) from exc


def _historic_source_identity(row: Mapping[str, Any], *, season_start_year: int) -> tuple[str, opening.TeamRef] | None:
    """Reuse an exact historic Transfermarkt club/competition path when supplied.

    The frozen squad capture already records paths such as
    ``squad/2007/ALB1/12457.html``.  They are stronger than a current-name
    lookup and avoid needing a separate competition-map entry.  Other source
    formats deliberately return ``None`` and remain explicit gaps.
    """
    source_path = str(row.get("source_path") or "").strip()
    match = re.fullmatch(r"squad/(\d{4})/([A-Z0-9]+)/([1-9]\d*)\.html", source_path)
    if match is None or int(match.group(1)) != season_start_year:
        return None
    selector = history._selector(row)
    code, club_id = match.group(2), int(match.group(3))
    return code, opening.TeamRef(
        source_club_name=selector[2], transfermarkt_name=selector[2], club_id=club_id,
        club_path=f"/-/startseite/verein/{club_id}", identity_match_method="frozen-historic-source-path",
    )


def _known_managers(
    ledger: Mapping[str, Any] | None, *, source_capture_sha256: str,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    """Index valid dated managers already in an immutable earlier ledger."""
    if ledger is None:
        return {}
    sources = ledger.get("sources")
    rows = ledger.get("managers")
    if not isinstance(sources, Mapping) or sources.get("squad_source_capture_sha256") != source_capture_sha256:
        raise AllocatedManagerHistoryError("known manager ledger is not bound to this source capture")
    if not isinstance(rows, list):
        raise AllocatedManagerHistoryError("known manager ledger has no manager rows")
    known: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise AllocatedManagerHistoryError("known manager ledger has a malformed manager row")
        selector = _manager_selector(row)
        if selector in known:
            raise AllocatedManagerHistoryError("known manager ledger has duplicate manager selectors")
        if _valid_known_manager(row):
            known[selector] = row
    return known


def _gap_scope(
    supplement: Mapping[str, Any] | None, *, supplement_sha256: str | None,
    source_capture_sha256: str, allocation_sha256: str,
) -> set[tuple[str, str, str]] | None:
    """Return the explicit unresolved selectors from an earlier raw capture.

    This enables a later repair pass to be strictly append-only: it may inspect
    only gaps written by a hash-bound earlier capture, never re-capture every
    allocated carrier just because one spelling or source issue was repaired.
    """
    if supplement is None:
        return None
    if not supplement_sha256:
        raise AllocatedManagerHistoryError("gap scope supplement hash is missing")
    if supplement.get("schema_version") != SCHEMA:
        raise AllocatedManagerHistoryError("gap scope has an unsupported manager supplement schema")
    sources = supplement.get("sources")
    gaps = supplement.get("gaps")
    if not isinstance(sources, Mapping) or not isinstance(gaps, list):
        raise AllocatedManagerHistoryError("gap scope has no sources or gap list")
    if sources.get("full_source_capture_sha256") != source_capture_sha256:
        raise AllocatedManagerHistoryError("gap scope targets a different source capture")
    if sources.get("carrier_allocation_sha256") != allocation_sha256:
        raise AllocatedManagerHistoryError("gap scope targets a different carrier allocation")
    result: set[tuple[str, str, str]] = set()
    for row in gaps:
        if not isinstance(row, Mapping):
            raise AllocatedManagerHistoryError("gap scope has a malformed gap row")
        selector = row.get("source_selector")
        if not isinstance(selector, Mapping):
            raise AllocatedManagerHistoryError("gap scope row has no source selector")
        key = history._selector(selector)
        if key in result:
            raise AllocatedManagerHistoryError("gap scope has duplicate source selectors")
        result.add(key)
    return result


def capture(
    *, source_capture: Mapping[str, Any], source_capture_sha256: str,
    allocation: Mapping[str, Any], allocation_sha256: str,
    competition_map: Mapping[tuple[str, str], str], competition_map_sha256: str,
    aliases: Mapping[tuple[str, str, str], Mapping[str, Any]], aliases_sha256: str | None,
    cache: opening.SnapshotCache,
    known_manager_ledger: Mapping[str, Any] | None = None,
    known_manager_ledger_sha256: str | None = None,
    gap_scope_supplement: Mapping[str, Any] | None = None,
    gap_scope_supplement_sha256: str | None = None,
) -> dict[str, Any]:
    if allocation.get("schema_version") != ALLOCATION_SCHEMA:
        raise AllocatedManagerHistoryError("unsupported carrier allocation")
    year = _season_start_year(allocation)
    rows = allocation.get("assignments")
    source_clubs = source_capture.get("clubs")
    if not isinstance(rows, list) or not isinstance(source_clubs, list):
        raise AllocatedManagerHistoryError("source capture or allocation has no rows")
    source_keys = {history._selector(row) for row in source_clubs if isinstance(row, Mapping)}
    if len(source_keys) != len(source_clubs):
        raise AllocatedManagerHistoryError("source capture has malformed or duplicate club selectors")
    source_identities: dict[tuple[str, str, str], tuple[str, opening.TeamRef]] = {}
    for row in source_clubs:
        if not isinstance(row, Mapping):
            continue
        identity = _historic_source_identity(row, season_start_year=year)
        if identity is not None:
            source_identities[history._selector(row)] = identity
    allocated: dict[tuple[str, str, str], int] = {}
    for assignment in rows:
        if not isinstance(assignment, Mapping):
            raise AllocatedManagerHistoryError("carrier allocation has a malformed assignment")
        selector = _selector(assignment)
        carrier = assignment.get("carrier_id")
        if not isinstance(carrier, int) or carrier <= 0 or selector in allocated:
            raise AllocatedManagerHistoryError("carrier allocation has a duplicate or invalid assignment")
        if selector not in source_keys:
            raise AllocatedManagerHistoryError(f"allocated selector is absent from source capture: {selector}")
        allocated[selector] = carrier
    gap_scope = _gap_scope(
        gap_scope_supplement, supplement_sha256=gap_scope_supplement_sha256,
        source_capture_sha256=source_capture_sha256, allocation_sha256=allocation_sha256,
    )
    if gap_scope is not None:
        absent = sorted(gap_scope - set(allocated))
        if absent:
            raise AllocatedManagerHistoryError(f"gap scope contains selectors absent from carrier allocation: {absent[:3]}")
        allocated = {selector: carrier for selector, carrier in allocated.items() if selector in gap_scope}
    known = _known_managers(known_manager_ledger, source_capture_sha256=source_capture_sha256)
    retained = {selector: row for selector, row in known.items() if selector in allocated}

    team_indexes: dict[str, list[opening.TeamRef]] = {}
    managers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for selector in sorted(set(allocated) - set(retained)):
        try:
            historic_identity = source_identities.get(selector)
            if historic_identity is not None:
                code, ref = historic_identity
            else:
                code = competition_map.get(selector[:2])
                if code is None:
                    raise AllocatedManagerHistoryError("no-explicit-transfermarkt-competition-map")
                if code not in team_indexes:
                    team_indexes[code] = opening._competition_teams(
                        season_start_year=year, competition_code=code, cache=cache,
                    )
                alias = aliases.get(selector)
                ref = (
                    opening._team_ref_alias(selector[2], alias, team_indexes[code])
                    if alias is not None else opening._team_ref(selector[2], team_indexes[code])
                )
            fixture = opening._first_fixture(
                ref, season_start_year=year, competition_code=code, cache=cache,
            )
            fixture_date = date.fromisoformat(str(fixture["date"]))
            slug = ref.club_path.split("/")[1]
            url = f"{opening.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{ref.club_id}"
            key = f"manager-history/{ref.club_id}.html"
            payload = cache.get(url, key)
            manager_name, manager_id = history.manager_at_date(payload, fixture_date)
            snapshot = cache.used[key]
            managers.append({
                "source_selector": _selector_object(selector),
                "opening_fixture_date": fixture_date.isoformat(),
                "manager_name": manager_name,
                "source_name": "Transfermarkt published club manager history",
                "source_url": url,
                "source_snapshot_sha256": snapshot["sha256"],
                "reason": f"manager id {manager_id} uniquely covers the sourced first-league-fixture date for fixed carrier {allocated[selector]} ({ref.identity_match_method})",
            })
        except (KeyError, OSError, ValueError, opening.CaptureError, history.ManagerHistoryError,
                AllocatedManagerHistoryError) as exc:
            gaps.append({
                "source_selector": _selector_object(selector),
                "carrier_id": allocated[selector],
                "reason": str(exc),
            })
    return {
        "schema_version": SCHEMA,
        "season_start_year": year,
        "sources": {
            "full_source_capture_sha256": source_capture_sha256,
            "carrier_allocation_sha256": allocation_sha256,
            "competition_map_sha256": competition_map_sha256,
            "club_identity_aliases_sha256": aliases_sha256,
            "known_manager_ledger_sha256": known_manager_ledger_sha256,
            "gap_scope_supplement_sha256": gap_scope_supplement_sha256,
            "gap_scope_policy": (
                "only-unresolved-selectors-from-earlier-hash-bound-raw-manager-supplement-v1"
                if gap_scope is not None else None
            ),
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "summary": {
            "allocated_carrier_count": len(allocated),
            "retained_known_manager_count": len(retained),
            "manager_capture_candidate_count": len(allocated) - len(retained),
            "supplemented_manager_count": len(managers),
            "unresolved_manager_count": len(gaps),
        },
        "managers": managers,
        "gaps": gaps,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--carrier-allocation", required=True, type=Path)
    parser.add_argument("--competition-map", required=True, type=Path)
    parser.add_argument("--club-identity-aliases", type=Path)
    parser.add_argument("--known-manager-ledger", type=Path,
                        help="immutable dated-manager ledger whose valid rows must not be fetched again")
    parser.add_argument("--gap-scope-supplement", type=Path,
                        help="earlier hash-bound raw supplement; retry only its explicit unresolved selectors")
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise AllocatedManagerHistoryError(f"refusing to overwrite manager supplement: {args.output}")
        source, source_sha = _load(args.source_capture, "source capture")
        allocation, allocation_sha = _load(args.carrier_allocation, "carrier allocation")
        competition_map, competition_map_sha = opening.load_competition_map(args.competition_map)
        aliases, aliases_sha = opening.load_club_identity_aliases(args.club_identity_aliases)
        if args.known_manager_ledger:
            known_ledger, known_ledger_sha = _load(args.known_manager_ledger, "known manager ledger")
        else:
            known_ledger, known_ledger_sha = None, None
        if args.gap_scope_supplement:
            gap_scope, gap_scope_sha = _load(args.gap_scope_supplement, "gap scope supplement")
        else:
            gap_scope, gap_scope_sha = None, None
        result = capture(
            source_capture=source, source_capture_sha256=source_sha,
            allocation=allocation, allocation_sha256=allocation_sha,
            competition_map=competition_map, competition_map_sha256=competition_map_sha,
            aliases=aliases, aliases_sha256=aliases_sha,
            known_manager_ledger=known_ledger, known_manager_ledger_sha256=known_ledger_sha,
            gap_scope_supplement=gap_scope, gap_scope_supplement_sha256=gap_scope_sha,
            cache=opening.SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay),
        )
    except (OSError, AllocatedManagerHistoryError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
