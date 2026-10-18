#!/usr/bin/env python3
"""Create factory-template 2015 kit candidates without touching a game tree.

The immutable 2015 materialisation supplies dated kit sources.  This command
turns those sources into small colour/pattern recipes, then renders them using
reviewed, unmodified PM99 illustrations.  It writes only a fresh
content-addressed candidate set and a provenance receipt.
"""

from __future__ import annotations

import argparse
import collections
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
from scripts.materialise_2015_world_kits import ARCHIVES, _write_content_addressed, canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from scripts import pm99_factory_kit_renderer_v1 as factory_renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402


INPUT_SCHEMA = "pm99-world-2015-combined-kit-materialisation-v1"
FIFA_STATUS = "release-eligible-fifa16-identity-bound"
REVIEWED_STATUS = "release-eligible-reviewed-2015-geometry"
APPROVED_STATUSES = {FIFA_STATUS, REVIEWED_STATUS}
RENDERER_ID = factory_renderer.RENDERER_ID


class FactoryRerenderError(ValueError):
    """The source receipt or clean template package is unsafe to use."""


def _records(dbdat: Path) -> dict[str, dict[int, Any]]:
    result: dict[str, dict[int, Any]] = {}
    for archive in ARCHIVES:
        records: dict[int, Any] = {}
        for record in iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
            match = re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE)
            if match:
                records[int(match.group(1))] = record
        if not records:
            raise FactoryRerenderError(f"clean kit archive is unreadable: {dbdat / archive}")
        result[archive] = records
    return result


def _hash_bound_source(row: Mapping[str, Any], carrier: int) -> Path:
    image = row.get("source_image")
    if not isinstance(image, Mapping):
        raise FactoryRerenderError(f"carrier {carrier} has no FIFA source image")
    path = Path(str(image.get("cache_path") or ""))
    expected = str(image.get("sha256") or "")
    if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise FactoryRerenderError(f"carrier {carrier} FIFA source image is not hash-bound")
    if sha256_file(path) != expected:
        raise FactoryRerenderError(f"carrier {carrier} FIFA source image hash has changed")
    return path


def _rgb(value: str) -> list[int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise FactoryRerenderError(f"invalid reviewed kit colour: {value!r}")
    return [int(value[offset : offset + 2], 16) for offset in (1, 3, 5)]


def _reviewed_recipe(row: Mapping[str, Any], carrier: int) -> dict[str, Any]:
    reviewed = row.get("reviewed_source")
    if not isinstance(reviewed, Mapping):
        raise FactoryRerenderError(f"reviewed carrier {carrier} has no reviewed source")
    pattern_by_design = {
        "plain": "solid",
        "stripes": "vertical_stripes",
        "half-and-half": "halves",
        "contrasting-sleeves": "sleeves",
        "hoops": "hoops",
    }
    design = str(reviewed.get("design") or "")
    pattern = pattern_by_design.get(design)
    colours = [_rgb(str(value)) for value in list(reviewed.get("colors") or [])]
    if pattern is None or len(colours) < 2:
        raise FactoryRerenderError(f"reviewed carrier {carrier} has unsupported geometry {design!r}")
    result: dict[str, Any] = {
        "renderer": "reviewed-geometry-recipe-v1",
        "pattern": pattern,
        "colors": colours,
        "shorts": colours[0],
        "trim": None,
    }
    if pattern == "sleeves":
        result["sleeves"] = colours[1]
    if pattern == "vertical_stripes":
        result["stripe_count"] = 6
    if pattern == "hoops":
        result["band_count"] = 6
    return result


def _assert_target_wrapper(target: Any, payload: bytes, label: str) -> None:
    try:
        shape = validate_minifoto_bitmap(payload)
        original = validate_minifoto_bitmap(target.raw_bitmap)
    except ValueError as exc:
        raise FactoryRerenderError(f"{label} is not a valid compact bitmap") from exc
    fields = ("width", "height", "bits_per_pixel", "pixel_offset", "bitmap_length")
    if any(getattr(shape, field) != getattr(original, field) for field in fields):
        raise FactoryRerenderError(f"{label} changes compact bitmap shape")
    start = int(target.pixel_offset)
    end = start + int(target.width) * int(target.height)
    if payload[:start] != target.raw_bitmap[:start] or payload[end:] != target.raw_bitmap[end:]:
        raise FactoryRerenderError(f"{label} changes target bytes outside indexed pixels")


def rerender(
    *,
    materialisation: Mapping[str, Any],
    clean_dbdat: Path,
    output_dir: Path,
    renderer_module: Any = factory_renderer,
) -> dict[str, Any]:
    """Re-render candidates with an explicitly versioned factory renderer.

    The default deliberately remains V1.  Later visual renderer revisions
    pass their module explicitly, which keeps every prior candidate receipt
    reproducible instead of silently changing an old release.
    """
    if materialisation.get("schema_version") != INPUT_SCHEMA:
        raise FactoryRerenderError("unsupported 2015 materialisation schema")
    renderer_id = str(getattr(renderer_module, "RENDERER_ID", ""))
    if not renderer_id:
        raise FactoryRerenderError("factory renderer has no stable identifier")
    records = _records(clean_dbdat)
    try:
        palette, palette_info = runtime_kit_palette(clean_dbdat)
    except ValueError as exc:
        raise FactoryRerenderError(str(exc)) from exc
    if palette_info.get("resource") != "DAT.PKF":
        raise FactoryRerenderError("factory kit renderer requires the runtime DAT.PKF palette")

    rows: list[dict[str, Any]] = []
    rendered = 0
    for source_row in materialisation.get("rows") or []:
        if not isinstance(source_row, Mapping):
            raise FactoryRerenderError("materialisation rows must be objects")
        row = dict(source_row)
        status = str(row.get("status") or "")
        if status not in APPROVED_STATUSES:
            rows.append(row)
            continue
        carrier = int(row.get("carrier_id") or -1)
        if carrier < 0:
            raise FactoryRerenderError("approved kit row has no carrier")
        if status == FIFA_STATUS:
            source_path = _hash_bound_source(row, carrier)
            recipe = recipe_from_source(source_path)
        else:
            recipe = _reviewed_recipe(row, carrier)
        prior_assets = row.get("assets")
        if not isinstance(prior_assets, Mapping):
            raise FactoryRerenderError(f"approved carrier {carrier} has no previous assets")
        assets: dict[str, Any] = {}
        for archive in ARCHIVES:
            target = records[archive].get(carrier)
            if target is None:
                raise FactoryRerenderError(f"{archive} has no target carrier {carrier}")
            template_carrier = renderer_module.factory_template_carrier(archive, recipe)
            template = records[archive].get(template_carrier)
            if template is None:
                raise FactoryRerenderError(f"{archive} has no factory template {template_carrier}")
            payload = renderer_module.render_template_on_record(target, template, palette, recipe)
            _assert_target_wrapper(target, payload, f"carrier {carrier} {archive}")
            path, digest = _write_content_addressed(payload, output_dir / "candidate-bmps" / archive, ".bmp")
            prior_asset = prior_assets.get(archive)
            if not isinstance(prior_asset, Mapping) or not re.fullmatch(r"[0-9a-f]{64}", str(prior_asset.get("sha256") or "")):
                raise FactoryRerenderError(f"carrier {carrier} prior {archive} asset has no receipt hash")
            assets[archive] = {
                "path": str(path.resolve()),
                "sha256": digest,
                "bitmap_length": len(payload),
                "file_name": str(target.file_name),
                "renderer": renderer_id,
                "replaces_asset_sha256": str(prior_asset["sha256"]),
                "target_base_bitmap_sha256": hashlib.sha256(target.raw_bitmap).hexdigest(),
                "factory_template": {
                    "carrier_id": template_carrier,
                    "bitmap_sha256": hashlib.sha256(template.raw_bitmap).hexdigest(),
                },
            }
        row["assets"] = assets
        row["renderer"] = renderer_id
        row["render_recipe"] = recipe
        row["render_template"] = {
            "id": renderer_id,
            "policy": "reviewed original PM99 compact-kit artwork; only indexed pixels are redrawn from a dated recipe",
        }
        rows.append(row)
        rendered += 1
    result = dict(materialisation)
    result["rows"] = rows
    result["result"] = "factory-template foreign kit candidates; no PM99 archive or game-tree writes"
    result["renderer"] = {
        "id": renderer_id,
        "policy": "dated recipe rendered through reviewed original PM99 kit artwork; target wrappers and runtime DAT.PKF palette are retained",
        "source_materialisation_sha256": sha256_bytes(canonical_json_bytes(dict(materialisation))),
        "clean_kit_archives": {archive: sha256_file(clean_dbdat / archive) for archive in ARCHIVES},
        "runtime_palette": {**palette_info, "sha256": sha256_file(Path(str(palette_info["path"])))},
        "template_policy": renderer_module.FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN,
    }
    result["coverage"] = dict(materialisation.get("coverage") or {})
    result["coverage"]["factory_template_rerendered_carrier_count"] = rendered
    result["coverage"]["factory_template_rerendered_asset_count"] = rendered * len(ARCHIVES)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        source_bytes = args.materialisation.read_bytes()
        result = rerender(
            materialisation=json.loads(source_bytes),
            clean_dbdat=args.clean_dbdat,
            output_dir=args.output_dir,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FactoryRerenderError) as exc:
        parser.error(str(exc))
        return 2
    result["renderer"]["source_materialisation_file_sha256"] = sha256_bytes(source_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"rerendered": result["coverage"]["factory_template_rerendered_carrier_count"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
