#!/usr/bin/env python3
"""Apply proven rendered-squad-number name repairs directly to an alpha game.

This is intentionally a small, direct repair command, not a review workflow.
It changes only source-backed player ``name`` values whose captured evidence
shows that a web page heading such as ``#8 Sam Morsy`` leaked its shirt number
into the name.  It then obtains parser-safe replacement player records from a
clean temporary compile and atomically replaces the live JUG file only if
every non-target player payload is byte-identical.

The package snapshots passed to ``--package`` are updated in place.  A compact
receipt is written solely so a later bug report can identify the exact names
and hashes that were applied; it is not an approval queue or a staged overlay.
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
from scripts import season_name_provenance_v1 as provenance  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import reconcile_mode1_roster_base_batch_v1 as mode1_batch  # noqa: E402
from scripts import season_package_display_alias_repair_v1 as aliases  # noqa: E402


SCHEMA = "pm99-season-number-label-name-direct-repair-v1"
REASON = "Remove rendered squad-number label accidentally included in player name."


class DirectRepairError(ValueError):
    """The requested direct repair is not exactly limited to proven names."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DirectRepairError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise DirectRepairError(f"{label} must be a JSON object: {path}")
    return value


def _repair_candidates(sidecar: Mapping[str, Any]) -> list[dict[str, str]]:
    if sidecar.get("schema_version") != provenance.SCHEMA:
        raise DirectRepairError(f"provenance must use {provenance.SCHEMA}")
    selected: list[dict[str, str]] = []
    for row in sidecar.get("players", []):
        if not isinstance(row, Mapping) or row.get("status") != "source-row-linked":
            continue
        component = row.get("component_candidate")
        captured = row.get("captured_source")
        if not isinstance(component, Mapping) or component.get("source_number_label_stripped") is not True:
            continue
        player_id = row.get("player_id")
        expected = row.get("canonical_name")
        replacement = component.get("proposed_display_name")
        if not all(isinstance(value, str) and value.strip() for value in (player_id, expected, replacement)):
            raise DirectRepairError("number-label provenance candidate is malformed")
        if expected == replacement:
            raise DirectRepairError(f"number-label provenance candidate does not change {player_id}")
        if not isinstance(captured, Mapping) or not isinstance(captured.get("source_path"), str):
            raise DirectRepairError(f"number-label provenance lacks source path for {player_id}")
        selected.append({
            "player_id": player_id,
            "expected": expected,
            "replacement": replacement,
            "evidence": f"{provenance.SCHEMA}:{captured['source_path']}#{captured.get('source_row_index')}",
        })
    if not selected:
        raise DirectRepairError("provenance contains no source-linked rendered-number name repairs")
    return sorted(selected, key=lambda row: row["player_id"])


def _apply_to_package(
    *, path: Path, candidates: Sequence[Mapping[str, str]], apply: bool,
) -> dict[str, Any]:
    package = package_v2.read_canonical_package(path)
    players = package.get("players")
    if not isinstance(players, list):
        raise DirectRepairError(f"package has no players list: {path}")
    by_id = {
        player.get("id"): player
        for player in players
        if isinstance(player, dict) and isinstance(player.get("id"), str)
    }
    before_sha256 = _sha256(path)
    changes: list[dict[str, str]] = []
    already_applied = 0
    for candidate in candidates:
        player_id = candidate["player_id"]
        player = by_id.get(player_id)
        if not isinstance(player, dict):
            raise DirectRepairError(f"package is missing repair player {player_id}: {path}")
        actual = player.get("name")
        if actual == candidate["replacement"]:
            already_applied += 1
            continue
        if actual != candidate["expected"]:
            raise DirectRepairError(
                f"package name differs from proven input for {player_id}: {actual!r} in {path}"
            )
        player["name"] = candidate["replacement"]
        changes.append({
            "player_id": player_id,
            "expected": candidate["expected"],
            "replacement": candidate["replacement"],
            "evidence": candidate["evidence"],
        })
    package_v2.validate_package(package, strict=True)
    payload = package_v2.canonical_json_bytes(package)
    after_sha256 = hashlib.sha256(payload).hexdigest()
    if apply and changes:
        temporary = path.with_name(f".{path.name}.number-label-repair.tmp")
        if temporary.exists() or temporary.is_symlink():
            raise DirectRepairError(f"temporary repair path already exists: {temporary}")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    return {
        "path": str(path),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "changed_player_count": len(changes),
        "already_applied_player_count": already_applied,
        "changes": changes,
    }


def _decoded_payloads(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    return {
        int(entry.record_id): entry.decode_payload(data)
        for entry in IndexedFDIFile.from_bytes(data).entries
    }


def _assert_only_repaired_names_changed(
    *, before: Mapping[str, Any], after: Mapping[str, Any], repaired_ids: set[str], label: str,
) -> list[dict[str, str]]:
    """Ensure a derived snapshot has not drifted beyond the direct name repair."""

    before_top = dict(before)
    after_top = dict(after)
    before_players = before_top.pop("players", None)
    after_players = after_top.pop("players", None)
    if before_top != after_top or not isinstance(before_players, list) or not isinstance(after_players, list):
        raise DirectRepairError(f"{label} changed package content outside player names")
    before_by_id = {
        player.get("id"): player for player in before_players
        if isinstance(player, Mapping) and isinstance(player.get("id"), str)
    }
    after_by_id = {
        player.get("id"): player for player in after_players
        if isinstance(player, Mapping) and isinstance(player.get("id"), str)
    }
    if before_by_id.keys() != after_by_id.keys():
        raise DirectRepairError(f"{label} changed player identity membership")
    changes: list[dict[str, str]] = []
    for player_id in sorted(before_by_id):
        old = dict(before_by_id[player_id])
        new = dict(after_by_id[player_id])
        old_name = old.pop("name", None)
        new_name = new.pop("name", None)
        if old != new:
            raise DirectRepairError(f"{label} changed player fields outside name: {player_id}")
        if old_name == new_name:
            continue
        if player_id not in repaired_ids:
            raise DirectRepairError(f"{label} changed an unproven player name: {player_id}")
        if not isinstance(old_name, str) or not isinstance(new_name, str):
            raise DirectRepairError(f"{label} produced a non-string player name: {player_id}")
        changes.append({"player_id": player_id, "expected": old_name, "replacement": new_name})
    return changes


def _write_package_direct(path: Path, package: Mapping[str, Any]) -> str:
    payload = package_v2.canonical_json_bytes(dict(package))
    temporary = path.with_name(f".{path.name}.number-label-repair.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise DirectRepairError(f"temporary repair path already exists: {temporary}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest()


def _refresh_derived_packages(
    *, source_package_path: Path, alias_package_path: Path, reconciled_package_path: Path,
    base_tree: Path, verified_base_path: Path, candidates: Sequence[Mapping[str, str]], apply: bool,
) -> list[dict[str, Any]]:
    """Refresh just the affected aliases, then the existing final snapshot."""

    before_alias = package_v2.read_canonical_package(alias_package_path)
    source_package = package_v2.read_canonical_package(source_package_path)
    source_players = {
        player.get("id"): player for player in source_package.get("players", [])
        if isinstance(player, Mapping) and isinstance(player.get("id"), str)
    }
    derived_alias = copy.deepcopy(before_alias)
    alias_players = {
        player.get("id"): player for player in derived_alias.get("players", [])
        if isinstance(player, dict) and isinstance(player.get("id"), str)
    }
    jug_path = base_tree / "DBDAT/JUG98030.FDI"
    if not jug_path.is_file():
        raise DirectRepairError(f"clean base lacks JUG98030.FDI: {jug_path}")
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    repaired_ids = {row["player_id"] for row in candidates}
    for candidate in candidates:
        player_id = candidate["player_id"]
        player = alias_players.get(player_id)
        source_player = source_players.get(player_id)
        if not isinstance(player, dict) or not isinstance(source_player, Mapping):
            raise DirectRepairError(f"alias refresh is missing repair player {player_id}")
        if player.get("policy") == "preserve-existing-mode1":
            # The compiler deliberately preserves this opaque native record;
            # the clean recipe is already fixed, but no invented binary
            # mutation is permitted for a preserve-only carrier.
            continue
        carrier_id = player.get("carrier_id")
        if not isinstance(carrier_id, int):
            raise DirectRepairError(f"alias refresh has no carrier for {player_id}")
        entry = entries.get(carrier_id)
        if entry is None:
            append_from = player.get("append_from_carrier_id")
            if not isinstance(append_from, int):
                raise DirectRepairError(f"alias refresh cannot resolve appended carrier for {player_id}")
            entry = entries.get(append_from)
        if entry is None:
            raise DirectRepairError(f"alias refresh carrier is absent from clean base for {player_id}")
        source_name = candidate["replacement"]
        display_name, _method = aliases._derive_display_name(
            payload=entry.decode_payload(jug_data),
            carrier_id=carrier_id,
            source_name=source_name,
            requested_name=source_name,
        )
        if display_name.lstrip().startswith("#"):
            raise DirectRepairError(f"alias refresh retained a rendered squad number for {player_id}")
        player["name"] = display_name
    package_v2.validate_package(derived_alias, strict=True)
    alias_changes = _assert_only_repaired_names_changed(
        before=before_alias, after=derived_alias, repaired_ids=repaired_ids,
        label="display-alias derivation",
    )
    if apply and alias_changes:
        alias_after_sha256 = _write_package_direct(alias_package_path, derived_alias)
    else:
        alias_after_sha256 = package_v2.sha256_bytes(package_v2.canonical_json_bytes(derived_alias))

    before_reconciled = package_v2.read_canonical_package(reconciled_package_path)
    try:
        reconciled, _reconciliation_audit = mode1_batch.reconcile_batch(
            package_path=alias_package_path if apply else source_package_path,
            base_tree=base_tree,
            verified_base_path=verified_base_path,
            preservation_artifact_id="world-mode1-runtime-contract",
            preservation_source_id="baseline-runtime-contract",
        )
    except mode1_batch.BatchReconciliationError as exc:
        if str(exc) != "no mode-1 clubs were eligible for whole-row base preservation":
            raise
        reconciled = copy.deepcopy(derived_alias)
    package_v2.validate_package(reconciled, strict=True)
    reconciled_changes = _assert_only_repaired_names_changed(
        before=before_reconciled, after=reconciled, repaired_ids=repaired_ids,
        label="mode-1 roster reconciliation",
    )
    if apply and reconciled_changes:
        reconciled_after_sha256 = _write_package_direct(reconciled_package_path, reconciled)
    else:
        reconciled_after_sha256 = package_v2.sha256_bytes(package_v2.canonical_json_bytes(reconciled))
    return [
        {
            "path": str(alias_package_path),
            "before_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(before_alias)),
            "after_sha256": alias_after_sha256,
            "changed_player_count": len(alias_changes),
            "derived_directly": "display-alias-repair",
            "changes": alias_changes,
        },
        {
            "path": str(reconciled_package_path),
            "before_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(before_reconciled)),
            "after_sha256": reconciled_after_sha256,
            "changed_player_count": len(reconciled_changes),
            "derived_directly": "mode1-roster-reconciliation",
            "changes": reconciled_changes,
        },
    ]


def _verify_jug_delta(
    *, before: Path, rebuilt: Path, package: Mapping[str, Any], repaired_ids: set[str],
) -> dict[str, Any]:
    players = package.get("players")
    if not isinstance(players, list):
        raise DirectRepairError("compiled package has no players list")
    expected_by_carrier: dict[int, str] = {}
    for player in players:
        if not isinstance(player, Mapping) or player.get("id") not in repaired_ids:
            continue
        carrier_id = player.get("carrier_id")
        name = player.get("name")
        if not isinstance(carrier_id, int) or not isinstance(name, str):
            raise DirectRepairError(f"malformed compiled repair player: {player.get('id')}")
        expected_by_carrier[carrier_id] = name
    if len(expected_by_carrier) != len(repaired_ids):
        raise DirectRepairError("not every repaired player is represented by one compiled carrier")
    previous = _decoded_payloads(before)
    candidate = _decoded_payloads(rebuilt)
    if previous.keys() != candidate.keys():
        raise DirectRepairError("direct name repair changed the JUG record-id set")
    changed_carriers = {
        carrier_id for carrier_id in previous
        if previous[carrier_id] != candidate[carrier_id]
    }
    unexpected = changed_carriers - set(expected_by_carrier)
    if unexpected:
        raise DirectRepairError(
            "direct JUG delta is not limited to repaired players: "
            f"unexpected={sorted(unexpected)}"
        )
    observed: list[dict[str, Any]] = []
    for carrier_id, expected in sorted(expected_by_carrier.items()):
        actual = compiler._player_name(candidate[carrier_id], record_id=carrier_id)
        if actual.casefold() != expected.casefold():
            raise DirectRepairError(
                f"compiled player name read-back failed for {carrier_id}: {actual!r} != {expected!r}"
            )
        observed.append({"carrier_id": carrier_id, "name": actual})
    return {"changed_carrier_count": len(changed_carriers), "players": observed}


def _refresh_live_jug(
    *, package_path: Path, base_tree: Path, runtime_game: Path, repaired_ids: set[str], apply: bool,
) -> dict[str, Any]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    runtime_game = runtime_game.resolve()
    base_tree = base_tree.resolve()
    if not runtime_game.is_dir() or not base_tree.is_dir():
        raise DirectRepairError("runtime game and base tree must both be directories")
    live_jug = runtime_game / "DBDAT/JUG98030.FDI"
    if not live_jug.is_file():
        raise DirectRepairError(f"runtime game lacks JUG98030.FDI: {runtime_game}")
    players = package.get("players")
    if not isinstance(players, list):
        raise DirectRepairError("compiled package has no players list")
    desired_by_carrier = {
        int(player["carrier_id"]): str(player["name"])
        for player in players
        if isinstance(player, Mapping) and player.get("id") in repaired_ids
    }
    if len(desired_by_carrier) != len(repaired_ids):
        raise DirectRepairError("not every direct repair player has one runtime carrier")
    original = live_jug.read_bytes()
    index = IndexedFDIFile.from_bytes(original)
    live_entries = {int(entry.record_id): entry for entry in index.entries}
    with tempfile.TemporaryDirectory(prefix="pm99-name-repair-", dir=runtime_game.parent) as temporary_root:
        materialisation = Path(temporary_root) / "game"
        shutil.copytree(base_tree, materialisation, symlinks=False, copy_function=shutil.copyfile)
        compile_receipt = compiler.compile_package_to_tree(
            package_path=package_path,
            base_tree=base_tree,
            materialisation_tree=materialisation,
        )
        compiled_jug = materialisation / "DBDAT/JUG98030.FDI"
        compiled_bytes = compiled_jug.read_bytes()
        compiled_entries = {
            int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(compiled_bytes).entries
        }
        replacements: dict[int, bytes] = {}
        for carrier_id, desired_name in desired_by_carrier.items():
            live_entry = live_entries.get(carrier_id)
            compiled_entry = compiled_entries.get(carrier_id)
            if live_entry is None or compiled_entry is None:
                raise DirectRepairError(f"runtime or clean compile lacks player carrier {carrier_id}")
            live_payload = live_entry.decode_payload(original)
            compiled_payload = compiled_entry.decode_payload(compiled_bytes)
            actual_name = compiler._player_name(compiled_payload, record_id=carrier_id)
            if actual_name.casefold() != desired_name.casefold():
                raise DirectRepairError(
                    f"clean compiler read-back failed for {carrier_id}: {actual_name!r} != {desired_name!r}"
                )
            live_name = compiler._player_name(live_payload, record_id=carrier_id)
            if live_name.casefold() != desired_name.casefold():
                replacements[carrier_id] = compiled_payload
        rebuilt = compiler._rebuild_indexed(original, index, replacements)
    rebuilt_jug = live_jug.with_name(f".{live_jug.name}.number-label-repair.tmp")
    if rebuilt_jug.exists() or rebuilt_jug.is_symlink():
        raise DirectRepairError(f"temporary JUG repair path already exists: {rebuilt_jug}")
    rebuilt_jug.write_bytes(rebuilt)
    try:
        delta = _verify_jug_delta(
            before=live_jug,
            rebuilt=rebuilt_jug,
            package=package,
            repaired_ids=repaired_ids,
        )
        before_sha256 = _sha256(live_jug)
        after_sha256 = _sha256(rebuilt_jug)
        if apply:
            os.replace(rebuilt_jug, live_jug)
    finally:
        if rebuilt_jug.exists() or rebuilt_jug.is_symlink():
            rebuilt_jug.unlink()
    return {
        "package_path": str(package_path),
        "package_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(package)),
        "runtime_game": str(runtime_game),
        "jug_before_sha256": before_sha256,
        "jug_after_sha256": after_sha256,
        "jug_delta": delta,
        "method": "clean-compile-parser-safe-player-payloads-only",
        "clean_compile": {
            "clubs_written": compile_receipt["clubs_written"],
            "players_written": compile_receipt["players_written"],
            "managers_written": compile_receipt["managers_written"],
        },
    }


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise DirectRepairError(f"temporary receipt path already exists: {temporary}")
    temporary.write_bytes(package_v2.canonical_json_bytes(dict(receipt)))
    os.replace(temporary, path)


def repair(
    *, provenance_path: Path, package_paths: Sequence[Path], compile_package_path: Path,
    alias_package_path: Path, reconciled_package_path: Path, base_tree: Path,
    verified_base_path: Path, runtime_game: Path, receipt_path: Path, apply: bool,
) -> dict[str, Any]:
    if len(set(package_paths)) != len(package_paths):
        raise DirectRepairError("each --package path must be supplied only once")
    resolved_packages = {path.resolve() for path in package_paths}
    if compile_package_path.resolve() not in resolved_packages:
        raise DirectRepairError("--compile-package must also be supplied through --package")
    sidecar = _read_object(provenance_path, label="provenance")
    candidates = _repair_candidates(sidecar)
    package_results = [
        _apply_to_package(path=path.resolve(), candidates=candidates, apply=apply)
        for path in package_paths
    ]
    all_repair_ids = {row["player_id"] for row in candidates}
    package_results.extend(_refresh_derived_packages(
        source_package_path=compile_package_path.resolve(),
        alias_package_path=alias_package_path.resolve(),
        reconciled_package_path=reconciled_package_path.resolve(),
        base_tree=base_tree,
        verified_base_path=verified_base_path,
        candidates=candidates,
        apply=apply,
    ))
    live = _refresh_live_jug(
        package_path=reconciled_package_path.resolve(), base_tree=base_tree,
        runtime_game=runtime_game, repaired_ids=all_repair_ids, apply=apply,
    )
    season = sidecar.get("season")
    receipt = {
        "schema_version": SCHEMA,
        "season": season,
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "reason": REASON,
        "provenance": {
            "path": str(provenance_path),
            "sha256": _sha256(provenance_path),
            "candidate_count": len(candidates),
        },
        "packages": package_results,
        "runtime_refresh": live,
    }
    if apply:
        _write_receipt(receipt_path, receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--package", action="append", required=True, type=Path,
                        help="Current recipe package to update directly; repeat for each derived snapshot.")
    parser.add_argument("--compile-package", required=True, type=Path,
                        help="One of --package: the source-writable package used for the direct derivation.")
    parser.add_argument("--alias-package", required=True, type=Path,
                        help="Existing alias-bound snapshot to refresh directly from --compile-package.")
    parser.add_argument("--reconciled-package", required=True, type=Path,
                        help="Existing final snapshot to refresh directly from --alias-package.")
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--runtime-game", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Apply the direct source and game changes.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = repair(
            provenance_path=args.provenance,
            package_paths=args.package,
            compile_package_path=args.compile_package,
            alias_package_path=args.alias_package,
            reconciled_package_path=args.reconciled_package,
            base_tree=args.base_tree,
            verified_base_path=args.verified_base,
            runtime_game=args.runtime_game,
            receipt_path=args.receipt,
            apply=args.apply,
        )
    except (DirectRepairError, compiler.SeasonCompilerError, OSError, ValueError) as exc:
        print(f"direct-number-label-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "season": receipt["season"],
        "state": receipt["state"],
        "candidate_count": receipt["provenance"]["candidate_count"],
        "jug_changed_carrier_count": receipt["runtime_refresh"]["jug_delta"]["changed_carrier_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
