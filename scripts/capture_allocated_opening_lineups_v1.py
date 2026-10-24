#!/usr/bin/env python3
"""Capture missing fixed-carrier opening XIs via frozen historic IDs.

This supplements an existing opening-lineup receipt without changing it.  A
candidate is eligible only when it is an assigned carrier, has no existing
lineup receipt, and its immutable squad source path declares an exact
``squad/<year>/<competition>/<club-id>.html`` identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402
from scripts import transfermarkt_calendar_year_policy_v1 as calendar_year_policy  # noqa: E402
from scripts import capture_opening_manager_history_supplements_v1 as history  # noqa: E402
from scripts import capture_allocated_manager_history_v1 as managers  # noqa: E402


ALLOCATION_SCHEMA = "pm99-season-carrier-allocation-v1"
SCHEMA = opening.SCHEMA


class AllocatedLineupError(ValueError):
    """An opening-XI supplement cannot be tied to immutable inputs."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllocatedLineupError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise AllocatedLineupError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    source = value.get("source_selector", value)
    if not isinstance(source, Mapping):
        raise AllocatedLineupError("source selector is missing")
    key = tuple(str(source.get(field) or value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise AllocatedLineupError("source selector is incomplete")
    return key  # type: ignore[return-value]


def _identity(source: Mapping[str, Any], *, season_start_year: int) -> tuple[str, opening.TeamRef] | None:
    path = str(source.get("source_path") or "").strip()
    match = re.fullmatch(r"squad/(\d{4})/([A-Z0-9]+)/([1-9]\d*)\.html", path)
    selector = _selector(source)
    route_doc = source.get("calendar_year_routing")
    if route_doc is None:
        if match is None or int(match.group(1)) != season_start_year:
            return None
        code, club_id = match.group(2), int(match.group(3))
    else:
        routed = re.fullmatch(
            r"squad-calendar-route-v1/(\d{4})/(\d{4})/([A-Z0-9]+)/([1-9]\d*)\.html", path
        )
        if not isinstance(route_doc, Mapping) or routed is None:
            raise AllocatedLineupError("calendar-routed squad has malformed route metadata or source path")
        target_year, provider_year = int(routed.group(1)), int(routed.group(2))
        code, club_id = routed.group(3), int(routed.group(4))
        try:
            expected_route = calendar_year_policy.route_provider_year(target_year, code, selector[0]).document()
        except calendar_year_policy.RoutingError as exc:
            raise AllocatedLineupError(f"calendar-routed squad has no reviewed route: {exc}") from exc
        if (target_year != season_start_year or provider_year != season_start_year - 1
                or int(route_doc.get("target_calendar_year", -1)) != target_year
                or int(route_doc.get("provider_season_id", -1)) != provider_year
                or route_doc.get("source_competition_code") != code
                or dict(route_doc) != expected_route):
            raise AllocatedLineupError("calendar-routed squad path and metadata do not match reviewed target/provider/country")
    return code, opening.TeamRef(
        source_club_name=selector[2], transfermarkt_name=selector[2], club_id=club_id,
        club_path=f"/-/startseite/verein/{club_id}", identity_match_method="frozen-historic-source-path",
    )


def _known_selectors(reconciliation: Mapping[str, Any], *, source_capture_sha256: str) -> set[tuple[str, str, str]]:
    if reconciliation.get("schema_version") != "pm99-transfermarkt-opening-lineup-reconciliation-v1":
        raise AllocatedLineupError("known opening reconciliation has an unsupported schema")
    if (reconciliation.get("sources") or {}).get("source_capture_sha256") != source_capture_sha256:
        raise AllocatedLineupError("known opening reconciliation is not bound to this source capture")
    rows = reconciliation.get("clubs")
    if not isinstance(rows, list):
        raise AllocatedLineupError("known opening reconciliation has no club rows")
    result: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise AllocatedLineupError("known opening reconciliation contains a malformed row")
        selector = _selector(row)
        if selector in result:
            raise AllocatedLineupError("known opening reconciliation duplicates a selector")
        result.add(selector)
    return result


def capture(
    *, source_capture: Mapping[str, Any], source_capture_sha256: str,
    allocation: Mapping[str, Any], allocation_sha256: str,
    known_reconciliation: Mapping[str, Any], known_reconciliation_sha256: str,
    cache: opening.SnapshotCache,
) -> dict[str, Any]:
    audit_binding = None
    if any(isinstance(row, Mapping) and row.get("calendar_year_routing") is not None
           for row in source_capture.get("clubs", [])):
        audit_binding = calendar_year_policy.verify_audit(ROOT)
    if allocation.get("schema_version") != ALLOCATION_SCHEMA:
        raise AllocatedLineupError("unsupported carrier allocation")
    year = managers._season_start_year(allocation)
    source_rows = source_capture.get("clubs")
    assignments = allocation.get("assignments")
    if not isinstance(source_rows, list) or not isinstance(assignments, list):
        raise AllocatedLineupError("source capture or carrier allocation has no rows")
    source_by_selector: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in source_rows:
        if not isinstance(row, Mapping):
            raise AllocatedLineupError("source capture has a malformed club")
        selector = _selector(row)
        if selector in source_by_selector:
            raise AllocatedLineupError("source capture duplicates a club selector")
        source_by_selector[selector] = row
    allocated: dict[tuple[str, str, str], int] = {}
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise AllocatedLineupError("carrier allocation has a malformed assignment")
        selector = _selector(assignment)
        carrier = assignment.get("carrier_id")
        if not isinstance(carrier, int) or carrier <= 0 or selector in allocated:
            raise AllocatedLineupError("carrier allocation has a duplicate or invalid assignment")
        if selector not in source_by_selector:
            raise AllocatedLineupError(f"allocated selector is absent from source capture: {selector}")
        allocated[selector] = carrier
    known = _known_selectors(known_reconciliation, source_capture_sha256=source_capture_sha256)
    candidates: dict[tuple[str, str, str], tuple[str, opening.TeamRef]] = {}
    for selector in sorted(set(allocated) - known):
        identity = _identity(source_by_selector[selector], season_start_year=year)
        if identity is not None:
            candidates[selector] = identity
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for selector, (code, ref) in sorted(candidates.items()):
        try:
            fixture = opening._first_fixture(ref, season_start_year=year, competition_code=code,
                                             country_catalog=selector[0], cache=cache)
            row = opening._lineup_from_report(ref, fixture, cache)
            if "calendar_year_routing" in fixture:
                row["calendar_year_routing"] = fixture["calendar_year_routing"]
                row["provider_season_id"] = fixture["provider_season_id"]
                row["target_calendar_year"] = fixture["target_calendar_year"]
            row["source_selector"].update({"country_catalog": selector[0], "competition_catalog": selector[1]})
            row["source_competition_code"] = code
            rows.append(row)
        except (OSError, ValueError, opening.CaptureError) as exc:
            failures.append({"country_catalog": selector[0], "competition_catalog": selector[1], "club_name": selector[2], "reason": str(exc)})
    rows.sort(key=lambda row: _selector(row["source_selector"]))
    failures.sort(key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"]))
    return {
        "schema_version": SCHEMA,
        "season_start_year": year,
        "snapshot_policy": "first domestic-league fixture per fixed carrier, using exact historic source club and competition IDs",
        "source": {
            "name": "Transfermarkt published schedules and match reports",
            "base_url": opening.BASE_URL,
            "source_capture_sha256": source_capture_sha256,
            "carrier_allocation_sha256": allocation_sha256,
            "known_opening_reconciliation_sha256": known_reconciliation_sha256,
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
            **({"calendar_year_routing_audit": audit_binding} if audit_binding is not None else {}),
        },
        "summary": {
            "allocated_carrier_count": len(allocated),
            "retained_existing_reconciliation_count": len(set(allocated) & known),
            "historic_id_capture_candidate_count": len(candidates),
            "captured_club_count": len(rows),
            "failed_club_count": len(failures),
        },
        "clubs": rows,
        "failures": failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--carrier-allocation", type=Path, required=True)
    parser.add_argument("--known-opening-reconciliation", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise AllocatedLineupError(f"refusing to overwrite opening-lineup supplement: {args.output}")
        source, source_sha = _load(args.source_capture, "source capture")
        allocation, allocation_sha = _load(args.carrier_allocation, "carrier allocation")
        known, known_sha = _load(args.known_opening_reconciliation, "known opening reconciliation")
        result = capture(
            source_capture=source, source_capture_sha256=source_sha,
            allocation=allocation, allocation_sha256=allocation_sha,
            known_reconciliation=known, known_reconciliation_sha256=known_sha,
            cache=opening.SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay),
        )
    except (OSError, AllocatedLineupError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
