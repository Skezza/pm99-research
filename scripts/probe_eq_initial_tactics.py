#!/usr/bin/env python3
"""Make a narrow, reversible PM99 EQ initial-tactics research mutation.

The 1,767 bytes immediately before the EQ manager/player-link tail contain
eleven twenty-state position blocks on large mode-0 records. DBASEPRE also
parses that shape on a 700-byte mode-1 record before advancing past the same
region. This helper does *not* promote mode 1 to a released contract: its
opt-in mode-1 path was solely for a disposable fresh-game runtime test. Mode-0
has no prefix and seven control bytes (MANAGPRE 5c2380, corrected October
2026). The mode-1 split remains unproven. This probe either swaps two
complete 160-byte player slices or copies only the 1,760-byte interior from
another club or a native saved-tactics file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


TACTICS_PREFIX_BYTES = 0
TACTICS_PLAYER_BYTES = 160
TACTICS_PLAYER_COUNT = 11
TACTICS_GRID_BYTES = TACTICS_PLAYER_BYTES * TACTICS_PLAYER_COUNT
TACTICS_TRAILER_BYTES = 7
TACTICS_TOTAL_BYTES = TACTICS_PREFIX_BYTES + TACTICS_GRID_BYTES + TACTICS_TRAILER_BYTES
ENT_LINK_DELTA = TACTICS_TOTAL_BYTES


@dataclass(frozen=True)
class IndexedEntry:
    record_id: int
    payload_offset: int
    payload_length: int


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def parse_index(data: bytes) -> dict[int, IndexedEntry]:
    if data[:8] != b"DMFIv1.0" or len(data) < 0x14:
        raise ValueError("Expected a DMFIv1.0 indexed FDI file")
    entries: dict[int, IndexedEntry] = {}
    cursor = 0x14
    for _ in range(u32(data, 0x10)):
        if cursor + 13 > len(data):
            raise ValueError("Truncated FDI directory")
        record_id = u32(data, cursor)
        key_size = data[cursor + 4]
        fields_offset = cursor + 5 + key_size
        if fields_offset + 8 > len(data):
            raise ValueError(f"Truncated FDI directory entry {record_id}")
        payload_offset = u32(data, fields_offset)
        payload_length = u32(data, fields_offset + 4)
        if payload_offset + payload_length > len(data):
            raise ValueError(f"FDI payload {record_id} lies outside the file")
        if record_id in entries:
            raise ValueError(f"Duplicate FDI record id {record_id}")
        entries[record_id] = IndexedEntry(record_id, payload_offset, payload_length)
        cursor = fields_offset + 8
    return entries


def legacy_string_end(payload: bytes, cursor: int, label: str) -> int:
    if cursor + 2 > len(payload):
        raise ValueError(f"{label} length lies outside EQ payload")
    end = cursor + 2 + u16(payload, cursor)
    if end > len(payload) or end == cursor + 2:
        raise ValueError(f"{label} is invalid")
    return end


def initial_tactics_offset(payload: bytes, *, allow_mode1_candidate: bool = False) -> int:
    """Return the start of the 1,767-byte tactics block/candidate.

    This mirrors the existing, proven EQ external-roster cursor without
    decoding or rewriting any unrelated record data.  `payload` is the raw
    byte sequence stored in EQ98030.FDI, before the file's outer XOR is
    decoded.
    """

    if len(payload) < 0x2A:
        raise ValueError("EQ payload is too short")
    record_size = u16(payload, 0x26)
    record_mode = payload[0x29]
    if record_mode == 0 and record_size >= 600:
        pass
    elif allow_mode1_candidate and record_mode == 1 and record_size == 700:
        # DBASEPRE FUN_00439f50 parses the 11 x 20 x 8 block for records whose
        # size is >= 0x2bc, then advances by 0x6e7 before reading the external
        # roster/manager tail. Runtime proof remains required before release.
        pass
    else:
        raise ValueError("Requires a large mode-0 record or --allow-mode1-candidate on a 700-byte mode-1 record")

    cursor = 0x2A
    cursor = legacy_string_end(payload, cursor, "team short name")
    cursor = legacy_string_end(payload, cursor, "stadium name")
    cursor += 1 + (1 if record_size > 0x20C else 0)
    cursor = legacy_string_end(payload, cursor, "full club name")
    cursor += 4 + (4 if record_size >= 0x1FE else 0) + 6

    # The modern mode-1 layout shares the three string/capacity lanes, then
    # enters the parsed 0x6e7 tactical block directly. It does not contain the
    # mode-0 chairman/finance/sponsor fields below.
    if record_mode == 1:
        if cursor + ENT_LINK_DELTA > len(payload):
            raise ValueError("Mode-1 initial-tactics candidate exceeds EQ payload")
        return cursor

    if record_size > 0x207:
        cursor += 2
    cursor += 4
    cursor = legacy_string_end(payload, cursor, "chairman")
    cursor += 8
    cursor = legacy_string_end(payload, cursor, "sponsor")
    cursor = legacy_string_end(payload, cursor, "supplier")
    cursor += 3 + (20 if record_size >= 0x1F9 else 10) + 15 + (46 if record_size >= 0x1F9 else 42)
    if record_size < 700:
        cursor += (7 if record_size < 0x1F9 else 17 if record_size < 0x203 else 21) * 2
    else:
        if cursor >= len(payload):
            raise ValueError("EQ sparse-count byte lies outside payload")
        cursor += 1 + payload[cursor] * 3

    if cursor + ENT_LINK_DELTA > len(payload):
        raise ValueError("Initial-tactics candidate exceeds EQ payload")
    return cursor


def entry_payload(data: bytes, entry: IndexedEntry) -> bytes:
    return data[entry.payload_offset : entry.payload_offset + entry.payload_length]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-eq", required=True, type=Path, help="Source EQ98030.FDI; never modified")
    parser.add_argument("--output-eq", required=True, type=Path, help="Disposable EQ98030.FDI output")
    parser.add_argument("--team-record-id", required=True, type=int, help="Target EQ record id")
    parser.add_argument(
        "--allow-mode1-candidate",
        action="store_true",
        help="Research-only opt-in for a 700-byte mode-1 carrier; never a release writer",
    )
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--swap-player-slots", nargs=2, type=int, metavar=("FIRST", "SECOND"), help="Swap two 1-based slices (1..11) in target club")
    choices.add_argument(
        "--reorder-player-slots",
        nargs=TACTICS_PLAYER_COUNT,
        type=int,
        metavar="SOURCE_SLOT",
        help="Assign the source slice for each target slot, in target-slot order; must be a 1..11 permutation",
    )
    choices.add_argument("--copy-grid-from-team-record-id", type=int, help="Copy only source club's 1,760-byte interior into target club")
    choices.add_argument(
        "--copy-grid-from-tactic-file",
        type=Path,
        help="Copy the final 1,760 bytes of one native TACTIC.* file into the target club; disposable compatibility probe only",
    )
    choices.add_argument(
        "--set-coordinate",
        nargs=4,
        type=int,
        metavar=("PLAYER", "BALL_ZONE", "LANE", "VALUE"),
        help="Set one raw uint16 in the candidate grid: player 1..11, ball zone 0..19, lane 0..3, value 0..65535",
    )
    choices.add_argument(
        "--set-static-player-positions",
        nargs=TACTICS_PLAYER_COUNT * 4,
        type=int,
        metavar="VALUE",
        help=(
            "Set all 20 ball zones for each player to one four-word position "
            "(raw attack depth/lane, defend depth/lane), repeated in player-slot order; "
            "disposable runtime proof only"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.allow_mode1_candidate:
        raise ValueError('mode-1 byte split is unproven; use a separately reviewed research probe')
    source = args.input_eq.resolve()
    target = args.output_eq.resolve()
    if source == target:
        raise ValueError("--output-eq must be a different, disposable file")
    data = source.read_bytes()
    entries = parse_index(data)
    target_entry = entries.get(args.team_record_id)
    if target_entry is None:
        raise ValueError(f"EQ record {args.team_record_id} is not present")
    target_payload = entry_payload(data, target_entry)
    target_offset = initial_tactics_offset(
        target_payload,
        allow_mode1_candidate=bool(args.allow_mode1_candidate),
    )
    result = bytearray(data)
    grid_start = target_entry.payload_offset + target_offset + TACTICS_PREFIX_BYTES
    grid_end = grid_start + TACTICS_GRID_BYTES
    before_grid = bytes(result[grid_start:grid_end])

    detail: dict[str, object]
    if args.swap_player_slots:
        first, second = args.swap_player_slots
        if not (1 <= first <= TACTICS_PLAYER_COUNT and 1 <= second <= TACTICS_PLAYER_COUNT) or first == second:
            raise ValueError("--swap-player-slots must name two different values from 1 through 11")
        first_start = grid_start + (first - 1) * TACTICS_PLAYER_BYTES
        second_start = grid_start + (second - 1) * TACTICS_PLAYER_BYTES
        first_bytes = bytes(result[first_start : first_start + TACTICS_PLAYER_BYTES])
        result[first_start : first_start + TACTICS_PLAYER_BYTES] = result[second_start : second_start + TACTICS_PLAYER_BYTES]
        result[second_start : second_start + TACTICS_PLAYER_BYTES] = first_bytes
        detail = {"kind": "swap_player_slots", "first": first, "second": second}
    elif args.reorder_player_slots:
        source_slots = tuple(args.reorder_player_slots)
        expected_slots = tuple(range(1, TACTICS_PLAYER_COUNT + 1))
        if tuple(sorted(source_slots)) != expected_slots:
            raise ValueError("--reorder-player-slots must contain each source slot from 1 through 11 exactly once")
        for target_slot, source_slot in enumerate(source_slots, start=1):
            target_start = grid_start + (target_slot - 1) * TACTICS_PLAYER_BYTES
            source_start = grid_start + (source_slot - 1) * TACTICS_PLAYER_BYTES
            result[target_start : target_start + TACTICS_PLAYER_BYTES] = before_grid[
                source_start - grid_start : source_start - grid_start + TACTICS_PLAYER_BYTES
            ]
        detail = {"kind": "reorder_player_slots", "source_slots_by_target_slot": list(source_slots)}
    elif args.copy_grid_from_team_record_id is not None:
        source_entry = entries.get(args.copy_grid_from_team_record_id)
        if source_entry is None:
            raise ValueError(f"EQ record {args.copy_grid_from_team_record_id} is not present")
        source_offset = initial_tactics_offset(
            entry_payload(data, source_entry),
            allow_mode1_candidate=bool(args.allow_mode1_candidate),
        )
        source_grid_start = source_entry.payload_offset + source_offset + TACTICS_PREFIX_BYTES
        result[grid_start:grid_end] = data[source_grid_start : source_grid_start + TACTICS_GRID_BYTES]
        detail = {"kind": "copy_grid", "source_team_record_id": source_entry.record_id}
    elif args.copy_grid_from_tactic_file is not None:
        tactic_file = args.copy_grid_from_tactic_file.resolve()
        tactic_bytes = tactic_file.read_bytes()
        if len(tactic_bytes) < TACTICS_GRID_BYTES:
            raise ValueError(
                f"Native tactics file {tactic_file} is shorter than the {TACTICS_GRID_BYTES}-byte tactical grid"
            )
        result[grid_start:grid_end] = tactic_bytes[-TACTICS_GRID_BYTES:]
        detail = {
            "kind": "copy_grid_from_tactic_file",
            "tactic_file": str(tactic_file),
            "tactic_file_sha256": sha256(tactic_bytes),
        }
    elif args.set_coordinate:
        player, ball_zone, lane, value = args.set_coordinate
        if not (1 <= player <= TACTICS_PLAYER_COUNT):
            raise ValueError("Coordinate player must be in 1..11")
        if not (0 <= ball_zone < 20):
            raise ValueError("Coordinate ball zone must be in 0..19")
        if not (0 <= lane < 4):
            raise ValueError("Coordinate lane must be in 0..3")
        if not (0 <= value <= 0xFFFF):
            raise ValueError("Coordinate value must be in 0..65535")
        coordinate_offset = grid_start + ((player - 1) * 20 + ball_zone) * 8 + lane * 2
        previous = u16(result, coordinate_offset)
        if previous == value:
            raise ValueError("Coordinate already has the requested value")
        struct.pack_into("<H", result, coordinate_offset, value)
        detail = {
            "kind": "set_coordinate",
            "player": player,
            "ball_zone": ball_zone,
            "lane": lane,
            "old_value": previous,
            "new_value": value,
        }
    else:
        values = tuple(args.set_static_player_positions)
        if len(values) != TACTICS_PLAYER_COUNT * 4:
            raise ValueError("Static player positions must provide four values for every player slot")
        if any(not (0 <= value <= 0x7FF) for value in values):
            raise ValueError("Static player positions must use raw values from 0 through 2047")
        for player_index in range(TACTICS_PLAYER_COUNT):
            position = values[player_index * 4 : player_index * 4 + 4]
            for ball_zone in range(20):
                position_offset = grid_start + ((player_index * 20 + ball_zone) * 8)
                struct.pack_into("<4H", result, position_offset, *position)
        detail = {
            "kind": "set_static_player_positions",
            "position_words_by_player_slot": [list(values[index : index + 4]) for index in range(0, len(values), 4)],
        }

    # Contract check: the candidate's header/trailer and every byte outside its
    # proven 1,760-byte interior remain exact.  The container index is fixed.
    after_target_payload = bytes(result[target_entry.payload_offset : target_entry.payload_offset + target_entry.payload_length])
    if initial_tactics_offset(
        after_target_payload,
        allow_mode1_candidate=bool(args.allow_mode1_candidate),
    ) != target_offset:
        raise AssertionError("Mutation changed the structural EQ cursor")
    after_grid = bytes(result[grid_start:grid_end])
    if after_grid == before_grid:
        raise AssertionError("Requested mutation did not change the target tactical grid")
    candidate_start = target_entry.payload_offset + target_offset
    candidate_end = candidate_start + TACTICS_TOTAL_BYTES
    if bytes(result[candidate_start : candidate_start + TACTICS_PREFIX_BYTES]) != data[candidate_start : candidate_start + TACTICS_PREFIX_BYTES]:
        raise AssertionError("Mutation changed the candidate prefix")
    if bytes(result[grid_end:candidate_end]) != data[grid_end:candidate_end]:
        raise AssertionError("Mutation changed the seven-byte candidate controls")
    if result[:grid_start] != data[:grid_start] or result[grid_end:] != data[grid_end:]:
        raise AssertionError("Mutation escaped the 1,760-byte candidate interior")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result)
    print(json.dumps({
        "success": True,
        "input_sha256": sha256(data),
        "output_sha256": sha256(bytes(result)),
        "team_record_id": target_entry.record_id,
        "team_record_mode": int(target_payload[0x29]),
        "mode1_candidate_opt_in": bool(args.allow_mode1_candidate),
        "candidate_offset": target_offset,
        "candidate_total_bytes": TACTICS_TOTAL_BYTES,
        "grid_bytes": TACTICS_GRID_BYTES,
        "before_grid_sha256": sha256(before_grid),
        "after_grid_sha256": sha256(after_grid),
        "mutation": detail,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AssertionError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
