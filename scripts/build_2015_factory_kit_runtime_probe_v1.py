#!/usr/bin/env python3
"""Put one factory-kit recipe in a selectable carrier for runtime evidence.

This is intentionally *not* a historical database build.  It exists because
the PM99 new-game selector exposes English carriers, while 2015 foreign
carriers are normally visible later in opponent flows.  The resulting receipt
labels the temporary target so a selector screenshot proves renderer/palette
behaviour without making a false historical assignment.
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
from scripts.materialise_2015_world_kits import ARCHIVES, sha256_file  # noqa: E402
from scripts import pm99_factory_kit_renderer_v1 as factory_renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


class ProbeError(ValueError):
    pass


def _records(path: Path) -> dict[int, Any]:
    return {
        int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE).group(1)): record
        for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")
    }


def build_probe(
    *,
    materialisation: Mapping[str, Any],
    target_game_tree: Path,
    source_club: str,
    target_carrier: int,
    renderer_module: Any = factory_renderer,
) -> dict[str, Any]:
    renderer = materialisation.get("renderer") if isinstance(materialisation.get("renderer"), Mapping) else {}
    renderer_id = str(getattr(renderer_module, "RENDERER_ID", ""))
    if not renderer_id or renderer.get("id") != renderer_id:
        raise ProbeError("input is not a factory-template candidate materialisation")
    source_rows = [
        row
        for row in materialisation.get("rows") or []
        if isinstance(row, Mapping) and str(row.get("source_club_name") or "").casefold() == source_club.casefold()
    ]
    if len(source_rows) != 1:
        raise ProbeError(f"expected one factory candidate for {source_club!r}, found {len(source_rows)}")
    source_row = source_rows[0]
    recipe = source_row.get("render_recipe")
    if not isinstance(recipe, Mapping):
        raise ProbeError(f"factory candidate for {source_club!r} lacks a render recipe")
    dbdat = target_game_tree / "DBDAT"
    if not dbdat.is_dir():
        raise ProbeError(f"target game tree has no DBDAT: {target_game_tree}")
    palette, palette_info = runtime_kit_palette(dbdat)
    events = []
    for archive in ARCHIVES:
        archive_path = dbdat / archive
        before = archive_path.read_bytes()
        records = _records(archive_path)
        target = records.get(target_carrier)
        if target is None:
            raise ProbeError(f"{archive} has no selectable target carrier {target_carrier}")
        template_carrier = renderer_module.factory_template_carrier(archive, dict(recipe))
        template = records.get(template_carrier)
        if template is None:
            raise ProbeError(f"{archive} has no factory template {template_carrier}")
        payload = renderer_module.render_template_on_record(target, template, palette, dict(recipe))
        try:
            shape = validate_minifoto_bitmap(payload)
        except ValueError as exc:
            raise ProbeError(f"rendered {archive} payload is invalid") from exc
        if (shape.width, shape.height, shape.bits_per_pixel, shape.bitmap_length) != (
            target.width,
            target.height,
            target.bits_per_pixel,
            target.bitmap_length,
        ):
            raise ProbeError(f"rendered {archive} payload changes target bitmap shape")
        start, end = int(target.bitmap_offset), int(target.bitmap_offset + target.bitmap_length)
        after = bytearray(before)
        after[start:end] = payload
        changed_offsets = [offset for offset, (old, new) in enumerate(zip(before, after)) if old != new]
        if any(offset < start or offset >= end for offset in changed_offsets):
            raise ProbeError(f"{archive} probe would change bytes outside target record")
        archive_path.write_bytes(after)
        readback = _records(archive_path).get(target_carrier)
        if readback is None or readback.raw_bitmap != payload:
            raise ProbeError(f"{archive} target readback failed")
        events.append(
            {
                "archive": archive,
                "target_carrier": target_carrier,
                "target_bitmap_sha256_before": hashlib.sha256(target.raw_bitmap).hexdigest(),
                "target_bitmap_sha256_after": hashlib.sha256(payload).hexdigest(),
                "factory_template_carrier": template_carrier,
                "factory_template_bitmap_sha256": hashlib.sha256(template.raw_bitmap).hexdigest(),
                "changed_byte_count": len(changed_offsets),
                "changes_limited_to_target_record": True,
                "archive_sha256_after": sha256_file(archive_path),
            }
        )
    return {
        "schema_version": "pm99-2015-factory-kit-runtime-probe-v1",
        "result": "runtime-visual-probe-only-not-a-historical-database",
        "warning": "Barcelona's recipe is temporarily rendered in Arsenal's selectable carrier solely to prove PM99's runtime indexed-kit display.",
        "source_candidate": {
            "club": source_row.get("source_club_name"),
            "carrier_id": source_row.get("carrier_id"),
            "recipe": recipe,
        },
        "temporary_target": {"club": "Arsenal", "carrier_id": target_carrier},
        "target_game_tree": str(target_game_tree.resolve()),
        "runtime_palette": {**palette_info, "sha256": sha256_file(Path(str(palette_info["path"])))},
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--target-game-tree", type=Path, required=True)
    parser.add_argument("--source-club", default="Barcelona")
    parser.add_argument("--target-carrier", type=int, default=309)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_probe(
            materialisation=json.loads(args.candidate_materialisation.read_text(encoding="utf-8")),
            target_game_tree=args.target_game_tree,
            source_club=args.source_club,
            target_carrier=args.target_carrier,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProbeError) as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "events": len(result["events"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
