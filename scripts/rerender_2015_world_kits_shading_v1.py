#!/usr/bin/env python3
"""Re-render approved 2015 foreign kit candidates with the sprite-safe renderer.

The input is the immutable, identity-bound 2015 materialisation receipt. This
tool reads its captured source images and clean compact-kit records, then
writes a new content-addressed candidate set and receipt. It never modifies a
PM99 archive, game tree, source cache, or prior candidate set.
"""

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
from scripts.materialise_2015_world_fifaindex_kits import render_fifaindex_candidate  # noqa: E402
from scripts.materialise_2015_world_kits import (  # noqa: E402
    ARCHIVES,
    _write_content_addressed,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from scripts.supplement_2015_world_reviewed_kits import (  # noqa: E402
    REVIEWED_STATUS,
    render_geometry,
)
from scripts.pm99_kit_recipe_v1 import recipe_from_source  # noqa: E402
from scripts import pm99_compact_kit_template_v1 as compact_template  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


INPUT_SCHEMAS = {
    "pm99-world-2015-fifaindex-kit-materialisation-v1",
    "pm99-world-2015-combined-kit-materialisation-v1",
}
FIFA_STATUS = "release-eligible-fifa16-identity-bound"
APPROVED_STATUSES = {FIFA_STATUS, REVIEWED_STATUS}
RENDERER_ID = "pm99-kit-centred-shirt-runtime-palette-v4"


class KitRerenderError(ValueError):
    """A historic input or immutable source prerequisite is unsafe."""


def _records(dbdat: Path) -> dict[str, dict[int, Any]]:
    output: dict[str, dict[int, Any]] = {}
    for archive in ARCHIVES:
        path = dbdat / archive
        if not path.is_file():
            raise KitRerenderError(f"missing clean compact-kit archive: {path}")
        records: dict[int, Any] = {}
        for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
            match = re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE)
            if match:
                records[int(match.group(1))] = record
        if not records:
            raise KitRerenderError(f"{path} has no readable compact-kit records")
        output[archive] = records
    return output


def _require_hash_bound_file(value: Mapping[str, Any], path_key: str, hash_key: str, label: str) -> Path:
    path = Path(str(value.get(path_key) or ""))
    expected = str(value.get(hash_key) or "")
    if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise KitRerenderError(f"{label} lacks an existing hash-bound source")
    if sha256_file(path) != expected:
        raise KitRerenderError(f"{label} hash differs from its materialisation receipt")
    return path


def _assert_candidate_shape(record: Any, payload: bytes, label: str) -> None:
    try:
        shape = validate_minifoto_bitmap(payload)
        base_shape = validate_minifoto_bitmap(record.raw_bitmap)
    except ValueError as exc:
        raise KitRerenderError(f"{label} is not an OS/2 8-bit compact-kit bitmap") from exc
    fields = ("width", "height", "bits_per_pixel", "pixel_offset", "bitmap_length")
    if any(getattr(shape, field) != getattr(base_shape, field) for field in fields):
        raise KitRerenderError(f"{label} changes the compact-kit bitmap shape")
    pixel_end = int(record.pixel_offset) + int(record.width) * int(record.height)
    if payload[: int(record.pixel_offset)] != record.raw_bitmap[: int(record.pixel_offset)] or payload[pixel_end:] != record.raw_bitmap[pixel_end:]:
        raise KitRerenderError(f"{label} changes bytes outside the indexed-pixel lane")


def rerender(*, materialisation: Mapping[str, Any], dbdat: Path, output_dir: Path) -> dict[str, Any]:
    if materialisation.get("schema_version") not in INPUT_SCHEMAS:
        raise KitRerenderError("unsupported 2015 materialisation schema")
    records = _records(dbdat)
    try:
        palette, palette_source = runtime_kit_palette(dbdat)
    except ValueError as exc:
        raise KitRerenderError(str(exc)) from exc
    rows: list[dict[str, Any]] = []
    rerendered = 0
    for source_row in materialisation.get("rows") or []:
        if not isinstance(source_row, Mapping):
            raise KitRerenderError("materialisation rows must be objects")
        row = dict(source_row)
        status = row.get("status")
        if status not in APPROVED_STATUSES:
            rows.append(row)
            continue
        carrier = int(row.get("carrier_id") or -1)
        if carrier < 0:
            raise KitRerenderError("approved kit row has no valid carrier")
        source_path: Path | None = None
        if status == FIFA_STATUS:
            source_image = row.get("source_image")
            if not isinstance(source_image, Mapping):
                raise KitRerenderError(f"carrier {carrier} has no FIFA source image")
            source_path = _require_hash_bound_file(source_image, "cache_path", "sha256", f"carrier {carrier} FIFA source image")
            recipe = recipe_from_source(source_path)
        else:
            reviewed = row.get("reviewed_source")
            if not isinstance(reviewed, Mapping):
                raise KitRerenderError(f"carrier {carrier} has no reviewed geometry source")
        new_assets: dict[str, dict[str, Any]] = {}
        source_assets = row.get("assets")
        if not isinstance(source_assets, Mapping):
            raise KitRerenderError(f"carrier {carrier} has no prior candidate assets")
        for archive in ARCHIVES:
            record = records[archive].get(carrier)
            if record is None:
                raise KitRerenderError(f"{archive} has no carrier {carrier}")
            old_asset = source_assets.get(archive)
            if not isinstance(old_asset, Mapping):
                raise KitRerenderError(f"carrier {carrier} is missing its prior {archive} asset")
            prior_path = _require_hash_bound_file(old_asset, "path", "sha256", f"carrier {carrier} prior {archive} asset")
            if status == FIFA_STATUS:
                payload = render_fifaindex_candidate(
                    record,
                    source_path,
                    palette,
                    recipe=recipe,
                )
            else:
                reviewed = row["reviewed_source"]
                payload = render_geometry(
                    record,
                    str(reviewed.get("design") or ""),
                    list(reviewed.get("colors") or []),
                    palette,
                )
            _assert_candidate_shape(record, payload, f"carrier {carrier} {archive}")
            path, digest = _write_content_addressed(payload, output_dir / "candidate-bmps" / archive, ".bmp")
            new_assets[archive] = {
                **dict(old_asset),
                "path": str(path.resolve()),
                "sha256": digest,
                "bitmap_length": len(payload),
                "rerendered_from_sha256": sha256_file(prior_path),
                "renderer": RENDERER_ID,
            }
        row["assets"] = new_assets
        row["renderer"] = RENDERER_ID
        row["render_template"] = {"id": compact_template.TEMPLATE_ID, "policy": "centred-front-shirt-and-shorts-silhouette-per-archive"}
        if status == FIFA_STATUS:
            row["render_recipe"] = recipe
        rows.append(row)
        rerendered += 1
    result = dict(materialisation)
    result["rows"] = rows
    result["result"] = "centred-shirt foreign kit candidates; no PM99 archive or game-tree writes"
    result["renderer"] = {
        "id": RENDERER_ID,
        "policy": "replace inconsistent legacy compact-kit artwork with one fixed centred shirt-and-shorts silhouette; render an editable source-derived PM99 colour/pattern recipe without source-pixel projection",
        "source_materialisation_sha256": sha256_bytes(canonical_json_bytes(dict(materialisation))),
        "clean_kit_archives": {archive: sha256_file(dbdat / archive) for archive in ARCHIVES},
        "palette": {**palette_source, "sha256": sha256_file(Path(str(palette_source["path"])))},
        "render_template": {"id": compact_template.TEMPLATE_ID},
    }
    result["coverage"] = dict(materialisation.get("coverage") or {})
    result["coverage"]["sprite_safe_rerendered_carrier_count"] = rerendered
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
            dbdat=args.clean_dbdat,
            output_dir=args.output_dir,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KitRerenderError) as exc:
        parser.error(str(exc))
    result["renderer"]["source_materialisation_file_sha256"] = sha256_bytes(source_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"rerendered": result["coverage"]["sprite_safe_rerendered_carrier_count"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
