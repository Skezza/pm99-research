#!/usr/bin/env python3
"""Atomically promote one verified calendar correction into live season recipes.

The calendar compiler never overwrites an executable.  This narrow promotion
step is its counterpart for an existing alpha game: it binds the new receipt
to every mirrored recipe, archives the prior calendar pair by hash, and
changes only MANAGPRE.EXE in the live game after all preconditions pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_calendar_package_overlay_v1 as overlay  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-calendar-contract-repair-v1"


class CalendarContractRepairError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.calendar-contract.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise CalendarContractRepairError(f"temporary output already exists: {temporary}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def repair(
    *, packages: Sequence[Path], calendar_executable: Path, calendar_receipt: Path,
    calendar_store: Path, runtime_game: Path, expected_old_executable_sha256: str,
    receipt_path: Path, apply: bool,
) -> dict[str, Any]:
    resolved = [path.resolve() for path in packages]
    if not resolved or len(set(resolved)) != len(resolved):
        raise CalendarContractRepairError("supply each mirrored recipe exactly once")
    executable = calendar_executable.resolve()
    receipt_source = calendar_receipt.resolve()
    if not executable.is_file() or not receipt_source.is_file():
        raise CalendarContractRepairError("new calendar executable or receipt is unavailable")
    receipt_bytes = receipt_source.read_bytes()
    try:
        calendar = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarContractRepairError("new calendar receipt is invalid JSON") from exc
    if not isinstance(calendar, Mapping):
        raise CalendarContractRepairError("new calendar receipt is not an object")
    executable_sha256 = _sha256(executable)
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    patch_count = overlay._validated_patch_count(calendar)
    store = calendar_store.resolve()
    store_executable = store / "MANAGPRE.EXE"
    store_receipt = store / "calendar-receipt.json"
    runtime_executable = runtime_game.resolve() / "MANAGPRE.EXE"
    for path, label in ((store_executable, "stored calendar executable"), (store_receipt, "stored calendar receipt"),
                        (runtime_executable, "runtime executable")):
        if not path.is_file() or path.is_symlink():
            raise CalendarContractRepairError(f"{label} is unavailable: {path}")
    if _sha256(store_executable) != expected_old_executable_sha256 or _sha256(runtime_executable) != expected_old_executable_sha256:
        raise CalendarContractRepairError("stored or runtime executable no longer has the declared pre-repair hash")
    relative_receipt = str(store_receipt.relative_to(ROOT))
    plans: list[dict[str, Any]] = []
    for index, path in enumerate(resolved):
        package = package_v2.read_canonical_package(path)
        before = _sha256(path)
        rebound, audit = overlay.bind_calendar(
            package=package, receipt=calendar, receipt_relative_path=relative_receipt,
            receipt_sha256=receipt_sha256, executable_sha256=executable_sha256,
        )
        # The first path is the canonical strict package.  The remaining
        # source/alias/reconciled snapshots are validated for schema and
        # receive only identical calendar-artifact metadata; their expensive
        # person-identity validation was already established before this
        # calendar-only promotion.
        package_v2.validate_package(rebound, strict=index == 0)
        plans.append({"path": path, "before_sha256": before, "payload": package_v2.canonical_json_bytes(rebound), "audit": audit})
    current_receipt_sha256 = _sha256(store_receipt)
    archive = ROOT / ".local/calendar-history-v1/2004-05" / expected_old_executable_sha256
    result = {
        "schema_version": SCHEMA,
        "state": "applied-to-alpha-game-and-recipes" if apply else "validated-calendar-contract-repair",
        "calendar": {
            "old_executable_sha256": expected_old_executable_sha256,
            "new_executable_sha256": executable_sha256,
            "new_receipt_sha256": receipt_sha256,
            "patch_count": patch_count,
            "day_override_count": len(calendar.get("day_overrides", [])),
        },
        "archive": {"path": str(archive.relative_to(ROOT)), "old_receipt_sha256": current_receipt_sha256},
        "packages": [
            {"path": str(plan["path"].relative_to(ROOT)), "before_sha256": plan["before_sha256"],
             "after_sha256": hashlib.sha256(plan["payload"]).hexdigest()} for plan in plans
        ],
        "runtime_executable": str(runtime_executable.relative_to(ROOT)),
    }
    if not apply:
        return result
    archive.mkdir(parents=True, exist_ok=True)
    for source, destination in ((store_executable, archive / "MANAGPRE.EXE"), (store_receipt, archive / "calendar-receipt.json")):
        if destination.exists():
            if _sha256(destination) != _sha256(source):
                raise CalendarContractRepairError(f"calendar history collision: {destination}")
        else:
            shutil.copyfile(source, destination)
    # Stage every byte before changing any live path.
    staged: list[tuple[Path, Path]] = []
    for plan in plans:
        target = plan["path"]
        temporary = target.with_name(f".{target.name}.calendar-contract.stage")
        if temporary.exists() or temporary.is_symlink():
            raise CalendarContractRepairError(f"staging path already exists: {temporary}")
        temporary.write_bytes(plan["payload"])
        staged.append((temporary, target))
    for target, payload in ((store_executable, executable.read_bytes()), (store_receipt, receipt_bytes),
                            (runtime_executable, executable.read_bytes())):
        temporary = target.with_name(f".{target.name}.calendar-contract.stage")
        if temporary.exists() or temporary.is_symlink():
            raise CalendarContractRepairError(f"staging path already exists: {temporary}")
        temporary.write_bytes(payload)
        staged.append((temporary, target))
    for temporary, target in staged:
        os.replace(temporary, target)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(receipt_path, package_v2.canonical_json_bytes(result))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--calendar-executable", type=Path, required=True)
    parser.add_argument("--calendar-receipt", type=Path, required=True)
    parser.add_argument("--calendar-store", type=Path, required=True)
    parser.add_argument("--runtime-game", type=Path, required=True)
    parser.add_argument("--expected-old-executable-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = repair(
            packages=args.package, calendar_executable=args.calendar_executable,
            calendar_receipt=args.calendar_receipt, calendar_store=args.calendar_store,
            runtime_game=args.runtime_game, expected_old_executable_sha256=args.expected_old_executable_sha256,
            receipt_path=args.receipt, apply=args.apply,
        )
    except (CalendarContractRepairError, overlay.CalendarOverlayError, OSError, ValueError) as exc:
        parser.exit(2, f"calendar-contract-repair: {exc}\n")
    print(json.dumps({"state": result["state"], "patch_count": result["calendar"]["patch_count"],
                      "package_count": len(result["packages"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
