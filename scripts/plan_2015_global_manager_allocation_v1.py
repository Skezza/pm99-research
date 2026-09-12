#!/usr/bin/env python3
"""Plan one exclusive PM99 manager carrier for every 2015/16 club.

The old worldwide release renamed foreign managers in place.  Fifty-seven
ENT records were already linked to one or more English clubs, so a foreign
rename leaked into English play (for example Diego Simeone/Newcastle United).

This is a read-only allocation step.  It proves that the clean base has a
unique writable ENT record for every live team before a compiler may change a
single EQ link or ENT name.  It deliberately separates the capacity/mechanics
question from the historical-source question: a row without a dated manager
fact remains an explicit source gap, never a native-manager fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_team_indexed_metadata import extract_indexed_team_payload_metadata
from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.fdi_indexed import IndexedFDIFile
from scripts.season_english_mode0_package_adapter_v1 import _manager_candidates
from scripts.season_package_compiler_v2 import _source_roster_owners


SCHEMA = "pm99-world-2015-global-manager-allocation-v1"
PACKAGE_SCHEMA = "pm99-season-package-v2"
HISTORY_SCHEMA = "pm99-world-2015-wikipedia-manager-history-v2"
MULTILINGUAL_HISTORY_SCHEMA = "pm99-world-2015-multilingual-wikipedia-manager-history-v3"
TRANSFERMARKT_SNAPSHOT_HISTORY_SCHEMA = (
    "pm99-world-2015-transfermarkt-squad-snapshot-manager-history-v5"
)


class AllocationError(ValueError):
    """The base graph cannot support a collision-free manager allocation."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _club_name(raw: bytes) -> str:
    metadata = extract_indexed_team_payload_metadata(raw)
    return " ".join(str(metadata.get("short_name") or "").split())


def _live_teams(eq_data: bytes) -> dict[int, dict[str, Any]]:
    indexed = IndexedFDIFile.from_bytes(eq_data)
    _owners, _rosters, modes = _source_roster_owners(eq_data)
    teams: dict[int, dict[str, Any]] = {}
    for entry in indexed.entries:
        carrier = int(entry.record_id)
        mode = modes.get(carrier)
        if mode not in {0, 1}:
            continue
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        manager = parse_indexed_eq_manager_links(raw).active_manager_record_id
        if not isinstance(manager, int):
            raise AllocationError(f"live EQ carrier {carrier} has no active ENT manager link")
        teams[carrier] = {
            "team_carrier_id": carrier,
            "club_name": _club_name(raw),
            "record_mode": int(mode),
            "baseline_manager_carrier_id": manager,
        }
    if not teams:
        raise AllocationError("base has no parser-backed live teams")
    return teams


def _allocate(
    teams: Mapping[int, Mapping[str, Any]], writable: Sequence[int],
) -> tuple[dict[int, int], dict[int, list[int]]]:
    """Allocate exclusive records, retaining English links where they collide.

    Existing one-owner records are retained.  A record shared by one or more
    teams retains the mode-0 owner first; that protects the human-playable
    English side while a new, currently unlinked record is allocated to every
    other owner.  The ordering is stable, hence exactly reproducible from the
    same clean base.
    """
    writable_set = {int(value) for value in writable}
    owners: dict[int, list[int]] = defaultdict(list)
    for carrier, team in teams.items():
        manager = int(team["baseline_manager_carrier_id"])
        if manager not in writable_set:
            raise AllocationError(
                f"live team {carrier} links non-writable ENT manager {manager}"
            )
        owners[manager].append(int(carrier))
    for values in owners.values():
        values.sort()

    linked = set(owners)
    unused = iter(sorted(writable_set - linked))
    allocation: dict[int, int] = {}
    displaced: dict[int, list[int]] = {}
    for manager, team_ids in sorted(owners.items()):
        if len(team_ids) == 1:
            allocation[team_ids[0]] = manager
            continue
        # Prefer a mode-0 English owner; then use the lowest stable carrier.
        retained = min(
            team_ids,
            key=lambda carrier: (0 if int(teams[carrier]["record_mode"]) == 0 else 1, carrier),
        )
        allocation[retained] = manager
        displaced[manager] = [carrier for carrier in team_ids if carrier != retained]
        for carrier in displaced[manager]:
            try:
                allocation[carrier] = next(unused)
            except StopIteration as exc:
                raise AllocationError(
                    "clean base lacks enough unlinked writable ENT records "
                    "to separate all shared manager links"
                ) from exc
    if set(allocation) != set(teams):
        raise AllocationError("allocation did not cover every live team")
    if len(set(allocation.values())) != len(allocation):
        raise AllocationError("allocation contains a duplicate manager carrier")
    return allocation, displaced


def _foreign_manager_sources(
    package: Mapping[str, Any], histories: Sequence[Mapping[str, Any]],
) -> dict[int, dict[str, str]]:
    managers = {
        str(row.get("id")): row
        for row in package.get("managers", [])
        if isinstance(row, Mapping)
    }
    result: dict[int, dict[str, str]] = {}
    for club in package.get("clubs", []):
        if not isinstance(club, Mapping):
            continue
        manager = managers.get(str(club.get("manager_id")))
        if manager and manager.get("policy") == "write":
            result[int(club["carrier_id"])] = {
                "status": "existing-dated-source",
                "name": " ".join(str(manager.get("name") or "").split()),
            }
    def add_source(carrier_id: int, status: str, name: str) -> None:
        existing = result.get(carrier_id)
        candidate = {"status": status, "name": name}
        if existing is not None and existing != candidate:
            raise AllocationError(
                f"conflicting dated manager sources for foreign carrier {carrier_id}"
            )
        result[carrier_id] = candidate

    accepted = {
        "dated-historical-club-page-manager-match": "dated-english-wikipedia-history-source",
        "dated-national-wikipedia-manager-match": "dated-national-wikipedia-history-source",
    }
    for history in histories:
        if history.get("schema_version") == TRANSFERMARKT_SNAPSHOT_HISTORY_SCHEMA:
            for row in history.get("rows", []):
                if not isinstance(row, Mapping):
                    continue
                carrier_id = row.get("carrier_id")
                name = " ".join(str(row.get("manager_name") or "").split())
                if not isinstance(carrier_id, int) or not name:
                    raise AllocationError("Transfermarkt snapshot history has a malformed manager row")
                add_source(
                    carrier_id,
                    "dated-transfermarkt-pinned-2015-squad-manager-history-source",
                    name,
                )
            continue
        for row in history.get("rows", []):
            if not isinstance(row, Mapping):
                continue
            status = accepted.get(str(row.get("status") or ""))
            if status is None:
                continue
            name = " ".join(str((row.get("facts") or {}).get("manager") or "").split())
            if name:
                add_source(int(row["carrier_id"]), status, name)
        for row in history.get("rows", []):
            if not isinstance(row, Mapping):
                continue
            if row.get("status") != "dated-national-wikipedia-manager-source-pm99-transliteration-required":
                continue
            name = " ".join(str((row.get("facts") or {}).get("manager") or "").split())
            if name:
                add_source(
                    int(row["carrier_id"]),
                    "target-manager-pm99-transliteration-required", name,
                )
    return result


def build(
    *, package: Mapping[str, Any], history: Mapping[str, Any],
    multilingual_history: Mapping[str, Any] | None = None,
    transfermarkt_snapshot_history: Mapping[str, Any] | None = None,
    eq_data: bytes, ent_data: bytes,
) -> dict[str, Any]:
    if package.get("schema_version") != PACKAGE_SCHEMA:
        raise AllocationError(f"world package must use {PACKAGE_SCHEMA}")
    if history.get("schema_version") != HISTORY_SCHEMA:
        raise AllocationError(f"history receipt must use {HISTORY_SCHEMA}")
    if multilingual_history is not None and multilingual_history.get("schema_version") != MULTILINGUAL_HISTORY_SCHEMA:
        raise AllocationError(f"multilingual history receipt must use {MULTILINGUAL_HISTORY_SCHEMA}")
    if (
        transfermarkt_snapshot_history is not None
        and transfermarkt_snapshot_history.get("schema_version") != TRANSFERMARKT_SNAPSHOT_HISTORY_SCHEMA
    ):
        raise AllocationError(
            "Transfermarkt snapshot history receipt must use "
            f"{TRANSFERMARKT_SNAPSHOT_HISTORY_SCHEMA}"
        )
    teams = _live_teams(eq_data)
    foreign_carriers = {
        int(club["carrier_id"])
        for club in package.get("clubs", [])
        if isinstance(club, Mapping)
    }
    if not foreign_carriers <= set(teams):
        missing = sorted(foreign_carriers - set(teams))
        raise AllocationError(f"world package has absent live team carrier {missing[0]}")
    allocation, displaced = _allocate(teams, _manager_candidates(ent_data))
    manager_sources = _foreign_manager_sources(
        package,
        [
            history,
            *([multilingual_history] if multilingual_history is not None else []),
            *([transfermarkt_snapshot_history] if transfermarkt_snapshot_history is not None else []),
        ],
    )
    non_club_foreign_carriers = {
        int(row["carrier_id"])
        for row in history.get("rows", [])
        if isinstance(row, Mapping) and row.get("status") == "out-of-scope-non-club-carrier"
    }
    assignments = []
    for team in sorted(teams.values(), key=lambda row: int(row["team_carrier_id"])):
        carrier = int(team["team_carrier_id"])
        baseline = int(team["baseline_manager_carrier_id"])
        target = allocation[carrier]
        source = manager_sources.get(carrier)
        if carrier not in foreign_carriers:
            source_status = "english-source-layer-required"
            source_name = None
        elif carrier in non_club_foreign_carriers:
            source_status = "out-of-scope-non-club-carrier"
            source_name = None
        elif source is None:
            source_status = "target-season-manager-source-required"
            source_name = None
        else:
            source_status = source["status"]
            source_name = source["name"]
        assignments.append({
            **team,
            "allocated_manager_carrier_id": target,
            "allocation_action": (
                "retain-exclusive-baseline-link" if target == baseline else
                "relink-from-shared-baseline-to-unlinked-writable-ent"
            ),
            "target_manager_source_status": source_status,
            "target_manager_name": source_name,
        })
    retained_shared = {
        manager: next(
            assignment["team_carrier_id"]
            for assignment in assignments
            if assignment["baseline_manager_carrier_id"] == manager
            and assignment["allocated_manager_carrier_id"] == manager
        )
        for manager in displaced
    }
    source_counts = Counter(row["target_manager_source_status"] for row in assignments)
    return {
        "schema_version": SCHEMA,
        "policy": (
            "read-only global ENT allocation; retain exclusive baseline links; "
            "for a shared link retain mode-0 English before lowest carrier; "
            "relink all other owners to deterministic unlinked writable ENT records; "
            "no-manager-name fallback"
        ),
        "coverage": {
            "live_team_count": len(teams),
            "foreign_team_count": len(foreign_carriers),
            "english_team_count": len(teams) - len(foreign_carriers),
            "writable_ent_manager_candidate_count": len(_manager_candidates(ent_data)),
            "shared_baseline_manager_carrier_count": len(displaced),
            "relinked_team_count": sum(len(rows) for rows in displaced.values()),
            "unallocated_writable_ent_count": len(_manager_candidates(ent_data)) - len(teams),
            "target_manager_source_status_counts": dict(sorted(source_counts.items())),
        },
        "shared_baseline_resolution": [
            {
                "baseline_manager_carrier_id": manager,
                "retained_team_carrier_id": retained_shared[manager],
                "relinked_team_carrier_ids": displaced[manager],
            }
            for manager in sorted(displaced)
        ],
        "assignments": assignments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world-package", required=True, type=Path)
    parser.add_argument("--history-receipt", required=True, type=Path)
    parser.add_argument("--multilingual-history", type=Path)
    parser.add_argument("--transfermarkt-snapshot-history", type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    package_raw = args.world_package.read_bytes()
    history_raw = args.history_receipt.read_bytes()
    multilingual_raw = args.multilingual_history.read_bytes() if args.multilingual_history else None
    transfermarkt_snapshot_raw = (
        args.transfermarkt_snapshot_history.read_bytes()
        if args.transfermarkt_snapshot_history else None
    )
    package = json.loads(package_raw.decode("utf-8"))
    history = json.loads(history_raw.decode("utf-8"))
    multilingual_history = json.loads(multilingual_raw.decode("utf-8")) if multilingual_raw else None
    transfermarkt_snapshot_history = (
        json.loads(transfermarkt_snapshot_raw.decode("utf-8"))
        if transfermarkt_snapshot_raw else None
    )
    if package_raw != canonical_json_bytes(package):
        parser.error("world package must use canonical JSON bytes")
    if history_raw != canonical_json_bytes(history):
        parser.error("history receipt must use canonical JSON bytes")
    if multilingual_raw is not None and multilingual_raw != canonical_json_bytes(multilingual_history):
        parser.error("multilingual history receipt must use canonical JSON bytes")
    if (
        transfermarkt_snapshot_raw is not None
        and transfermarkt_snapshot_raw != canonical_json_bytes(transfermarkt_snapshot_history)
    ):
        parser.error("Transfermarkt snapshot history receipt must use canonical JSON bytes")
    eq_path = args.base_tree / "DBDAT" / "EQ98030.FDI"
    ent_path = args.base_tree / "DBDAT" / "ENT98030.FDI"
    try:
        receipt = build(
            package=package, history=history, multilingual_history=multilingual_history,
            transfermarkt_snapshot_history=transfermarkt_snapshot_history,
            eq_data=eq_path.read_bytes(), ent_data=ent_path.read_bytes(),
        )
    except (AllocationError, OSError) as exc:
        parser.error(str(exc))
    receipt["inputs"] = {
        "world_package_sha256": hashlib.sha256(package_raw).hexdigest(),
        "history_receipt_sha256": hashlib.sha256(history_raw).hexdigest(),
        "multilingual_history_sha256": hashlib.sha256(multilingual_raw).hexdigest() if multilingual_raw else None,
        "transfermarkt_snapshot_history_sha256": (
            hashlib.sha256(transfermarkt_snapshot_raw).hexdigest()
            if transfermarkt_snapshot_raw else None
        ),
        "EQ98030.FDI_sha256": _sha256(eq_path),
        "ENT98030.FDI_sha256": _sha256(ent_path),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
