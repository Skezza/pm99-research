#!/usr/bin/env python3
"""Verify a PM99 foreign *host-country* capture without inventing topology.

PM99's preseason rival picker visibly groups existing foreign carriers beneath
country flags.  That UI is useful evidence for the immutable host-country of a
carrier, but it does not reveal a writable domestic-league or continental-draw
field.  This tool binds a reviewed UI capture to the exact EQ records shown in
the base database and produces a small, machine-readable host map.

It deliberately treats a stale screenshot as unresolved.  A click is not
evidence by itself: the post-click frame must differ from the preceding tile
frame, and its decoded EQ short name must agree with the reviewed visible name.
The result can feed a fixed-carrier assignment ledger; it is never authority to
reorder EQ records or write country/division/competition bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.eq_jug_linked import load_eq_linked_team_rosters  # noqa: E402


SCHEMA = "pm99-foreign-host-capture-v1"
REPORT_SCHEMA = "pm99-foreign-host-mapping-report-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalise(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _require(value: Any, label: str, expected_type: type) -> Any:
    if not isinstance(value, expected_type):
        raise ValueError(f"{label} must be a {expected_type.__name__}")
    return value


@dataclass(frozen=True)
class TileVerdict:
    tile_index: int
    selector: dict[str, int]
    eq_record_id: int
    expected_club_name: str
    decoded_club_name: str | None
    screenshot: str
    screenshot_sha256: str | None
    reviewed_frame_sha256: str
    status: str
    reason: str | None


def load_capture(path: Path) -> dict[str, Any]:
    payload = _require(json.loads(path.read_text(encoding="utf-8")), "capture", dict)
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported capture schema {payload.get('schema')!r}; expected {SCHEMA}")
    _require(payload.get("country"), "country", dict)
    tiles = _require(payload.get("tiles"), "tiles", list)
    if not tiles:
        raise ValueError("tiles must not be empty")
    return payload


def _eq_short_names(dbdat: Path) -> dict[int, str]:
    eq_file = dbdat / "EQ98030.FDI"
    jug_file = dbdat / "JUG98030.FDI"
    if not eq_file.is_file() or not jug_file.is_file():
        raise FileNotFoundError("dbdat must contain EQ98030.FDI and JUG98030.FDI")
    result: dict[int, str] = {}
    for roster in load_eq_linked_team_rosters(team_file=str(eq_file), player_file=str(jug_file)):
        result[int(roster.eq_record_id)] = " ".join(str(roster.short_name or "").split())
    return result


def verify_capture(*, capture: dict[str, Any], dbdat: Path, capture_root: Path) -> dict[str, Any]:
    country = _require(capture["country"], "country", dict)
    country_name = str(country.get("canonical_name") or "").strip()
    ui_label = str(country.get("ui_label") or "").strip()
    if not country_name or not ui_label:
        raise ValueError("country.canonical_name and country.ui_label are required")
    expected = _eq_short_names(dbdat)
    tiles = _require(capture["tiles"], "tiles", list)
    # The rival screen has four actual friendly-opponent slots. A subsequent
    # tile click mutates that provisional rival list, so a long sweep cannot
    # independently prove all tiles. One fresh preseason route proves exactly
    # one post-click carrier. The old twenty-click Spain attempt is retained as
    # a diagnostic only; every row after the first has this explicit reason.
    route_selection_limit = capture.get("route_selection_limit", 1)
    if not isinstance(route_selection_limit, int) or route_selection_limit != 1:
        raise ValueError("capture.route_selection_limit must be exactly 1; use one fresh route per tile")
    seen_frame_hashes: set[str] = set()
    seen_tiles: set[int] = set()
    seen_records: set[int] = set()
    verdicts: list[TileVerdict] = []

    for selection_number, raw in enumerate(tiles):
        item = _require(raw, "tile", dict)
        tile_index = item.get("tile_index")
        record_id = item.get("eq_record_id")
        if isinstance(tile_index, bool) or not isinstance(tile_index, int) or tile_index < 0:
            raise ValueError("tile.tile_index must be a non-negative integer")
        if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id < 1:
            raise ValueError("tile.eq_record_id must be a positive integer")
        if tile_index in seen_tiles:
            raise ValueError(f"duplicate tile_index {tile_index}")
        if record_id in seen_records:
            raise ValueError(f"duplicate eq_record_id {record_id}")
        seen_tiles.add(tile_index)
        seen_records.add(record_id)

        selector = _require(item.get("selector"), "tile.selector", dict)
        x, y = selector.get("x"), selector.get("y")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (x, y)):
            raise ValueError("tile.selector.x and tile.selector.y must be integers")
        expected_name = str(item.get("reviewed_visible_club_name") or "").strip()
        if not expected_name:
            raise ValueError("tile.reviewed_visible_club_name is required")
        screenshot = str(item.get("screenshot") or "").strip()
        if not screenshot or Path(screenshot).is_absolute() or ".." in Path(screenshot).parts:
            raise ValueError("tile.screenshot must be a safe relative path")
        path = capture_root / screenshot
        reviewed_hash = str(item.get("reviewed_frame_sha256") or "").strip().lower()
        if len(reviewed_hash) != 64 or any(character not in "0123456789abcdef" for character in reviewed_hash):
            raise ValueError("tile.reviewed_frame_sha256 must be a lowercase SHA-256 digest")
        decoded = expected.get(record_id)
        screenshot_hash = sha256(path) if path.is_file() else None
        reason: str | None = None
        status = "accepted"
        if screenshot_hash is None:
            status, reason = "unresolved", "screenshot-missing"
        elif screenshot_hash != reviewed_hash:
            status, reason = "unresolved", "reviewed-frame-sha256-mismatch"
        elif selection_number >= route_selection_limit:
            status, reason = "unresolved", "route-selection-capacity-exhausted"
        elif screenshot_hash in seen_frame_hashes:
            status, reason = "unresolved", "repeated-frame-after-earlier-selection"
        elif decoded is None:
            status, reason = "unresolved", "eq-record-absent"
        elif normalise(decoded) != normalise(expected_name):
            status, reason = "unresolved", "decoded-eq-name-mismatch"

        verdicts.append(
            TileVerdict(
                tile_index=tile_index,
                selector={"x": x, "y": y},
                eq_record_id=record_id,
                expected_club_name=expected_name,
                decoded_club_name=decoded,
                screenshot=screenshot,
                screenshot_sha256=screenshot_hash,
                reviewed_frame_sha256=reviewed_hash,
                status=status,
                reason=reason,
            )
        )
        if screenshot_hash is not None:
            seen_frame_hashes.add(screenshot_hash)

    accepted = [row for row in verdicts if row.status == "accepted"]
    unresolved = [row for row in verdicts if row.status != "accepted"]
    return {
        "schema": REPORT_SCHEMA,
        "read_only": True,
        "capture_id": str(capture.get("capture_id") or ""),
        "country": {
            "canonical_name": country_name,
            "ui_label": ui_label,
            "flag_selector": country.get("flag_selector"),
            "meaning": "existing PM99 preseason-picker host country; not a writable competition field",
        },
        "base": {
            "dbdat": str(dbdat.resolve()),
            "eq98030_sha256": sha256(dbdat / "EQ98030.FDI"),
        },
        "counts": {"captured": len(verdicts), "accepted": len(accepted), "unresolved": len(unresolved)},
        "route_selection_limit": route_selection_limit,
        "accepted_host_mappings": [
            {
                "eq_record_id": row.eq_record_id,
                "host_country": country_name,
                "ui_label": ui_label,
                "club_short_name": row.decoded_club_name,
                "evidence": {
                    "kind": "reviewed-preseason-picker-frame",
                    "screenshot": row.screenshot,
                    "sha256": row.screenshot_sha256,
                    "tile_index": row.tile_index,
                    "selector": row.selector,
                },
            }
            for row in accepted
        ],
        "tiles": [asdict(row) for row in verdicts],
        "writer_boundary": {
            "may_do": "assign historical club content to an existing accepted carrier while preserving EQ id and order",
            "must_not_do": [
                "write a country/division/competition field",
                "reorder EQ entries",
                "infer continental draw membership",
                "treat an unresolved stale frame as a host mapping",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_capture(
            capture=load_capture(args.capture),
            dbdat=args.dbdat.resolve(),
            capture_root=args.capture_root.resolve(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
