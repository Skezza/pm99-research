#!/usr/bin/env python3
"""Create a bounded mode-0 indexed-JUG append control from a clean PM99 tree.

This is a research probe for the one missing English 25-player carrier route.
It clones one existing *mode-0-only* dd6361 player into a fresh JUG directory
ID, rewires one existing mode-0 EQ roster slot, and leaves every mode-1 roster
tail untouched.  It is intentionally not a public database editor command.
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
    parser.add_argument("--team-record-id", required=True, type=int)
    parser.add_argument("--slot", required=True, type=int, help="zero-based existing roster slot to replace")
    parser.add_argument("--new-player-id", required=True, type=int)
    parser.add_argument("--clone-player-id", type=int, help="mode-0-only dd6361 source; default is replaced player")
    parser.add_argument("--name", default="Append Probe", help="visible name for the new JUG carrier")
    return parser.parse_args()


def main() -> int:
    args = _args()
    base_game = args.base_game.expanduser().resolve()
    output_game = args.output_game.expanduser().resolve()
    receipt_path = args.receipt.expanduser().resolve()
    if not base_game.is_dir() or not (base_game / "DBDAT").is_dir():
        raise SystemExit("--base-game must contain DBDAT")
    if output_game.exists():
        raise SystemExit("--output-game must not already exist")
    if output_game == base_game or output_game in base_game.parents:
        raise SystemExit("--output-game must be distinct from --base-game")
    if args.new_player_id < 1 or args.new_player_id > 0xFFFFFFFF:
        raise SystemExit("--new-player-id must fit uint32")

    eq_base = (base_game / "DBDAT" / "EQ98030.FDI").read_bytes()
    jug_base = (base_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    eq_index = IndexedFDIFile.from_bytes(eq_base)
    jug_index = IndexedFDIFile.from_bytes(jug_base)
    entries = {entry.record_id: entry for entry in eq_index.entries}
    team = entries.get(args.team_record_id)
    if team is None:
        raise SystemExit(f"mode-0 target EQ carrier {args.team_record_id} is absent")
    team_raw = eq_base[team.payload_offset : team.payload_offset + team.payload_length]
    if int(extract_indexed_team_payload_metadata(team_raw)["record_mode"]) != 0:
        raise SystemExit(f"EQ carrier {args.team_record_id} is not mode 0")
    team_roster = parse_eq_external_team_roster_payload(team_raw, {})
    if team_roster is None or not team_roster.rows:
        raise SystemExit(f"EQ carrier {args.team_record_id} has no parser-backed roster")
    if args.slot < 0 or args.slot >= len(team_roster.rows):
        raise SystemExit(f"--slot must be 0..{len(team_roster.rows) - 1}")

    owners, _rosters, modes = _source_roster_owners(eq_base)
    existing_jug_ids = {entry.record_id for entry in jug_index.entries}
    if args.new_player_id in existing_jug_ids or args.new_player_id in owners:
        raise SystemExit("--new-player-id already exists or is referenced by an EQ roster")
    replaced_id = int(team_roster.rows[args.slot].player_record_id)
    clone_id = int(args.clone_player_id if args.clone_player_id is not None else replaced_id)
    clone = next((entry for entry in jug_index.entries if entry.record_id == clone_id), None)
    if clone is None:
        raise SystemExit(f"clone JUG carrier {clone_id} is absent")
    clone_owners = owners.get(clone_id, [])
    if not clone_owners or any(modes.get(owner) != 0 for owner in clone_owners):
        raise SystemExit(f"clone JUG carrier {clone_id} is not mode-0-only")
    clone_payload = clone.decode_payload(jug_base)
    if clone_payload[2:5] != b"\xdd\x63\x61":
        raise SystemExit("append probe only supports a dd6361 clone source")
    clone_record = PlayerRecord.from_bytes(clone_payload, clone.payload_offset)
    renamed_payload, name_proof = _patch_indexed_player_variable_name_payload(
        clone_payload, clone_record.name, args.name
    )

    baseline_mode1_tails = _mode1_roster_tails(eq_base)
    appended_jug = _append_indexed_fdi_records(
        original=jug_base,
        records=[(args.new_player_id, clone.key, renamed_payload)],
    )
    rows = [int(row.player_record_id) for row in team_roster.rows]
    rows[args.slot] = args.new_player_id
    replaced_eq = _rebuild_indexed(
        eq_base,
        eq_index,
        {args.team_record_id: xor_decode(_rewrite_roster_tail(team_raw, rows))},
    )
    _assert_mode1_roster_tails_match_plan(
        before=baseline_mode1_tails,
        after_eq_data=replaced_eq,
        planned_player_ids={},
    )

    shutil.copytree(base_game, output_game, symlinks=True, ignore=shutil.ignore_patterns("SAVE", "output", "wineprefix", "*.png", "*.log"))
    (output_game / "DBDAT" / "JUG98030.FDI").write_bytes(appended_jug)
    (output_game / "DBDAT" / "EQ98030.FDI").write_bytes(replaced_eq)
    output_jug = (output_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    output_entry = next(entry for entry in IndexedFDIFile.from_bytes(output_jug).entries if entry.record_id == args.new_player_id)
    observed_name = PlayerRecord.from_bytes(output_entry.decode_payload(output_jug), output_entry.payload_offset).name
    if observed_name.casefold() != args.name.casefold():
        raise RuntimeError(f"appended name read-back failed: {observed_name!r}")

    receipt = {
        "schema_version": "pm99-mode0-indexed-jug-append-probe-v1",
        "base_game_dbdat": {
            "eq98030_sha256": _sha256(base_game / "DBDAT" / "EQ98030.FDI"),
            "jug98030_sha256": _sha256(base_game / "DBDAT" / "JUG98030.FDI"),
        },
        "result": "pass",
        "mode0_team_record_id": args.team_record_id,
        "replaced_slot": args.slot,
        "replaced_player_id": replaced_id,
        "appended_player_id": args.new_player_id,
        "clone_player_id": clone_id,
        "appended_name": observed_name,
        "name_anchor": name_proof,
        "mode1_roster_tail_count": len(baseline_mode1_tails),
        "output_dbdat": {
            "eq98030_sha256": _sha256(output_game / "DBDAT" / "EQ98030.FDI"),
            "jug98030_sha256": _sha256(output_game / "DBDAT" / "JUG98030.FDI"),
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "pass", "receipt": str(receipt_path), "output_game": str(output_game)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
