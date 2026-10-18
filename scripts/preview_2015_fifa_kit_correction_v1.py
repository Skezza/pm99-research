#!/usr/bin/env python3
"""Render a before/after visual receipt for one 2015 FIFA-index kit.

This is a review artefact generator only.  It never writes a PM99 archive or
candidate bitmap; it re-renders one source image in memory, proves its native
mask/container contract, and writes enlarged PNG previews plus a JSON receipt.
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

from app.minifoto_bitmap_archive import (  # noqa: E402
    iter_obfuscated_bmp_records,
    validate_minifoto_bitmap,
)
from scripts.materialise_2015_world_fifaindex_kits import render_fifaindex_candidate  # noqa: E402
from scripts import pm99_compact_kit_template_v1 as compact_template  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


SCHEMA = "pm99-2015-fifa-kit-visual-receipt-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(dbdat: Path, carrier: int, archive: str) -> Any:
    name = f"EQ96{carrier:04d}.BMP"
    for record in iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=rf"^{name}$"):
        return record
    raise ValueError(f"{archive} has no compact-kit record for carrier {carrier}")


def _indices(payload: bytes, record: Any) -> list[int]:
    start = int(record.pixel_offset)
    return list(payload[start : start + int(record.width) * int(record.height)])


def _top_down(indices: list[int], record: Any) -> list[list[int]]:
    width, height = int(record.width), int(record.height)
    return [
        indices[(height - 1 - y) * width : (height - y) * width]
        for y in range(height)
    ]


def _metrics(payload: bytes, record: Any, palette: list[tuple[int, int, int]]) -> dict[str, Any]:
    values = [index for index in _indices(payload, record) if index]
    brightness = [0.299 * palette[index][0] + 0.587 * palette[index][1] + 0.114 * palette[index][2] for index in values]
    mean = sum(brightness) / len(brightness) if brightness else 0.0
    variance = sum((value - mean) ** 2 for value in brightness) / len(brightness) if brightness else 0.0
    return {
        "visible_pixel_count": len(values),
        "unique_palette_index_count": len(set(values)),
        "luminance": {
            "min": round(min(brightness), 4) if brightness else None,
            "max": round(max(brightness), 4) if brightness else None,
            "mean": round(mean, 4),
            "standard_deviation": round(variance ** 0.5, 4),
        },
    }


def _preview(payload: bytes, record: Any, palette: list[tuple[int, int, int]], scale: int) -> Image.Image:
    rows = _top_down(_indices(payload, record), record)
    width, height = int(record.width), int(record.height)
    image = Image.new("RGB", (width, height), (236, 236, 236))
    for y, row in enumerate(rows):
        for x, index in enumerate(row):
            if index:
                image.putpixel((x, y), palette[index])
    return image.resize((width * scale, height * scale), Image.Resampling.NEAREST)


def preview(
    *,
    dbdat: Path,
    carrier: int,
    archive: str,
    source_png: Path,
    existing_candidate: Path | None,
    reference_dbdat: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    record = _record(dbdat, carrier, archive)
    palette, palette_source = runtime_kit_palette(dbdat)
    if reference_dbdat is not None:
        reference_record = _record(reference_dbdat, carrier, archive)
        if (int(reference_record.width), int(reference_record.height), int(reference_record.pixel_offset)) != (
            int(record.width), int(record.height), int(record.pixel_offset)
        ):
            raise ValueError("reference compact-kit record shape does not match the native carrier")
        before = bytes(reference_record.raw_bitmap)
        before_label = "reference carrier"
    elif existing_candidate is not None:
        before = existing_candidate.read_bytes()
        before_label = "legacy candidate"
    else:
        raise ValueError("one existing candidate or reference DBDAT is required")
    after = render_fifaindex_candidate(record, source_png, palette)
    base_indices = _indices(record.raw_bitmap, record)
    before_indices = _indices(before, record)
    after_indices = _indices(after, record)
    shape = validate_minifoto_bitmap(after)
    pixel_end = int(record.pixel_offset) + int(record.width) * int(record.height)
    checks = {
        "corrected_os2_8bit_shape": shape.bits_per_pixel == 8 and shape.width == record.width and shape.height == record.height,
        "corrected_header_unchanged": after[: int(record.pixel_offset)] == record.raw_bitmap[: int(record.pixel_offset)],
        "corrected_suffix_unchanged": after[pixel_end:] == record.raw_bitmap[pixel_end:],
        "corrected_expected_transparency_mask": [value == 0 for value in after_indices]
        == [
            value
            for y in range(int(record.height) - 1, -1, -1)
            for value in compact_template.transparency_mask(int(record.width), int(record.height))[y * int(record.width) : (y + 1) * int(record.width)]
        ],
        "corrected_replaces_legacy_candidate": after != before,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_image = _preview(record.raw_bitmap, record, palette, 6)
    before_image = _preview(before, record, palette, 6)
    after_image = _preview(after, record, palette, 6)
    label_height = 24
    contact = Image.new("RGB", (baseline_image.width + before_image.width + after_image.width, before_image.height + label_height), (236, 236, 236))
    contact.paste(baseline_image, (0, label_height))
    contact.paste(before_image, (baseline_image.width, label_height))
    contact.paste(after_image, (baseline_image.width + before_image.width, label_height))
    draw = ImageDraw.Draw(contact)
    draw.text((6, 6), "native carrier", fill=(0, 0, 0))
    draw.text((baseline_image.width + 6, 6), before_label, fill=(0, 0, 0))
    draw.text((baseline_image.width + before_image.width + 6, 6), "source-recipe candidate", fill=(0, 0, 0))
    baseline_path = output_dir / f"{carrier:04d}-{archive.removesuffix('.PKF').lower()}-native.png"
    before_path = output_dir / f"{carrier:04d}-{archive.removesuffix('.PKF').lower()}-legacy.png"
    after_path = output_dir / f"{carrier:04d}-{archive.removesuffix('.PKF').lower()}-corrected.png"
    contact_path = output_dir / f"{carrier:04d}-{archive.removesuffix('.PKF').lower()}-comparison.png"
    baseline_image.save(baseline_path)
    before_image.save(before_path)
    after_image.save(after_path)
    contact.save(contact_path)
    return {
        "schema_version": SCHEMA,
        "result": "preview-ready" if all(checks.values()) else "preview-contract-failed",
        "carrier_id": carrier,
        "archive": archive,
        "inputs": {
            "dbdat": str(dbdat.resolve()),
            "source_png": {"path": str(source_png.resolve()), "sha256": sha256_file(source_png)},
            "reference_candidate": (
                {"path": str(existing_candidate.resolve()), "sha256": sha256_file(existing_candidate)}
                if existing_candidate is not None
                else {"dbdat": str(reference_dbdat.resolve()), "sha256": sha256_file(reference_dbdat / archive)}
            ),
            "palette": {**palette_source, "sha256": sha256_file(Path(str(palette_source["path"])))},
            "render_template": compact_template.TEMPLATE_ID,
        },
        "checks": checks,
        "metrics": {"legacy": _metrics(before, record, palette), "corrected": _metrics(after, record, palette)},
        "previews": {
            "native": str(baseline_path.resolve()),
            "legacy": str(before_path.resolve()),
            "corrected": str(after_path.resolve()),
            "comparison": str(contact_path.resolve()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--carrier", type=int, required=True)
    parser.add_argument("--archive", choices=("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"), default="MINIESC.PKF")
    parser.add_argument("--source-png", type=Path, required=True)
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument("--legacy-candidate", type=Path)
    reference.add_argument("--reference-dbdat", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = preview(
        dbdat=args.dbdat,
        carrier=args.carrier,
        archive=args.archive,
        source_png=args.source_png,
        existing_candidate=args.legacy_candidate,
        reference_dbdat=args.reference_dbdat,
        output_dir=args.output_dir,
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "previews": result["previews"]}, sort_keys=True))
    return 0 if result["result"] == "preview-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
