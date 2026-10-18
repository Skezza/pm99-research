#!/usr/bin/env python3
"""Backfill missing 2015 player biography fields from cached SoFIFA files.

FIFA 15 is the closest local snapshot; FIFA 17 is used only to recognise a
player absent from FIFA 15.  A declared target-season source name must map to
one and only one SoFIFA player id across all supplied editions, using an exact
normalised short or long display name.  This is a biographical fact lane, not
an assertion that the later edition reflects a 2015 squad or rating.
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


SCHEMA = "pm99-world-2015-sofifa-secondary-player-facts-v1"
FACT_FIELDS = ("birth_date", "nationality", "height_cm", "weight_kg")
NATIONALITY_EXCEPTIONS = {"curacao": "CUW"}


class SofifaFactError(ValueError):
    """A local snapshot cannot prove a narrow player fact safely."""


def _number(value: object, *, lower: int, upper: int) -> int | None:
    try:
        result = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return result if lower <= result <= upper else None


def _facts(row: Mapping[str, str]) -> dict[str, Any]:
    try:
        birth_date = dt.date.fromisoformat(str(row.get("dob") or "")).isoformat()
    except ValueError:
        birth_date = None
    nationality_label = fifa._normalise_label(row.get("nationality"))
    nationality = NATIONALITY_EXCEPTIONS.get(nationality_label) or fifa.FIFA_NATIONALITY_TO_PM99.get(nationality_label)
    return {
        "birth_date": birth_date,
        "nationality": nationality,
        "height_cm": _number(row.get("height_cm"), lower=140, upper=220),
        "weight_kg": _number(row.get("weight_kg"), lower=40, upper=130),
    }


def _read(path: Path, edition: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    required = {"sofifa_id", "short_name", "long_name", "dob", "height_cm", "weight_kg", "nationality"}
    if not rows or not required <= set(rows[0]):
        raise SofifaFactError(f"FIFA {edition} snapshot lacks biographical columns")
    if not all(str(row.get("sofifa_id") or "").isdigit() for row in rows):
        raise SofifaFactError(f"FIFA {edition} snapshot has a non-numeric player id")
    return rows, {"edition": edition, "sha256": hashlib.sha256(raw).hexdigest(), "row_count": len(rows)}


def capture(*, package: Mapping[str, Any], package_sha256: str,
            snapshots: Sequence[tuple[int, Sequence[Mapping[str, str]], Mapping[str, Any]]]) -> dict[str, Any]:
    by_name: dict[str, dict[int, list[tuple[int, Mapping[str, str]]]]] = defaultdict(lambda: defaultdict(list))
    for edition, rows, _receipt in snapshots:
        for row in rows:
            sofifa_id = int(str(row["sofifa_id"]))
            for name in {common._normalise(row.get("short_name")), common._normalise(row.get("long_name"))}:
                if name:
                    by_name[name][edition].append((sofifa_id, row))

    rows_out: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for target in common._targets(package):
        candidate_by_edition = by_name.get(common._normalise(target["source_name"]), {})
        candidates: dict[int, list[tuple[int, Mapping[str, str]]]] = defaultdict(list)
        for edition, matches in candidate_by_edition.items():
            for sofifa_id, row in matches:
                candidates[sofifa_id].append((edition, row))
        if len(candidates) != 1:
            gaps.append({
                **target,
                "reason": "no-exact-sofifa-name" if not candidates else "ambiguous-exact-sofifa-name-across-snapshots",
                "candidate_sofifa_ids": sorted(candidates),
            })
            continue
        sofifa_id, versions = next(iter(candidates.items()))
        # Prefer the nearest dated file (15) but only after proving that all
        # present editions point to this same EA/SoFIFA identity.
        edition, selected = min(versions, key=lambda item: item[0])
        available = _facts(selected)
        facts = {field: available[field] for field in target["missing_fields"] if available.get(field) is not None}
        if not facts:
            gaps.append({**target, "reason": "unique-sofifa-row-has-none-of-the-missing-facts", "sofifa_id": sofifa_id})
            continue
        rows_out.append({
            **target,
            "facts": facts,
            "source_name": "cached FIFA/SoFIFA close-era player biography snapshot",
            "sofifa_id": sofifa_id,
            "selected_edition": edition,
            "matched_editions": sorted({entry[0] for entry in versions}),
            "sofifa_short_name": selected.get("short_name"),
            "sofifa_long_name": selected.get("long_name"),
            "sofifa_player_url": selected.get("player_url"),
            "reason": "declared source_name maps to one exact normalised SoFIFA id across supplied snapshots",
        })
    sourced = Counter(field for row in rows_out for field in row["facts"])
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; declared source_name only; one exact normalised short/long-name SoFIFA id "
            "across cached close-era snapshots; fill absent biography facts only; no fuzzy identity or binary write"
        ),
        "sources": {
            "base_package_sha256": package_sha256,
            "snapshots": [dict(receipt) for _edition, _rows, receipt in snapshots],
        },
        "coverage": {
            "source_named_player_with_missing_facts_count": len(common._targets(package)),
            "player_rows_with_at_least_one_sourced_fact": len(rows_out),
            "sourced_field_counts": dict(sorted(sourced.items())),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": sorted(rows_out, key=lambda row: str(row["player_id"])),
        "gaps": sorted(gaps, key=lambda row: str(row["player_id"])),
        "identity_gaps": common._identity_gaps(package),
    }


def _snapshot_arg(value: str) -> tuple[int, Path]:
    try:
        edition_text, path_text = value.split(":", 1)
        edition = int(edition_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("snapshot must be EDITION:PATH") from exc
    if edition not in {15, 17, 18, 19, 20} or not path_text:
        raise argparse.ArgumentTypeError("snapshot edition must be 15, 17, 18, 19 or 20")
    return edition, Path(path_text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--snapshot", action="append", required=True, type=_snapshot_arg)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise SofifaFactError(f"refusing to overwrite output: {args.output}")
        if len({edition for edition, _path in args.snapshot}) != len(args.snapshot):
            raise SofifaFactError("each FIFA edition may be supplied once")
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package)
        snapshots = [
            (edition, *_read(path, edition))
            for edition, path in sorted(args.snapshot)
        ]
        result = capture(
            package=package, package_sha256=hashlib.sha256(args.package.read_bytes()).hexdigest(),
            snapshots=snapshots,
        )
    except (OSError, UnicodeDecodeError, package_v2.PackageValidationError, SofifaFactError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(package_v2.canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
