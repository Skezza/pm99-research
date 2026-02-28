"""Parser-backed EQ to JUG roster extraction using DBASEPRE.EXE layout."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import xor_decode


_EXTERNAL_LINK_JUMP = 0x6E7
_MIN_EXTERNAL_LINK_RECORD_SIZE = 600


@dataclass(frozen=True)
class EQLinkedRosterRow:
    slot_index: int
    flag: int
    player_record_id: int
    player_name: str = ""


@dataclass
class EQLinkedTeamRoster:
    eq_record_id: int
    short_name: str
    stadium_name: str
    full_club_name: str
    record_size: int
    mode_byte: int
    ent_count: int
    rows: List[EQLinkedRosterRow] = field(default_factory=list)


def _read_xor_u16_string(raw_payload: bytes, cursor: int) -> tuple[str, int]:
    if cursor + 2 > len(raw_payload):
        raise ValueError("truncated string length")
    size = int.from_bytes(raw_payload[cursor : cursor + 2], "little")
    cursor += 2
    end = cursor + size
    if end > len(raw_payload):
        raise ValueError("truncated string payload")
    decoded = xor_decode(raw_payload[cursor:end])
    try:
        text = decoded.decode("cp1252")
    except UnicodeDecodeError:
        text = decoded.decode("cp1252", errors="replace")
    return text.rstrip("\x00"), end


def parse_eq_external_team_roster_payload(
    raw_payload: bytes,
    player_name_by_id: Dict[int, str],
) -> Optional[EQLinkedTeamRoster]:
    """
    Parse one raw EQ indexed payload using the DBASEPRE.EXE external-link layout.

    Only the large-record mode currently used by the external JUG link path is
    supported here. Legacy mode-0 payloads are left unresolved for now.
    """
    if len(raw_payload) < 0x2A:
        return None

    record_size = int.from_bytes(raw_payload[0x26:0x28], "little")
    mode_byte = raw_payload[0x29]
    if record_size < _MIN_EXTERNAL_LINK_RECORD_SIZE:
        return None

    cursor = 0x2A
    try:
        short_name, cursor = _read_xor_u16_string(raw_payload, cursor)
        stadium_name, cursor = _read_xor_u16_string(raw_payload, cursor)
        cursor += 1
        if record_size > 0x20C:
            cursor += 1
        full_club_name, cursor = _read_xor_u16_string(raw_payload, cursor)
    except Exception:
        return None

    # Skip the fixed scalar fields that precede the external link tables.
    cursor += 4
    if record_size >= 0x1FE:
        cursor += 4
    cursor += 2 + 2 + 2

    # The older inline payload mode is still unresolved.
    if mode_byte == 0:
        return None

    ent_cursor = cursor + _EXTERNAL_LINK_JUMP
    if ent_cursor >= len(raw_payload):
        return None

    ent_count = raw_payload[ent_cursor]
    player_cursor = ent_cursor + 1 + ent_count * 4
    if player_cursor >= len(raw_payload):
        return None

    player_count = raw_payload[player_cursor]
    player_cursor += 1
    rows: List[EQLinkedRosterRow] = []
    for slot_index in range(player_count):
        if player_cursor + 5 > len(raw_payload):
            return None
        flag = raw_payload[player_cursor]
        player_record_id = int.from_bytes(raw_payload[player_cursor + 1 : player_cursor + 5], "little")
        rows.append(
            EQLinkedRosterRow(
                slot_index=slot_index,
                flag=flag,
                player_record_id=player_record_id,
                player_name=str(player_name_by_id.get(player_record_id) or ""),
            )
        )
        player_cursor += 5

    return EQLinkedTeamRoster(
        eq_record_id=0,
        short_name=short_name,
        stadium_name=stadium_name,
        full_club_name=full_club_name,
        record_size=record_size,
        mode_byte=mode_byte,
        ent_count=ent_count,
        rows=rows,
    )


def _build_jug_player_name_index(player_file: str) -> Dict[int, str]:
    player_bytes = Path(player_file).read_bytes()
    indexed = IndexedFDIFile.from_bytes(player_bytes)
    out: Dict[int, str] = {}
    for entry in indexed.entries:
        try:
            payload = entry.decode_payload(player_bytes)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
        except Exception:
            continue
        name = str(getattr(record, "name", "") or "").strip()
        if not name:
            given = str(getattr(record, "given_name", "") or "").strip()
            surname = str(getattr(record, "surname", "") or "").strip()
            name = f"{given} {surname}".strip()
        if not name or name in ("Unknown Player", "Parse Error"):
            continue
        out[entry.record_id] = name
    return out


def load_eq_linked_team_rosters(
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
) -> List[EQLinkedTeamRoster]:
    """Load parser-backed EQ team rosters via external JUG record links."""
    team_bytes = Path(team_file).read_bytes()
    player_name_by_id = _build_jug_player_name_index(player_file)
    indexed = IndexedFDIFile.from_bytes(team_bytes)

    rosters: List[EQLinkedTeamRoster] = []
    for entry in indexed.entries:
        raw_payload = team_bytes[entry.payload_offset : entry.payload_offset + entry.payload_length]
        roster = parse_eq_external_team_roster_payload(raw_payload, player_name_by_id)
        if roster is None:
            continue
        roster.eq_record_id = entry.record_id
        rosters.append(roster)
    return rosters


__all__ = [
    "EQLinkedRosterRow",
    "EQLinkedTeamRoster",
    "load_eq_linked_team_rosters",
    "parse_eq_external_team_roster_payload",
]
