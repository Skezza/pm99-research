"""Shared data source helpers for the PM99 editor GUI/CLI."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, List, Tuple, TypeVar

from app.loaders import load_coaches
from app.loaders import load_teams
from app.models import PlayerRecord, TeamRecord
from app.scanner import find_player_records
from app.xor import decode_entry

T = TypeVar('T')
_PLAYER_SUBRECORD_SEPARATOR = bytes([0xDD, 0x63, 0x60])


@dataclass
class RecordEntry(Generic[T]):
    offset: int
    record: T
    source: str


def _has_name_marker(record: PlayerRecord) -> bool:
    raw = getattr(record, "raw_data", None)
    if raw is None:
        return False
    marker = PlayerRecord._find_name_end_in_data(raw)
    return marker is not None


def gather_player_records(file_path: str) -> Tuple[List[RecordEntry[PlayerRecord]], List[RecordEntry[PlayerRecord]]]:
    """Return (valid_records, uncertain_records) parsed from the player FDI."""
    data = Path(file_path).read_bytes()
    valid: List[RecordEntry[PlayerRecord]] = []
    uncertain: List[RecordEntry[PlayerRecord]] = []
    for offset, record in find_player_records(data):
        entry = RecordEntry(offset=offset, record=record, source="scanner")
        if _has_name_marker(record):
            entry.source = "scanner (marker)"
            valid.append(entry)
        else:
            entry.source = "scanner (no marker)"
            uncertain.append(entry)
    return valid, uncertain


def gather_player_records_strict(
    file_path: str,
    require_team_id: bool = False,
    include_subrecords: bool = True,
) -> Tuple[List[RecordEntry[PlayerRecord]], List[RecordEntry[PlayerRecord]]]:
    """
    Return player-like records found at real FDI entry boundaries via sequential scan.

    This is slower than the scanner path but avoids many embedded-text false positives.
    """
    data = Path(file_path).read_bytes()
    valid: List[RecordEntry[PlayerRecord]] = []
    uncertain: List[RecordEntry[PlayerRecord]] = []
    seen_offsets: set[int] = set()

    offset = 0x400
    data_len = len(data)
    while offset + 2 <= data_len:
        length = int.from_bytes(data[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue

        # Player records are small compared to biography/news blobs.
        if 40 <= length <= 1024:
            try:
                decoded, _ = decode_entry(data, offset)
                record = PlayerRecord.from_bytes(decoded, offset)
                name = (getattr(record, "name", None) or "").strip()
                if not name:
                    name = f"{getattr(record, 'given_name', '') or ''} {getattr(record, 'surname', '') or ''}".strip()
                if name in ("", "Unknown Player", "Parse Error"):
                    raise ValueError("not a named player")

                squad_number = getattr(record, "squad_number", None)
                if not isinstance(squad_number, int) or not (0 <= squad_number <= 255):
                    raise ValueError("invalid squad number")

                team_id = getattr(record, "team_id", None)
                if require_team_id and int(team_id or 0) == 0:
                    raise ValueError("missing team id")

                if offset in seen_offsets:
                    raise ValueError("duplicate offset")
                seen_offsets.add(offset)

                entry = RecordEntry(offset=offset, record=record, source="entry (strict)")
                if _has_name_marker(record):
                    valid.append(entry)
                else:
                    uncertain.append(entry)
            except Exception:
                pass
            offset += length + 2
            continue

        # Large container records may hold separator-delimited player subrecords.
        if include_subrecords and 1024 < length <= 200000:
            try:
                decoded, _ = decode_entry(data, offset)
                if _PLAYER_SUBRECORD_SEPARATOR in decoded:
                    starts: List[int] = []
                    pos = decoded.find(_PLAYER_SUBRECORD_SEPARATOR)
                    while pos != -1:
                        starts.append(pos)
                        pos = decoded.find(_PLAYER_SUBRECORD_SEPARATOR, pos + 1)

                    for idx, start in enumerate(starts):
                        end = starts[idx + 1] if idx + 1 < len(starts) else len(decoded)
                        segment = decoded[start:end]
                        # Separator-delimited player chunks in this dataset are usually small.
                        if not (50 <= len(segment) <= 256):
                            continue
                        try:
                            subrecord = PlayerRecord.from_bytes(segment, offset + 2 + start)
                            # Preserve provenance for future container-aware writes/investigation.
                            try:
                                setattr(subrecord, "container_offset", offset)
                                setattr(subrecord, "container_relative_offset", start)
                                setattr(subrecord, "original_raw_data", bytes(segment))
                            except Exception:
                                pass

                            name = (getattr(subrecord, "name", None) or "").strip()
                            if not name:
                                name = f"{getattr(subrecord, 'given_name', '') or ''} {getattr(subrecord, 'surname', '') or ''}".strip()
                            if name in ("", "Unknown Player", "Parse Error"):
                                continue

                            squad_number = getattr(subrecord, "squad_number", None)
                            if not isinstance(squad_number, int) or not (0 <= squad_number <= 255):
                                continue

                            team_id = getattr(subrecord, "team_id", None)
                            if require_team_id and int(team_id or 0) == 0:
                                continue

                            sub_offset = offset + 2 + start
                            if sub_offset in seen_offsets:
                                continue
                            seen_offsets.add(sub_offset)

                            entry = RecordEntry(offset=sub_offset, record=subrecord, source="entry-subrecord (strict)")
                            if _has_name_marker(subrecord):
                                valid.append(entry)
                            else:
                                uncertain.append(entry)
                        except Exception:
                            continue
            except Exception:
                pass

        # Valid length-prefixed entry, but too large/small to be a player record.
        offset += length + 2

    return valid, uncertain


def _scan_team_sections(data: bytes) -> List[Tuple[int, TeamRecord]]:
    separator = bytes([0x61, 0xdd, 0x63])
    positions = []
    pos = data.find(separator)
    while pos != -1:
        positions.append(pos)
        pos = data.find(separator, pos + 1)
    records: List[Tuple[int, TeamRecord]] = []
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else len(data)
        segment = data[start:end]
        try:
            team = TeamRecord(segment, start)
            records.append((start, team))
        except Exception:
            continue
    return records


def gather_team_records(file_path: str) -> Tuple[List[RecordEntry[TeamRecord]], List[RecordEntry[TeamRecord]]]:
    data = Path(file_path).read_bytes()
    aggregated: dict[int, RecordEntry[TeamRecord]] = {}

    def _add_team(offset: int, team: TeamRecord, source: str) -> None:
        if offset in aggregated:
            return
        aggregated[offset] = RecordEntry(offset=offset, record=team, source=source)

    for offset, team in load_teams(file_path):
        _add_team(offset, team, "loader")

    for offset, team in _scan_team_sections(data):
        _add_team(offset, team, "scan")

    valid: List[RecordEntry[TeamRecord]] = []
    uncertain: List[RecordEntry[TeamRecord]] = []
    for offset in sorted(aggregated.keys()):
        entry = aggregated[offset]
        name = getattr(entry.record, 'name', '') or ''
        if name and name not in ("Unknown Team", "Parse Error"):
            valid.append(entry)
        else:
            uncertain.append(entry)
    return valid, uncertain


def gather_coach_records(file_path: str) -> Tuple[List[RecordEntry[Any]], List[RecordEntry[Any]]]:
    """Return (valid_records, uncertain_records) parsed from the coach FDI."""
    valid: List[RecordEntry[Any]] = []
    for offset, coach in load_coaches(file_path):
        valid.append(RecordEntry(offset=offset, record=coach, source="loader"))
    return valid, []
