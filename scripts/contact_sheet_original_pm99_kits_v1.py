#!/usr/bin/env python3
"""Make a visual catalogue of unmodified PM99 compact-kit illustrations.

This is deliberately read-only.  The catalogue makes template selection a
reviewable editorial decision rather than an accidental choice of a carrier
record during kit materialisation.
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
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render(record: Any, palette: list[tuple[int, int, int]], scale: int) -> Image.Image:
    width, height, offset = int(record.width), int(record.height), int(record.pixel_offset)
    pixels = record.raw_bitmap[offset : offset + width * height]
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            index = pixels[(height - 1 - y) * width + x]
            if index:
                image.putpixel((x, y), (*palette[index], 255))
    return image.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--archive", default="MINIESC.PKF")
    parser.add_argument("--columns", type=int, default=16)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.columns < 1 or args.scale < 1:
        parser.error("--columns and --scale must be positive")
    archive_path = args.dbdat / args.archive
    try:
        palette, palette_info = runtime_kit_palette(args.dbdat)
        records = list(iter_obfuscated_bmp_records(archive_path, file_name_pattern=r"^EQ96\d{4}\.BMP$"))
        if not records:
            raise ValueError(f"no kit records in {archive_path}")
        cell_width = int(records[0].width) * args.scale + 8
        cell_height = int(records[0].height) * args.scale + 20
        rows = (len(records) + args.columns - 1) // args.columns
        sheet = Image.new("RGB", (cell_width * args.columns, cell_height * rows), (237, 237, 233))
        draw = ImageDraw.Draw(sheet)
        receipt_records = []
        for ordinal, record in enumerate(records):
            carrier = int(str(record.file_name)[4:8])
            column, row = ordinal % args.columns, ordinal // args.columns
            x0, y0 = column * cell_width, row * cell_height
            draw.rectangle((x0, y0, x0 + cell_width - 1, y0 + cell_height - 1), outline=(180, 180, 175))
            draw.text((x0 + 3, y0 + 3), f"EQ{carrier:04d}", fill=(20, 20, 20))
            visual = render(record, palette, args.scale)
            bg = Image.new("RGB", visual.size, (249, 249, 247))
            bg.paste(visual, (0, 0), visual)
            sheet.paste(bg, (x0 + (cell_width - bg.width) // 2, y0 + 16))
            receipt_records.append({"carrier_id": carrier, "bitmap_sha256": hashlib.sha256(record.raw_bitmap).hexdigest()})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.output)
        receipt = {
            "result": "catalogue-ready",
            "archive": args.archive,
            "archive_sha256": sha256_file(archive_path),
            "runtime_palette": palette_info,
            "records": receipt_records,
            "preview": str(args.output.resolve()),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(receipt["preview"])
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
