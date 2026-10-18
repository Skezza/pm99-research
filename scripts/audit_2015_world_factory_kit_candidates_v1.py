#!/usr/bin/env python3
"""Independently reproduce and audit 2015 factory-template kit candidates."""

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
from scripts import pm99_factory_kit_renderer_v1 as factory_renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402
from scripts.rerender_2015_world_kits_factory_v1 import (  # noqa: E402
    APPROVED_STATUSES,
    FIFA_STATUS,
    RENDERER_ID,
    _reviewed_recipe,
)


SCHEMA = "pm99-2015-world-factory-kit-audit-v1"


def _records(dbdat: Path) -> dict[str, dict[int, Any]]:
    return {
        archive: {
            int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE).group(1)): record
            for record in iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=r"^EQ96\d{4}\.BMP$")
        }
        for archive in ARCHIVES
    }


def _error(errors: list[dict[str, Any]], code: str, carrier: int | None = None, archive: str | None = None) -> None:
    item: dict[str, Any] = {"code": code}
    if carrier is not None:
        item["carrier_id"] = carrier
    if archive is not None:
        item["archive"] = archive
    errors.append(item)


def _pixel_lane(record: Any, payload: bytes) -> bytes:
    start = int(record.pixel_offset)
    return payload[start : start + int(record.width) * int(record.height)]


def audit(
    *,
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    clean_dbdat: Path,
    renderer_module: Any = factory_renderer,
    renderer_id: str = RENDERER_ID,
) -> dict[str, Any]:
    """Independently reproduce a candidate using its explicit renderer.

    V1 remains the default so historic V1 receipts stay independently
    auditable.  A newer renderer must be opted into by its own entry point.
    """
    errors: list[dict[str, Any]] = []
    source_hash = sha256_bytes(canonical_json_bytes(dict(source)))
    renderer = candidate.get("renderer") if isinstance(candidate.get("renderer"), Mapping) else {}
    if renderer.get("id") != renderer_id:
        _error(errors, "wrong-renderer-id")
    if renderer.get("source_materialisation_sha256") != source_hash:
        _error(errors, "source-materialisation-hash-mismatch")
    palette, palette_info = runtime_kit_palette(clean_dbdat)
    expected_palette = {**palette_info, "sha256": sha256_file(Path(str(palette_info["path"]))) }
    if renderer.get("runtime_palette") != expected_palette or palette_info.get("resource") != "DAT.PKF":
        _error(errors, "runtime-dat-palette-provenance-mismatch")
    if "SIMUL" in json.dumps(renderer, sort_keys=True).upper():
        _error(errors, "simulator-palette-reference-present")

    source_rows = {int(row["carrier_id"]): row for row in source.get("rows") or [] if isinstance(row, Mapping)}
    candidate_rows = {int(row["carrier_id"]): row for row in candidate.get("rows") or [] if isinstance(row, Mapping)}
    if set(source_rows) != set(candidate_rows):
        _error(errors, "carrier-set-mismatch")
    records = _records(clean_dbdat)
    checked_assets = 0
    approved = 0
    for carrier, source_row in sorted(source_rows.items()):
        candidate_row = candidate_rows.get(carrier)
        if candidate_row is None:
            continue
        status = source_row.get("status")
        if status not in APPROVED_STATUSES:
            if source_row.get("assets") != candidate_row.get("assets"):
                _error(errors, "unapproved-assets-changed", carrier)
            continue
        approved += 1
        if candidate_row.get("status") != status or candidate_row.get("renderer") != renderer_id:
            _error(errors, "approved-row-provenance-mismatch", carrier)
        try:
            if status == FIFA_STATUS:
                source_image = source_row.get("source_image")
                if not isinstance(source_image, Mapping):
                    raise ValueError("missing source image")
                source_path = Path(str(source_image.get("cache_path") or ""))
                if not source_path.is_file() or sha256_file(source_path) != source_image.get("sha256"):
                    raise ValueError("source image hash mismatch")
                recipe = recipe_from_source(source_path)
            else:
                recipe = _reviewed_recipe(source_row, carrier)
        except (OSError, ValueError):
            _error(errors, "dated-recipe-source-invalid", carrier)
            continue
        if candidate_row.get("render_recipe") != recipe:
            _error(errors, "render-recipe-mismatch", carrier)
        assets = candidate_row.get("assets")
        if not isinstance(assets, Mapping):
            _error(errors, "candidate-assets-missing", carrier)
            continue
        source_assets = source_row.get("assets") if isinstance(source_row.get("assets"), Mapping) else {}
        for archive in ARCHIVES:
            asset = assets.get(archive)
            target = records[archive].get(carrier)
            if target is None or not isinstance(asset, Mapping):
                _error(errors, "candidate-asset-or-target-missing", carrier, archive)
                continue
            candidate_path = Path(str(asset.get("path") or ""))
            if not candidate_path.is_file() or sha256_file(candidate_path) != asset.get("sha256"):
                _error(errors, "candidate-asset-hash-mismatch", carrier, archive)
                continue
            payload = candidate_path.read_bytes()
            try:
                shape, original = validate_minifoto_bitmap(payload), validate_minifoto_bitmap(target.raw_bitmap)
                shape_ok = all(getattr(shape, name) == getattr(original, name) for name in ("width", "height", "bits_per_pixel", "pixel_offset", "bitmap_length"))
            except ValueError:
                shape_ok = False
            start = int(target.pixel_offset)
            end = start + int(target.width) * int(target.height)
            wrapper_ok = payload[:start] == target.raw_bitmap[:start] and payload[end:] == target.raw_bitmap[end:]
            template_carrier = renderer_module.factory_template_carrier(archive, recipe)
            template = records[archive].get(template_carrier)
            if template is None:
                _error(errors, "factory-template-missing", carrier, archive)
                continue
            expected = renderer_module.render_template_on_record(target, template, palette, recipe)
            asset_template = asset.get("factory_template") if isinstance(asset.get("factory_template"), Mapping) else {}
            template_ok = asset_template == {
                "carrier_id": template_carrier,
                "bitmap_sha256": hashlib.sha256(template.raw_bitmap).hexdigest(),
            }
            if not shape_ok:
                _error(errors, "bitmap-shape-mismatch", carrier, archive)
            if not wrapper_ok:
                _error(errors, "target-wrapper-changed", carrier, archive)
            if not template_ok:
                _error(errors, "template-provenance-mismatch", carrier, archive)
            if payload != expected:
                _error(errors, "renderer-reproduction-mismatch", carrier, archive)
            prior = source_assets.get(archive) if isinstance(source_assets, Mapping) else None
            if not isinstance(prior, Mapping) or asset.get("replaces_asset_sha256") != prior.get("sha256"):
                _error(errors, "prior-asset-provenance-mismatch", carrier, archive)
            checked_assets += 1
    result = "pass" if not errors else "fail"
    return {
        "schema_version": SCHEMA,
        "result": result,
        "renderer": renderer_id,
        "source_materialisation_sha256": source_hash,
        "candidate_materialisation_sha256": sha256_bytes(canonical_json_bytes(dict(candidate))),
        "coverage": {"approved_carrier_count": approved, "checked_asset_count": checked_assets, "error_count": len(errors)},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-materialisation", type=Path, required=True)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(
            source=json.loads(args.source_materialisation.read_text(encoding="utf-8")),
            candidate=json.loads(args.candidate_materialisation.read_text(encoding="utf-8")),
            clean_dbdat=args.clean_dbdat,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
