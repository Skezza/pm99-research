#!/usr/bin/env python3
"""Repair every proven ``XXX`` nationality fallback without rebuilding a game.

The recipe already holds each player's declared nationality.  This command is
therefore deliberately a one-byte, carrier-ID repair of the live JUG file:
it maps the declared source code through the shared compiler table, accepts
only an old ``XXX`` runtime value, and proves that no other decoded payload or
byte inside a target payload changed.  It is safe to run on every preferred
season because unrepresentable PM99 countries and explicit ``UNK`` values are
reported but never substituted.
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

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import season_package_compiler_v2 as compiler  # noqa: E402
from scripts.build_2015_english92_release import (  # noqa: E402
    UNKNOWN_NATIONALITY,
    UNREPRESENTABLE_NATIONALITY,
    _country_code,
)
from scripts.pm99_season_play_v1 import REVISIONS, game_path  # noqa: E402
from scripts.pm99_season_qa_v1 import resolve_package  # noqa: E402


SCHEMA = "pm99-season-direct-compiled-nationality-readback-repair-v1"


class NationalityRepairError(ValueError):
    """The observed nationality issue is outside the bounded repair lane."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _season_label(package: Mapping[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, Mapping):
        raise NationalityRepairError("package has no season object")
    try:
        return f"{int(season['start_year']):04d}-{int(season['end_year']) % 100:02d}"
    except (KeyError, TypeError, ValueError) as exc:
        raise NationalityRepairError("package season is malformed") from exc


def _nationality_offset(payload: bytes, *, carrier: int, declared_family: str) -> int:
    family = payload[2:5]
    if declared_family == "dd6361" and family == b"\xdd\x63\x61":
        offset = compiler._find_dd6361_name_end(payload) + 8
    elif declared_family == "dd6360" and family == b"\xdd\x63\x60":
        offset = int(compiler._native_dd6360_role_start(payload)) + 8
    else:
        raise NationalityRepairError(
            f"carrier {carrier} has {family.hex()} but recipe declares {declared_family}"
        )
    if offset < 0 or offset >= len(payload):
        raise NationalityRepairError(f"carrier {carrier} nationality offset is outside its payload")
    return offset


def _decoded_payloads(data: bytes) -> dict[int, bytes]:
    return {
        int(entry.record_id): entry.decode_payload(data)
        for entry in IndexedFDIFile.from_bytes(data).entries
    }


def _plan(package: Mapping[str, Any], *, jug_data: bytes, textos_path: Path) -> dict[str, Any]:
    players = package.get("players")
    if not isinstance(players, list):
        raise NationalityRepairError("package has no players list")
    country_codes = compiler._extract_country_codes_from_textos(textos_path)
    if "XXX" not in country_codes:
        raise NationalityRepairError("TEXTOS country table has no XXX row")
    xxx_code = int(country_codes["XXX"])
    payloads = _decoded_payloads(jug_data)
    targets: list[dict[str, Any]] = []
    already_correct: list[dict[str, Any]] = []
    existing_non_xxx_mismatches: list[dict[str, Any]] = []
    explicitly_unrepresentable: list[dict[str, Any]] = []
    explicitly_unknown: list[dict[str, Any]] = []
    skipped_preserved: list[dict[str, Any]] = []
    seen_carriers: set[int] = set()

    for player in players:
        if not isinstance(player, Mapping):
            raise NationalityRepairError("package players contain a non-object row")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            raise NationalityRepairError(f"player {player.get('id')!r} has no facts object")
        source_code = facts.get("nationality")
        common = {
            "player_id": str(player.get("id") or ""),
            "name": str(player.get("name") or ""),
            "carrier_id": int(player.get("carrier_id") or 0),
        }
        if isinstance(source_code, Mapping):
            if source_code.get("policy") != "preserve-existing-mode1":
                raise NationalityRepairError(
                    f"player {common['player_id']!r} has unsupported nationality policy"
                )
            skipped_preserved.append(common)
            continue
        if not isinstance(source_code, str):
            raise NationalityRepairError(f"player {common['player_id']!r} has a non-text nationality")
        code = source_code.strip().upper()
        row = {**common, "source_nationality": code}
        if code in UNKNOWN_NATIONALITY:
            explicitly_unknown.append(row)
            continue
        if code in UNREPRESENTABLE_NATIONALITY:
            explicitly_unrepresentable.append(row)
            continue
        expected = _country_code(code, country_codes)
        if expected == xxx_code:
            raise NationalityRepairError(
                f"representable nationality {code!r} unexpectedly resolves to XXX"
            )
        carrier = common["carrier_id"]
        if carrier <= 0 or carrier in seen_carriers:
            raise NationalityRepairError(f"player carrier ownership is malformed for {common['player_id']!r}")
        seen_carriers.add(carrier)
        payload = payloads.get(carrier)
        if payload is None:
            raise NationalityRepairError(f"live JUG lacks package carrier {carrier}")
        offset = _nationality_offset(
            payload, carrier=carrier, declared_family=str(player.get("carrier_family") or ""),
        )
        observed = int(payload[offset] ^ 0x61)
        row.update({"expected_country_code": expected, "runtime_country_code_before": observed})
        if observed == expected:
            already_correct.append(row)
        elif observed == xxx_code:
            targets.append({**row, "decoded_offset": offset})
        else:
            # This bounded repair exists only for the silent XXX fallback.
            # A different live country is evidence of a separate source or
            # historic-build discrepancy, not authority to overwrite it.
            existing_non_xxx_mismatches.append(row)

    return {
        "target_count": len(targets),
        "targets": sorted(targets, key=lambda row: int(row["carrier_id"])),
        "already_correct_count": len(already_correct),
        "existing_non_xxx_mismatch_count": len(existing_non_xxx_mismatches),
        "existing_non_xxx_mismatches": existing_non_xxx_mismatches,
        "explicit_unknown_count": len(explicitly_unknown),
        "explicit_unknown": explicitly_unknown,
        "unrepresentable_count": len(explicitly_unrepresentable),
        "unrepresentable": explicitly_unrepresentable,
        "preserved_field_count": len(skipped_preserved),
    }


def repair(*, package_path: Path, runtime_game: Path, receipt_path: Path, apply: bool) -> dict[str, Any]:
    package_path = package_path.resolve()
    runtime_game = runtime_game.resolve()
    if not package_path.is_file() or not runtime_game.is_dir():
        raise NationalityRepairError("package or runtime game is unavailable")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NationalityRepairError(f"cannot read package {package_path}") from exc
    if not isinstance(package, Mapping):
        raise NationalityRepairError("package root is not an object")
    jug_path = runtime_game / "DBDAT/JUG98030.FDI"
    textos_path = runtime_game / "DBDAT/TEXTOS.PKF"
    if not jug_path.is_file() or not textos_path.is_file():
        raise NationalityRepairError("runtime game lacks JUG98030.FDI or TEXTOS.PKF")
    original = jug_path.read_bytes()
    plan = _plan(package, jug_data=original, textos_path=textos_path)
    targets = plan["targets"]
    replacements: dict[int, bytes] = {}
    before_payloads = _decoded_payloads(original)
    for row in targets:
        carrier, offset, expected = (
            int(row["carrier_id"]), int(row["decoded_offset"]), int(row["expected_country_code"]),
        )
        patched = bytearray(before_payloads[carrier])
        patched[offset] = expected ^ 0x61
        replacements[carrier] = bytes(patched)
    rebuilt = compiler._rebuild_indexed(original, IndexedFDIFile.from_bytes(original), replacements)
    after_payloads = _decoded_payloads(rebuilt)
    if before_payloads.keys() != after_payloads.keys():
        raise NationalityRepairError("repair changed the JUG carrier set")
    changed_carriers = sorted(
        carrier for carrier in before_payloads if before_payloads[carrier] != after_payloads[carrier]
    )
    expected_carriers = sorted(replacements)
    if changed_carriers != expected_carriers:
        raise NationalityRepairError(
            f"repair changed unexpected JUG carriers: expected {expected_carriers}, got {changed_carriers}"
        )
    for row in targets:
        carrier, offset, expected = (
            int(row["carrier_id"]), int(row["decoded_offset"]), int(row["expected_country_code"]),
        )
        different_offsets = [
            index for index, pair in enumerate(zip(before_payloads[carrier], after_payloads[carrier], strict=True))
            if pair[0] != pair[1]
        ]
        if different_offsets != [offset]:
            raise NationalityRepairError(
                f"carrier {carrier} changed outside nationality byte: {different_offsets[:10]}"
            )
        if int(after_payloads[carrier][offset] ^ 0x61) != expected:
            raise NationalityRepairError(f"carrier {carrier} nationality did not read back")

    before_sha256 = _sha256(jug_path)
    after_sha256 = hashlib.sha256(rebuilt).hexdigest()
    if apply and targets:
        temporary = jug_path.with_name(f".{jug_path.name}.nationality-repair.tmp")
        if temporary.exists() or temporary.is_symlink():
            raise NationalityRepairError(f"temporary repair already exists: {temporary}")
        temporary.write_bytes(rebuilt)
        os.replace(temporary, jug_path)
        if _sha256(jug_path) != after_sha256:
            raise NationalityRepairError("live JUG hash differs after atomic nationality replacement")

    receipt = {
        "schema_version": SCHEMA,
        "season": _season_label(package),
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "package": str(package_path.relative_to(ROOT)),
        "package_sha256": _sha256(package_path),
        "runtime_game": str(runtime_game.relative_to(ROOT)),
        "jug_before_sha256": before_sha256,
        "jug_after_sha256": after_sha256,
        "byte_contract": {
            "jug_before_sha256": before_sha256,
            "jug_after_sha256": after_sha256,
            "eq_unchanged_sha256": _sha256(runtime_game / "DBDAT/EQ98030.FDI"),
            "ent_unchanged_sha256": _sha256(runtime_game / "DBDAT/ENT98030.FDI"),
        },
        "runtime_changed_carrier_count": len(changed_carriers),
        "targets": [{key: value for key, value in row.items() if key != "decoded_offset"} for row in targets],
        "already_correct_representable_count": plan["already_correct_count"],
        "existing_non_xxx_mismatch_count": plan["existing_non_xxx_mismatch_count"],
        "existing_non_xxx_mismatches": plan["existing_non_xxx_mismatches"],
        "explicit_unknown_nationality_count": plan["explicit_unknown_count"],
        "unrepresentable_nationality_count": plan["unrepresentable_count"],
        "unrepresentable_nationalities": plan["unrepresentable"],
        "preserved_nationality_field_count": plan["preserved_field_count"],
        "contract": "only a target carrier's decoded nationality byte may change; non-XXX values are refused",
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="YYYY-YY or all")
    parser.add_argument("--apply", action="store_true", help="atomically write the bounded JUG repairs")
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / ".local/season-nationality-repair-v1",
        help="where per-season immutable repair receipts are written",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    seasons = [*sorted(REVISIONS), "2015-16"] if args.season == "all" else [args.season]
    unknown = [season for season in seasons if season not in {*REVISIONS, "2015-16"}]
    if unknown:
        raise SystemExit(f"compiled-nationality-repair: unsupported season {unknown[0]!r}")
    summaries = []
    try:
        for season in seasons:
            receipt = repair(
                package_path=resolve_package(season), runtime_game=game_path(season),
                receipt_path=args.output_root / season / "repair-receipt.json", apply=args.apply,
            )
            summary = {
                "season": season,
                "target_count": len(receipt["targets"]),
                "changed_carrier_count": receipt["runtime_changed_carrier_count"],
                "unrepresentable_count": receipt["unrepresentable_nationality_count"],
                "existing_non_xxx_mismatch_count": receipt["existing_non_xxx_mismatch_count"],
            }
            summaries.append(summary)
            print(json.dumps(summary, sort_keys=True), flush=True)
    except (NationalityRepairError, OSError, ValueError) as exc:
        print(f"compiled-nationality-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "season_count": len(summaries),
        "target_count": sum(int(row["target_count"]) for row in summaries),
        "changed_carrier_count": sum(int(row["changed_carrier_count"]) for row in summaries),
        "unrepresentable_count": sum(int(row["unrepresentable_count"]) for row in summaries),
        "existing_non_xxx_mismatch_count": sum(int(row["existing_non_xxx_mismatch_count"]) for row in summaries),
        "seasons": summaries,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
