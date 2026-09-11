#!/usr/bin/env python3
"""Promote one receipt-verified quality revision into its active runtime.

Only the three compiled FDI database files are promoted.  Kit archives and the
season executable are deliberately preserved.  Before an apply the active FDI
files are copied to an explicitly supplied archive root and checked by SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pm99_season_play_v1 import REVISIONS, ROOT, game_path
from scripts.season_package_v2 import canonical_json_bytes


DATABASE_FILES = ("DBDAT/ENT98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/JUG98030.FDI")
KIT_FILES = ("DBDAT/MINIESC.PKF", "DBDAT/NANOESC.PKF", "DBDAT/RIDIESC.PKF")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quality_root(season: str) -> Path:
    if season == "2017-18":
        return ROOT / ".local/season-static-ingress-v1/2017-18-worldwide-source-backed-qa2"
    return ROOT / ".local/season-quality-ingress-v1" / season / "qa1"


def checked_source(season: str) -> tuple[Path, dict[str, str]]:
    root = quality_root(season)
    receipt_path = root / "compiler-receipt.json"
    if not receipt_path.is_file():
        raise ValueError(f"missing compiler receipt: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    outputs = {str(row.get("path")): str(row.get("sha256")) for row in receipt.get("outputs", []) if isinstance(row, dict)}
    expected = {name: outputs.get(name, "") for name in DATABASE_FILES}
    if any(len(value) != 64 for value in expected.values()):
        raise ValueError(f"compiler receipt does not declare all FDI outputs for {season}")
    for name, expected_hash in expected.items():
        source = root / "game" / name
        if not source.is_file() or sha256(source) != expected_hash:
            raise ValueError(f"quality source receipt mismatch: {source}")
    return root, expected


def plan(season: str) -> dict[str, Any]:
    source_root, expected = checked_source(season)
    target = game_path(season)
    if not target.is_dir():
        raise ValueError(f"missing active runtime: {target}")
    kit_before = {name: sha256(target / name) for name in KIT_FILES}
    before = {name: sha256(target / name) for name in DATABASE_FILES}
    return {
        "schema_version": "pm99-season-quality-promotion-v1",
        "season": season,
        "quality_root": str(source_root.relative_to(ROOT)),
        "target_runtime": str(target.relative_to(ROOT)),
        "database_before": before,
        "database_after": expected,
        "kits_preserved": kit_before,
    }


def apply(row: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    season = str(row["season"])
    target = ROOT / str(row["target_runtime"])
    source = ROOT / str(row["quality_root"]) / "game"
    archive = archive_root / season / "DBDAT"
    if archive.exists():
        raise ValueError(f"refusing existing rollback archive: {archive}")
    archive.mkdir(parents=True)
    for name, expected in row["database_before"].items():
        original = target / name
        backup = archive / Path(name).name
        shutil.copy2(original, backup)
        if sha256(backup) != expected:
            raise ValueError(f"rollback copy mismatch: {backup}")
    for name, expected in row["database_after"].items():
        original = target / name
        replacement = source / name
        temporary = original.with_name(original.name + ".quality-promotion.tmp")
        if temporary.exists():
            raise ValueError(f"stale promotion temporary exists: {temporary}")
        shutil.copyfile(replacement, temporary)
        if sha256(temporary) != expected:
            temporary.unlink()
            raise ValueError(f"promotion temporary mismatch: {temporary}")
        temporary.replace(original)
        if sha256(original) != expected:
            raise ValueError(f"promoted output mismatch: {original}")
    after_kits = {name: sha256(target / name) for name in KIT_FILES}
    if after_kits != row["kits_preserved"]:
        raise ValueError("kit archive changed during database-only promotion")
    row["rollback_archive"] = str(archive)
    row["result"] = "applied"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", choices=sorted(REVISIONS))
    parser.add_argument("--apply", action="store_true", help="copy verified FDI files after writing a Pi rollback archive")
    parser.add_argument("--archive-root", type=Path, help="existing Pi rollback root; required with --apply")
    args = parser.parse_args()
    row = plan(args.season)
    receipt = ROOT / ".local/season-quality-promotion-v1" / args.season / "promotion-receipt.json"
    if args.apply:
        if args.archive_root is None:
            parser.error("--archive-root is required with --apply")
        if receipt.exists():
            parser.error(f"refusing existing promotion receipt: {receipt}")
        row = apply(row, args.archive_root)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(canonical_json_bytes(row))
        row["receipt"] = str(receipt.relative_to(ROOT))
    else:
        row["result"] = "planned"
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
