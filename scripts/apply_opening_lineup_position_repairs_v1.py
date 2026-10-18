#!/usr/bin/env python3
"""Repair invalid opening-XI broad positions from its recorded tactics layout.

The historic recipe keeps each opening XI's on-pitch coordinates.  When an
otherwise sourced XI has zero or multiple goalkeepers, those coordinates are
the least speculative authoritative input: the sole row on the goalkeeper
line is ``G``, followed by defence, midfield and attack bands.  This tool
updates only failed XI rows in the active mirrored recipe snapshots, then
refreshes exactly those JUG player records in the playable alpha game.

It deliberately does not re-order squads, alter the XI, acquire sources, or
touch managers, clubs, kits, dates, ratings, or calendars.
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
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import prepare_provisional_compile_package_v1 as preparation  # noqa: E402


SCHEMA = "pm99-season-direct-opening-lineup-position-repair-v1"


class OpeningLineupPositionRepairError(ValueError):
    """The tactical-coordinate repair would exceed its deliberately small scope."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_package(path: Path, package: Mapping[str, Any]) -> str:
    payload = package_v2.canonical_json_bytes(dict(package))
    temporary = path.with_name(f".{path.name}.opening-position-repair.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise OpeningLineupPositionRepairError(f"temporary recipe path already exists: {temporary}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest()


def _position_from_tactics(row: object, *, index: int) -> str:
    if not isinstance(row, list) or len(row) != 4 or any(not isinstance(value, int) for value in row):
        raise OpeningLineupPositionRepairError(f"opening tactics row {index} is malformed")
    # The writer stores four coordinate values for a player.  The two y values
    # must agree; accepting a mismatched pair would turn a broken tactics row
    # into a fabricated player position.
    y_values = (row[1], row[3])
    if y_values[0] != y_values[1]:
        raise OpeningLineupPositionRepairError(f"opening tactics row {index} has conflicting y coordinates")
    y = y_values[0]
    if y < 100:
        return "G"
    if y < 200:
        return "D"
    if y < 350:
        return "M"
    return "F"


def _plan_package(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    before = package_v2.read_canonical_package(path)
    after = copy.deepcopy(before)
    players = after.get("players")
    clubs = after.get("clubs")
    if not isinstance(players, list) or not isinstance(clubs, list):
        raise OpeningLineupPositionRepairError(f"recipe has no players/clubs lists: {path}")
    players_by_id = {
        str(player.get("id")): player
        for player in players
        if isinstance(player, dict) and isinstance(player.get("id"), str)
    }
    if len(players_by_id) != len(players):
        raise OpeningLineupPositionRepairError(f"recipe has malformed player IDs: {path}")

    changes: list[dict[str, Any]] = []
    for club in clubs:
        if not isinstance(club, Mapping):
            continue
        opening = club.get("opening")
        if not isinstance(opening, Mapping):
            continue
        xi = opening.get("starting_xi_player_ids")
        tactics = opening.get("tactics_positions")
        if not isinstance(xi, list) or not isinstance(tactics, list):
            continue
        if len(xi) != 11 or len(tactics) != 11 or any(not isinstance(player_id, str) for player_id in xi):
            raise OpeningLineupPositionRepairError(
                f"club {club.get('id')!r} has malformed opening XI/tactics shape"
            )
        try:
            current = [str(players_by_id[player_id]["facts"]["primary_position"]) for player_id in xi]
        except (KeyError, TypeError) as exc:
            raise OpeningLineupPositionRepairError(
                f"club {club.get('id')!r} opening XI has no writable broad positions"
            ) from exc
        if current.count("G") == 1:
            continue
        intended = [_position_from_tactics(row, index=index) for index, row in enumerate(tactics)]
        if intended.count("G") != 1:
            raise OpeningLineupPositionRepairError(
                f"club {club.get('id')!r} tactics do not define exactly one goalkeeper"
            )
        for player_id, before_position, after_position in zip(xi, current, intended, strict=True):
            if before_position == after_position:
                continue
            player = players_by_id[player_id]
            facts = player.get("facts")
            if not isinstance(facts, dict):
                raise OpeningLineupPositionRepairError(f"player {player_id} facts are malformed")
            if isinstance(facts.get("primary_position"), Mapping):
                raise OpeningLineupPositionRepairError(
                    f"player {player_id} has a preserved primary position and cannot be inferred"
                )
            facts["primary_position"] = after_position
            changes.append({
                "club_id": str(club["id"]),
                "club_name": str(club.get("name") or ""),
                "player_id": player_id,
                "before": before_position,
                "after": after_position,
            })
    change_by_player = {row["player_id"]: row for row in changes}
    if len(change_by_player) != len(changes):
        raise OpeningLineupPositionRepairError("one player is implicated by multiple invalid opening XIs")
    # Changing a goalkeeper-labelled source row into an on-pitch outfielder
    # must also apply the established deterministic Handling guard.  Leaving
    # a 50+ Handling value behind would satisfy the XI count while creating a
    # worse semantic-rating fault.  Limit the normalisation strictly to the
    # opening-XI rows changed above.
    changed_players = {player_id: players_by_id[player_id] for player_id in change_by_player}
    handling = preparation._normalise_position_handling(changed_players)
    for row in [*handling["outfield"], *handling["goalkeeper"]]:
        change_by_player[row["player_id"]]["handling_before"] = row["before"]
        change_by_player[row["player_id"]]["handling_after"] = row["after"]
    return after, {
        "path": str(path),
        "before_sha256": _sha256(path),
        "after_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(after)),
        "changes": changes,
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
        raise OpeningLineupPositionRepairError("compiled recipe has no players")
    target_carriers = {
        int(player["carrier_id"]): str(player["id"])
        for player in players
        if isinstance(player, Mapping) and str(player.get("id")) in target_ids
    }
    if len(target_carriers) != len(target_ids):
        raise OpeningLineupPositionRepairError("not every opening-position target has one player carrier")
    runtime_game = runtime_game.resolve()
    base_tree = base_tree.resolve()
    live_jug = runtime_game / "DBDAT/JUG98030.FDI"
    if not runtime_game.is_dir() or not base_tree.is_dir() or not live_jug.is_file():
        raise OpeningLineupPositionRepairError("runtime game, clean base or live JUG is unavailable")
    original = live_jug.read_bytes()
    live_index = IndexedFDIFile.from_bytes(original)
    live_entries = {int(entry.record_id): entry for entry in live_index.entries}
    with tempfile.TemporaryDirectory(prefix="pm99-opening-position-repair-", dir=runtime_game.parent) as temporary_root:
        materialisation = Path(temporary_root) / "game"
        shutil.copytree(base_tree, materialisation, symlinks=False, copy_function=shutil.copyfile)
        compiler_receipt = compiler.compile_package_to_tree(
            package_path=package_path, base_tree=base_tree, materialisation_tree=materialisation,
        )
        compiled_jug = materialisation / "DBDAT/JUG98030.FDI"
        compiled_bytes = compiled_jug.read_bytes()
        compiled_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(compiled_bytes).entries}
        replacements: dict[int, bytes] = {}
        for carrier in target_carriers:
            if carrier not in live_entries or carrier not in compiled_entries:
                raise OpeningLineupPositionRepairError(
                    f"live or clean compiled JUG lacks target carrier {carrier}"
                )
            replacements[carrier] = compiled_entries[carrier].decode_payload(compiled_bytes)
        rebuilt = compiler._rebuild_indexed(original, live_index, replacements)
        temporary_jug = live_jug.with_name(f".{live_jug.name}.opening-position-repair.tmp")
        if temporary_jug.exists() or temporary_jug.is_symlink():
            raise OpeningLineupPositionRepairError(f"temporary JUG path already exists: {temporary_jug}")
        temporary_jug.write_bytes(rebuilt)
        try:
            before_payloads = _decoded_payloads(live_jug)
            after_payloads = _decoded_payloads(temporary_jug)
            if before_payloads.keys() != after_payloads.keys():
                raise OpeningLineupPositionRepairError("repair changed the JUG record-id set")
            changed_carriers = {carrier for carrier in before_payloads if before_payloads[carrier] != after_payloads[carrier]}
            unexpected = changed_carriers - set(target_carriers)
            if unexpected:
                raise OpeningLineupPositionRepairError(
                    f"repair changed non-target JUG carriers: {sorted(unexpected)}"
                )
            if set(target_carriers) - changed_carriers:
                raise OpeningLineupPositionRepairError(
                    "clean compiler did not write every requested opening-position change"
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
        raise OpeningLineupPositionRepairError("each --package must be supplied once")
    compile_package_path = compile_package_path.resolve()
    if compile_package_path not in resolved:
        raise OpeningLineupPositionRepairError("--compile-package must also be supplied through --package")
    plans = [(path, *_plan_package(path)) for path in resolved]
    change_maps = [
        {row["player_id"]: (row["before"], row["after"]) for row in plan["changes"]}
        for _path, _package, plan in plans
    ]
    if not change_maps or any(row != change_maps[0] for row in change_maps[1:]):
        raise OpeningLineupPositionRepairError("current recipe snapshots disagree about opening-position targets")
    target_ids = set(change_maps[0])
    if not target_ids:
        raise OpeningLineupPositionRepairError("no invalid opening-XI position repairs are required")
    if apply:
        for path, package, plan in plans:
            plan["after_sha256"] = _write_package(path, package)
    compile_plan = next(plan for path, _package, plan in plans if path == compile_package_path)
    live = _refresh_live_jug(
        package_path=compile_package_path, base_tree=base_tree,
        runtime_game=runtime_game, target_ids=target_ids, apply=apply,
    )
    season = package_v2.read_canonical_package(compile_package_path).get("season")
    if not isinstance(season, Mapping) or not isinstance(season.get("start_year"), int) or not isinstance(season.get("end_year"), int):
        raise OpeningLineupPositionRepairError("compiled recipe has no numeric season")
    result = {
        "schema_version": SCHEMA,
        "season": f"{season['start_year']:04d}-{int(season['end_year']) % 100:02d}",
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "policy": {
            "source": "recorded-opening-xi-tactics-coordinates",
            "bands": {"goalkeeper_y_lt": 100, "defender_y_lt": 200, "midfielder_y_lt": 350},
            "scope": "only XIs failing exactly-one-goalkeeper validation",
        },
        "packages": [plan for _path, _package, plan in plans],
        "target_player_count": len(target_ids),
        "changed_opening_xi_count": len({row["club_id"] for row in compile_plan["changes"]}),
        "runtime_refresh": live,
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(package_v2.canonical_json_bytes(result))
    return result


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
        result = repair(
            package_paths=args.package, compile_package_path=args.compile_package,
            base_tree=args.base_tree, runtime_game=args.runtime_game,
            receipt_path=args.receipt, apply=args.apply,
        )
    except (OpeningLineupPositionRepairError, compiler.SeasonCompilerError, OSError, ValueError) as exc:
        print(f"direct-opening-lineup-position-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "state": result["state"],
        "target_player_count": result["target_player_count"],
        "changed_opening_xi_count": result["changed_opening_xi_count"],
        "runtime_changed_carrier_count": result["runtime_refresh"]["changed_carrier_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
