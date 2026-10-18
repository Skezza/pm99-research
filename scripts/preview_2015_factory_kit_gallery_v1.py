#!/usr/bin/env python3
"""Render a varied, reviewable gallery with the PM99 factory-kit candidate.

No game data is written.  Each panel uses the same clean original PM99
template so reviewers can assess the renderer rather than a carrier's
accidental old art.  The dated home-kit PNG is reduced to its stored recipe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402
from scripts import pm99_factory_kit_renderer_v1 as factory_renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402


DEFAULT_CLUBS = ("Barcelona", "Athletic Bilbao", "Villarreal", "Real Madrid", "Valencia", "Arsenal")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_record(dbdat: Path, archive: str, carrier: int) -> Any:
    rows = iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
    if len(rows) != 1:
        raise ValueError(f"expected one {archive} factory template {carrier}, got {len(rows)}")
    return rows[0]


def image(raw: bytes, record: Any, palette: list[tuple[int, int, int]], scale: int = 4) -> Image.Image:
    width, height, offset = int(record.width), int(record.height), int(record.pixel_offset)
    pixels = raw[offset : offset + width * height]
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            index = pixels[(height - 1 - y) * width + x]
            if index:
                result.putpixel((x, y), (*palette[index], 255))
    return result.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--materialisation", type=Path, required=True)
    parser.add_argument("--archive", default="MINIESC.PKF", choices=("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"))
    parser.add_argument("--club", action="append", default=[])
    parser.add_argument(
        "--template-carrier",
        type=int,
        help="override the reviewed per-archive/per-pattern factory template",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    requested = tuple(args.club) if args.club else DEFAULT_CLUBS
    try:
        manifest = json.loads(args.materialisation.read_text(encoding="utf-8"))
        by_club = {
            str(row.get("source_club_name")): row
            for row in manifest.get("rows", [])
            if row.get("action") == "write-candidate-only" and row.get("source_club_name")
        }
        missing = [club for club in requested if club not in by_club]
        if missing:
            raise ValueError(f"requested clubs absent from materialisation: {missing}")
        palette, palette_info = runtime_kit_palette(args.dbdat)
        panel_width, panel_height, label_height = 230, 330, 70
        sheet = Image.new("RGB", (panel_width * len(requested), panel_height), (235, 235, 232))
        draw = ImageDraw.Draw(sheet)
        receipt_rows = []
        for column, club in enumerate(requested):
            row = by_club[club]
            source_path = Path(str(row["source_image"]["cache_path"]))
            recipe = recipe_from_source(source_path)
            template_carrier = args.template_carrier or factory_renderer.factory_template_carrier(args.archive, recipe)
            template = get_record(args.dbdat, args.archive, template_carrier)
            raw = factory_renderer.render_record(template, palette, recipe)
            visual = image(raw, template, palette)
            x0 = column * panel_width
            draw.rectangle((x0, 0, x0 + panel_width - 1, panel_height - 1), outline=(170, 170, 165))
            draw.text((x0 + 7, 7), club, fill=(15, 15, 15))
            draw.text((x0 + 7, 23), f"{recipe['pattern']}: {recipe['colors']}", fill=(35, 35, 35))
            draw.text((x0 + 7, 39), f"shorts: {recipe['shorts']}", fill=(35, 35, 35))
            background = Image.new("RGB", visual.size, (248, 248, 246))
            background.paste(visual, (0, 0), visual)
            sheet.paste(background, (x0 + (panel_width - background.width) // 2, label_height))
            receipt_rows.append(
                {
                    "source_club_name": club,
                    "carrier_id": int(row["carrier_id"]),
                    "source_png": str(source_path.resolve()),
                    "source_png_sha256": file_sha256(source_path),
                    "recipe": recipe,
                    "factory_template_carrier": template_carrier,
                    "factory_template_bitmap_sha256": hashlib.sha256(template.raw_bitmap).hexdigest(),
                    "bitmap_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.output)
        receipt = {
            "result": "review-ready",
            "renderer": factory_renderer.RENDERER_ID,
            "factory_template_policy": {
                "archive": args.archive,
                "override_carrier_id": args.template_carrier,
                "selection": "explicit override or reviewed per-archive/per-pattern mapping",
            },
            "runtime_palette": palette_info,
            "rows": receipt_rows,
            "preview": str(args.output.resolve()),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(receipt["preview"])
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
