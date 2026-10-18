#!/usr/bin/env python3
"""Audit that a compiled season changed only declared fixed carriers."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline_v2
from scripts import season_package_compiler_v2 as compiler_v2
from app.fdi_indexed import IndexedFDIFile


DATABASE_RELATIVE_PATHS = compiler_v2.DATABASE_RELATIVE_PATHS
_mode1_roster_tails = compiler_v2._mode1_roster_tails


SCHEMA = "pm99-season-clean-base-audit-v1"


class CleanBaseAuditError(ValueError):
    """The materialisation is not a bounded clean-base compilation."""


def _payloads(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    return {entry.record_id: entry.decode_payload(data) for entry in indexed.entries}


def _changed(
    before: dict[int, bytes], after: dict[int, bytes], *, label: str,
    allowed_added: set[int] | None = None,
) -> list[int]:
    allowed_added = allowed_added or set()
    if set(after) != set(before) | allowed_added:
        raise CleanBaseAuditError(f"{label} record ID set changed")
    return sorted(
        identity for identity in after
        if identity not in before or before[identity] != after[identity]
    )


def _mode0_donor_removals(
    *, package: dict[str, Any], base_eq_data: bytes
) -> tuple[dict[int, set[int]], dict[int, list[int]], dict[int, int]]:
    """Derive the only unselected EQ changes the compiler is permitted to make.

    A selected player carrier can belong to an unselected mode-0 base team.
    The compiler removes that one carrier from the donor's parser-backed roster
    only when its documented minimum-tail guard passes.  This helper makes the
    derived change visible to the clean-base audit rather than allowing an
    undeclared mutation to pass implicitly.
    """

    owners, rosters, modes = compiler_v2._source_roster_owners(base_eq_data)
    selected_clubs = {int(row["carrier_id"]) for row in package["clubs"]}
    removals: dict[int, set[int]] = {}
    for player in package["players"]:
        player_carrier = int(player["carrier_id"])
        for owner in owners.get(player_carrier, []):
            if owner in selected_clubs:
                continue
            if modes.get(owner) == 1:
                raise CleanBaseAuditError(
                    f"selected player carrier {player_carrier} has unselected mode-1 owner {owner}"
                )
            if owner not in rosters:
                raise CleanBaseAuditError(
                    f"selected player carrier {player_carrier} has unparsed donor roster {owner}"
                )
            removals.setdefault(owner, set()).add(player_carrier)
    return removals, rosters, modes


def audit(*, package_path: Path, base_tree: Path, output_tree: Path) -> dict[str, Any]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    base_tree, output_tree = base_tree.resolve(), output_tree.resolve()
    if base_tree == output_tree:
        raise CleanBaseAuditError("base and output trees must be distinct")
    base_eq_data = (base_tree / "DBDAT/EQ98030.FDI").read_bytes()
    donor_removals, base_rosters, base_modes = _mode0_donor_removals(
        package=package, base_eq_data=base_eq_data
    )
    declared = {
        "DBDAT/JUG98030.FDI": {int(row["carrier_id"]) for row in package["players"]},
        "DBDAT/EQ98030.FDI": (
            {int(row["carrier_id"]) for row in package["clubs"]} | set(donor_removals)
        ),
        "DBDAT/ENT98030.FDI": {int(row["carrier_id"]) for row in package["managers"]},
    }
    appended_player_ids = {
        int(row["carrier_id"]) for row in package["players"]
        if row.get("append_from_carrier_id") is not None
    }
    changed: dict[str, list[int]] = {}
    output_hashes: dict[str, str] = {}
    for relative in DATABASE_RELATIVE_PATHS:
        base_path, output_path = base_tree / relative, output_tree / relative
        if not base_path.is_file() or not output_path.is_file():
            raise CleanBaseAuditError(f"missing database file {relative}")
        changed[relative] = _changed(
            _payloads(base_path), _payloads(output_path), label=relative,
            allowed_added=appended_player_ids if relative == "DBDAT/JUG98030.FDI" else set(),
        )
        unexpected = sorted(set(changed[relative]) - declared[relative])
        if unexpected:
            raise CleanBaseAuditError(f"{relative} changed undeclared carriers: {unexpected[:20]}")
        output_hashes[relative] = hashlib.sha256(output_path.read_bytes()).hexdigest()

    base_tails = _mode1_roster_tails(base_eq_data)
    output_tails = _mode1_roster_tails((output_tree / "DBDAT/EQ98030.FDI").read_bytes())
    roster_mismatches = [
        int(club["carrier_id"])
        for club in package["clubs"]
        if base_tails.get(int(club["carrier_id"])) != output_tails.get(int(club["carrier_id"]))
    ]
    if roster_mismatches:
        raise CleanBaseAuditError(
            f"fixed foreign roster tails changed: {roster_mismatches[:20]}"
        )
    _after_owners, output_rosters, _after_modes = compiler_v2._source_roster_owners(
        (output_tree / "DBDAT/EQ98030.FDI").read_bytes()
    )
    donor_mismatches: list[int] = []
    for donor, removed in sorted(donor_removals.items()):
        if base_modes.get(donor) == 1:
            raise CleanBaseAuditError(f"mode-1 donor was declared for rewrite: {donor}")
        expected = [carrier for carrier in base_rosters[donor] if carrier not in removed]
        if len(expected) < 20 or output_rosters.get(donor) != expected:
            donor_mismatches.append(donor)
    if donor_mismatches:
        raise CleanBaseAuditError(
            f"mode-0 donor roster transaction mismatch: {donor_mismatches[:20]}"
        )
    unsafe_allocations = sorted(
        row["id"] for row in package["players"]
        if any(key in row for key in ("recycle_from_mode1_carrier_id", "mode0_clone_carrier_id"))
    )
    if unsafe_allocations:
        raise CleanBaseAuditError(f"package contains append/recycle allocations: {unsafe_allocations[:20]}")
    return {
        "schema_version": SCHEMA,
        "result": "pass",
        "package_canonical_sha256": package_v2.sha256_file(package_path),
        "base_inventory_fingerprint": pipeline_v2.build_tree_inventory(base_tree)["files_fingerprint"],
        "output_database_sha256": output_hashes,
        "changed_carrier_counts": {key: len(value) for key, value in sorted(changed.items())},
        "changed_carrier_ids": {key: value for key, value in sorted(changed.items())},
        "fixed_roster_tail_count": len(package["clubs"]),
        "fixed_roster_tail_mismatch_count": 0,
        "derived_mode0_donor_carrier_ids": sorted(donor_removals),
        "derived_mode0_donor_removals": {
            str(carrier): sorted(rows) for carrier, rows in sorted(donor_removals.items())
        },
        "derived_mode0_donor_mismatch_count": 0,
        "append_or_recycle_count": len(appended_player_ids),
        "appended_player_carrier_ids": sorted(appended_player_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--output-tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit(
            package_path=args.package,
            base_tree=args.base_tree,
            output_tree=args.output_tree,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(package_v2.canonical_json_bytes(result))
    except (CleanBaseAuditError, package_v2.PackageValidationError, OSError, ValueError) as exc:
        print(f"clean-base audit error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "result": result["result"],
        "fixed_roster_tail_count": result["fixed_roster_tail_count"],
        "changed_carrier_counts": result["changed_carrier_counts"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
