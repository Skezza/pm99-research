#!/usr/bin/env python3
"""Make a visual acceptance sheet from factory-kit candidate assets.

The sheet is a read-only QA artifact.  It renders each indexed BMP with the
actual PM99 DAT.PKF palette, so it catches the exact palette mismatch that an
ordinary external BMP viewer cannot see.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import validate_minifoto_bitmap  # noqa: E402
from scripts.materialise_2015_world_kits import canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts.rerender_2015_world_kits_factory_v1 import APPROVED_STATUSES, RENDERER_ID  # noqa: E402


def render(payload: bytes, palette: list[tuple[int, int, int]], scale: int) -> Image.Image:
    shape = validate_minifoto_bitmap(payload)
    width, height, offset = int(shape.width), int(shape.height), int(shape.pixel_offset)
    pixels = payload[offset : offset + width * height]
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            index = pixels[(height - 1 - y) * width + x]
            if index:
                image.putpixel((x, y), (*palette[index], 255))
    return image.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--runtime-dbdat", type=Path, required=True)
    parser.add_argument("--archive", required=True, choices=("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"))
    parser.add_argument(
        "--renderer-id",
        default=RENDERER_ID,
        help="expected explicitly versioned factory renderer (defaults to V1)",
    )
    parser.add_argument("--columns", type=int, default=12)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.columns < 1 or args.scale < 1:
        parser.error("--columns and --scale must be positive")
    try:
        source_bytes = args.candidate_materialisation.read_bytes()
        materialisation = json.loads(source_bytes)
        renderer = materialisation.get("renderer") if isinstance(materialisation.get("renderer"), Mapping) else {}
        if renderer.get("id") != args.renderer_id:
            raise ValueError("candidate materialisation does not use the factory renderer")
        palette, palette_info = runtime_kit_palette(args.runtime_dbdat)
        rows = []
        for row in materialisation.get("rows") or []:
            if not isinstance(row, Mapping) or row.get("status") not in APPROVED_STATUSES:
                continue
            asset = row.get("assets", {}).get(args.archive) if isinstance(row.get("assets"), Mapping) else None
            if not isinstance(asset, Mapping):
                raise ValueError(f"carrier {row.get('carrier_id')} lacks {args.archive}")
            path = Path(str(asset.get("path") or ""))
            if not path.is_file() or sha256_file(path) != asset.get("sha256"):
                raise ValueError(f"candidate asset is missing or altered: {path}")
            recipe = row.get("render_recipe") if isinstance(row.get("render_recipe"), Mapping) else {}
            rows.append((str(recipe.get("pattern") or "unknown"), str(row.get("source_club_name") or "unknown"), int(row["carrier_id"]), path, dict(asset)))
        if not rows:
            raise ValueError("no approved factory-kit assets")
        rows.sort(key=lambda item: (item[0], item[1].casefold(), item[2]))
        first_shape = validate_minifoto_bitmap(rows[0][3].read_bytes())
        cell_width = int(first_shape.width) * args.scale + 14
        cell_height = int(first_shape.height) * args.scale + 31
        row_count = (len(rows) + args.columns - 1) // args.columns
        sheet = Image.new("RGB", (cell_width * args.columns, cell_height * row_count), (237, 237, 233))
        draw = ImageDraw.Draw(sheet)
        receipt_rows = []
        for position, (pattern, club, carrier, path, asset) in enumerate(rows):
            column, row_index = position % args.columns, position // args.columns
            x0, y0 = column * cell_width, row_index * cell_height
            draw.rectangle((x0, y0, x0 + cell_width - 1, y0 + cell_height - 1), outline=(178, 178, 174))
            draw.text((x0 + 3, y0 + 2), f"{carrier} {pattern[:9]}", fill=(25, 25, 25))
            payload = path.read_bytes()
            visual = render(payload, palette, args.scale)
            background = Image.new("RGB", visual.size, (249, 249, 247))
            background.paste(visual, (0, 0), visual)
            sheet.paste(background, (x0 + (cell_width - background.width) // 2, y0 + 17))
            receipt_rows.append({"carrier_id": carrier, "club": club, "pattern": pattern, "asset_sha256": asset["sha256"]})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.output)
        receipt = {
            "result": "visual-qa-ready",
            "renderer": args.renderer_id,
            "candidate_materialisation_sha256": sha256_bytes(canonical_json_bytes(materialisation)),
            "candidate_materialisation_file_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "archive": args.archive,
            "runtime_palette": {**palette_info, "sha256": sha256_file(Path(str(palette_info["path"])))},
            "asset_count": len(receipt_rows),
            "rows": receipt_rows,
            "preview": str(args.output.resolve()),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(receipt["preview"])
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, KeyError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
