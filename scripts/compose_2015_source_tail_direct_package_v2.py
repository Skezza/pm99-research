#!/usr/bin/env python3
"""Promote one complete strict 2015 squad capture into a V2 source package.

The first package composition needed three routes because the inherited row
parser made six historical pages look too short.  The corrected identity-aware
parser now captures all 49 planned clubs directly.  This promoter deliberately
does not mix those receipts with the earlier fallback routes: it verifies one
complete, zero-gap, hash-bound source capture before any opening-squad choice
or database writing step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compose_2015_source_tail_package_v1 as v1


SCHEMA = "pm99-world-2015-source-tail-package-v2"


class DirectPackageError(ValueError):
    """A full strict source capture cannot safely become a V2 package."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _read(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DirectPackageError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise DirectPackageError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def compose(*, plan: Mapping[str, Any], plan_sha256: str, squad_capture: Mapping[str, Any], squad_sha256: str) -> dict[str, Any]:
    expected = v1._expected_carriers(plan)
    if squad_capture.get("schema_version") != v1.PINNED_SCHEMA:
        raise DirectPackageError("squad capture has an unsupported schema")
    source = squad_capture.get("sources")
    if not isinstance(source, Mapping) or source.get("source_tail_plan_sha256") != plan_sha256:
        raise DirectPackageError("squad capture is not bound to this exact source-tail plan")
    gaps = squad_capture.get("gaps")
    clubs = squad_capture.get("clubs")
    if gaps != [] or not isinstance(clubs, list):
        raise DirectPackageError("V2 promotion requires a zero-gap squad capture")
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    input_ref = v1.CaptureInput(
        name="complete-pinned-historic-squads", route="pinned-historic-season-squad",
        value=squad_capture, sha256=squad_sha256,
    )
    for club in clubs:
        if not isinstance(club, Mapping):
            raise DirectPackageError("squad capture has a malformed club")
        carrier_id = club.get("candidate_carrier_id")
        if not isinstance(carrier_id, int) or carrier_id not in expected or carrier_id in seen:
            raise DirectPackageError(f"squad capture has an unexpected or duplicate carrier {carrier_id!r}")
        try:
            v1._validate_club(club=club, expected=expected[carrier_id], capture=input_ref)
        except v1.SourceTailPackageError as exc:
            raise DirectPackageError(str(exc)) from exc
        result.append({
            **dict(club),
            "source_package": {
                "capture_name": input_ref.name,
                "capture_sha256": squad_sha256,
                "route": input_ref.route,
                "roster_selection_status": "capacity-safe-season-roster-awaiting-explicit-opening-order",
            },
        })
        seen.add(carrier_id)
    missing = sorted(set(expected) - seen)
    if missing:
        raise DirectPackageError(f"squad capture is missing planned carriers {missing}")
    result.sort(key=lambda club: int(club["candidate_carrier_id"]))
    unresolved = Counter(
        field for club in result for player in club["players"] for field in player["unresolved_fields"]
    )
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only V2 promotion; one complete hash-bound historical squad capture; published player IDs "
            "preserved so same-named people remain distinct; secondary missing facts stay logged; no PM99 write "
            "and no implicit roster truncation"
        ),
        "sources": {
            "source_tail_plan_sha256": plan_sha256,
            "captures": [{
                "capture_name": input_ref.name,
                "capture_sha256": squad_sha256,
                "route": input_ref.route,
                "schema_version": squad_capture["schema_version"],
                "source_repository": source.get("repository"),
                "source_title": source.get("title"),
            }],
        },
        "clubs": result,
        "summary": {
            "planned_carrier_count": len(expected),
            "covered_carrier_count": len(result),
            "source_candidate_player_count": sum(len(club["players"]) for club in result),
            "source_route_counts": {"pinned-historic-season-squad": len(result)},
            "roster_selection_status_counts": {
                "capacity-safe-season-roster-awaiting-explicit-opening-order": len(result),
            },
            "unresolved_secondary_field_counts": dict(sorted(unresolved.items())),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--squad-capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source package: {args.output}")
    try:
        plan, plan_sha = _read(args.plan, label="source-tail plan")
        squad_capture, squad_sha = _read(args.squad_capture, label="squad capture")
        result = compose(
            plan=plan, plan_sha256=plan_sha,
            squad_capture=squad_capture, squad_sha256=squad_sha,
        )
    except (OSError, DirectPackageError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
