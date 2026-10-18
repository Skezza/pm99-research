#!/usr/bin/env python3
"""Apply the existing deterministic, position-aware Handling policy directly.

Older playable alpha builds pre-date the established global Handling policy:
outfield players must be 1..20 and goalkeepers must be at least
``max(35, quality - 12)``.  This command applies that exact existing model to
the selected current recipe snapshots and to the live JUG file.  It uses a
clean temporary compile only to obtain parser-safe replacement player records,
then proves every non-target JUG payload is byte-identical before replacing
the live file.  No manager, club, kit, roster or calendar data is changed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import prepare_provisional_compile_package_v1 as preparation  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts.pm99_season_qa_v1 import audit_compiled_handling  # noqa: E402


SCHEMA = "pm99-season-direct-position-handling-repair-v1"


class HandlingRepairError(ValueError):
    """The direct position-aware Handling repair cannot remain bounded."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_package(path: Path, package: Mapping[str, Any]) -> str:
    payload = package_v2.canonical_json_bytes(dict(package))
    temporary = path.with_name(f".{path.name}.handling-repair.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise HandlingRepairError(f"temporary package repair exists: {temporary}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest()


def _plan_package(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    before = package_v2.read_canonical_package(path)
    after = copy.deepcopy(before)
    players = after.get("players")
    if not isinstance(players, list):
        raise HandlingRepairError(f"package has no players list: {path}")
    by_id = {
        str(player["id"]): player for player in players
        if isinstance(player, dict) and isinstance(player.get("id"), str)
    }
    if len(by_id) != len(players):
        raise HandlingRepairError(f"package player IDs are malformed: {path}")
    policy = preparation._normalise_position_handling(by_id)
    rows = [*policy["outfield"], *policy["goalkeeper"]]
    changed = {
        str(row["player_id"]): int(row["after"])
        for row in rows
    }
    # The live compile path below strictly validates the reconciled package.
    # Do not repeat the costly whole-package schema walk for every mirrored
    # snapshot here: this repair changes one already-range-checked integer per
    # player, and the equality check across snapshots is the relevant guard.
    return after, {
        "path": str(path),
        "before_sha256": _sha256(path),
        "after_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(after)),
        "outfield_changed_player_count": len(policy["outfield"]),
        "goalkeeper_changed_player_count": len(policy["goalkeeper"]),
        "changed_handling_by_player_id": changed,
    }


def _decoded_payloads(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    return {
        int(entry.record_id): entry.decode_payload(data)
        for entry in IndexedFDIFile.from_bytes(data).entries
    }


def _refresh_live_jug(
    *, package_path: Path, base_tree: Path, runtime_game: Path, target_ids: set[str], apply: bool,
) -> dict[str, Any]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    players = package.get("players")
    if not isinstance(players, list):
        raise HandlingRepairError("compiled package has no players")
    target_carriers = {
        int(player["carrier_id"]): str(player["id"])
        for player in players
        if isinstance(player, Mapping) and str(player.get("id")) in target_ids
    }
    if len(target_carriers) != len(target_ids):
        raise HandlingRepairError("not every Handling repair target has one package carrier")
    runtime_game = runtime_game.resolve()
    base_tree = base_tree.resolve()
    live_jug = runtime_game / "DBDAT/JUG98030.FDI"
    if not runtime_game.is_dir() or not base_tree.is_dir() or not live_jug.is_file():
        raise HandlingRepairError("runtime game, clean base or live JUG is unavailable")
    original = live_jug.read_bytes()
    live_index = IndexedFDIFile.from_bytes(original)
    live_entries = {int(entry.record_id): entry for entry in live_index.entries}
    with tempfile.TemporaryDirectory(prefix="pm99-handling-repair-", dir=runtime_game.parent) as temporary_root:
        materialisation = Path(temporary_root) / "game"
        shutil.copytree(base_tree, materialisation, symlinks=False, copy_function=shutil.copyfile)
        compiler_receipt = compiler.compile_package_to_tree(
            package_path=package_path, base_tree=base_tree, materialisation_tree=materialisation,
        )
        compiled_jug = materialisation / "DBDAT/JUG98030.FDI"
        compiled_bytes = compiled_jug.read_bytes()
        compiled_entries = {
            int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(compiled_bytes).entries
        }
        replacements: dict[int, bytes] = {}
        for carrier in target_carriers:
            if carrier not in live_entries or carrier not in compiled_entries:
                raise HandlingRepairError(f"live or clean compiled JUG lacks target carrier {carrier}")
            replacements[carrier] = compiled_entries[carrier].decode_payload(compiled_bytes)
        rebuilt = compiler._rebuild_indexed(original, live_index, replacements)
        temporary_jug = live_jug.with_name(f".{live_jug.name}.handling-repair.tmp")
        if temporary_jug.exists() or temporary_jug.is_symlink():
            raise HandlingRepairError(f"temporary JUG repair exists: {temporary_jug}")
        temporary_jug.write_bytes(rebuilt)
        try:
            before_payloads = _decoded_payloads(live_jug)
            after_payloads = _decoded_payloads(temporary_jug)
            if before_payloads.keys() != after_payloads.keys():
                raise HandlingRepairError("direct Handling repair changed the JUG record-id set")
            changed_carriers = {
                carrier for carrier in before_payloads
                if before_payloads[carrier] != after_payloads[carrier]
            }
            unexpected = changed_carriers - set(target_carriers)
            if unexpected:
                raise HandlingRepairError(
                    f"direct Handling repair changed non-target JUG carriers: {sorted(unexpected)}"
                )
            binary_audit = audit_compiled_handling(package, game=materialisation)
            target_failures = [
                row for row in binary_audit["failures"]
                if int(row.get("record_id") or -1) in target_carriers
            ]
            if target_failures:
                raise HandlingRepairError(
                    f"clean compiler does not read back repaired Handling: {target_failures[:3]}"
                )
            before_sha256 = _sha256(live_jug)
            after_sha256 = _sha256(temporary_jug)
            if apply:
                os.replace(temporary_jug, live_jug)
        finally:
            if temporary_jug.exists() or temporary_jug.is_symlink():
                temporary_jug.unlink()
    return {
        "package_path": str(package_path),
        "package_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(package)),
        "runtime_game": str(runtime_game),
        "jug_before_sha256": before_sha256,
        "jug_after_sha256": after_sha256,
        "changed_carrier_count": len(changed_carriers),
        "clean_compile": {
            "clubs_written": compiler_receipt["clubs_written"],
            "players_written": compiler_receipt["players_written"],
            "managers_written": compiler_receipt["managers_written"],
        },
    }


def repair(
    *, package_paths: Sequence[Path], compile_package_path: Path, base_tree: Path,
    runtime_game: Path, receipt_path: Path, apply: bool,
) -> dict[str, Any]:
    resolved = [path.resolve() for path in package_paths]
    if len(set(resolved)) != len(resolved):
        raise HandlingRepairError("each --package must be supplied once")
    compile_package_path = compile_package_path.resolve()
    if compile_package_path not in resolved:
        raise HandlingRepairError("--compile-package must also be supplied through --package")
    plans = []
    for path in resolved:
        package, plan = _plan_package(path)
        plans.append((path, package, plan))
    change_maps = [plan["changed_handling_by_player_id"] for _path, _package, plan in plans]
    if not change_maps or any(row != change_maps[0] for row in change_maps[1:]):
        raise HandlingRepairError("current recipe snapshots disagree about Handling repair targets")
    target_ids = set(change_maps[0])
    if not target_ids:
        raise HandlingRepairError("no position-aware Handling repairs are required")
    if apply:
        for path, package, plan in plans:
            plan["after_sha256"] = _write_package(path, package)
    final_plan = next(plan for path, _package, plan in plans if path == compile_package_path)
    live = _refresh_live_jug(
        package_path=compile_package_path, base_tree=base_tree,
        runtime_game=runtime_game, target_ids=target_ids, apply=apply,
    )
    package_season = package_v2.read_canonical_package(compile_package_path)["season"]
    if not isinstance(package_season, Mapping):
        raise HandlingRepairError("compiled package has an invalid season object")
    start_year, end_year = package_season.get("start_year"), package_season.get("end_year")
    if not isinstance(start_year, int) or not isinstance(end_year, int):
        raise HandlingRepairError("compiled package season lacks numeric years")
    receipt = {
        "schema_version": SCHEMA,
        "season": f"{start_year:04d}-{end_year % 100:02d}",
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "policy": {
            "outfield": "deterministic-editorial-1-to-20",
            "goalkeeper": "deterministic-editorial-floor-max-35-or-quality-minus-12",
        },
        "packages": [plan for _path, _package, plan in plans],
        "target_player_count": len(target_ids),
        "outfield_target_player_count": final_plan["outfield_changed_player_count"],
        "goalkeeper_target_player_count": final_plan["goalkeeper_changed_player_count"],
        "runtime_refresh": live,
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(package_v2.canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--compile-package", type=Path, required=True)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--runtime-game", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = repair(
            package_paths=args.package, compile_package_path=args.compile_package,
            base_tree=args.base_tree, runtime_game=args.runtime_game,
            receipt_path=args.receipt, apply=args.apply,
        )
    except (HandlingRepairError, compiler.SeasonCompilerError, OSError, ValueError) as exc:
        print(f"direct-position-handling-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "state": receipt["state"],
        "target_player_count": receipt["target_player_count"],
        "outfield_target_player_count": receipt["outfield_target_player_count"],
        "goalkeeper_target_player_count": receipt["goalkeeper_target_player_count"],
        "runtime_changed_carrier_count": receipt["runtime_refresh"]["changed_carrier_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
