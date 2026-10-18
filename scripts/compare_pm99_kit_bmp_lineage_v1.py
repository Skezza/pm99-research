#!/usr/bin/env python3
"""Render original, live and candidate PM99 kit BMPs with their own runtime palettes.

This is a forensic visual comparison tool.  It makes no game or archive
changes and deliberately avoids treating same-sized BMP containers as visual
equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


ARCHIVE = "MINIESC.PKF"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def records(dbdat: Path) -> dict[int, Any]:
    return {
        int(str(record.file_name)[4:8]): record
        for record in iter_obfuscated_bmp_records(dbdat / ARCHIVE, file_name_pattern=r"^EQ96\d{4}\.BMP$")
    }


def image(record: Any, palette: list[tuple[int, int, int]], scale: int = 3) -> Image.Image:
    width, height, offset = int(record.width), int(record.height), int(record.pixel_offset)
    pixels = record.raw_bitmap[offset : offset + width * height]
    output = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            index = pixels[(height - 1 - y) * width + x]
            if index:
                output.putpixel((x, y), (*palette[index], 255))
    return output.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def compare(*, entries: list[tuple[str, Path]], carriers: list[int], output: Path) -> dict[str, Any]:
    sources = []
    for label, dbdat in entries:
        palette, palette_info = runtime_kit_palette(dbdat)
        sources.append((label, dbdat, records(dbdat), palette, palette_info))
    cell_width, cell_height = 170, 232
    sheet = Image.new("RGB", (len(sources) * cell_width, len(carriers) * cell_height), (232, 232, 228))
    draw = ImageDraw.Draw(sheet)
    checks = []
    for row_index, carrier in enumerate(carriers):
        for col_index, (label, dbdat, index, palette, palette_info) in enumerate(sources):
            record = index.get(carrier)
            if record is None:
                raise ValueError(f"{label} has no {ARCHIVE} carrier {carrier}")
            shape = validate_minifoto_bitmap(record.raw_bitmap)
            x0, y0 = col_index * cell_width, row_index * cell_height
            draw.rectangle((x0, y0, x0 + cell_width - 1, y0 + cell_height - 1), outline=(170, 170, 165))
            draw.text((x0 + 6, y0 + 6), f"EQ{carrier:04d} {label}", fill=(20, 20, 20))
            rendered = image(record, palette)
            background = Image.new("RGB", rendered.size, (245, 245, 242))
            background.paste(rendered, (0, 0), rendered)
            sheet.paste(background, (x0 + (cell_width - background.width) // 2, y0 + 26))
            checks.append(
                {
                    "carrier_id": carrier,
                    "label": label,
                    "archive_sha256": sha256_file(dbdat / ARCHIVE),
                    "bitmap_sha256": hashlib.sha256(record.raw_bitmap).hexdigest(),
                    "shape": {"width": shape.width, "height": shape.height, "bits_per_pixel": shape.bits_per_pixel},
                    "runtime_palette": palette_info,
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return {"result": "comparison-ready", "archive": ARCHIVE, "entries": checks, "preview": str(output.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dbdat", type=Path, required=True)
    parser.add_argument("--live-dbdat", type=Path, required=True)
    parser.add_argument("--candidate-dbdat", type=Path, required=True)
    parser.add_argument("--carrier", action="append", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(
            entries=[("original", args.original_dbdat), ("live", args.live_dbdat), ("candidate", args.candidate_dbdat)],
            carriers=args.carrier,
            output=args.output,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    import json
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["preview"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
