#!/usr/bin/env python3
"""Directly repair the sourced 2015/16 English manager names in an alpha game.

The 2015/16 world game's English club-to-manager carrier links are already
correct.  This bounded repair replaces only the incorrectly retained ENT
manager name records with the dated, source-backed names in the English-92
manifest.  It never changes an EQ manager link, squad, player, kit, calendar,
or any manager profile field beyond the parser-supported name span.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts.build_2015_english92_release import _patch_ent_name, _rebuild_indexed  # noqa: E402
from scripts.season_package_v2 import canonical_json_bytes  # noqa: E402


SCHEMA = "pm99-2015-16-direct-english-manager-name-repair-v1"


class ManagerRepairError(ValueError):
    """The known English manager-name repair cannot be applied safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerRepairError(f"cannot read manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ManagerRepairError("manifest must be an object")
    return value


def _manager_targets(manifest: Mapping[str, Any]) -> dict[int, dict[str, str]]:
    teams = manifest.get("teams")
    if not isinstance(teams, list):
        raise ManagerRepairError("manifest has no teams")
    targets: dict[int, dict[str, str]] = {}
    for team in teams:
        if not isinstance(team, Mapping):
            continue
        manager_id = team.get("manager_record_id")
        name = team.get("manager_name")
        club = team.get("club")
        source = team.get("manager_source_url")
        if not isinstance(manager_id, int) or not isinstance(name, str) or not name.strip() or not isinstance(club, str):
            raise ManagerRepairError("manifest has a malformed English manager target")
        row = {
            "club": club,
            "name": name,
            "source_url": str(source or ""),
        }
        previous = targets.get(manager_id)
        if previous is not None and previous != row:
            raise ManagerRepairError(f"manager carrier {manager_id} has conflicting English target names")
        targets[manager_id] = row
    if len(targets) != 92:
        raise ManagerRepairError(f"expected 92 English manager targets, found {len(targets)}")
    return targets


def repair(*, manifest_path: Path, game_root: Path, receipt_path: Path, apply: bool) -> dict[str, Any]:
    manifest = _read(manifest_path)
    targets = _manager_targets(manifest)
    ent_path = game_root.resolve() / "DBDAT" / "ENT98030.FDI"
    if not ent_path.is_file() or ent_path.is_symlink():
        raise ManagerRepairError(f"game does not have a safe ENT file: {ent_path}")
    before_sha256 = _sha256(ent_path)
    data = ent_path.read_bytes()
    index = IndexedFDIFile.from_bytes(data)
    entries = {int(entry.record_id): entry for entry in index.entries}
    replacements: dict[int, bytes] = {}
    changes: list[dict[str, Any]] = []
    already_correct = 0
    for manager_id, target in sorted(targets.items()):
        entry = entries.get(manager_id)
        if entry is None:
            raise ManagerRepairError(f"ENT lacks English manager carrier {manager_id}")
        raw_payload = data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        profile = parse_indexed_ent_manager_profile(raw_payload, record_id=manager_id)
        before = profile.display_name
        target_name = target["name"]
        if before.casefold() == target_name.casefold():
            already_correct += 1
            continue
        replacements[manager_id] = _patch_ent_name(
            entry.decode_payload(data), manager_id, target_name
        )
        changes.append({
            "manager_record_id": manager_id,
            "club": target["club"],
            "expected_name": target_name,
            "before_name": before,
            "source_url": target["source_url"],
        })
    rebuilt = _rebuild_indexed(data, index, replacements)
    temporary = ent_path.with_name(f".{ent_path.name}.english-manager-repair.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ManagerRepairError(f"temporary manager repair exists: {temporary}")
    temporary.write_bytes(rebuilt)
    try:
        rebuilt_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(rebuilt).entries}
        for manager_id, target in targets.items():
            entry = rebuilt_entries[manager_id]
            profile = parse_indexed_ent_manager_profile(
                rebuilt[entry.payload_offset : entry.payload_offset + entry.payload_length], record_id=manager_id
            )
            if profile.display_name.casefold() != target["name"].casefold():
                raise ManagerRepairError(
                    f"ENT read-back differs for manager {manager_id}: {profile.display_name!r}"
                )
        after_sha256 = _sha256(temporary)
        if apply:
            os.replace(temporary, ent_path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
    receipt = {
        "schema_version": SCHEMA,
        "season": "2015-16",
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "input": {
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "ent_before_sha256": before_sha256,
        },
        "output": {
            "game": str(game_root.resolve()),
            "ent_after_sha256": after_sha256,
            "changed_manager_count": len(changes),
            "already_correct_manager_count": already_correct,
            "changes": changes,
        },
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / ".local/season-2015-16/english92-2015-16-build36-native-no-photo/2015-16-english92-manifest.json",
    )
    parser.add_argument("--game", type=Path, default=ROOT / ".local/releases/pm99-2015-16-world")
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / ".local/season-2015-16/direct-english-manager-name-repair-v1.json",
    )
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = repair(
            manifest_path=args.manifest, game_root=args.game,
            receipt_path=args.receipt, apply=args.apply,
        )
    except (ManagerRepairError, OSError, ValueError) as exc:
        print(f"direct-2015-manager-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "state": result["state"],
        "changed_manager_count": result["output"]["changed_manager_count"],
        "already_correct_manager_count": result["output"]["already_correct_manager_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
