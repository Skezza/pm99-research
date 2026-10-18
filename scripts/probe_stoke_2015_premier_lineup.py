#!/usr/bin/env python3
"""Build a narrow, self-checking PM99 control database for the 2015 Stoke proof.

This is deliberately an investigation artefact, not the season compiler.  It
starts from a browser-built Stoke 2015/16 package, moves that complete roster
from the old Championship carrier (EQ 341) to the Premier League carrier
(EQ 314), removes every moved player from its old carrier, and writes the
historic shirt-number byte known to be consumed by the running game.

The result has deliberately incomplete replacement squads for the displaced
clubs, so it must never be shipped as a historical database.  Its only job is
to answer one bounded runtime question: does a 2015 Stoke carrier in the
Premier League retain the supplied shirt numbers on PM99's Line-up screen?
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.eq_jug_linked import load_eq_linked_team_rosters, parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import xor_decode, xor_encode


PREMIER_STOKE_EQ_ID = 314
OLD_STOKE_EQ_ID = 341
SOUTHAMPTON_EQ_ID = 317
WIMBLEDON_CARRIER_PLAYER_ID = 7951

# The 9 August 2015 Stoke v Liverpool XI, followed by the five bench players
# which PM99's first Line-Up page can show.  The source match sheet lists the
# full seven-player bench; PM99 only has five substitute rows, so Crouch and
# Wollscheid remain immediately after the visible bench.  The final nine rows
# complete the 2015/16 registered squad control.
#
# Crucially, this order is not merely the EQ roster order.  It is also written
# into the dd6361 `initial squad order` byte below: the running game uses that
# byte to produce its initial line-up/substitute/reserve ordering.
STOKE_2015_25: tuple[tuple[int, int, str], ...] = (
    (9778, 1, "Jack Butland"),
    (26935, 8, "Glen Johnson"),
    (9782, 20, "Geoff Cameron"),
    (26936, 5, "Marc Muniesa"),
    (9404, 3, "Erik Pieters"),
    (12446, 15, "Marco van Ginkel"),
    (9781, 6, "Glenn Whelan"),
    (15578, 19, "Jonathan Walters"),
    (32960, 16, "Charlie Adam"),
    (9785, 14, "Ibrahim Afellay"),
    (10001, 18, "Mame Biram Diouf"),
    (10065, 7, "Stephen Ireland"),
    (33150, 9, "Peter Odemwingie"),
    (32959, 11, "Joselu"),
    (33151, 21, "Steve Sidwell"),
    (9310, 24, "Shay Given"),
    (32958, 25, "Peter Crouch"),
    (9426, 26, "Philipp Wollscheid"),
    (10242, 2, "Phil Bardsley"),
    (15577, 12, "Marc Wilson"),
    (9581, 10, "Marko Arnautovic"),
    (9772, 27, "Bojan Krkic"),
    (9773, 22, "Xherdan Shaqiri"),
    (24054, 29, "Jakob Haugaard"),
    (10217, 17, "Ryan Shawcross"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Browser-built 2015 Stoke package containing JUG/EQ/ENT/MINIFOTO.")
    parser.add_argument("--output", required=True, type=Path, help="New empty directory for this disposable control database.")
    return parser.parse_args()


def _entry_by_id(indexed: IndexedFDIFile, record_id: int):
    try:
        return next(entry for entry in indexed.entries if entry.record_id == record_id)
    except StopIteration as exc:
        raise ValueError(f"FDI has no record {record_id}.") from exc


def _rebuild_indexed_fdi(original: bytes, indexed: IndexedFDIFile, decoded_replacements: dict[int, bytes]) -> bytes:
    """Rebuild a DMFIv1.0 file while preserving all untouched ranges exactly."""
    entries_by_id = {entry.record_id: entry for entry in indexed.entries}
    missing = sorted(set(decoded_replacements) - set(entries_by_id))
    if missing:
        raise ValueError(f"Replacement ids missing from FDI directory: {missing}")
    ordered = sorted(indexed.entries, key=lambda entry: entry.payload_offset)
    if not ordered:
        raise ValueError("Cannot rebuild an empty indexed FDI file.")
    rebuilt = bytearray(original[: ordered[0].payload_offset])
    new_offsets: dict[int, int] = {}
    new_lengths: dict[int, int] = {}
    for offset, entry in enumerate(ordered):
        old_end = entry.payload_offset + entry.payload_length
        replacement = decoded_replacements.get(entry.record_id)
        encoded = xor_encode(replacement) if replacement is not None else original[entry.payload_offset:old_end]
        new_offsets[entry.payload_offset] = len(rebuilt)
        new_lengths[entry.payload_offset] = len(encoded)
        rebuilt.extend(encoded)
        next_entry = ordered[offset + 1] if offset + 1 < len(ordered) else None
        if next_entry is None:
            rebuilt.extend(original[old_end:])
        else:
            if next_entry.payload_offset < old_end:
                raise ValueError(f"Overlapping FDI payload at 0x{entry.payload_offset:x}.")
            rebuilt.extend(original[old_end:next_entry.payload_offset])
    for entry in indexed.entries:
        key_length = rebuilt[entry.index_offset + 4]
        payload_offset_at = entry.index_offset + 5 + key_length
        struct.pack_into("<I", rebuilt, payload_offset_at, new_offsets[entry.payload_offset])
        struct.pack_into("<I", rebuilt, payload_offset_at + 4, new_lengths[entry.payload_offset])
    reparsed = IndexedFDIFile.from_bytes(bytes(rebuilt))
    if len(reparsed.entries) != len(indexed.entries):
        raise ValueError("FDI directory count changed during rebuild.")
    return bytes(rebuilt)


def _rewrite_roster_tail(raw_payload: bytes, player_ids: list[int]) -> bytes:
    """Replace the terminal external roster tail and check it structurally."""
    before = parse_eq_external_team_roster_payload(raw_payload, {})
    if before is None or not before.rows:
        raise ValueError("EQ record has no supported external roster tail.")
    first_row_offset = before.rows[0].raw_row_offset
    old_tail_end = before.rows[-1].raw_row_offset + 5
    if old_tail_end != len(raw_payload):
        raise ValueError("EQ roster tail is not terminal; refusing to resize it.")
    count_offset = first_row_offset - 1
    if not player_ids or len(player_ids) > 255 or len(set(player_ids)) != len(player_ids):
        raise ValueError("Roster must contain 1..255 unique player ids.")
    result = bytearray(raw_payload[:count_offset])
    result.append(len(player_ids))
    for index, player_id in enumerate(player_ids):
        flag = before.rows[index].flag if index < len(before.rows) else 0
        result.append(flag)
        result.extend(struct.pack("<I", player_id))
    reparsed = parse_eq_external_team_roster_payload(bytes(result), {})
    if reparsed is None or [row.player_record_id for row in reparsed.rows] != player_ids:
        raise ValueError("EQ roster tail did not survive structural read-back.")
    return bytes(result)


def _set_dd6361_shirt_number(raw_file: bytearray, indexed: IndexedFDIFile, record_id: int, number: int) -> None:
    entry = _entry_by_id(indexed, record_id)
    payload = xor_decode(raw_file[entry.payload_offset : entry.payload_offset + entry.payload_length])
    if len(payload) < 8 or payload[2:5] != b"\xddca":
        raise ValueError(f"JUG record {record_id} does not have the proven dd6361 number layout.")
    if not 1 <= number <= 99:
        raise ValueError(f"Invalid historic shirt number {number} for JUG record {record_id}.")
    # The outer FDI and inner player stream use the same XOR key.  The file
    # byte at payload+7 is therefore the plain PM99 shirt number.  This exact
    # byte was runtime-proven with the Yorke/Solskjaer control swap.
    raw_file[entry.payload_offset + 7] = number
    readback = xor_decode(raw_file[entry.payload_offset : entry.payload_offset + entry.payload_length])
    if readback[7] ^ 0x61 != number:
        raise ValueError(f"JUG record {record_id} shirt-number read-back failed.")


def _set_dd6361_initial_squad_order(raw_file: bytearray, indexed: IndexedFDIFile, record_id: int, order: int) -> None:
    """Set the runtime-proven dd6361 initial Line-Up order byte.

    In a dd6361 record it is the byte immediately before the two marker bytes
    and six fine-role bytes.  It is individually XOR encoded within an outer
    XOR FDI payload, so its on-disk byte is the desired decoded order value.
    This narrow helper only supports the record shape exercised by this
    Stoke control; it is not a generic editor write path.
    """
    if not 1 <= order <= 99:
        raise ValueError(f"Invalid initial squad order {order} for JUG record {record_id}.")
    entry = _entry_by_id(indexed, record_id)
    payload = xor_decode(raw_file[entry.payload_offset : entry.payload_offset + entry.payload_length])
    if len(payload) < 8 or payload[2:5] != b"\xdd\x63\x61":
        raise ValueError(f"JUG record {record_id} does not have the proven dd6361 squad-order layout.")
    record = PlayerRecord.from_bytes(payload, entry.payload_offset)
    anchor = PlayerRecord._find_indexed_suffix_anchor(payload, record.name)
    if anchor is None or anchor + 18 > len(payload):
        raise ValueError(f"Could not resolve dd6361 initial squad-order byte for JUG record {record_id}.")
    # Outer and field-level XOR cancel at this byte, exactly as for shirt no.
    raw_file[entry.payload_offset + anchor] = order
    readback = xor_decode(raw_file[entry.payload_offset : entry.payload_offset + entry.payload_length])
    checked = PlayerRecord.from_bytes(readback, entry.payload_offset)
    if checked.indexed_unknown_0 != order:
        raise ValueError(f"JUG record {record_id} initial squad-order read-back failed.")


def _copy_source(source: Path, output: Path) -> None:
    required = ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise ValueError(f"Source is missing required files: {', '.join(missing)}")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    output.mkdir(parents=True)
    for name in required:
        shutil.copy2(source / name, output / name)


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    _copy_source(source, output)

    jug_path = output / "JUG98030.FDI"
    jug = bytearray(jug_path.read_bytes())
    jug_indexed = IndexedFDIFile.from_bytes(jug)
    for initial_squad_order, (player_id, number, _) in enumerate(STOKE_2015_25, start=1):
        _set_dd6361_shirt_number(jug, jug_indexed, player_id, number)
        _set_dd6361_initial_squad_order(jug, jug_indexed, player_id, initial_squad_order)
    jug_path.write_bytes(jug)

    eq_path = output / "EQ98030.FDI"
    eq = eq_path.read_bytes()
    eq_indexed = IndexedFDIFile.from_bytes(eq)
    # The external-roster parser is traced against the raw outer-FDI bytes.
    # `rebuild_indexed_fdi`, conversely, accepts decoded payload replacements.
    old_stoke_entry = _entry_by_id(eq_indexed, OLD_STOKE_EQ_ID)
    southampton_entry = _entry_by_id(eq_indexed, SOUTHAMPTON_EQ_ID)
    source_stoke = eq[old_stoke_entry.payload_offset : old_stoke_entry.payload_offset + old_stoke_entry.payload_length]
    southampton = eq[southampton_entry.payload_offset : southampton_entry.payload_offset + southampton_entry.payload_length]
    stoke_ids = [player_id for player_id, _, _ in STOKE_2015_25]
    # The source is already a full browser-built 25: carrier 341 previously
    # owns them and Southampton has had its five donor records removed.
    source_stoke_ids = [row.player_record_id for row in parse_eq_external_team_roster_payload(source_stoke, {}).rows]
    if len(source_stoke_ids) != len(stoke_ids) or set(source_stoke_ids) != set(stoke_ids):
        raise ValueError("Source 341 does not contain the expected browser-built Stoke 25.")
    if any(row.player_record_id in stoke_ids for row in parse_eq_external_team_roster_payload(southampton, {}).rows):
        raise ValueError("Source 317 still owns a Stoke 2015 donor player.")
    # Carrier 341 cannot be left empty under the released writer contract.
    # Move one displaced Wimbledon record to it solely to preserve unique
    # external links in this control package.
    premier_stoke = _rewrite_roster_tail(source_stoke, stoke_ids)
    replacements = {
        PREMIER_STOKE_EQ_ID: xor_decode(premier_stoke),
        OLD_STOKE_EQ_ID: xor_decode(_rewrite_roster_tail(source_stoke, [WIMBLEDON_CARRIER_PLAYER_ID])),
    }
    built_eq = _rebuild_indexed_fdi(eq, eq_indexed, replacements)
    eq_path.write_bytes(built_eq)

    rosters = {team.eq_record_id: team for team in load_eq_linked_team_rosters(str(eq_path), str(jug_path))}
    if [row.player_record_id for row in rosters[PREMIER_STOKE_EQ_ID].rows] != stoke_ids:
        raise ValueError("Premier carrier roster read-back failed.")
    if [row.player_record_id for row in rosters[OLD_STOKE_EQ_ID].rows] != [WIMBLEDON_CARRIER_PLAYER_ID]:
        raise ValueError("Old Stoke carrier roster read-back failed.")
    if rosters[PREMIER_STOKE_EQ_ID].short_name != "Stoke C.":
        raise ValueError("Premier carrier did not inherit Stoke identity.")
    proof = {
        "purpose": "Disposable runtime proof only; not a releasable historical database.",
        "premier_stoke_eq_record_id": PREMIER_STOKE_EQ_ID,
        "former_stoke_eq_record_id": OLD_STOKE_EQ_ID,
        "opening_xi": [{"record_id": pid, "shirt_number": no, "name": name} for pid, no, name in STOKE_2015_25[:11]],
        "pm99_visible_substitutes": [{"record_id": pid, "shirt_number": no, "name": name} for pid, no, name in STOKE_2015_25[11:16]],
        "registered_squad": [{"record_id": pid, "shirt_number": no, "name": name} for pid, no, name in STOKE_2015_25],
        "checks": {
            "premier_carrier_has_complete_stoke_25": True,
            "former_carrier_has_no_stoke_player_links": True,
            "southampton_donors_removed": True,
            "dd6361_number_byte_readback": True,
            "dd6361_initial_squad_order_readback": True,
        },
    }
    (output / "proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
