#!/usr/bin/env python3
"""Prepare and review a single fresh-route foreign picker probe.

The PM99 rival screen is stateful: it has four friendly slots, so a twenty
shirt sweep is not twenty independent carrier probes. This helper makes the
safe unit of evidence explicit. ``prepare`` extracts one tile from a reviewed
country plan; the normal runner then starts a fresh game route for that file;
after visual review, ``review`` binds the actual new screenshot digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "pm99-foreign-host-capture-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError(f"expected {SCHEMA} input")
    return payload


def _safe_screenshot(value: object) -> str:
    text = str(value or "").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts or path.parent != Path("screens"):
        raise ValueError("tile screenshot must be a safe screens/<name>.png path")
    return text


def prepare(*, capture: dict[str, Any], tile_index: int) -> dict[str, Any]:
    if not isinstance(tile_index, int) or tile_index < 0:
        raise ValueError("tile_index must be non-negative")
    tiles = capture.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError("capture tiles must be a list")
    matches = [item for item in tiles if isinstance(item, dict) and item.get("tile_index") == tile_index]
    if len(matches) != 1:
        raise ValueError(f"capture must contain exactly one tile_index {tile_index}")
    tile = dict(matches[0])
    old_path = _safe_screenshot(tile.get("screenshot"))
    old_name = Path(old_path).name
    label = re.sub(r"^[0-9]+_", "", old_name)
    if label == old_name:
        raise ValueError("source tile screenshot must have a numeric runner prefix")
    tile["screenshot"] = f"screens/19_{label}"
    # Runner only needs selectors. All-zero hash makes accidental auditing
    # fail closed until `review` binds the fresh screenshot.
    tile["reviewed_frame_sha256"] = "0" * 64
    return {
        "schema": SCHEMA,
        "capture_id": f"{str(capture.get('capture_id') or 'country')}-tile-{tile_index}-fresh-route",
        "route_selection_limit": 1,
        "country": capture.get("country"),
        "tiles": [tile],
    }


def review(*, capture: dict[str, Any], capture_root: Path) -> dict[str, Any]:
    tiles = capture.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != 1:
        raise ValueError("single-tile capture must contain exactly one tile")
    result = json.loads(json.dumps(capture))
    screenshot = _safe_screenshot(result["tiles"][0].get("screenshot"))
    path = capture_root / screenshot
    if not path.is_file():
        raise FileNotFoundError(f"fresh runner screenshot is missing: {path}")
    result["tiles"][0]["reviewed_frame_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--review", action="store_true")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--tile-index", type=int)
    parser.add_argument("--capture-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        capture = _read(args.capture)
        if args.prepare:
            if args.tile_index is None:
                raise ValueError("--prepare requires --tile-index")
            result = prepare(capture=capture, tile_index=args.tile_index)
        else:
            if args.capture_root is None:
                raise ValueError("--review requires --capture-root")
            result = review(capture=capture, capture_root=args.capture_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    _write(args.output, result)
    print(json.dumps({"capture_id": result["capture_id"], "tile_count": len(result["tiles"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
