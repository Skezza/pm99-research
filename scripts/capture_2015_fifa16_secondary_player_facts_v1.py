#!/usr/bin/env python3
"""Capture absent 2015/16 secondary player facts from the local FIFA 16 source.

FIFA 16 is a dated, locally cached biographical source complementary to the
slower Wikipedia lane.  A row is accepted only when the package already has a
dated ``source_name`` and that exact normalised name appears once in FIFA 16.
It fills absent facts only; an ambiguous or unrepresentable source identity is
recorded rather than guessed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_wikipedia_player_facts_v1 as common  # noqa: E402
from scripts import prepare_2015_world_fifa16_drafts as fifa  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-world-2015-fifa16-secondary-player-facts-v1"
FACT_FIELDS = ("birth_date", "nationality", "height_cm", "weight_kg")
NATIONALITY_EXCEPTIONS = {"curacao": "CUW"}


class FifaFactCaptureError(ValueError):
    """The local FIFA snapshot cannot safely fill the requested fact."""


def _read_csv(path: Path) -> tuple[list[dict[str, str]], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"player_id", "name", "birthdate", "nationality", "height", "weight"}
    if not rows or not required <= set(rows[0]):
        raise FifaFactCaptureError("FIFA 16 CSV lacks required biographical columns")
    return rows, digest


def _number(value: object, *, lower: int, upper: int) -> int | None:
    try:
        result = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return result if lower <= result <= upper else None


def _facts(row: Mapping[str, str]) -> dict[str, Any]:
    try:
        birth_date = dt.date.fromisoformat(str(row.get("birthdate") or "")).isoformat()
    except ValueError:
        birth_date = None
    label = fifa._normalise_label(row.get("nationality"))
    nationality = NATIONALITY_EXCEPTIONS.get(label) or fifa.FIFA_NATIONALITY_TO_PM99.get(label)
    return {
        "birth_date": birth_date,
        "nationality": nationality,
        "height_cm": _number(row.get("height"), lower=140, upper=220),
        "weight_kg": _number(row.get("weight"), lower=40, upper=130),
    }


def capture(*, package: Mapping[str, Any], package_sha256: str,
            fifa_rows: Sequence[Mapping[str, str]], fifa_sha256: str) -> dict[str, Any]:
    by_name: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in fifa_rows:
        key = common._normalise(row.get("name"))
        if key:
            by_name[key].append(row)
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for target in common._targets(package):
        candidates = by_name.get(common._normalise(target["source_name"]), [])
        if len(candidates) != 1:
            gaps.append({
                **target,
                "reason": "no-unique-exact-fifa16-source-name" if not candidates else "ambiguous-exact-fifa16-source-name",
                "candidate_count": len(candidates),
            })
            continue
        selected = candidates[0]
        available = _facts(selected)
        facts = {field: available[field] for field in target["missing_fields"] if available.get(field) is not None}
        if not facts:
            gaps.append({**target, "reason": "unique-fifa16-row-has-none-of-the-missing-facts", "fifa16_player_id": selected.get("player_id")})
            continue
        rows.append({
            **target,
            "facts": facts,
            "source_name": "FIFA 16 local player snapshot",
            "fifa16_player_id": int(selected["player_id"]),
            "fifa16_name": selected["name"],
            "fifa16_page_url": selected.get("page_url"),
            "fifa16_nationality_label": selected.get("nationality"),
            "reason": "declared source_name has one exact normalised FIFA 16 player row",
        })
    sourced = Counter(field for row in rows for field in row["facts"])
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; declared source_name only; one exact normalised FIFA 16 name; "
            "fill absent facts only; no fuzzy identity and no PM99 binary write"
        ),
        "sources": {"base_package_sha256": package_sha256, "fifa16_player_snapshot_sha256": fifa_sha256},
        "coverage": {
            "source_named_player_with_missing_facts_count": len(common._targets(package)),
            "player_rows_with_at_least_one_sourced_fact": len(rows),
            "sourced_field_counts": dict(sorted(sourced.items())),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": sorted(rows, key=lambda row: str(row["player_id"])),
        "gaps": sorted(gaps, key=lambda row: str(row["player_id"])),
        "identity_gaps": common._identity_gaps(package),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--fifa16-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise FifaFactCaptureError(f"refusing to overwrite output: {args.output}")
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package)
        fifa_rows, fifa_sha = _read_csv(args.fifa16_csv)
        result = capture(
            package=package, package_sha256=hashlib.sha256(args.package.read_bytes()).hexdigest(),
            fifa_rows=fifa_rows, fifa_sha256=fifa_sha,
        )
    except (OSError, package_v2.PackageValidationError, FifaFactCaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
