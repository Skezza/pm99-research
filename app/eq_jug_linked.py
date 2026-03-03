"""Parser-backed EQ to JUG roster extraction using DBASEPRE.EXE layout."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional

from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import xor_decode


_EXTERNAL_LINK_JUMP = 0x6E7
_MIN_EXTERNAL_LINK_RECORD_SIZE = 600
_JUG_NAME_SCAN_START = 10
_JUG_NAME_SCAN_BYTES = 192
_JUG_NAME_SEGMENT_SPLIT_RE = re.compile(r"a(?=[A-ZÀ-Ý])")
_JUG_NAME_UPPER_BOUNDARY_RE = re.compile(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Ý])")
_JUG_NAME_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:[.'-][A-Za-zÀ-ÿ]+)*")
_JUG_NAME_CONNECTORS = {
    "da",
    "das",
    "de",
    "del",
    "den",
    "der",
    "di",
    "do",
    "dos",
    "du",
    "el",
    "la",
    "las",
    "le",
    "los",
    "van",
    "von",
    "y",
}


@dataclass(frozen=True)
class EQLinkedRosterRow:
    slot_index: int
    flag: int
    player_record_id: int
    player_name: str = ""
    raw_row_offset: int = -1


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
    payload_offset: int = 0
    payload_length: int = 0


def _alpha_letters(text: str) -> str:
    return "".join(ch for ch in text if ch.isalpha())


def _trim_uppercase_suffix_artifact(token: str) -> str:
    alpha = _alpha_letters(token)
    if len(alpha) < 4:
        return token

    uppercase_prefix = 0
    for ch in alpha:
        if ch.isupper():
            uppercase_prefix += 1
        else:
            break

    if uppercase_prefix < 3 or uppercase_prefix >= len(alpha):
        return token
    if not alpha[uppercase_prefix:].islower():
        return token

    out: List[str] = []
    seen_letters = 0
    for ch in token:
        out.append(ch)
        if ch.isalpha():
            seen_letters += 1
            if seen_letters >= uppercase_prefix:
                break
    return "".join(out).rstrip(" .'-")


def _normalize_jug_name_token(token: str) -> Optional[tuple[str, str]]:
    token = token.strip(" .'-")
    if not token:
        return None

    lowered = token.lower()
    if lowered in _JUG_NAME_CONNECTORS:
        return lowered, "connector"

    token = _trim_uppercase_suffix_artifact(token)
    alpha = _alpha_letters(token)
    if not alpha:
        return None

    if len(alpha) == 1 and alpha[0].isupper():
        return alpha, "initial"
    if all(ch.isupper() for ch in alpha):
        return token, "upper"
    if alpha[0].isupper() and all(ch.islower() for ch in alpha[1:]):
        if len(alpha) > 22:
            return None
        if len(alpha) < 3 and alpha != "Mc":
            return None
        return token, "title"
    return None


def _extract_name_from_jug_prefix_segment(segment: str) -> str:
    segment = re.split(r"a{3,}", segment, maxsplit=1)[0]
    if not segment:
        return ""

    # The legacy name block often glues tokens together at lower->upper boundaries.
    segment = re.sub(r"(?<=[A-Za-zÀ-ÿ])\.(?=[A-Za-zÀ-ÿ])", " ", segment)
    segment = _JUG_NAME_UPPER_BOUNDARY_RE.sub(" ", segment)
    segment = re.sub(r"[^A-Za-zÀ-ÿ .'-]+", " ", segment)
    segment = re.sub(r"\s+", " ", segment).strip()
    if not segment:
        return ""

    tokens: List[tuple[str, str]] = []
    for raw_token in _JUG_NAME_TOKEN_RE.findall(segment):
        normalized = _normalize_jug_name_token(raw_token)
        if normalized is None:
            if tokens:
                break
            continue
        tokens.append(normalized)

    while tokens and tokens[0][1] == "connector":
        tokens.pop(0)
    while tokens and tokens[-1][1] == "connector":
        tokens.pop()

    real_tokens = [(token, kind) for token, kind in tokens if kind != "connector"]
    if len(real_tokens) < 2:
        return ""

    # Keep this conservative: the recovered suffix must still include at least one
    # clear uppercase surname-style token, otherwise we keep the name unresolved.
    if not any(kind == "upper" and len(_alpha_letters(token)) >= 2 for token, kind in real_tokens):
        return ""

    return " ".join(token for token, _ in tokens)


def _extract_jug_name_from_raw_payload(raw_payload: bytes) -> str:
    probe = xor_decode(raw_payload[:_JUG_NAME_SCAN_BYTES])
    if len(probe) <= _JUG_NAME_SCAN_START:
        return ""

    region = probe[_JUG_NAME_SCAN_START:]
    marker = region.find(b"aaaa")
    if marker != -1:
        region = region[:marker]
    if not region:
        return ""

    text = region.decode("cp1252", errors="replace")
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    segments = [segment for segment in _JUG_NAME_SEGMENT_SPLIT_RE.split(text) if segment.strip()]
    names: List[str] = []
    for segment in segments:
        name = _extract_name_from_jug_prefix_segment(segment)
        if name:
            names.append(name)

    if names:
        return names[-1]
    return _extract_name_from_jug_prefix_segment(text)


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


def _advance_legacy_mode_zero_cursor(raw_payload: bytes, cursor: int, record_size: int) -> int:
    """Skip the legacy inline mode-0 block and return the base for the external link tables."""
    if record_size > 0x207:
        cursor += 2
    cursor += 4
    _, cursor = _read_xor_u16_string(raw_payload, cursor)
    cursor += 4
    cursor += 4
    _, cursor = _read_xor_u16_string(raw_payload, cursor)
    _, cursor = _read_xor_u16_string(raw_payload, cursor)
    cursor += 3
    cursor += 20 if record_size >= 0x1F9 else 10
    cursor += 15
    cursor += 46 if record_size >= 0x1F9 else 42
    if record_size < 700:
        if record_size < 0x1F9:
            pair_count = 7
        elif record_size < 0x203:
            pair_count = 17
        else:
            pair_count = 21
        cursor += pair_count * 2
    else:
        if cursor >= len(raw_payload):
            raise ValueError("truncated legacy sparse-count byte")
        sparse_count = raw_payload[cursor]
        cursor += 1 + sparse_count * 3
    if cursor > len(raw_payload):
        raise ValueError("legacy mode-0 block overruns payload")
    return cursor


def parse_eq_external_team_roster_payload(
    raw_payload: bytes,
    player_name_by_id: Dict[int, str],
) -> Optional[EQLinkedTeamRoster]:
    """
    Parse one raw EQ indexed payload using the DBASEPRE.EXE external-link layout.

    Only the large-record (`>= 600`) path is handled here. Both the external mode
    and the legacy inline mode-0 prelude are supported up to the shared external
    ENT/JUG link tables.
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

    link_base = cursor
    if mode_byte == 0:
        try:
            link_base = _advance_legacy_mode_zero_cursor(raw_payload, cursor, record_size)
        except Exception:
            return None

    ent_cursor = link_base + _EXTERNAL_LINK_JUMP
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
                raw_row_offset=player_cursor,
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
        raw_payload = player_bytes[entry.payload_offset : entry.payload_offset + entry.payload_length]
        record = None
        try:
            payload = entry.decode_payload(player_bytes)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            name = str(getattr(record, "name", "") or "").strip()
        except Exception:
            name = ""
        if not name:
            given = str(getattr(record, "given_name", "") or "").strip()
            surname = str(getattr(record, "surname", "") or "").strip()
            name = f"{given} {surname}".strip()
        if not name or name in ("Unknown Player", "Parse Error"):
            name = _extract_jug_name_from_raw_payload(raw_payload)
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
        roster.payload_offset = entry.payload_offset
        roster.payload_length = entry.payload_length
        rosters.append(roster)
    return rosters


__all__ = [
    "EQLinkedRosterRow",
    "EQLinkedTeamRoster",
    "load_eq_linked_team_rosters",
    "parse_eq_external_team_roster_payload",
]
