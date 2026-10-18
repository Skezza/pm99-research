#!/usr/bin/env python3
"""Read-only validation for the versioned sprite-safe 2015 kit candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from scripts.materialise_2015_world_kits import ARCHIVES, canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from scripts.rerender_2015_world_kits_shading_v1 import (  # noqa: E402
    APPROVED_STATUSES,
    RENDERER_ID,
)
from scripts import pm99_compact_kit_template_v1 as compact_template  # noqa: E402


SCHEMA = "pm99-2015-world-kit-rerender-audit-v1"


def _records(dbdat: Path) -> dict[str, dict[int, Any]]:
    return {
        archive: {
            int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE).group(1)): record
            for record in iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=r"^EQ96\d{4}\.BMP$")
        }
        for archive in ARCHIVES
    }


def _fail(errors: list[dict[str, Any]], code: str, carrier: int | None = None, archive: str | None = None) -> None:
    errors.append({key: value for key, value in {"code": code, "carrier_id": carrier, "archive": archive}.items() if value is not None})


def audit(*, source: Mapping[str, Any], rerendered: Mapping[str, Any], dbdat: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    expected_source_sha = sha256_bytes(canonical_json_bytes(dict(source)))
    renderer = rerendered.get("renderer") if isinstance(rerendered.get("renderer"), Mapping) else {}
    if renderer.get("id") != RENDERER_ID:
        _fail(errors, "wrong-renderer-id")
    if renderer.get("source_materialisation_sha256") != expected_source_sha:
        _fail(errors, "source-materialisation-hash-mismatch")
    source_rows = {int(row["carrier_id"]): row for row in source.get("rows") or [] if isinstance(row, Mapping)}
    revised_rows = {int(row["carrier_id"]): row for row in rerendered.get("rows") or [] if isinstance(row, Mapping)}
    if set(source_rows) != set(revised_rows):
        _fail(errors, "carrier-set-mismatch")
    records = _records(dbdat)
    approved = 0
    checked_assets = 0
    for carrier, old_row in sorted(source_rows.items()):
        new_row = revised_rows.get(carrier)
        if new_row is None:
            continue
        status = old_row.get("status")
        if status not in APPROVED_STATUSES:
            if old_row.get("assets") != new_row.get("assets"):
                _fail(errors, "unapproved-row-changed", carrier)
            continue
        approved += 1
        if new_row.get("status") != status or new_row.get("renderer") != RENDERER_ID:
            _fail(errors, "approved-row-provenance-mismatch", carrier)
        if status == "release-eligible-fifa16-identity-bound":
            source_image = old_row.get("source_image") if isinstance(old_row.get("source_image"), Mapping) else {}
            path = Path(str(source_image.get("cache_path") or ""))
            if not path.is_file() or sha256_file(path) != source_image.get("sha256"):
                _fail(errors, "fifa-source-image-hash-mismatch", carrier)
        for archive in ARCHIVES:
            old_asset = (old_row.get("assets") or {}).get(archive) if isinstance(old_row.get("assets"), Mapping) else None
            new_asset = (new_row.get("assets") or {}).get(archive) if isinstance(new_row.get("assets"), Mapping) else None
            if not isinstance(old_asset, Mapping) or not isinstance(new_asset, Mapping):
                _fail(errors, "missing-asset", carrier, archive)
                continue
            path = Path(str(new_asset.get("path") or ""))
            if not path.is_file() or sha256_file(path) != new_asset.get("sha256"):
                _fail(errors, "rerendered-asset-hash-mismatch", carrier, archive)
                continue
            if new_asset.get("rerendered_from_sha256") != old_asset.get("sha256") or new_asset.get("renderer") != RENDERER_ID:
                _fail(errors, "asset-provenance-mismatch", carrier, archive)
            record = records.get(archive, {}).get(carrier)
            if record is None:
                _fail(errors, "base-record-missing", carrier, archive)
                continue
            payload = path.read_bytes()
            try:
                shape, base_shape = validate_minifoto_bitmap(payload), validate_minifoto_bitmap(record.raw_bitmap)
                shape_ok = all(getattr(shape, field) == getattr(base_shape, field) for field in ("width", "height", "bits_per_pixel", "pixel_offset", "bitmap_length"))
            except ValueError:
                shape_ok = False
            pixel_end = int(record.pixel_offset) + int(record.width) * int(record.height)
            bytes_ok = payload[: int(record.pixel_offset)] == record.raw_bitmap[: int(record.pixel_offset)] and payload[pixel_end:] == record.raw_bitmap[pixel_end:]
            expected_top_down = compact_template.transparency_mask(int(record.width), int(record.height))
            expected_raw = []
            for y in range(int(record.height) - 1, -1, -1):
                expected_raw.extend(expected_top_down[y * int(record.width) : (y + 1) * int(record.width)])
            mask_ok = [value == 0 for value in payload[int(record.pixel_offset) : pixel_end]] == expected_raw
            if not shape_ok:
                _fail(errors, "bitmap-shape-mismatch", carrier, archive)
            if not bytes_ok:
                _fail(errors, "nonpixel-byte-changed", carrier, archive)
            if not mask_ok:
                _fail(errors, "centred-template-transparency-mask-mismatch", carrier, archive)
            checked_assets += 1
    result = "pass" if not errors else "fail"
    return {
        "schema_version": SCHEMA,
        "result": result,
        "source_materialisation_sha256": expected_source_sha,
        "rerendered_materialisation_sha256": sha256_bytes(canonical_json_bytes(dict(rerendered))),
        "renderer": RENDERER_ID,
        "coverage": {"approved_carrier_count": approved, "checked_asset_count": checked_assets, "error_count": len(errors)},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-materialisation", type=Path, required=True)
    parser.add_argument("--rerendered-materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source_materialisation.read_text(encoding="utf-8"))
    rerendered = json.loads(args.rerendered_materialisation.read_text(encoding="utf-8"))
    result = audit(source=source, rerendered=rerendered, dbdat=args.clean_dbdat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
