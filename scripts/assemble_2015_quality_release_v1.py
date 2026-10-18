#!/usr/bin/env python3
"""Assemble the sourced 2015/16 facts and manager graph into one playable tree."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import finalize_season_release_v1 as finalizer  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


SEASON = "2015-16"
RELEASE_ID = "quality-bound-20260913-r1"
SOURCE_GAME = (ROOT / ".local/releases/pm99-2015-16-world").resolve()
DATABASE_TREE = ROOT / ".local/operations/2015-16/manager-facts-runner-game-r2-20260913"
PACKAGE = ROOT / ".local/operations/2015-16/season-package.composed-facts-residual-managers-r3-20260913.json"
COMPILER_RECEIPT = ROOT / ".local/operations/2015-16/manager-facts-compiler-receipt-r2-20260913.json"
MANAGER_RECEIPT = ROOT / ".local/operations/2015-16/manager-facts-manager-graph-application-v1-r2-20260913.json"
KIT_RECEIPT = ROOT / ".local/season-kit-runtime-overlays-v1/2015-16/v5/foreign-kit-application-receipt.json"
CALENDAR = ROOT / ".local/calendar-v1/2015-16/MANAGPRE.EXE"
OUTPUT_ROOT = ROOT / ".local/season-runtime-candidates-v1/2015-16/worldwide-quality-bound-20260913-r1"
OUTPUT_GAME = OUTPUT_ROOT / "game"
ASSEMBLY_RECEIPT = OUTPUT_ROOT / "assembly-receipt.json"


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    pipeline.write_canonical_json(path, value)


def main() -> int:
    if OUTPUT_ROOT.exists():
        raise SystemExit(f"refusing to overwrite existing 2015/16 assembly: {OUTPUT_ROOT}")
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".worldwide-quality-bound-20260913-r1.partial-", dir=OUTPUT_ROOT.parent))
    temp_game = temp_root / "game"
    try:
        shutil.copytree(SOURCE_GAME, temp_game, symlinks=False)
        before = {
            relative: registry.sha256_file(temp_game / relative)
            for relative in ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI")
        }
        for relative in ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI"):
            shutil.copy2(DATABASE_TREE / relative, temp_game / relative)
        shutil.copy2(CALENDAR, temp_game / "MANAGPRE.EXE")
        after = {
            relative: registry.sha256_file(temp_game / relative)
            for relative in ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI")
        }
        compiler = _read(COMPILER_RECEIPT)
        manager = _read(MANAGER_RECEIPT)
        compiler_outputs = {str(row["path"]): str(row["sha256"]) for row in compiler["outputs"]}  # type: ignore[index]
        byte_contract = manager["byte_contract"]  # type: ignore[index]
        expected_after = {
            "DBDAT/JUG98030.FDI": str(byte_contract["jug_unchanged_sha256"]),  # type: ignore[index]
            "DBDAT/EQ98030.FDI": str(byte_contract["eq_after_sha256"]),  # type: ignore[index]
            "DBDAT/ENT98030.FDI": str(byte_contract["ent_after_sha256"]),  # type: ignore[index]
        }
        if compiler_outputs["DBDAT/JUG98030.FDI"] != expected_after["DBDAT/JUG98030.FDI"]:
            raise ValueError("manager graph is not bound to the selected compiler JUG")
        if after != expected_after:
            raise ValueError("assembled 2015/16 database hashes do not match the manager graph receipt")
        temp_root.rename(OUTPUT_ROOT)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise

    receipt = {
        "schema_version": "pm99-season-runtime-assembly-v1",
        "season": SEASON,
        "source_game_inventory_fingerprint": pipeline.build_tree_inventory(SOURCE_GAME)["files_fingerprint"],
        "database_before": before,
        "database_after": after,
        "compiler_receipt_sha256": registry.sha256_file(COMPILER_RECEIPT),
        "manager_receipt_sha256": registry.sha256_file(MANAGER_RECEIPT),
        "kit_receipt_sha256": registry.sha256_file(KIT_RECEIPT),
        "calendar_sha256": registry.sha256_file(CALENDAR),
    }
    _write(ASSEMBLY_RECEIPT, receipt)
    result = finalizer.finalize(
        season=SEASON, release_id=RELEASE_ID, game=OUTPUT_GAME,
        package=PACKAGE, compiler_receipt=COMPILER_RECEIPT,
        static_receipt=None, kit_receipt=KIT_RECEIPT,
        calendar_source=CALENDAR, extra_receipts=[MANAGER_RECEIPT],
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
