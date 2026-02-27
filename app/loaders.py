"""
Data loaders for Premier Manager 99 FDI files.

This module provides shared loading logic for coaches and teams,
applying strict validation filters to reject corrupted entries.
"""

from pathlib import Path
import sys
from typing import List, Tuple, Any
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode
from app.models import TeamRecord
from app.coach_models import parse_coaches_from_record, EditableCoachRecord


def decode_entry(data: bytes, offset: int) -> Tuple[bytes, int]:
    """
    Decode an entry at the given offset.
    
    Args:
        data: Raw file data
        offset: Starting offset in the file
        
    Returns:
        Tuple of (decoded_data, length)
    """
    if offset + 2 > len(data):
        return b'', 0
    
    # Read length (2 bytes, little-endian)
    length = int.from_bytes(data[offset:offset+2], 'little')
    
    if offset + 2 + length > len(data):
        return b'', 0
    
    # Extract encoded data
    encoded = data[offset+2:offset+2+length]
    
    # XOR decode
    decoded = xor_decode(encoded)
    
    return decoded, length


def _is_valid_team_name(name: str) -> bool:
    """Return True when the parsed team name is conservative enough to trust."""
    if not name or name in ("Unknown Team", "Parse Error", ""):
        return False
    if len(name) < 4 or len(name) > 60:
        return False
    if not name[0].isupper():
        return False
    if not any(c.isalpha() for c in name):
        return False
    return True


def _append_team_segments(
    *,
    decoded_payload: bytes,
    base_offset: int,
    parsed: List[Tuple[int, TeamRecord]],
    seen_names: set[str],
    container_offset: int | None = None,
    container_relative_base: int = 0,
    container_length: int | None = None,
    container_encoding: str | None = None,
) -> None:
    """Extract separator-delimited team subrecords from one decoded payload."""
    separator = bytes([0x61, 0xdd, 0x63])
    if separator not in decoded_payload:
        return

    positions = []
    search_pos = 0
    while search_pos < len(decoded_payload):
        search_pos = decoded_payload.find(separator, search_pos)
        if search_pos == -1:
            break
        positions.append(search_pos)
        search_pos += 3

    for idx, sep_pos in enumerate(positions):
        next_sep = positions[idx + 1] if idx + 1 < len(positions) else len(decoded_payload)
        record_data = decoded_payload[sep_pos:next_sep]
        try:
            record_offset = base_offset + sep_pos
            team = TeamRecord(record_data, record_offset)
        except Exception:
            continue

        name = getattr(team, "name", None) or ""
        if not _is_valid_team_name(name):
            continue
        if name in seen_names:
            continue

        if container_offset is not None:
            team.container_offset = container_offset
            team.container_relative_offset = container_relative_base + sep_pos
            team.container_length = container_length
            team.container_encoding = container_encoding

        seen_names.add(name)
        parsed.append((record_offset, team))


def _load_teams_from_indexed_container(data: bytes) -> List[Tuple[int, TeamRecord]]:
    """Load teams using the DMFI indexed layout confirmed in DBASEPRE.EXE."""
    parsed: List[Tuple[int, TeamRecord]] = []
    seen_names: set[str] = set()

    indexed = IndexedFDIFile.from_bytes(data)
    for entry in indexed.entries:
        try:
            decoded_payload = entry.decode_payload(data)
        except Exception:
            continue
        _append_team_segments(
            decoded_payload=decoded_payload,
            base_offset=entry.payload_offset,
            parsed=parsed,
            seen_names=seen_names,
            container_offset=entry.payload_offset,
            container_length=entry.payload_length,
            container_encoding="indexed_xor",
        )
    return parsed


def _load_teams_by_sequential_scan(data: bytes) -> List[Tuple[int, TeamRecord]]:
    """Legacy fallback for files that do not parse as indexed DMFI containers."""
    parsed: List[Tuple[int, TeamRecord]] = []
    seen_names: set[str] = set()

    pos = 0x400
    data_len = len(data)
    while pos + 2 <= data_len:
        try:
            decoded, length = decode_entry(data, pos)
            if length <= 0 or pos + 2 + length > data_len:
                pos += 1
                continue

            _append_team_segments(
                decoded_payload=decoded,
                base_offset=pos,
                parsed=parsed,
                seen_names=seen_names,
                container_offset=pos,
                container_encoding="length_prefixed_entry",
            )
            pos += 2 + length
        except Exception:
            pos += 1

    return parsed


def load_teams(file_path: str) -> List[Tuple[int, TeamRecord]]:
    """
    Load teams from EQ98030.FDI using the binary-backed indexed parser when available.
    """
    parsed: List[Tuple[int, TeamRecord]] = []

    try:
        data = Path(file_path).read_bytes()
        try:
            parsed = _load_teams_from_indexed_container(data)
        except Exception:
            parsed = []

        if not parsed:
            parsed = _load_teams_by_sequential_scan(data)
    except Exception as e:
        print(f"[TEAM LOADER] Error loading teams: {e}", file=sys.stderr)

    print(f"[TEAM LOADER] Loading teams from {file_path}... {len(parsed)} teams loaded", file=sys.stderr)
    return parsed


_COACH_COMMON_PHRASES = (
    "boa morte", "rui barros", "mark hatelely", "stan collymore",
    "jamie redknapp", "bobby moore", "bryan robson", "nick barmby",
    "darren huckerby", "michael gray", "asa harford", "john wark",
    "ian rush", "dave beasant", "steve simonsen", "fabrizio ravanelli",
    "roberto baggio", "marcus stewart", "wayne allison", "delroy facey",
    "darren eadie", "keith gillespie", "pal lydersen", "john jensen",
    "peter hill", "steve gibson", "don megson", "billy bonds",
    "mick buxton", "frank worthington", "don givens", "archie gemmil",
    "willie johnston", "alan buckley", "billy hamilton", "bob lord",
    "jock stein", "andy roxburgh", "dave basset", "dennis smith",
    "viv anderson", "steve gritt", "alan smith", "dave sexton",
    "terry fenwick", "colin todd", "peter robinson", "roy evans",
    "bill shankly", "stan ternent", "bobby robson", "lou macari",
    "archie knox", "roy hodgson", "john reames", "jeff wood",
    "premier league", "first division", "second division", "third division", "fourth division",
    "first divis", "second divsion", "third divison", "italian second", "italian championship",
    "scottish first", "scottish second", "french fifth", "norwegian first", "norwegian premier",
    "norwegian champions", "league championsh", "danish football", "swiss first", "swedish olympic",
    "norwegian olympic", "swedish national", "norway olympic", "sweden under", "sweden olympic",
    "vauxhall conference", "french league", "spanish league", "italian league", "german league",
    "football league", "scottish league", "english league", "north american", "soccer league",
    "league cup", "european cup", "world cup", "french cup", "spanish cup", "italian cup", "japan cup",
    "cup winner", "cup winners", "champions league", "uefa cup", "scottish cup", "irish cup",
    "cup champion", "winners cup", "charity shield", "european championship", "intercontinental cup",
    "european supercup", "dutch league", "dutch cup", "italian supercup", "dutch first",
    "european champions", "european champion", "cup title", "league champion", "twice league",
    "auto windscreen", "auto windscreens", "twin towers", "amateur cup", "systems cup", "cup usa",
    "olympic games", "world champions", "european player", "european super",
    "old trafford", "san siro", "goodison park", "highbury arsenal", "elland road",
    "white hart", "upton park", "loftus road", "stamford bridge", "maine road",
    "selhurst park", "burnden park", "the dell", "ewood park",
    "real madrid", "manchester utd", "manchester uniyed", "queens park", "preston north",
    "oldham ahtletic", "liverpool sch", "sheffield wednesday", "west brom", "port vale",
    "paris saint", "werder bremen", "borussia", "bayern munich", "grasshopper zurich",
    "bristol rov", "doncaster rov", "plymouth argyle", "meadowbank thistle",
    "seattle sounders", "vancouver whitecaps", "fort lauderdale",
    "atletico madrid", "viking stavanger", "real sociedad", "south liverpool",
    "the england", "durham school", "east durham", "north londoners", "east london",
    "witton gilbert", "east stirling", "liverpool university", "united school",
    "the scottish", "the gallic", "the french", "the hornets", "red devils",
    "the hammers", "the dutchman", "the samp", "the bald eagle", "the rams",
    "captain marvel", "bald eagle", "fergie babes",
    "head coach", "technical advisor", "national team", "segundo entrenador",
    "union coach", "norwegian coach",
    "although harry", "although robson", "although john", "under gordon", "under ron",
    "after bobby", "eventually leicester", "eventually portsmouth", "considered arsenal",
    "replaced howard", "around december",
    "division champion", "division runner", "league championship", "quarter finals",
    "cup runner", "british championship", "league champions",
    "belgian ", "liberian ", "yugoslavian ", "frenchman ", "german ", "argentinian ",
    "united states", "northern ireland", "soviet union",
    "when ", "with ", "from ", "new year", "second jun",
    "monaco arsene", "european parliament",
    "scottish footballer", "french football", "french federation",
    "second world",
    "highfield road", "shepshed charterhouse", "filbert street",
)

_COACH_GARBAGE_SUFFIXES = {
    "aa", "ba", "ca", "da", "ea", "fa", "ga", "ha", "ia", "ja", "ka",
    "la", "ma", "na", "oa", "pa", "qa", "ra", "sa", "ta", "ua", "va",
    "wa", "xa", "ya", "za",
}
_COACH_SUFFIX_EXCEPTIONS = {"da", "de", "van", "von", "del", "di", "el", "la"}


def _is_valid_coach_name(name: str, seen_names: set[str]) -> bool:
    """Return True when a parsed coach name is conservative enough to trust."""
    if not name or len(name) < 6 or len(name) > 40:
        return False
    if not name[0].isupper() or " " not in name:
        return False

    parts = name.split()
    if len(parts) < 2:
        return False

    name_lower = name.lower()
    if any(phrase in name_lower for phrase in _COACH_COMMON_PHRASES):
        return False

    for part in parts:
        if len(part) < 2 or len(part) > 20:
            return False
        if not part[0].isupper():
            return False
        if len(part) > 3:
            last_two = part[-2:].lower()
            if last_two in _COACH_GARBAGE_SUFFIXES and part.lower() not in _COACH_SUFFIX_EXCEPTIONS:
                return False

    ascii_ratio = sum(1 for ch in name if 32 <= ord(ch) < 127) / len(name)
    if ascii_ratio < 0.85:
        return False
    if name.count("a") > len(name) * 0.6:
        return False
    if name in seen_names:
        return False
    return True


def _append_coaches_from_payload(
    *,
    decoded_payload: bytes,
    record_offset: int,
    parsed_coaches: List[Tuple[int, Any]],
    seen_names: set[str],
    container_offset: int | None = None,
    container_length: int | None = None,
    container_encoding: str | None = None,
) -> None:
    """Parse and append trusted coaches from one decoded ENT payload."""
    try:
        coaches = parse_coaches_from_record(decoded_payload) or []
    except Exception:
        return

    for coach in coaches:
        name = getattr(coach, "full_name", "")
        given = getattr(coach, "given_name", "")
        surname = getattr(coach, "surname", "")
        if not _is_valid_coach_name(name, seen_names):
            continue

        seen_names.add(name)
        editable_coach = EditableCoachRecord(decoded_payload, record_offset, given, surname)
        if container_offset is not None:
            editable_coach.container_offset = container_offset
            editable_coach.container_length = container_length
            editable_coach.container_encoding = container_encoding
        parsed_coaches.append((record_offset, editable_coach))


def load_coaches(file_path: str) -> List[Tuple[int, Any]]:
    """
    Load coaches from ENT98030.FDI with the binary-backed indexed parser when available.
    
    Args:
        file_path: Path to the coaches FDI file
        
    Returns:
        List of (offset, CoachRecord) tuples for valid coaches
    """
    parsed_coaches: List[Tuple[int, Any]] = []
    
    try:
        data = Path(file_path).read_bytes()
        seen_names = set()

        try:
            indexed = IndexedFDIFile.from_bytes(data)
            for entry in indexed.entries:
                try:
                    decoded_payload = entry.decode_payload(data)
                except Exception:
                    continue
                _append_coaches_from_payload(
                    decoded_payload=decoded_payload,
                    record_offset=entry.payload_offset,
                    parsed_coaches=parsed_coaches,
                    seen_names=seen_names,
                    container_offset=entry.payload_offset,
                    container_length=entry.payload_length,
                    container_encoding="indexed_xor",
                )
        except Exception:
            pass

        if parsed_coaches:
            return parsed_coaches

        pos = 0x400
        while pos < len(data) - 1000:
            length = 0
            try:
                decoded, length = decode_entry(data, pos)
                if length < 100 or length > 50000:
                    pos += 2
                    continue
                _append_coaches_from_payload(
                    decoded_payload=decoded,
                    record_offset=pos,
                    parsed_coaches=parsed_coaches,
                    seen_names=seen_names,
                )
            except Exception:
                pass

            pos += 2 + length if length > 0 else 1
            
    except Exception as e:
        print(f"[COACH LOADER] Error loading coaches: {e}", file=sys.stderr)
    
    return parsed_coaches
