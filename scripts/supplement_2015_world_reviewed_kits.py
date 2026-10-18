#!/usr/bin/env python3
"""Supplement FIFA-absent clubs with reviewed dated kit geometry."""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402
from scripts.materialise_2015_world_fifaindex_kits import identity_key  # noqa: E402
from scripts.materialise_2015_world_kits import ARCHIVES, _nearest_palette, _write_content_addressed, canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402
from scripts import pm99_compact_kit_template_v1 as compact_template  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402

INPUT_SCHEMA = "pm99-world-2015-fifaindex-kit-materialisation-v1"
LEDGER_SCHEMA = "pm99-world-2015-reviewed-kit-geometry-v1"
OUTPUT_SCHEMA = "pm99-world-2015-combined-kit-materialisation-v1"
REVIEWED_STATUS = "release-eligible-reviewed-2015-geometry"


class ReviewedKitError(ValueError):
    pass


def _rgb(value: str) -> tuple[int, int, int]:
    if len(value) != 7 or not value.startswith("#"):
        raise ReviewedKitError(f"invalid colour: {value}")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def render_geometry(
    record: Any,
    design: str,
    colors: list[str],
    palette: list[tuple[int, int, int]],
) -> bytes:
    if design not in {"plain", "stripes", "half-and-half", "contrasting-sleeves", "hoops"} or len(colors) < 2:
        raise ReviewedKitError(f"unsupported reviewed geometry: {design}/{colors}")
    pattern = {
        "plain": "solid",
        "stripes": "vertical_stripes",
        "half-and-half": "halves",
        "contrasting-sleeves": "sleeves",
        "hoops": "hoops",
    }[design]
    rgb_colours = [_rgb(color) for color in colors]
    style: dict[str, Any] = {
        "pattern": pattern,
        "colors": [list(colour) for colour in rgb_colours],
        "shorts": list(rgb_colours[0]),
        "trim": None,
    }
    if pattern == "sleeves":
        style["sleeves"] = list(rgb_colours[1])
    if pattern == "vertical_stripes":
        style["stripe_count"] = 6
    if pattern == "hoops":
        style["band_count"] = 6
    return compact_template.render(record, palette, style)


def supplement(*, materialisation: Mapping[str, Any], ledger: Mapping[str, Any], dbdat: Path, output_dir: Path) -> dict[str, Any]:
    if materialisation.get("schema_version") != INPUT_SCHEMA or ledger.get("schema_version") != LEDGER_SCHEMA:
        raise ReviewedKitError("unsupported materialisation or ledger schema")
    rows = [dict(row) for row in materialisation.get("rows", [])]
    by_carrier = {int(row["carrier_id"]): row for row in rows}
    try:
        palette, _palette_source = runtime_kit_palette(dbdat)
    except ValueError as exc:
        raise ReviewedKitError(str(exc)) from exc
    archive_records = {archive: {int(record.file_name[4:8]): record for record in iter_obfuscated_bmp_records(dbdat / archive, file_name_pattern=r"^EQ96\d{4}\.BMP$")} for archive in ARCHIVES}
    applied = 0
    for reviewed in ledger.get("clubs", []):
        carrier = int(reviewed["carrier_id"])
        row = by_carrier.get(carrier)
        if row is None or row.get("status") != "blocked-no-unique-fifa16-team":
            raise ReviewedKitError(f"reviewed carrier is absent or not identity-blocked: {carrier}")
        if identity_key(str(row.get("source_club_name") or "")) != identity_key(str(reviewed["source_club_name"])):
            raise ReviewedKitError(f"reviewed identity mismatch: carrier {carrier}")
        assets: dict[str, Any] = {}
        for archive in ARCHIVES:
            record = archive_records[archive].get(carrier)
            if record is None:
                raise ReviewedKitError(f"missing archive record: {archive} carrier {carrier}")
            payload = render_geometry(record, str(reviewed["design"]), list(reviewed["colors"]), palette)
            path, digest = _write_content_addressed(payload, output_dir / archive.removesuffix(".PKF"), ".bmp")
            assets[archive] = {"path": str(path.resolve()), "sha256": digest, "bitmap_length": len(payload)}
        row.update({"status": REVIEWED_STATUS, "action": "write-candidate-only", "assets": assets, "reviewed_source": dict(reviewed), "binding": {"status": "identity-bound", "method": "carrier-and-source-name-reviewed-season-catalogue", "source_team_name": reviewed["source_team_name"]}})
        applied += 1
    counts = collections.Counter(row.get("status") for row in rows)
    result = dict(materialisation)
    result.update({"schema_version": OUTPUT_SCHEMA, "result": "combined source-only kit candidates; no PM99 binary writes", "rows": rows})
    result["coverage"] = dict(materialisation.get("coverage") or {})
    result["coverage"].update({"release_eligible_count": counts["release-eligible-fifa16-identity-bound"] + counts[REVIEWED_STATUS], "reviewed_geometry_count": applied, "status_counts": dict(sorted(counts.items()))})
    result["sources"] = dict(materialisation.get("sources") or {})
    result["sources"]["reviewed_geometry_ledger"] = {"sha256": sha256_bytes(canonical_json_bytes(ledger)), "policy": ledger.get("policy")}
    result["sources"]["reviewed_geometry_archives"] = {archive: sha256_file(dbdat / archive) for archive in ARCHIVES}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialisation", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = supplement(materialisation=json.loads(args.materialisation.read_text()), ledger=json.loads(args.ledger.read_text()), dbdat=args.dbdat, output_dir=args.output_dir)
    except (OSError, json.JSONDecodeError, ReviewedKitError) as exc:
        parser.error(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
