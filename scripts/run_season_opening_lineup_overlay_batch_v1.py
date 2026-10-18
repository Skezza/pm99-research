#!/usr/bin/env python3
"""Materialise write-once opening-XI overlays from historic-ID receipts.

The raw capture batch is deliberately serial because it shares the frozen
Transfermarkt snapshot cache.  This second stage is local-only: it validates
the current source pointer and then appends an immutable reconciliation overlay
without changing the established opening-plan files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_allocated_manager_backfill_batch_v1 as common  # noqa: E402
from scripts import season_opening_lineup_overlay_v1 as overlay_v1  # noqa: E402


SCHEMA = "pm99-season-opening-lineup-overlay-batch-v1"


class OpeningOverlayBatchError(ValueError):
    """A raw historic-ID receipt cannot safely be used as an overlay."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _latest_raw_lineups(operations_root: Path, season: str) -> Path:
    candidates = list((operations_root / season).glob("opening-lineups.allocated-historic-id*.json"))
    if not candidates:
        raise OpeningOverlayBatchError(f"{season}: allocated historic-ID opening-XI receipt is missing")

    def version(path: Path) -> int:
        match = re.search(r"-v(\d+)\.json$", path.name)
        return int(match.group(1)) if match else 0

    return max(candidates, key=lambda path: (version(path), path.name))


def _current_source(current_root: Path, season: str) -> Path:
    pointer_path = current_root / season / "current.json"
    pointer, _pointer_sha = common._load(pointer_path, "current pointer")
    if pointer.get("schema_version") != common.CURRENT_SCHEMA or pointer.get("season") != season:
        raise OpeningOverlayBatchError(f"{season}: unsupported current pointer")
    source_path, _source, _source_sha = common._bound_artifact(pointer_path, pointer, "source")
    return source_path


def _existing(output_root: Path, season: str) -> dict[str, Any]:
    audit_path = output_root / "opening-lineup-overlay-audit.json"
    audit, digest = common._load(audit_path, "existing opening-XI overlay audit")
    if audit.get("schema_version") != overlay_v1.SCHEMA or audit.get("season") != season:
        raise OpeningOverlayBatchError(f"{season}: existing opening-XI overlay audit has an unexpected schema or season")
    outputs = audit.get("outputs")
    reconciliation_path = output_root / "opening-lineup-reconciliation.json"
    expected = outputs.get("opening_reconciliation_sha256") if isinstance(outputs, dict) else None
    actual = hashlib.sha256(reconciliation_path.read_bytes()).hexdigest() if reconciliation_path.is_file() else None
    if not isinstance(expected, str) or actual != expected:
        raise OpeningOverlayBatchError(f"{season}: existing opening-XI overlay reconciliation is stale or missing")
    return {"season": season, "state": "already-materialised", "audit": str(audit_path), "sha256": digest,
            "coverage": audit.get("coverage")}


def run_batch(
    *, baseline_index: Path, current_root: Path, opening_root: Path,
    operations_root: Path, overlays_root: Path, seasons: Sequence[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    baseline, baseline_sha = overlay_v1._read(baseline_index, "baseline index")
    for season in sorted(set(seasons)):
        output_root = overlays_root / season / "opening-xi-v1"
        if output_root.exists():
            rows.append(_existing(output_root, season))
            continue
        source_path = _current_source(current_root, season)
        opening_dir = opening_root / season
        try:
            source, source_sha = overlay_v1._read(source_path, "current source capture")
            base, base_sha = overlay_v1._read(opening_dir / "opening-lineup-reconciliation.json", "base opening reconciliation")
            raw_path = _latest_raw_lineups(operations_root, season)
            raw, raw_sha = overlay_v1._read(raw_path, "historic-ID opening-XI receipt")
            reconciliation, audit = overlay_v1.build_overlay(
                baseline=baseline, baseline_sha256=baseline_sha, season=season,
                source=source, source_sha256=source_sha,
                base_reconciliation=base, base_reconciliation_sha256=base_sha,
                raw_lineups=raw, raw_lineups_sha256=raw_sha,
            )
        except (OSError, common.BatchError, overlay_v1.OpeningOverlayError) as exc:
            raise OpeningOverlayBatchError(f"{season}: {exc}") from exc
        output_root.mkdir(parents=True, exist_ok=False)
        reconciliation_path = output_root / "opening-lineup-reconciliation.json"
        audit_path = output_root / "opening-lineup-overlay-audit.json"
        reconciliation_path.write_bytes(_bytes(reconciliation))
        audit_path.write_bytes(_bytes(audit))
        rows.append({"season": season, "state": "materialised", "audit": str(audit_path),
                     "sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(), "coverage": audit["coverage"],
                     "source_capture": str(source_path), "historic_id_lineups": str(raw_path)})
    return {
        "schema_version": SCHEMA,
        "policy": "write-once-opening-XI-overlay-from-current-hash-bound-source-and-historic-ID-receipt",
        "results": rows,
        "summary": {
            "season_count": len(rows),
            "materialised_count": sum(row["state"] == "materialised" for row in rows),
            "already_materialised_count": sum(row["state"] == "already-materialised" for row in rows),
            "reconciled_xi_club_count": sum(int((row.get("coverage") or {}).get("reconciled_xi_club_count") or 0) for row in rows),
            "historic_id_supplement_reconciled_xi_club_count": sum(int((row.get("coverage") or {}).get("historic_id_supplement_reconciled_xi_club_count") or 0) for row in rows),
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
            raise OpeningOverlayBatchError(f"refusing to overwrite batch receipt: {args.receipt}")
        result = run_batch(
            baseline_index=args.baseline_index, current_root=args.current_root, opening_root=args.opening_root,
            operations_root=args.operations_root, overlays_root=args.overlays_root, seasons=args.seasons,
        )
    except (OSError, common.BatchError, OpeningOverlayBatchError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
