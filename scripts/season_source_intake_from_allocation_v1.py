#!/usr/bin/env python3
"""Adapt deterministic carrier allocation into a canonical source intake.

The allocation algorithm chooses only same-country fixed carriers, while the
older intake contract consumes the stricter assignment ledger shape.  This
adapter preserves every allocation row as a candidate assignment, hash-locks
both generated documents, and adds explicit evidence/capacity blockers.  It
does not promote an algorithmic allocation to an editorially approved one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import season_source_intake_v1 as intake_lib  # noqa: E402

ALLOCATION_SCHEMA = "pm99-season-carrier-allocation-v1"


def _identity(name: str, selector: Mapping[str, Any]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:48] or "club"
    if not stem[0].isalpha():
        stem = f"club-{stem}"
    digest = hashlib.sha256(assignment_lib.canonical_json_bytes(dict(selector))).hexdigest()[:12]
    return f"{stem}-{digest}"


def adapt(*, allocation: Mapping[str, Any], registry: Mapping[str, Any], source: Mapping[str, Any], assignment_id: str) -> dict[str, Any]:
    if allocation.get("schema_version") != ALLOCATION_SCHEMA or not isinstance(allocation.get("assignments"), list):
        raise assignment_lib.AssignmentError(f"allocation must use {ALLOCATION_SCHEMA}")
    expected_source_sha = hashlib.sha256(assignment_lib.canonical_json_bytes(dict(source))).hexdigest()
    expected_registry_sha = hashlib.sha256(assignment_lib.canonical_json_bytes(dict(registry))).hexdigest()
    if allocation.get("source_sha256") != expected_source_sha or allocation.get("registry_sha256") != expected_registry_sha:
        raise assignment_lib.AssignmentError("allocation is not hash-bound to the supplied source and registry")
    assignment = assignment_lib.initialise_assignment(
        registry=registry, source_capture=source, host_reports=[], assignment_id=assignment_id,
    )
    rows = []
    for row in allocation["assignments"]:
        if not isinstance(row, Mapping):
            raise assignment_lib.AssignmentError("allocation contains a malformed row")
        selector = {**dict(row["source_selector"]), "club_name": str(row["club_name"])}
        blockers = ["algorithmic-same-country-allocation-pending-source-review", "no-reviewed-host-evidence"]
        if int(row.get("roster_capacity") or 0) > 0:
            source_club = next((club for club in source["clubs"] if all(club.get(k) == v for k, v in selector.items())), None)
            if source_club is None:
                raise assignment_lib.AssignmentError(f"allocation selector is absent from source: {selector}")
            if len(source_club.get("players") or []) < int(row["roster_capacity"]):
                blockers.append("source-squad-below-fixed-capacity")
        rows.append({
            "blockers": sorted(blockers), "carrier_id": int(row["carrier_id"]),
            "historical_club": {"identity_key": _identity(str(row["club_name"]), selector), "name": str(row["club_name"])},
            "source_selector": selector, "status": "candidate",
        })
    assignment["assignments"] = sorted(rows, key=lambda row: row["carrier_id"])
    assignment_lib.validate_assignment(assignment=assignment, registry=registry, source_capture=source)
    return assignment


def read(path: Path) -> dict[str, Any]:
    value, _digest = assignment_lib.read_canonical_json(path, label=str(path))
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allocation", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--intake-id", required=True)
    parser.add_argument("--assignment-output", required=True, type=Path)
    parser.add_argument("--intake-output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        allocation, registry, source = read(args.allocation), read(args.registry), read(args.source)
        assignment = adapt(allocation=allocation, registry=registry, source=source, assignment_id=args.assignment_id)
        intake = intake_lib.build_intake(
            registry=registry, source_capture=source, assignment=assignment, intake_id=args.intake_id,
        )
    except (OSError, assignment_lib.AssignmentError, intake_lib.SourceIntakeError) as exc:
        parser.error(str(exc))
    assignment_lib.write_canonical_json(args.assignment_output, assignment)
    assignment_lib.write_canonical_json(args.intake_output, intake)
    print(json.dumps({"assignment_count": len(assignment["assignments"]), "source_club_count": len(intake["source_clubs"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
