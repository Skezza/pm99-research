#!/usr/bin/env python3
"""Compare two native-art-preserving 2015 kit render options without writing a game.

The original PM99 compact kit art is the visual ground truth.  This tool keeps
that carrier geometry and uses the actual runtime palette while testing either
an editable PM99 recipe or a bounded dated-source colour band.
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
from scripts import patch_english80_reference_kits_v2 as recipe_renderer  # noqa: E402
from scripts import pm99_factory_kit_renderer_v1 as factory_renderer  # noqa: E402
from scripts import pm99_kit_raster_v1 as raster  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402


ARCHIVE = "MINIESC.PKF"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(dbdat: Path, carrier: int) -> Any:
    wanted = f"EQ96{carrier:04d}.BMP"
    for row in iter_obfuscated_bmp_records(dbdat / ARCHIVE, file_name_pattern=rf"^{wanted}$"):
        return row
    raise ValueError(f"{ARCHIVE} has no carrier {carrier}")


def native_recipe(record: Any, palette: list[tuple[int, int, int]], recipe: dict[str, Any]) -> bytes:
    rows = recipe_renderer.record_to_top_down_indices(record)
    mapper = recipe_renderer.PaletteMapper(palette)
    return recipe_renderer.top_down_indices_to_raw(
        record, recipe_renderer.build_updated_kit_rows(rows, palette, mapper, recipe)
    )


def source_band(record: Any, palette: list[tuple[int, int, int]], source_path: Path) -> bytes:
    with Image.open(source_path) as opened:
        source = opened.convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("source kit has no opaque pixels")
    width, height = int(record.width), int(record.height)
    shirt_top, shirt_bottom = int(height * 0.22), int(height * 0.60)
    source = source.crop(bbox).resize((width, shirt_bottom - shirt_top), Image.Resampling.LANCZOS)

    def colour_at(x: int, y: int) -> tuple[int, int, int] | None:
        if not shirt_top <= y < shirt_bottom:
            return None
        red, green, blue, alpha = source.getpixel((x, y - shirt_top))
        return (int(red), int(green), int(blue)) if alpha >= 64 else None

    return raster.rasterize_preserving_native_shading(record, palette, colour_at)


def source_shirt_and_shorts(
    record: Any, palette: list[tuple[int, int, int]], source_path: Path, recipe: dict[str, Any]
) -> bytes:
    """Project the complete shirt only over PM99's native shirt area.

    This is deliberately a diagnostic option.  It keeps the original game's
    artist-drawn shirt/shorts layout and tests whether a full shirt range,
    rather than the rejected central band, retains the native visual language.
    """
    with Image.open(source_path) as opened:
        source = opened.convert("RGBA")
    bbox = source.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("source kit has no opaque pixels")
    width, height = int(record.width), int(record.height)
    shirt_top, shirt_bottom = int(height * 0.04), int(height * 0.62)
    source = source.crop(bbox).resize((width, shirt_bottom - shirt_top), Image.Resampling.LANCZOS)
    shorts_rgb = tuple(int(value) for value in recipe["shorts"])
    body_fallback = tuple(int(value) for value in recipe["colors"][0])

    def colour_at(x: int, y: int) -> tuple[int, int, int] | None:
        if shirt_top <= y < shirt_bottom:
            red, green, blue, alpha = source.getpixel((x, y - shirt_top))
            return (int(red), int(green), int(blue)) if alpha >= 64 else body_fallback
        if shirt_bottom <= y <= int(height * 0.92):
            return shorts_rgb
        return None

    return raster.rasterize_preserving_native_shading(record, palette, colour_at)


def preview_image(payload: bytes, record: Any, palette: list[tuple[int, int, int]], scale: int = 5) -> Image.Image:
    width, height, offset = int(record.width), int(record.height), int(record.pixel_offset)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = payload[offset : offset + width * height]
    for y in range(height):
        for x in range(width):
            index = pixels[(height - 1 - y) * width + x]
            if index:
                image.putpixel((x, y), (*palette[index], 255))
    return image.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--carrier", type=int, required=True)
    parser.add_argument("--native-template-carrier", type=int, default=4, help="original-game kit image used only for the visual template trial")
    parser.add_argument("--source-png", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        source_record = record(args.dbdat, args.carrier)
        template_record = record(args.dbdat, args.native_template_carrier)
        palette, palette_info = runtime_kit_palette(args.dbdat)
        recipe = recipe_from_source(args.source_png)
        payloads = [
            ("original game artwork", source_record.raw_bitmap),
            ("native artwork + V4 recipe colours", native_recipe(source_record, palette, recipe)),
            ("native artwork + dated source band", source_band(source_record, palette, args.source_png)),
            ("native artwork + full source shirt", source_shirt_and_shorts(source_record, palette, args.source_png, recipe)),
            (
                f"original EQ{args.native_template_carrier:04d} template + full source shirt",
                source_shirt_and_shorts(template_record, palette, args.source_png, recipe),
            ),
            (
                f"original EQ{args.native_template_carrier:04d} template + PM99 recipe",
                native_recipe(template_record, palette, recipe),
            ),
            (
                f"original EQ{args.native_template_carrier:04d} factory template + protected line work",
                factory_renderer.render_record(template_record, palette, recipe),
            ),
        ]
        rendered = [preview_image(payload, source_record, palette) for _label, payload in payloads]
        label_height = 26
        sheet = Image.new("RGB", (sum(image.width for image in rendered), rendered[0].height + label_height), (236, 236, 232))
        draw = ImageDraw.Draw(sheet)
        x = 0
        rows = []
        for (label, payload), image in zip(payloads, rendered):
            background = Image.new("RGB", image.size, (245, 245, 242))
            background.paste(image, (0, 0), image)
            sheet.paste(background, (x, label_height))
            draw.text((x + 5, 6), label, fill=(20, 20, 20))
            rows.append({"label": label, "sha256": hashlib.sha256(payload).hexdigest()})
            x += image.width
        args.output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.output)
        result = {
            "result": "review-ready",
            "carrier_id": args.carrier,
            "archive": ARCHIVE,
            "source_png": {"path": str(args.source_png.resolve()), "sha256": sha256_file(args.source_png)},
            "runtime_palette": {**palette_info, "sha256": sha256_file(Path(str(palette_info["path"])))},
            "recipe": recipe,
            "outputs": rows,
            "preview": str(args.output.resolve()),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        import json
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(result["preview"])
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
