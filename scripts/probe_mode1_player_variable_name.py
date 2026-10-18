#!/usr/bin/env python3
"""Run one indexed player-name rebuild as a foreign runtime research probe.

The product's own staged writer is used deliberately.  The probe then compares
the complete indexed directory by record id so that a variable-length rebuild
cannot silently mutate a different player payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from app.editor_actions import (  # type: ignore[import-not-found]
    PlayerVariableNameTarget,
    _native_dd6360_role_start,
    _read_native_dd6360_fields,
    apply_player_variable_names,
)
from app.fdi_indexed import IndexedFDIFile  # type: ignore[import-not-found]
from app.models import PlayerRecord  # type: ignore[import-not-found]


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--player-record-id", required=True, type=int)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--new-name", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _display_name(payload: bytes, offset: int) -> str:
    record = PlayerRecord.from_bytes(payload, offset)
    return " ".join(str(record.name or "").split())


def _payloads_by_id(data: bytes) -> dict[int, bytes]:
    indexed = IndexedFDIFile.from_bytes(data)
    return {
        int(entry.record_id): data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        for entry in indexed.entries
    }


def main() -> int:
    args = _args()
    player_path = args.dbdat.resolve() / "JUG98030.FDI"
    if not player_path.is_file():
        raise SystemExit(f"missing JUG98030.FDI: {player_path}")
    if not args.new_name.strip():
        raise SystemExit("new name must not be empty")

    before = player_path.read_bytes()
    before_index = IndexedFDIFile.from_bytes(before)
    entry = next((item for item in before_index.entries if int(item.record_id) == int(args.player_record_id)), None)
    if entry is None:
        raise SystemExit(f"JUG record id not found: {args.player_record_id}")
    before_payload = entry.decode_payload(before)
    before_name = _display_name(before_payload, int(entry.payload_offset))
    if before_name.casefold() != args.expected_name.casefold():
        raise SystemExit(f"JUG {args.player_record_id} is {before_name!r}, not {args.expected_name!r}")
    family = before_payload[2:5].hex() if len(before_payload) >= 5 else "short"
    if family not in {"dd6360", "dd6361"}:
        raise SystemExit(f"JUG {args.player_record_id} has unsupported indexed family {family}")
    before_fine_roles: list[int] | None = None
    if family == "dd6360":
        before_fine_roles = list(
            _read_native_dd6360_fields(
                before_payload, _native_dd6360_role_start(before_payload)
            )["fine_role_codes"]
        )

    staged_path = player_path.with_name("JUG98030.variable-name-probe.FDI")
    if staged_path.exists():
        raise SystemExit(f"refusing to replace existing probe output: {staged_path}")
    target = PlayerVariableNameTarget(
        row_number=1,
        record_id=int(args.player_record_id),
        payload_offset=int(entry.payload_offset),
        expected_current_name=before_name,
        target_name=args.new_name,
    )
    result = apply_player_variable_names(
        str(player_path),
        [target],
        output_file=staged_path,
        create_backup_before_write=False,
    )
    if not bool(result.ok) or not bool(result.applied_to_disk):
        raise SystemExit(f"variable-name writer rejected the probe: {asdict(result)}")
    after = staged_path.read_bytes()
    after_index = IndexedFDIFile.from_bytes(after)
    after_entry = next((item for item in after_index.entries if int(item.record_id) == int(args.player_record_id)), None)
    if after_entry is None:
        raise SystemExit("target record vanished after indexed rebuild")
    after_payload = after_entry.decode_payload(after)
    after_name = _display_name(after_payload, int(after_entry.payload_offset))
    if after_name.casefold() != args.new_name.casefold():
        raise SystemExit(f"reopened player name is {after_name!r}, not {args.new_name!r}")
    after_fine_roles: list[int] | None = None
    if family == "dd6360":
        after_fine_roles = list(
            _read_native_dd6360_fields(
                after_payload, _native_dd6360_role_start(after_payload)
            )["fine_role_codes"]
        )
        if after_fine_roles != before_fine_roles:
            raise SystemExit(
                "variable-name rebuild changed the dd6360 native fine-role window: "
                f"{before_fine_roles} -> {after_fine_roles}"
            )

    before_payloads = _payloads_by_id(before)
    after_payloads = _payloads_by_id(after)
    if set(before_payloads) != set(after_payloads):
        raise SystemExit("indexed rebuild changed the record-id set")
    unrelated_changes = [
        record_id
        for record_id in sorted(before_payloads)
        if record_id != int(args.player_record_id) and before_payloads[record_id] != after_payloads[record_id]
    ]
    if unrelated_changes:
        raise SystemExit(f"indexed rebuild changed unrelated player payloads: {unrelated_changes[:12]}")

    # `replace` is atomic within this disposable DBDAT directory.  It avoids
    # testing a sibling output file which PM99 will never load.
    staged_path.replace(player_path)
    receipt = {
        "schema": "pm99-mode1-player-variable-name-probe/v1",
        "player_path": str(player_path),
        "player_record_id": int(args.player_record_id),
        "family": family,
        "before_name": before_name,
        "after_name": after_name,
        "before_payload_length": int(entry.payload_length),
        "after_payload_length": int(after_entry.payload_length),
        "payload_length_delta": int(after_entry.payload_length) - int(entry.payload_length),
        "directory_entry_count": len(after_index.entries),
        "unrelated_payloads_unchanged": True,
        "native_fine_roles_before": before_fine_roles,
        "native_fine_roles_after": after_fine_roles,
        "native_fine_roles_preserved": (
            None if family != "dd6360" else after_fine_roles == before_fine_roles
        ),
        "writer_result": asdict(result),
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
