#!/usr/bin/env python3
"""Merge disjoint season authoring matrices without rebuilding packages."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_batch_authoring_v1 as batch


class MatrixMergeError(ValueError):
    pass


def merge(matrices: Sequence[Mapping[str, Any]], *, replace_duplicates: bool = False) -> dict[str, Any]:
    by_season: dict[str, dict[str, Any]] = {}
    for matrix in matrices:
        if matrix.get("schema_version") != batch.SCHEMA or not isinstance(matrix.get("rows"), list):
            raise MatrixMergeError("input is not a season authoring matrix")
        for raw in matrix["rows"]:
            season = str(raw.get("season_id") or "") if isinstance(raw, Mapping) else ""
            if not season or (season in by_season and not replace_duplicates):
                raise MatrixMergeError(f"blank or duplicate season row: {season!r}")
            by_season[season] = dict(raw)
    rows = [by_season[season] for season in sorted(by_season)]
    return {
        "schema_version": batch.SCHEMA,
        "rows": rows,
        "summary": {
            "season_count": len(rows),
            "candidate_ready_count": sum(row["status"] == "candidate-ready" for row in rows),
            "blocked_count": sum(row["status"] == "blocked" for row in rows),
            "draft_package_count": sum("draft_package" in row["outputs"] for row in rows),
            "database_count": 0,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrices", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replace-duplicates", action="store_true", help="let a later matrix replace the same season row")
    args = parser.parse_args(argv)
    try:
        result = merge([json.loads(path.read_text(encoding="utf-8")) for path in args.matrices], replace_duplicates=args.replace_duplicates)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(batch.canonical_json_bytes(result))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
