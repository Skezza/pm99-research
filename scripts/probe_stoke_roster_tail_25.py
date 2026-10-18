#!/usr/bin/env python3
"""Create an isolated 25-link Stoke runtime probe from a supplied DBDAT copy.

This is a format probe, not a season builder. It proves that Stoke's existing
EQ record can be extended without replacing the club record, and writes the
selected club id into five donor JUG payload headers for the MANAGPRE current
squad filter experiment.
"""

from __future__ import annotations

import argparse
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
sys.path.insert(0, str(EDITOR))

from app.editor_actions import _IndexedRawStageRecord, write_player_staged_records
from app.eq_jug_linked import load_eq_linked_team_rosters
from app.fdi_indexed import IndexedFDIFile


def rebuild_raw_indexed(original: bytes, entry_id: int, replacement: bytes) -> bytes:
    indexed = IndexedFDIFile.from_bytes(original)
    entries = sorted(indexed.entries, key=lambda item: int(item.payload_offset))
    changed = next((entry for entry in entries if int(entry.record_id) == entry_id), None)
    if changed is None:
        raise ValueError(f"EQ record {entry_id} does not exist")
    first = int(entries[0].payload_offset)
    output = bytearray(original[:first])
    new_offsets: dict[int, int] = {}
    new_lengths: dict[int, int] = {}
    for index, entry in enumerate(entries):
        start, length = int(entry.payload_offset), int(entry.payload_length)
        end = start + length
        payload = replacement if entry is changed else original[start:end]
        new_offsets[start] = len(output)
        new_lengths[start] = len(payload)
        output.extend(payload)
        if index + 1 < len(entries):
            output.extend(original[end:int(entries[index + 1].payload_offset)])
        else:
            output.extend(original[end:])
    for entry in indexed.entries:
        key_length = output[int(entry.index_offset) + 4]
        offset_pos = int(entry.index_offset) + 5 + key_length
        struct.pack_into("<I", output, offset_pos, new_offsets[int(entry.payload_offset)])
        struct.pack_into("<I", output, offset_pos + 4, new_lengths[int(entry.payload_offset)])
    IndexedFDIFile.from_bytes(bytes(output))
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dbdat", required=True, type=Path)
    parser.add_argument("--output-dbdat", required=True, type=Path)
    parser.add_argument("--append-player-id", type=int, action="append", required=True)
    args = parser.parse_args()
    if len(args.append_player_id) != 5:
        raise SystemExit("This fixed probe requires exactly five additional player ids.")
    if args.output_dbdat.exists():
        raise SystemExit(f"Output already exists: {args.output_dbdat}")
    shutil.copytree(args.input_dbdat, args.output_dbdat)
    eq_path = args.output_dbdat / "EQ98030.FDI"
    jug_path = args.output_dbdat / "JUG98030.FDI"
    rosters = load_eq_linked_team_rosters(str(eq_path), str(jug_path))
    stoke = next(row for row in rosters if int(row.eq_record_id) == 341)
    if len(stoke.rows) != 20:
        raise RuntimeError(f"Expected the original Stoke 20-row tail, got {len(stoke.rows)}")
    raw = eq_path.read_bytes()
    entry = next(item for item in IndexedFDIFile.from_bytes(raw).entries if int(item.record_id) == 341)
    payload = raw[int(entry.payload_offset):int(entry.payload_offset) + int(entry.payload_length)]
    first_row = int(stoke.rows[0].raw_row_offset)
    count_offset = first_row - 1
    tail_end = int(stoke.rows[-1].raw_row_offset) + 5
    if tail_end != len(payload):
        raise RuntimeError("Stoke roster is not a terminal tail; refusing to resize it")
    updated = bytearray(payload[:count_offset])
    updated.append(25)
    for index, row in enumerate(stoke.rows):
        offset = int(row.raw_row_offset)
        updated.extend(payload[offset:offset + 5])
    for player_id in args.append_player_id:
        updated.extend(b"\x00" + int(player_id).to_bytes(4, "little"))
    eq_path.write_bytes(rebuild_raw_indexed(raw, 341, bytes(updated)))

    jug_bytes = jug_path.read_bytes()
    jug_index = IndexedFDIFile.from_bytes(jug_bytes)
    stages = []
    for player_id in args.append_player_id:
        entry = next((item for item in jug_index.entries if int(item.record_id) == player_id), None)
        if entry is None:
            raise RuntimeError(f"JUG player {player_id} does not exist")
        decoded = bytearray(entry.decode_payload(jug_bytes))
        if len(decoded) < 2:
            raise RuntimeError(f"JUG player {player_id} is too short")
        struct.pack_into("<H", decoded, 0, 3425)
        stages.append((int(entry.payload_offset), _IndexedRawStageRecord(raw_payload=bytes(decoded), container_offset=int(entry.payload_offset), container_length=int(entry.payload_length))))
    write_player_staged_records(str(jug_path), stages, create_backup_before_write=False)
    after = next(row for row in load_eq_linked_team_rosters(str(eq_path), str(jug_path)) if int(row.eq_record_id) == 341)
    if len(after.rows) != 25:
        raise RuntimeError("25-link roster readback failed")
    print(f"created={args.output_dbdat} stoke_rows={len(after.rows)} appended={','.join(map(str, args.append_player_id))}")


if __name__ == "__main__":
    main()
