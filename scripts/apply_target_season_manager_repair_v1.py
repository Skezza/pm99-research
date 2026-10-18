#!/usr/bin/env python3
"""Apply dated manager evidence to one playable alpha season, safely.

All current recipe mirrors are derived with the same ledger.  The reconciled
package is compiled twice from the verified clean base; both builds must be
byte-identical, player data must match the live game exactly, and only declared
club/manager records may differ.  Only then are the recipe mirrors and the
live EQ/ENT files replaced.  Kits, calendar, portraits and JUG are untouched.
"""

from __future__ import annotations

import argparse
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
from scripts import apply_target_season_manager_ledger_v1 as ledger_v1  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts.pm99_season_qa_v1 import audit_compiled_managers  # noqa: E402


SCHEMA = "pm99-season-direct-target-manager-repair-v1"


class ManagerRepairError(ValueError):
    """A target-season manager repair cannot remain bounded."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decoded_payloads(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    return {
        int(entry.record_id): entry.decode_payload(data)
        for entry in IndexedFDIFile.from_bytes(data).entries
    }


def _changed_records(before: Path, after: Path) -> set[int]:
    before_rows, after_rows = _decoded_payloads(before), _decoded_payloads(after)
    if before_rows.keys() != after_rows.keys():
        raise ManagerRepairError(f"record-id set changed: {before.name}")
    return {record_id for record_id in before_rows if before_rows[record_id] != after_rows[record_id]}


def _stage_file(path: Path, payload: bytes, suffix: str) -> Path:
    staged = path.with_name(f".{path.name}.{suffix}.tmp")
    if staged.exists() or staged.is_symlink():
        raise ManagerRepairError(f"stale temporary output exists: {staged}")
    staged.write_bytes(payload)
    return staged


def _derive(
    *, package_path: Path, ledger: Mapping[str, Any], ledger_path: Path, ledger_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    return ledger_v1.apply_ledger(
        package, ledger,
        ledger_path=ledger_path.resolve().relative_to(ROOT).as_posix(),
        ledger_sha256=ledger_sha256,
    )


def repair(
    *, package_paths: Sequence[Path], compile_package_path: Path, ledger_path: Path,
    base_tree: Path, runtime_game: Path, receipt_path: Path, apply: bool,
) -> dict[str, Any]:
    package_paths = [path.resolve() for path in package_paths]
    if len(package_paths) != len(set(package_paths)):
        raise ManagerRepairError("each recipe mirror must be supplied once")
    compile_package_path = compile_package_path.resolve()
    if compile_package_path not in package_paths:
        raise ManagerRepairError("--compile-package must also be supplied through --package")
    ledger_path, base_tree = ledger_path.resolve(), base_tree.resolve()
    runtime_game, receipt_path = runtime_game.resolve(), receipt_path.resolve()
    if not ledger_path.is_file() or not base_tree.is_dir() or not runtime_game.is_dir():
        raise ManagerRepairError("manager ledger, clean base or runtime game is missing")
    try:
        ledger_path.relative_to(ROOT)
    except ValueError as exc:
        raise ManagerRepairError("manager ledger must be inside the workspace") from exc
    ledger_raw = ledger_path.read_bytes()
    ledger = json.loads(ledger_raw.decode("utf-8"))
    if not isinstance(ledger, dict):
        raise ManagerRepairError("manager ledger must be a JSON object")
    ledger_sha256 = hashlib.sha256(ledger_raw).hexdigest()

    plans = []
    for path in package_paths:
        derived, audit = _derive(
            package_path=path, ledger=ledger, ledger_path=ledger_path,
            ledger_sha256=ledger_sha256,
        )
        plans.append({
            "path": path, "before_sha256": _sha256(path), "package": derived,
            "after_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(derived)),
            "coverage": audit["coverage"],
        })
    coverage = plans[0]["coverage"]
    if any(plan["coverage"] != coverage for plan in plans[1:]):
        raise ManagerRepairError("current recipe mirrors disagree about manager evidence coverage")
    compile_plan = next(plan for plan in plans if plan["path"] == compile_package_path)
    package_v2.validate_package(compile_plan["package"], strict=True)

    live_jug = runtime_game / "DBDAT/JUG98030.FDI"
    live_eq = runtime_game / "DBDAT/EQ98030.FDI"
    live_ent = runtime_game / "DBDAT/ENT98030.FDI"
    for path in (live_jug, live_eq, live_ent):
        if not path.is_file() or path.is_symlink():
            raise ManagerRepairError(f"live database input is missing or unsafe: {path}")
    live_jug_before_sha256 = _sha256(live_jug)
    live_eq_before_sha256 = _sha256(live_eq)
    live_ent_before_sha256 = _sha256(live_ent)

    with tempfile.TemporaryDirectory(prefix="pm99-manager-repair-", dir=runtime_game.parent) as temporary:
        temporary_root = Path(temporary)
        compiled_games = []
        receipts = []
        for index in (1, 2):
            derived_path = temporary_root / f"season-package-{index}.json"
            derived_path.write_bytes(package_v2.canonical_json_bytes(compile_plan["package"]))
            game = temporary_root / f"game-{index}"
            # The compiler touches only its three database files and reads the
            # country table.  A minimal clean materialisation avoids copying
            # hundreds of megabytes of unrelated game media for every proof.
            for relative in (*compiler.DATABASE_RELATIVE_PATHS, compiler.COUNTRY_TABLE_RELATIVE_PATH):
                source, target = base_tree / relative, game / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            receipts.append(compiler.compile_package_to_tree(
                package_path=derived_path, base_tree=base_tree, materialisation_tree=game,
            ))
            compiled_games.append(game)
        first, second = compiled_games
        output_names = ("DBDAT/JUG98030.FDI", "DBDAT/EQ98030.FDI", "DBDAT/ENT98030.FDI")
        first_hashes = {name: _sha256(first / name) for name in output_names}
        second_hashes = {name: _sha256(second / name) for name in output_names}
        if first_hashes != second_hashes:
            raise ManagerRepairError("two clean manager builds produced different database hashes")
        if first_hashes["DBDAT/JUG98030.FDI"] != _sha256(live_jug):
            raise ManagerRepairError("manager-only build would change player data")

        binary_audit = audit_compiled_managers(
            compile_plan["package"], game=first,
            season=f"{int(compile_plan['package']['season']['start_year']):04d}-{int(compile_plan['package']['season']['end_year']) % 100:02d}",
        )
        if binary_audit["failure_count"]:
            raise ManagerRepairError(
                f"compiled manager readback failed: {binary_audit['failures'][:3]}"
            )

        season = ledger_v1._season_key(compile_plan["package"])
        evidence_manager_carriers = {
            int(manager["carrier_id"])
            for manager in compile_plan["package"]["managers"]
            if isinstance(manager, Mapping)
            and isinstance(manager.get("proof"), Mapping)
            and manager["proof"].get("artifact_id") == f"opening-manager-ledger-{season}"
        }
        evidence_club_carriers = {
            int(club["carrier_id"])
            for club in compile_plan["package"]["clubs"]
            if isinstance(club, Mapping)
            and str(club.get("manager_id") or "") in {
                str(manager["id"])
                for manager in compile_plan["package"]["managers"]
                if isinstance(manager, Mapping) and int(manager.get("carrier_id") or -1) in evidence_manager_carriers
            }
        }
        changed_eq = _changed_records(live_eq, first / "DBDAT/EQ98030.FDI")
        changed_ent = _changed_records(live_ent, first / "DBDAT/ENT98030.FDI")
        if changed_eq - evidence_club_carriers:
            raise ManagerRepairError(
                f"manager repair changed unrelated club records: {sorted(changed_eq - evidence_club_carriers)}"
            )
        if changed_ent - evidence_manager_carriers:
            raise ManagerRepairError(
                f"manager repair changed unrelated manager records: {sorted(changed_ent - evidence_manager_carriers)}"
            )

        staged_packages = [
            (plan["path"], _stage_file(
                plan["path"], package_v2.canonical_json_bytes(plan["package"]), "manager-repair"
            ))
            for plan in plans
        ]
        staged_eq = _stage_file(live_eq, (first / "DBDAT/EQ98030.FDI").read_bytes(), "manager-repair")
        staged_ent = _stage_file(live_ent, (first / "DBDAT/ENT98030.FDI").read_bytes(), "manager-repair")
        try:
            if apply:
                for target, staged in staged_packages:
                    os.replace(staged, target)
                os.replace(staged_eq, live_eq)
                os.replace(staged_ent, live_ent)
        finally:
            for _target, staged in staged_packages:
                if staged.exists() or staged.is_symlink():
                    staged.unlink()
            for staged in (staged_eq, staged_ent):
                if staged.exists() or staged.is_symlink():
                    staged.unlink()

    receipt = {
        "schema_version": SCHEMA,
        "season": season,
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "manager_ledger": {
            "path": ledger_path.relative_to(ROOT).as_posix(), "sha256": ledger_sha256,
        },
        "coverage": coverage,
        "packages": [
            {
                key: (
                    value.relative_to(ROOT).as_posix()
                    if key == "path" and isinstance(value, Path)
                    else value
                )
                for key, value in plan.items() if key != "package"
            }
            for plan in plans
        ],
        "deterministic_compile": {
            "first": first_hashes, "second": second_hashes,
            "identical": first_hashes == second_hashes,
            "clubs_written": receipts[0]["clubs_written"],
            "players_written": receipts[0]["players_written"],
            "managers_written": receipts[0]["managers_written"],
        },
        "runtime_refresh": {
            "game": runtime_game.relative_to(ROOT).as_posix(),
            "jug_unchanged_sha256": live_jug_before_sha256,
            "eq_before_sha256": live_eq_before_sha256,
            "eq_after_sha256": first_hashes["DBDAT/EQ98030.FDI"],
            "ent_before_sha256": live_ent_before_sha256,
            "ent_after_sha256": first_hashes["DBDAT/ENT98030.FDI"],
            "changed_club_carrier_count": len(changed_eq),
            "changed_manager_carrier_count": len(changed_ent),
        },
        "compiled_manager_readback_failure_count": binary_audit["failure_count"],
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(package_v2.canonical_json_bytes(receipt))
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--compile-package", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--runtime-game", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = repair(
            package_paths=args.package, compile_package_path=args.compile_package,
            ledger_path=args.ledger, base_tree=args.base_tree,
            runtime_game=args.runtime_game, receipt_path=args.receipt, apply=args.apply,
        )
    except (OSError, json.JSONDecodeError, ManagerRepairError, compiler.SeasonCompilerError,
            package_v2.PackageValidationError, ValueError) as exc:
        print(f"target-manager-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
