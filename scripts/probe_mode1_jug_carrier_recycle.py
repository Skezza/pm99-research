#!/usr/bin/env python3
"""Build a disposable cross-mode JUG-carrier recycle runtime probe.

The probe appends a *mode-0 dd6361* clone, moves its original English roster
row to that new carrier, then reuses the now-unrostered old ID for a compact
mode-1 clone.  It is the smallest way to test whether PM99 rejects an enlarged
foreign JUG directory specifically, rather than the historical ID itself.

This is research tooling only.  It must not be used as a release builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import _patch_indexed_player_variable_name_payload  # noqa: E402
from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.eq_team_indexed_metadata import extract_indexed_team_payload_metadata  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from app.xor import xor_decode  # noqa: E402
from scripts.build_2015_english92_release import _rebuild_indexed, _rewrite_roster_tail  # noqa: E402
from scripts.season_package_compiler_v2 import (  # noqa: E402
    _append_indexed_fdi_records,
    _assert_mode1_roster_tails_match_plan,
    _mode1_roster_tails,
    _source_roster_owners,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-game", required=True, type=Path)
    parser.add_argument("--output-game", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--mode0-team-record-id", required=True, type=int)
    parser.add_argument("--mode0-slot", required=True, type=int)
    parser.add_argument("--mode1-team-record-id", required=True, type=int)
    parser.add_argument("--mode1-slot", required=True, type=int)
    parser.add_argument("--new-mode0-player-id", required=True, type=int)
    parser.add_argument("--mode1-clone-player-id", type=int)
    parser.add_argument(
        "--mode0-source-role-set",
        help=(
            "research-only six-slot dd6361 tactical role vector for the appended "
            "mode-0 clone; values are 0..17 or 98 for native unassigned"
        ),
    )
    parser.add_argument("--name", default="Recycle Probe")
    parser.add_argument(
        "--mode1-keep-recycled-payload",
        action="store_true",
        help="leave the recycled carrier's original JUG bytes untouched; control for the paired runtime record",
    )
    return parser.parse_args()


def _parse_role_set(value: str | None) -> list[int] | None:
    """Parse an explicit dd6361 role-window control without inventing a hierarchy."""

    if value is None:
        return None
    raw_values = [item.strip() for item in value.split(",")]
    if len(raw_values) != 6:
        raise ValueError("--mode0-source-role-set requires exactly six comma-separated values")
    roles = [int(item) for item in raw_values]
    if any(role not in {*range(18), 98} for role in roles):
        raise ValueError("--mode0-source-role-set supports PM99 role codes 0..17 and 98 only")
    if not any(role != 98 for role in roles):
        raise ValueError("--mode0-source-role-set requires at least one active tactical role")
    return roles


def _set_dd6361_role_set(payload: bytes, roles: list[int]) -> tuple[bytes, dict[str, object]]:
    """Patch only the proven dd6361 six-slot role window for a disposable probe.

    The source player is immediately moved to a newly appended ID, so this
    control lets the runner distinguish the *role-vector compatibility* of an
    existing mode-0 carrier from merely the availability of an old JUG ID.
    It deliberately preserves the variable-name area, shirt/order bytes and
    every opaque suffix byte.
    """

    if payload[2:5] != b"\xdd\x63\x61":
        raise ValueError("mode-0 source role control requires a dd6361 payload")
    if len(roles) != 6 or any(role not in {*range(18), 98} for role in roles):
        raise ValueError("dd6361 role control received an invalid six-slot role vector")

    # The conservative anchor is shared with the release builder.  It begins
    # after the full variable name; the role bytes are two positions later.
    from scripts.build_2015_english92_release import _find_dd6361_name_end

    name_end = _find_dd6361_name_end(payload)
    start = int(name_end) + 2
    if start + 6 > len(payload):
        raise ValueError("dd6361 role control window overruns payload")
    result = bytearray(payload)
    before = [((result[start + slot] ^ 0x61) - 1) if (result[start + slot] ^ 0x61) else 98 for slot in range(6)]
    for slot, role in enumerate(roles):
        stored = 0 if role == 98 else int(role) + 1
        result[start + slot] = stored ^ 0x61
    after = [((result[start + slot] ^ 0x61) - 1) if (result[start + slot] ^ 0x61) else 98 for slot in range(6)]
    changed_offsets = [offset for offset in range(start, start + 6) if payload[offset] != result[offset]]
    if any(payload[offset] != result[offset] for offset in range(len(payload)) if offset not in set(changed_offsets)):
        raise AssertionError("dd6361 role control altered bytes outside its six-slot window")
    return bytes(result), {
        "decoded_role_window_offset": start,
        "before": before,
        "after": after,
        "changed_payload_offsets": changed_offsets,
    }


def _team_roster(eq_data: bytes, index: IndexedFDIFile, team_id: int):
    entry = next((item for item in index.entries if int(item.record_id) == team_id), None)
    if entry is None:
        raise ValueError(f"EQ carrier {team_id} is absent")
    raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
    metadata = extract_indexed_team_payload_metadata(raw)
    roster = parse_eq_external_team_roster_payload(raw, {})
    if roster is None or not roster.rows:
        raise ValueError(f"EQ carrier {team_id} has no parser-backed roster")
    return entry, raw, metadata, roster


def main() -> int:
    args = _args()
    try:
        source_role_set = _parse_role_set(args.mode0_source_role_set)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    base_game = args.base_game.expanduser().resolve()
    output_game = args.output_game.expanduser().resolve()
    receipt_path = args.receipt.expanduser().resolve()
    if not base_game.is_dir() or not (base_game / "DBDAT").is_dir():
        raise SystemExit("--base-game must contain DBDAT")
    if output_game.exists():
        raise SystemExit("--output-game must not already exist")
    if not 1 <= args.new_mode0_player_id <= 0xFFFFFFFF:
        raise SystemExit("--new-mode0-player-id must fit uint32")

    eq_base = (base_game / "DBDAT" / "EQ98030.FDI").read_bytes()
    jug_base = (base_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    eq_index = IndexedFDIFile.from_bytes(eq_base)
    jug_index = IndexedFDIFile.from_bytes(jug_base)
    mode0_entry, mode0_raw, mode0_meta, mode0_roster = _team_roster(eq_base, eq_index, args.mode0_team_record_id)
    mode1_entry, mode1_raw, mode1_meta, mode1_roster = _team_roster(eq_base, eq_index, args.mode1_team_record_id)
    if int(mode0_meta["record_mode"]) != 0 or int(mode1_meta["record_mode"]) != 1:
        raise SystemExit("probe requires exactly one mode-0 team and one mode-1 team")
    if not 0 <= args.mode0_slot < len(mode0_roster.rows) or not 0 <= args.mode1_slot < len(mode1_roster.rows):
        raise SystemExit("requested roster slot is outside its team tail")

    owners, _rosters, modes = _source_roster_owners(eq_base)
    existing_ids = {int(entry.record_id) for entry in jug_index.entries}
    if args.new_mode0_player_id in existing_ids or args.new_mode0_player_id in owners:
        raise SystemExit("new mode-0 carrier already exists or is referenced")
    recycled_id = int(mode0_roster.rows[args.mode0_slot].player_record_id)
    if owners.get(recycled_id) != [args.mode0_team_record_id] or modes.get(args.mode0_team_record_id) != 0:
        raise SystemExit("recycled carrier must be owned by exactly the selected mode-0 team")
    mode0_source = next(entry for entry in jug_index.entries if int(entry.record_id) == recycled_id)
    mode0_payload = mode0_source.decode_payload(jug_base)
    if mode0_payload[2:5] != b"\xdd\x63\x61":
        raise SystemExit("selected recyclable mode-0 carrier must be dd6361")
    source_role_control: dict[str, object] | None = None
    if source_role_set is not None:
        mode0_payload, source_role_control = _set_dd6361_role_set(mode0_payload, source_role_set)
    mode1_source = None
    name_proof: dict[str, object] | None = None
    renamed_compact: bytes | None = None
    if not args.mode1_keep_recycled_payload:
        if args.mode1_clone_player_id is None:
            raise SystemExit("--mode1-clone-player-id is required unless --mode1-keep-recycled-payload is used")
        mode1_source = next((entry for entry in jug_index.entries if int(entry.record_id) == args.mode1_clone_player_id), None)
        if mode1_source is None:
            raise SystemExit("mode-1 clone player is absent")
        if modes.get(next(iter(owners.get(args.mode1_clone_player_id, [])), -1)) != 1:
            raise SystemExit("mode-1 clone player is not owned by a mode-1 team")
        compact_payload = mode1_source.decode_payload(jug_base)
        if compact_payload[2:5] != b"\xdd\x63\x60":
            raise SystemExit("mode-1 clone player must be compact dd6360")
        compact_record = PlayerRecord.from_bytes(compact_payload, mode1_source.payload_offset)
        renamed_compact, name_proof = _patch_indexed_player_variable_name_payload(
            compact_payload, compact_record.name, args.name
        )

    appended = _append_indexed_fdi_records(
        original=jug_base,
        records=[(args.new_mode0_player_id, mode0_source.key, mode0_payload)],
    )
    appended_index = IndexedFDIFile.from_bytes(appended)
    rewritten_jug = (
        appended
        if args.mode1_keep_recycled_payload
        else _rebuild_indexed(appended, appended_index, {recycled_id: renamed_compact})
    )

    mode0_ids = [int(row.player_record_id) for row in mode0_roster.rows]
    mode1_ids = [int(row.player_record_id) for row in mode1_roster.rows]
    mode0_ids[args.mode0_slot] = args.new_mode0_player_id
    mode1_ids[args.mode1_slot] = recycled_id
    rewritten_eq = _rebuild_indexed(
        eq_base,
        eq_index,
        {
            int(mode0_entry.record_id): xor_decode(_rewrite_roster_tail(mode0_raw, mode0_ids)),
            int(mode1_entry.record_id): xor_decode(_rewrite_roster_tail(mode1_raw, mode1_ids)),
        },
    )
    _assert_mode1_roster_tails_match_plan(
        before=_mode1_roster_tails(eq_base),
        after_eq_data=rewritten_eq,
        planned_player_ids={args.mode1_team_record_id: mode1_ids},
    )
    checked_mode0 = _team_roster(rewritten_eq, IndexedFDIFile.from_bytes(rewritten_eq), args.mode0_team_record_id)[3]
    if [int(row.player_record_id) for row in checked_mode0.rows] != mode0_ids:
        raise RuntimeError("mode-0 tail read-back failed")
    if [int(row.flag) for row in checked_mode0.rows] != [int(row.flag) for row in mode0_roster.rows]:
        raise RuntimeError("mode-0 row flags changed")

    shutil.copytree(
        base_game,
        output_game,
        symlinks=True,
        ignore=shutil.ignore_patterns("SAVE", "output", "wineprefix", "*.png", "*.log"),
    )
    (output_game / "DBDAT" / "JUG98030.FDI").write_bytes(rewritten_jug)
    (output_game / "DBDAT" / "EQ98030.FDI").write_bytes(rewritten_eq)
    output_jug = (output_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    verified = next(entry for entry in IndexedFDIFile.from_bytes(output_jug).entries if int(entry.record_id) == recycled_id)
    observed_name = PlayerRecord.from_bytes(verified.decode_payload(output_jug), verified.payload_offset).name
    if not args.mode1_keep_recycled_payload and observed_name.casefold() != args.name.casefold():
        raise RuntimeError(f"recycled compact player did not read back as {args.name!r}: {observed_name!r}")

    receipt = {
        "schema_version": "pm99-mode1-carrier-recycle-probe-v1",
        "result": "pass",
        "scope": "disposable-cross-mode-carrier-recycle-not-a-season-release",
        "mode0": {
            "team_record_id": args.mode0_team_record_id,
            "slot": args.mode0_slot,
            "recycled_player_id": recycled_id,
            "new_appended_player_id": args.new_mode0_player_id,
            "preserved_row_flag": int(mode0_roster.rows[args.mode0_slot].flag),
            "source_role_control": source_role_control,
        },
        "mode1": {
            "team_record_id": args.mode1_team_record_id,
            "slot": args.mode1_slot,
            "recycled_player_id": recycled_id,
            "clone_player_id": args.mode1_clone_player_id,
            "kept_recycled_payload": bool(args.mode1_keep_recycled_payload),
            "preserved_row_flag": int(mode1_roster.rows[args.mode1_slot].flag),
            "name": observed_name,
            "name_anchor": name_proof,
        },
        "base_game_dbdat": {
            "eq98030_sha256": _sha256(base_game / "DBDAT" / "EQ98030.FDI"),
            "jug98030_sha256": _sha256(base_game / "DBDAT" / "JUG98030.FDI"),
        },
        "output_dbdat": {
            "eq98030_sha256": _sha256(output_game / "DBDAT" / "EQ98030.FDI"),
            "jug98030_sha256": _sha256(output_game / "DBDAT" / "JUG98030.FDI"),
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "pass", "output_game": str(output_game), "receipt": str(receipt_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
