#!/usr/bin/env python3
"""Serially capture unresolved fixed-carrier managers for selected seasons.

This is an operations runner, not a database generator.  It reads each
hash-bound current pointer, retains managers already evidenced by that
season's ledger, and writes one new raw supplement per season.  Capture is
intentionally serial because every season shares the immutable Transfermarkt
snapshot cache; downstream overlay and validation work may run in parallel.
"""

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

from scripts import capture_allocated_manager_history_v1 as capture_v1  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-allocated-manager-backfill-batch-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"


class BatchError(ValueError):
    """A batch input is mutable, malformed or outside its declared scope."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BatchError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _bound_artifact(pointer_path: Path, pointer: Mapping[str, Any], name: str) -> tuple[Path, dict[str, Any], str]:
    artifact = (pointer.get("artifacts") or {}).get(name)
    if not isinstance(artifact, Mapping):
        raise BatchError(f"{pointer_path}: missing {name} artifact")
    relative = artifact.get("path")
    expected = artifact.get("sha256")
    if not isinstance(relative, str) or not relative or not isinstance(expected, str) or len(expected) != 64:
        raise BatchError(f"{pointer_path}: malformed {name} artifact")
    path = (pointer_path.parent / relative).resolve()
    if pointer_path.parent.resolve() not in path.parents:
        raise BatchError(f"{pointer_path}: unsafe {name} artifact path")
    document, actual = _load(path, name)
    if actual != expected:
        raise BatchError(f"{pointer_path}: {name} artifact hash mismatch")
    return path, document, actual


def _output_path(operations_root: Path, season: str) -> Path:
    return operations_root / season / "opening-manager-supplement.allocated-transfermarkt-v1.json"


def _existing_output(operations_root: Path, season: str) -> Path | None:
    """Select the latest explicit version so an earlier failed receipt is not rerun."""
    directory = operations_root / season
    candidates = list(directory.glob("opening-manager-supplement.allocated-transfermarkt*.json"))
    if not candidates:
        return None
    def version(path: Path) -> int:
        match = re.search(r"-v(\d+)\.json$", path.name)
        return int(match.group(1)) if match else 0
    return max(candidates, key=lambda path: (version(path), path.name))


def run_batch(
    *, current_root: Path, opening_root: Path, cache_dir: Path, operations_root: Path,
    seasons: Sequence[str] | None, offline: bool, delay: float,
) -> dict[str, Any]:
    requested = set(seasons or ())
    pointers = sorted(current_root.glob("*/current.json"))
    if requested:
        pointers = [path for path in pointers if path.parent.name in requested]
        missing = requested - {path.parent.name for path in pointers}
        if missing:
            raise BatchError(f"missing current pointers: {', '.join(sorted(missing))}")
    if not pointers:
        raise BatchError("no seasons selected")

    results: list[dict[str, Any]] = []
    for pointer_path in pointers:
        season = pointer_path.parent.name
        existing_output = _existing_output(operations_root, season)
        if existing_output is not None:
            existing, digest = _load(existing_output, "existing manager supplement")
            if existing.get("schema_version") != capture_v1.SCHEMA:
                raise BatchError(f"{season}: existing output has an unexpected schema: {existing_output}")
            results.append({"season": season, "state": "already-captured", "output": str(existing_output), "sha256": digest,
                            "summary": existing.get("summary")})
            continue
        output = _output_path(operations_root, season)
        pointer, _pointer_sha = _load(pointer_path, "current pointer")
        if pointer.get("schema_version") != CURRENT_SCHEMA or pointer.get("season") != season:
            raise BatchError(f"{pointer_path}: unsupported current pointer")
        source_path, source, source_sha = _bound_artifact(pointer_path, pointer, "source")
        allocation_path, allocation, allocation_sha = _bound_artifact(pointer_path, pointer, "allocation")
        opening_dir = opening_root / season
        competition_map, competition_map_sha = opening.load_competition_map(opening_dir / "competition-map.json")
        known_ledger, known_ledger_sha = _load(opening_dir / "opening-manager-ledger.json", "known manager ledger")
        try:
            result = capture_v1.capture(
                source_capture=source, source_capture_sha256=source_sha,
                allocation=allocation, allocation_sha256=allocation_sha,
                competition_map=competition_map, competition_map_sha256=competition_map_sha,
                aliases={}, aliases_sha256=None,
                known_manager_ledger=known_ledger, known_manager_ledger_sha256=known_ledger_sha,
                cache=opening.SnapshotCache(cache_dir, offline=offline, delay=delay),
            )
        except (capture_v1.AllocatedManagerHistoryError, opening.CaptureError) as exc:
            raise BatchError(f"{season}: {exc}") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise BatchError(f"{season}: refusing to overwrite manager supplement: {output}")
        payload = _bytes(result)
        output.write_bytes(payload)
        results.append({
            "season": season, "state": "captured", "output": str(output),
            "sha256": hashlib.sha256(payload).hexdigest(), "summary": result["summary"],
            "source_capture": str(source_path), "carrier_allocation": str(allocation_path),
        })
    return {
        "schema_version": SCHEMA,
        "policy": "serial-shared-snapshot-cache; write-once-raw-supplements; retain-valid-known-managers",
        "results": results,
        "summary": {
            "season_count": len(results),
            "captured_count": sum(row["state"] == "captured" for row in results),
            "already_captured_count": sum(row["state"] == "already-captured" for row in results),
            "new_dated_manager_count": sum(
                int((row.get("summary") or {}).get("supplemented_manager_count") or 0)
                for row in results if row["state"] == "captured"
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--opening-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".local/external-sources/cache.transfermarkt-opening")
    parser.add_argument("--operations-root", type=Path, default=ROOT / ".local/operations")
    parser.add_argument("--season", action="append", dest="seasons")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists():
            raise BatchError(f"refusing to overwrite batch receipt: {args.receipt}")
        result = run_batch(
            current_root=args.current_root, opening_root=args.opening_root,
            cache_dir=args.cache_dir, operations_root=args.operations_root,
            seasons=args.seasons, offline=args.offline, delay=args.delay,
        )
    except (OSError, BatchError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
