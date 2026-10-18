#!/usr/bin/env python3
"""Build a disposable foreign JUG-append and roster-link runtime probe.

This is deliberately research-only.  It clones one existing mode-1 ``dd6360``
player into a fresh indexed JUG record, changes one existing foreign EQ roster
row to the new ID, and verifies the row's count and flag bytes plus every
unplanned mode-1 roster tail.  It does not claim a complete historical roster
transaction; that is the compiler's separate all-carrier guard.
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
from scripts.probe_minifoto_append_entry import append_entry as append_minifoto_entry  # noqa: E402


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
    allocation_group = parser.add_mutually_exclusive_group(required=True)
    allocation_group.add_argument(
        "--new-player-id",
        type=int,
        help="append a fresh JUG directory entry (the runtime-blocked control)",
    )
    allocation_group.add_argument(
        "--reuse-player-id",
        type=int,
        help="replace an existing unrostered JUG entry without changing JUG record count",
    )
    parser.add_argument("--clone-player-id", type=int, help="mode-1-only dd6360 source; default is replaced player")
    parser.add_argument("--name", default="Append Probe", help="visible name for the fresh JUG carrier")
    parser.add_argument(
        "--photo-donor-player-id",
        type=int,
        help=(
            "append a copied MINIFOTO entry for the fresh JUG ID, using this existing "
            "player as donor; research-only control for the profile failure"
        ),
    )
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
    target_id = int(args.new_player_id if args.new_player_id is not None else args.reuse_player_id)
    if not 1 <= target_id <= 0xFFFFFFFF:
        raise SystemExit("target player ID must fit uint32")

    eq_base = (base_game / "DBDAT" / "EQ98030.FDI").read_bytes()
    jug_base = (base_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    eq_index = IndexedFDIFile.from_bytes(eq_base)
    jug_index = IndexedFDIFile.from_bytes(jug_base)
    team = next((entry for entry in eq_index.entries if int(entry.record_id) == args.team_record_id), None)
    if team is None:
        raise SystemExit(f"mode-1 target EQ carrier {args.team_record_id} is absent")
    team_raw = eq_base[team.payload_offset : team.payload_offset + team.payload_length]
    if int(extract_indexed_team_payload_metadata(team_raw)["record_mode"]) != 1:
        raise SystemExit(f"EQ carrier {args.team_record_id} is not mode 1")
    team_roster = parse_eq_external_team_roster_payload(team_raw, {})
    if team_roster is None or not team_roster.rows:
        raise SystemExit(f"EQ carrier {args.team_record_id} has no parser-backed roster")
    if not 0 <= args.slot < len(team_roster.rows):
        raise SystemExit(f"--slot must be 0..{len(team_roster.rows) - 1}")

    owners, _rosters, modes = _source_roster_owners(eq_base)
    existing_jug_ids = {int(entry.record_id) for entry in jug_index.entries}
    is_reuse = args.reuse_player_id is not None
    if is_reuse:
        if target_id not in existing_jug_ids:
            raise SystemExit("--reuse-player-id is absent from the clean JUG file")
        if target_id in owners:
            raise SystemExit("--reuse-player-id is already referenced by an EQ roster")
    elif target_id in existing_jug_ids or target_id in owners:
        raise SystemExit("--new-player-id already exists or is referenced by an EQ roster")
    replaced_id = int(team_roster.rows[args.slot].player_record_id)
    clone_id = int(args.clone_player_id if args.clone_player_id is not None else replaced_id)
    clone = next((entry for entry in jug_index.entries if int(entry.record_id) == clone_id), None)
    if clone is None:
        raise SystemExit(f"clone JUG carrier {clone_id} is absent")
    clone_owners = owners.get(clone_id, [])
    if not clone_owners or any(modes.get(owner) != 1 for owner in clone_owners):
        raise SystemExit(f"clone JUG carrier {clone_id} is not mode-1-only")
    clone_payload = clone.decode_payload(jug_base)
    if clone_payload[2:5] != b"\xdd\x63\x60":
        raise SystemExit("foreign append probe only supports a dd6360 clone source")
    clone_record = PlayerRecord.from_bytes(clone_payload, clone.payload_offset)
    renamed_payload, name_proof = _patch_indexed_player_variable_name_payload(
        clone_payload, clone_record.name, args.name
    )

    baseline_mode1_tails = _mode1_roster_tails(eq_base)
    if is_reuse:
        appended_jug = _rebuild_indexed(jug_base, jug_index, {target_id: renamed_payload})
    else:
        appended_jug = _append_indexed_fdi_records(
            original=jug_base,
            records=[(target_id, clone.key, renamed_payload)],
        )
    new_roster_ids = [int(row.player_record_id) for row in team_roster.rows]
    new_roster_ids[args.slot] = target_id
    rewritten_eq = _rebuild_indexed(
        eq_base,
        eq_index,
        {args.team_record_id: xor_decode(_rewrite_roster_tail(team_raw, new_roster_ids))},
    )
    _assert_mode1_roster_tails_match_plan(
        before=baseline_mode1_tails,
        after_eq_data=rewritten_eq,
        planned_player_ids={args.team_record_id: new_roster_ids},
    )

    shutil.copytree(
        base_game,
        output_game,
        symlinks=True,
        ignore=shutil.ignore_patterns("SAVE", "output", "wineprefix", "*.png", "*.log"),
    )
    (output_game / "DBDAT" / "JUG98030.FDI").write_bytes(appended_jug)
    (output_game / "DBDAT" / "EQ98030.FDI").write_bytes(rewritten_eq)
    minifoto_proof: dict[str, object] | None = None
    if args.photo_donor_player_id is not None:
        minifoto_path = output_game / "DBDAT" / "MINIFOTO.PKF"
        minifoto_data, minifoto_proof = append_minifoto_entry(
            minifoto_path.read_bytes(),
            target_id=target_id,
            donor_id=args.photo_donor_player_id,
        )
        minifoto_path.write_bytes(minifoto_data)

    output_jug = (output_game / "DBDAT" / "JUG98030.FDI").read_bytes()
    output_entry = next(
        entry for entry in IndexedFDIFile.from_bytes(output_jug).entries if int(entry.record_id) == target_id
    )
    observed_name = PlayerRecord.from_bytes(
        output_entry.decode_payload(output_jug), output_entry.payload_offset
    ).name
    if observed_name.casefold() != args.name.casefold():
        raise RuntimeError(f"appended name read-back failed: {observed_name!r}")

    receipt = {
        "schema_version": "pm99-mode1-jug-carrier-allocation-probe-v2",
        "result": "pass",
        "scope": "disposable-one-row-runtime-control-not-a-season-release",
        "base_game_dbdat": {
            "eq98030_sha256": _sha256(base_game / "DBDAT" / "EQ98030.FDI"),
            "jug98030_sha256": _sha256(base_game / "DBDAT" / "JUG98030.FDI"),
        },
        "mode1_team_record_id": args.team_record_id,
        "replaced_slot": args.slot,
        "preserved_row_flag": int(team_roster.rows[args.slot].flag),
        "replaced_player_id": replaced_id,
        "allocation_kind": "existing_unrostered_carrier_reuse" if is_reuse else "fresh_directory_append",
        "appended_player_id": target_id,
        "clone_player_id": clone_id,
        "appended_name": observed_name,
        "name_anchor": name_proof,
        "minifoto_append": minifoto_proof,
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
