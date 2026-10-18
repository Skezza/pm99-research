#!/usr/bin/env python3
"""Create a visual receipt comparing legacy and canonical 2015 foreign kits.

This is a read-only reviewer.  It verifies content-addressed candidate assets,
then renders representative MINIESC records at an enlarged nearest-neighbour
scale.  It never changes an archive or a game workspace.
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

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


ARCHIVE = "MINIESC.PKF"
DEFAULT_CLUBS = ("Barcelona", "Real Madrid", "Juventus", "Bayern Munich", "Ajax", "Galatasaray")
SCHEMA = "pm99-2015-world-kit-visual-receipt-v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(dbdat: Path) -> dict[int, Any]:
    result: dict[int, Any] = {}
    for record in iter_obfuscated_bmp_records(dbdat / ARCHIVE, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
        result[int(str(record.file_name)[4:8])] = record
    return result


def _image(payload: bytes, record: Any, palette: list[tuple[int, int, int]], scale: int) -> Image.Image:
    width, height, offset = int(record.width), int(record.height), int(record.pixel_offset)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = payload[offset : offset + width * height]
    for y in range(height):
        source_y = height - 1 - y
        for x in range(width):
            index = pixels[source_y * width + x]
            if index:
                image.putpixel((x, y), (*palette[index], 255))
    return image.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def _row_by_name(document: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    matches = [row for row in document.get("rows") or [] if isinstance(row, Mapping) and row.get("source_club_name") == name]
    if len(matches) != 1:
        raise ValueError(f"expected one materialisation row for {name!r}, found {len(matches)}")
    return matches[0]


def _asset(row: Mapping[str, Any], label: str) -> tuple[Path, str]:
    assets = row.get("assets")
    if not isinstance(assets, Mapping) or not isinstance(assets.get(ARCHIVE), Mapping):
        raise ValueError(f"{label} has no {ARCHIVE} asset")
    asset = assets[ARCHIVE]
    path, digest = Path(str(asset.get("path") or "")), str(asset.get("sha256") or "")
    if not path.is_file() or sha256_file(path) != digest:
        raise ValueError(f"{label} {ARCHIVE} asset is missing or hash-mismatched")
    return path, digest


def preview(
    *, source: Mapping[str, Any], candidate: Mapping[str, Any], dbdat: Path, clubs: tuple[str, ...], output: Path
) -> dict[str, Any]:
    palette, palette_source = runtime_kit_palette(dbdat)
    records = _records(dbdat)
    scale, columns, cell_width, cell_height = 3, 3, 312, 252
    rows = (len(clubs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), (232, 232, 228))
    draw = ImageDraw.Draw(sheet)
    receipt_rows = []
    for ordinal, name in enumerate(clubs):
        old_row, new_row = _row_by_name(source, name), _row_by_name(candidate, name)
        carrier = int(new_row["carrier_id"])
        if carrier not in records:
            raise ValueError(f"clean DBDAT has no carrier {carrier} for {name}")
        if int(old_row["carrier_id"]) != carrier:
            raise ValueError(f"legacy/candidate carrier mismatch for {name}")
        old_path, old_hash = _asset(old_row, f"legacy {name}")
        new_path, new_hash = _asset(new_row, f"candidate {name}")
        record = records[carrier]
        old_payload, new_payload = old_path.read_bytes(), new_path.read_bytes()
        for payload, label in ((old_payload, "legacy"), (new_payload, "candidate")):
            shape = validate_minifoto_bitmap(payload)
            if (shape.width, shape.height, shape.bits_per_pixel) != (record.width, record.height, 8):
                raise ValueError(f"{label} {name} has a compact-kit shape mismatch")
        col, row = ordinal % columns, ordinal // columns
        x0, y0 = col * cell_width, row * cell_height
        draw.rectangle((x0, y0, x0 + cell_width - 1, y0 + cell_height - 1), outline=(170, 170, 165))
        draw.text((x0 + 8, y0 + 7), f"EQ{carrier:04d}  {name}", fill=(20, 20, 20))
        recipe = new_row.get("render_recipe") if isinstance(new_row.get("render_recipe"), Mapping) else {}
        draw.text((x0 + 8, y0 + 22), f"{recipe.get('pattern', 'reviewed')}  legacy → runtime-palette V4", fill=(50, 50, 50))
        old_image, new_image = _image(old_payload, record, palette, scale), _image(new_payload, record, palette, scale)
        bg_old, bg_new = Image.new("RGB", old_image.size, (245, 245, 242)), Image.new("RGB", new_image.size, (245, 245, 242))
        bg_old.paste(old_image, (0, 0), old_image)
        bg_new.paste(new_image, (0, 0), new_image)
        sheet.paste(bg_old, (x0 + 10, y0 + 44))
        sheet.paste(bg_new, (x0 + 158, y0 + 44))
        draw.text((x0 + 10, y0 + 238), "legacy texture", fill=(60, 60, 60))
        draw.text((x0 + 158, y0 + 238), "runtime recipe", fill=(60, 60, 60))
        receipt_rows.append(
            {
                "club": name,
                "carrier_id": carrier,
                "recipe": recipe,
                "legacy_sha256": old_hash,
                "candidate_sha256": new_hash,
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return {
        "schema_version": SCHEMA,
        "result": "review-ready",
        "archive": ARCHIVE,
        "clubs": receipt_rows,
        "palette": {**palette_source, "sha256": sha256_file(Path(str(palette_source["path"])))},
        "preview": str(output.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-materialisation", type=Path, required=True)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--club", action="append", dest="clubs", help="exact source club name; repeat for a custom review set")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = preview(
            source=json.loads(args.source_materialisation.read_text(encoding="utf-8")),
            candidate=json.loads(args.candidate_materialisation.read_text(encoding="utf-8")),
            dbdat=args.clean_dbdat,
            clubs=tuple(args.clubs or DEFAULT_CLUBS),
            output=args.output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "preview": result["preview"], "club_count": len(result["clubs"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
