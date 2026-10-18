#!/usr/bin/env python3
"""Compare repeated foreign-picker captures before trusting a host map.

This is a read-only diagnostic for a subtle but important runner outcome: a
twenty-shirt country screen need not yield twenty distinct visual picker states.
When independent captures produce the identical per-tile frame sequence, the
result is a deterministic PM99 picker behaviour, not a timing or screenshot
race.  It still does not reveal a writable competition topology field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "pm99-foreign-host-capture-v1"
REPORT_SCHEMA = "pm99-foreign-host-frame-comparison-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_capture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError(f"Expected {SCHEMA} capture JSON")
    tiles = payload.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("capture.tiles must be a non-empty array")
    return payload


def compare(*, capture: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    if len(roots) < 2:
        raise ValueError("at least two --capture-root values are required")
    tiles = sorted(capture["tiles"], key=lambda item: int(item["tile_index"]))
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    sequences: list[list[str | None]] = []
    for root in roots:
        sequence: list[str | None] = []
        for item in tiles:
            screenshot = str(item.get("screenshot") or "")
            if not screenshot or Path(screenshot).is_absolute() or ".." in Path(screenshot).parts:
                raise ValueError("tile screenshot must be a safe relative path")
            path = root / screenshot
            sequence.append(sha256(path) if path.is_file() else None)
        sequences.append(sequence)
    for index, item in enumerate(tiles):
        tile_index = int(item["tile_index"])
        if tile_index in seen:
            raise ValueError(f"duplicate tile index {tile_index}")
        seen.add(tile_index)
        hashes = [sequence[index] for sequence in sequences]
        rows.append(
            {
                "tile_index": tile_index,
                "eq_record_id": int(item["eq_record_id"]),
                "expected_club_name": str(item["reviewed_visible_club_name"]),
                "screenshot": str(item["screenshot"]),
                "hashes": hashes,
                "status": "deterministic-across-captures" if None not in hashes and len(set(hashes)) == 1 else "not-proven",
            }
        )
    first_sequence = sequences[0]
    exact_sequence_match = all(sequence == first_sequence for sequence in sequences[1:])
    groups: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        digest = row["hashes"][0]
        if digest is not None:
            groups[str(digest)].append(int(row["tile_index"]))
    repeated = [
        {"sha256": digest, "tile_indices": indices}
        for digest, indices in sorted(groups.items())
        if len(indices) > 1
    ]
    unique_frames = len(groups)
    return {
        "schema": REPORT_SCHEMA,
        "read_only": True,
        "capture_id": capture.get("capture_id"),
        "roots": [str(root.resolve()) for root in roots],
        "counts": {
            "captures": len(roots),
            "tiles": len(rows),
            "unique_first_capture_frames": unique_frames,
            "repeated_first_capture_frame_groups": len(repeated),
        },
        "exact_per_tile_sequence_match": exact_sequence_match,
        "tiles": rows,
        "repeated_first_capture_frames": repeated,
        "interpretation": (
            "The reviewed picker probes are deterministic but not one-to-one with the supplied tile list; "
            "do not promote all visible shirts to carrier mappings."
            if exact_sequence_match and unique_frames < len(rows)
            else "No picker-capacity conclusion is available from this comparison."
        ),
        "writer_boundary": "No country, division, competition, draw-pool or EQ-order writer is implied.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare(capture=load_capture(args.capture), roots=[path.resolve() for path in args.capture_root])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
