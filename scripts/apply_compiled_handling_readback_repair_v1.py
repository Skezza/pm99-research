#!/usr/bin/env python3
"""Repair a proven old compiler Handling readback drift in a live alpha game.

This is deliberately narrower than a rebuild.  It accepts only a direct
carrier-ID readback failure where the recipe contains a valid outfield value
but the live JUG value is outside the outfield range.  The current compiler
produces a parser-safe replacement for that one record; all other decoded JUG
payloads must remain byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.apply_position_handling_repair_v1 import (  # noqa: E402
    HandlingRepairError,
    _refresh_live_jug,
)
from scripts.pm99_season_qa_v1 import OUTFIELD_HANDLING_MAXIMUM, audit_compiled_handling  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-direct-compiled-handling-readback-repair-v1"


class ReadbackRepairError(ValueError):
    """The observed compiler readback mismatch is outside this bounded repair."""


def _target_ids(package: Mapping[str, Any], *, game: Path) -> tuple[set[str], list[dict[str, Any]]]:
    players = package.get("players")
    if not isinstance(players, list):
        raise ReadbackRepairError("package has no players")
    by_carrier = {
        int(player["carrier_id"]): player
        for player in players
        if isinstance(player, Mapping)
        and isinstance(player.get("id"), str)
        and isinstance(player.get("carrier_id"), int)
    }
    audit = audit_compiled_handling(package, game=game)
    targets: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for failure in audit["failures"]:
        if not isinstance(failure, Mapping):
            raise ReadbackRepairError("compiled Handling audit contains a malformed failure")
        record_id = failure.get("record_id")
        runtime_record_id = failure.get("runtime_record_id")
        position = failure.get("position")
        recipe_handling = failure.get("handling")
        runtime_handling = failure.get("runtime_handling")
        if not (
            isinstance(record_id, int)
            and runtime_record_id == record_id
            and failure.get("resolution") == "carrier-id"
            and position in {"D", "M", "F"}
            and isinstance(recipe_handling, int)
            and 1 <= recipe_handling <= OUTFIELD_HANDLING_MAXIMUM
            and isinstance(runtime_handling, int)
            and runtime_handling > OUTFIELD_HANDLING_MAXIMUM
            and record_id in by_carrier
        ):
            raise ReadbackRepairError(
                "compiled Handling failure is not the known bounded outfield readback drift: "
                + json.dumps(dict(failure), ensure_ascii=False, sort_keys=True)
            )
        player_id = str(by_carrier[record_id]["id"])
        targets.add(player_id)
        accepted.append({
            "player_id": player_id,
            "record_id": record_id,
            "name": failure.get("name"),
            "position": position,
            "recipe_handling": recipe_handling,
            "runtime_handling_before": runtime_handling,
        })
    return targets, accepted


def repair(
    *, package_path: Path, base_tree: Path, runtime_game: Path, receipt_path: Path, apply: bool,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    runtime_game = runtime_game.resolve()
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    target_ids, accepted = _target_ids(package, game=runtime_game)
    if not target_ids:
        receipt = {
            "schema_version": SCHEMA,
            "season": f"{package['season']['start_year']:04d}-{package['season']['end_year'] % 100:02d}",
            "state": "no-bounded-readback-repair-required",
            "targets": [],
        }
        if apply:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(package_v2.canonical_json_bytes(receipt))
        return receipt
    try:
        live = _refresh_live_jug(
            package_path=package_path,
            base_tree=base_tree.resolve(),
            runtime_game=runtime_game,
            target_ids=target_ids,
            apply=apply,
        )
    except HandlingRepairError as exc:
        raise ReadbackRepairError(str(exc)) from exc
    after = audit_compiled_handling(package, game=runtime_game) if apply else None
    if after is not None:
        remaining_target_records = {
            int(row.get("record_id"))
            for row in after["failures"]
            if isinstance(row, Mapping) and isinstance(row.get("record_id"), int)
        } & {int(row["record_id"]) for row in accepted}
        if remaining_target_records:
            raise ReadbackRepairError(
                f"direct readback repair did not clear carriers: {sorted(remaining_target_records)}"
            )
    receipt = {
        "schema_version": SCHEMA,
        "season": f"{package['season']['start_year']:04d}-{package['season']['end_year'] % 100:02d}",
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "reason": "carrier-id readback drift with invalid live outfield Handling",
        "targets": accepted,
        "runtime_refresh": live,
        "remaining_compiled_handling_failure_count": (
            int(after["failure_count"]) if after is not None else None
        ),
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(package_v2.canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--runtime-game", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = repair(
            package_path=args.package,
            base_tree=args.base_tree,
            runtime_game=args.runtime_game,
            receipt_path=args.receipt,
            apply=args.apply,
        )
    except (ReadbackRepairError, compiler.SeasonCompilerError, OSError, ValueError) as exc:
        print(f"direct-compiled-handling-readback-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "season": receipt["season"],
        "state": receipt["state"],
        "target_count": len(receipt["targets"]),
        "runtime_changed_carrier_count": receipt.get("runtime_refresh", {}).get("changed_carrier_count"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
