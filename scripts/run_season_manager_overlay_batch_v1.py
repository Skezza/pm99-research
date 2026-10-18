#!/usr/bin/env python3
"""Materialise write-once manager overlays from captured raw supplements."""

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

from scripts import run_allocated_manager_backfill_batch_v1 as raw_batch  # noqa: E402
from scripts import season_manager_overlay_v1 as overlay_v1  # noqa: E402


SCHEMA = "pm99-season-manager-overlay-batch-v1"


class OverlayBatchError(ValueError):
    """A raw receipt cannot safely be applied as an immutable overlay."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _latest_raw_supplement(operations_root: Path, season: str) -> Path:
    candidates = list((operations_root / season).glob("opening-manager-supplement.allocated-transfermarkt*.json"))
    if not candidates:
        raise OverlayBatchError(f"{season}: allocated-manager raw supplement is missing")
    def version(path: Path) -> int:
        match = re.search(r"-v(\d+)\.json$", path.name)
        return int(match.group(1)) if match else 0
    return max(candidates, key=lambda path: (version(path), path.name))


def _source_path(current_root: Path, season: str) -> Path:
    pointer_path = current_root / season / "current.json"
    pointer, _pointer_sha = raw_batch._load(pointer_path, "current pointer")
    if pointer.get("schema_version") != raw_batch.CURRENT_SCHEMA or pointer.get("season") != season:
        raise OverlayBatchError(f"{season}: unsupported current pointer")
    source_path, _source, _source_sha = raw_batch._bound_artifact(pointer_path, pointer, "source")
    return source_path


def run_batch(
    *, baseline_index: Path, current_root: Path, opening_root: Path,
    operations_root: Path, overlays_root: Path, seasons: Sequence[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for season in sorted(set(seasons)):
        output_root = overlays_root / season / "manager-v1"
        if output_root.exists():
            audit_path = output_root / "manager-overlay-audit.json"
            audit, digest = raw_batch._load(audit_path, "existing manager overlay audit")
            if audit.get("schema_version") != overlay_v1.SCHEMA:
                raise OverlayBatchError(f"{season}: existing overlay audit has an unexpected schema")
            rows.append({"season": season, "state": "already-materialised", "audit": str(audit_path), "sha256": digest,
                         "coverage": audit.get("coverage")})
            continue
        opening_dir = opening_root / season
        try:
            receipt = overlay_v1.write_overlay(
                baseline_index=baseline_index, season=season, source_capture=_source_path(current_root, season),
                opening_lineups=opening_dir / "opening-lineups.json",
                supplements=[
                    opening_dir / "opening-manager-supplement.json",
                    _latest_raw_supplement(operations_root, season),
                ],
                output_root=output_root,
            )
        except (OSError, raw_batch.BatchError, overlay_v1.ManagerOverlayError) as exc:
            raise OverlayBatchError(str(exc)) from exc
        audit_path = output_root / "manager-overlay-audit.json"
        rows.append({"season": season, "state": "materialised", "audit": str(audit_path),
                     "sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(), "coverage": receipt["coverage"]})
    return {
        "schema_version": SCHEMA,
        "policy": "write-once-manager-overlays-from-hash-bound-current-source-and-raw-supplements",
        "results": rows,
        "summary": {
            "season_count": len(rows),
            "materialised_count": sum(row["state"] == "materialised" for row in rows),
            "already_materialised_count": sum(row["state"] == "already-materialised" for row in rows),
            "resolved_manager_count": sum(int((row.get("coverage") or {}).get("resolved_manager_count") or 0) for row in rows),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", type=Path, default=ROOT / ".local/season-baselines-v1/calendar-bound-v2.json")
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--opening-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--operations-root", type=Path, default=ROOT / ".local/operations")
    parser.add_argument("--overlays-root", type=Path, default=ROOT / ".local/season-overlays-v1")
    parser.add_argument("--season", action="append", dest="seasons", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists():
            raise OverlayBatchError(f"refusing to overwrite batch receipt: {args.receipt}")
        result = run_batch(
            baseline_index=args.baseline_index, current_root=args.current_root, opening_root=args.opening_root,
            operations_root=args.operations_root, overlays_root=args.overlays_root, seasons=args.seasons,
        )
    except (OSError, OverlayBatchError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
