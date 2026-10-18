#!/usr/bin/env python3
"""Serial, write-once historic-ID opening-XI capture batch."""

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

from scripts import capture_allocated_opening_lineups_v1 as xi  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402
from scripts import run_allocated_manager_backfill_batch_v1 as common  # noqa: E402


SCHEMA = "pm99-allocated-opening-lineup-backfill-batch-v1"


class LineupBatchError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _latest_output(operations_root: Path, season: str) -> Path | None:
    candidates = list((operations_root / season).glob("opening-lineups.allocated-historic-id*.json"))
    if not candidates:
        return None
    def version(path: Path) -> int:
        match = re.search(r"-v(\d+)\.json$", path.name)
        return int(match.group(1)) if match else 0
    return max(candidates, key=lambda path: (version(path), path.name))


def run_batch(*, current_root: Path, opening_root: Path, operations_root: Path, cache_dir: Path,
              seasons: Sequence[str] | None, offline: bool, delay: float) -> dict[str, Any]:
    requested = set(seasons or ())
    pointers = sorted(current_root.glob("*/current.json"))
    if requested:
        pointers = [path for path in pointers if path.parent.name in requested]
        missing = requested - {path.parent.name for path in pointers}
        if missing:
            raise LineupBatchError(f"missing current pointers: {', '.join(sorted(missing))}")
    if not pointers:
        raise LineupBatchError("no seasons selected")
    rows: list[dict[str, Any]] = []
    for pointer_path in pointers:
        season = pointer_path.parent.name
        previous = _latest_output(operations_root, season)
        if previous is not None:
            document, digest = common._load(previous, "existing opening-lineup supplement")
            if document.get("schema_version") != xi.SCHEMA:
                raise LineupBatchError(f"{season}: existing output has an unexpected schema")
            rows.append({"season": season, "state": "already-captured", "output": str(previous), "sha256": digest,
                         "summary": document.get("summary")})
            continue
        pointer, _pointer_sha = common._load(pointer_path, "current pointer")
        if pointer.get("schema_version") != common.CURRENT_SCHEMA or pointer.get("season") != season:
            raise LineupBatchError(f"{season}: unsupported current pointer")
        source_path, source, source_sha = common._bound_artifact(pointer_path, pointer, "source")
        allocation_path, allocation, allocation_sha = common._bound_artifact(pointer_path, pointer, "allocation")
        opening_dir = opening_root / season
        known_path = opening_dir / "opening-lineup-reconciliation.json"
        known, known_sha = common._load(known_path, "known opening reconciliation")
        try:
            result = xi.capture(
                source_capture=source, source_capture_sha256=source_sha,
                allocation=allocation, allocation_sha256=allocation_sha,
                known_reconciliation=known, known_reconciliation_sha256=known_sha,
                cache=opening.SnapshotCache(cache_dir, offline=offline, delay=delay),
            )
        except (xi.AllocatedLineupError, opening.CaptureError) as exc:
            raise LineupBatchError(f"{season}: {exc}") from exc
        output = operations_root / season / "opening-lineups.allocated-historic-id-v1.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise LineupBatchError(f"{season}: refusing to overwrite {output}")
        payload = _bytes(result)
        output.write_bytes(payload)
        rows.append({"season": season, "state": "captured", "output": str(output),
                     "sha256": hashlib.sha256(payload).hexdigest(), "summary": result["summary"],
                     "source_capture": str(source_path), "carrier_allocation": str(allocation_path),
                     "known_opening_reconciliation": str(known_path)})
    return {"schema_version": SCHEMA, "policy": "serial-shared-snapshot-cache; fixed-carrier-historic-id-only; write-once",
            "results": rows, "summary": {"season_count": len(rows), "captured_count": sum(row["state"] == "captured" for row in rows),
            "already_captured_count": sum(row["state"] == "already-captured" for row in rows),
            "new_opening_lineup_count": sum(int((row.get("summary") or {}).get("captured_club_count") or 0) for row in rows if row["state"] == "captured")}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--opening-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--operations-root", type=Path, default=ROOT / ".local/operations")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".local/external-sources/cache.transfermarkt-opening")
    parser.add_argument("--season", action="append", dest="seasons")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists():
            raise LineupBatchError(f"refusing to overwrite batch receipt: {args.receipt}")
        result = run_batch(current_root=args.current_root, opening_root=args.opening_root, operations_root=args.operations_root,
                           cache_dir=args.cache_dir, seasons=args.seasons, offline=args.offline, delay=args.delay)
    except (OSError, common.BatchError, LineupBatchError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
