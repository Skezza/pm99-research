"""Data models for PM99 database records.

Implements Python dataclasses matching the binary structures from MANAGPRE.EXE.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import struct
import logging

from pm99_editor.xor import decode_entry, encode_entry, read_string, write_string
 
logger = logging.getLogger(__name__)
import re

class TeamRecord:
    """Team record with ID and stadium extraction + modification support."""

    def __init__(self, data: bytes, record_offset: int):
        self.raw_data = bytearray(data)
        self.record_offset = record_offset

        # Team ID and where it was found (offset inside raw_data) so we can write it back
        try:
            tid, tid_off = self._extract_team_id()
        except Exception:
            tid, tid_off = 0, None
        self.team_id = tid
        self.team_id_offset = tid_off

        # Team name and byte-range
        try:
            name, ns, ne = self._extract_name()
        except Exception:
            name, ns, ne = "Unknown Team", 0, 0
        self.name = name
        self.name_start = ns
        self.name_end = ne

        # Stadium name and its byte-range (usually follows the team name)
        try:
            stadium, ss, se = self._extract_stadium()
        except Exception:
            stadium, ss, se = "", 0, 0
        self.stadium = stadium
        self.stadium_start = ss
        self.stadium_end = se

        # Parsed stadium details (capacity, car park, pitch quality)
        try:
            cap, car, pitch = self._parse_stadium_details(self.stadium or "")
        except Exception:
            cap, car, pitch = None, None, None
        self.stadium_capacity = cap
        self.car_park = car
        self.pitch = pitch

        # League information (to be parsed from metadata)
        try:
            league = self._extract_league()
        except Exception:
            league = "Unknown League"
        self.league = league

    def _extract_team_id(self):
        """Scan for plausible team ID (3000-5000 range) and return (value, offset)."""
        for i in range(0, len(self.raw_data) - 1, 2):
            if i + 2 <= len(self.raw_data):
                try:
                    val = struct.unpack_from("<H", self.raw_data, i)[0]
                except Exception:
                    continue
                if 3000 <= val <= 5000:
                    return val, i
        return 0, None

    def _extract_name(self):
        """Extract team name from team record data.
        
        Team records from EQ98030.FDI have structure:
        [separator: 0x61 0xdd 0x63] [prefix bytes] [TEAM NAME] [lowercase 'a' separator] [STADIUM/DATA]
        """
        try:
            data_bytes = bytes(self.raw_data)
            
            # Skip separator if present at start (3 bytes: 0x61 0xdd 0x63)
            start = 0
            if len(data_bytes) >= 3 and data_bytes[0:3] == bytes([0x61, 0xdd, 0x63]):
                start = 3
            
            # Skip prefix bytes until we find first uppercase letter
            # Prefix is typically like: 0x61 0x60 XX 0x61 or similar
            while start < len(data_bytes) and start < 20:
                if data_bytes[start] >= ord('A') and data_bytes[start] <= ord('Z'):
                    break
                start += 1
            
            if start >= len(data_bytes):
                return "Unknown Team", 0, 0
            
            # Find end of team name
            # Team names typically end with lowercase 'a' before stadium text
            # or when we hit the stadium name (next uppercase run)
            end = start
            for i in range(start, min(start + 60, len(data_bytes))):
                c = data_bytes[i]
                
                # Stop at certain separator patterns:
                # 1. Lowercase 'a' followed by uppercase (stadium name starts)
                if c == ord('a') and i > start + 5:
                    # Check if next char is uppercase (stadium name)
                    if i + 1 < len(data_bytes):
                        next_c = data_bytes[i + 1]
                        # Also check for common stadium prefixes
                        if (ord('A') <= next_c <= ord('Z')) or next_c in [ord('S'), ord('O'), ord('V')]:
                            end = i
                            break
                
                # Stop at non-printable characters
                if c < 32 or c > 126:
                    end = i
                    break
                
                end = i + 1
            
            if end > start:
                name_bytes = data_bytes[start:end]
                name = name_bytes.decode('latin1', errors='replace').strip()
                
                # Clean up: remove ONLY the final trailing single lowercase letter if it's a separator
                # Pattern: "Barcelonai" -> "Barcelona", "Athletic Clubh" -> "Athletic Club"
                # But preserve: "Barcelona" (already clean)
                if len(name) > 5 and name[-1].islower():
                    # Check if it looks like a separator (single letter after word)
                    last_char = name[-1]
                    
                    # If preceded by uppercase, space, or period: definitely a separator
                    # Examples: "F.|p", "Club|h", "Madrid|q"
                    if len(name) >= 2:
                        prev_char = name[-2]
                        if prev_char.isupper() or prev_char in ['.', ' ']:
                            # Remove just this one letter
                            name = name[:-1].strip()
                        elif prev_char.islower():
                            # It's part of a word - check if it's a common separator letter
                            # Common separators: single letters like i, o, g, h, j, k, m, n, p, q, r, u, v, x
                            # that wouldn't normally end a team name
                            # Preserve: s (plural), d (Madrid, United)
                            separator_chars = set('aioghijkmnpqruvwx')
                            if last_char in separator_chars:
                                # Additional check: Spanish/Italian team names often end in specific letters
                                # Keep if it's part of a valid ending
                                valid_endings = {'ona', 'ivo', 'alo', 'ano', 'ino'}  # Barcelona, Deportivo, etc.
                                if len(name) >= 4:
                                    last_three = name[-3:].lower()
                                    if last_three not in valid_endings:
                                        name = name[:-1].strip()
                
                # Additional cleanup: remove trailing dots, commas, spaces
                name = name.rstrip('., ')
                
                # Final validation
                if len(name) >= 3 and name[0].isupper() and any(c.isalpha() for c in name):
                    return name, start, end
            
            return "Unknown Team", 0, 0
            
        except Exception as e:
            logger.debug("TeamRecord._extract_name failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
            return "Parse Error", 0, 0

    def _find_name_start(self) -> int:
        """Helper to find name start offset; kept for compatibility with older callers."""
        try:
            return self.name_start or 0
        except Exception:
            return 0

    def _extract_stadium(self):
        """Attempt to locate a stadium name appearing after the team name.

        Heuristics:
        - Search for printable runs after the name_end
        - Prefer runs containing common stadium keywords (stadium, ground, park, lane, arena, road, centre)
        - Fallback: the first printable run after the team name
        """
        try:
            data = bytes(self.raw_data)
            start_search = self.name_end if getattr(self, 'name_end', None) else 0
            if start_search < 0:
                start_search = 0

            text_pattern = rb'[\x20-\x7e]{4,80}'
            # Search in the remainder of the data
            tail = data[start_search:]
            matches = list(re.finditer(text_pattern, tail))
            if not matches:
                return "", 0, 0

            # Look for stadium-like keywords
            stadium_keywords = ('stadium', 'ground', 'park', 'lane', 'field', 'arena', 'centre', 'center', 'stadio', 'road')
            for m in matches:
                text = m.group().decode('latin-1', errors='replace').strip()
                if not text:
                    continue
                lower = text.lower()
                if any(k in lower for k in stadium_keywords):
                    abs_start = start_search + m.start()
                    abs_end = start_search + m.end()
                    return text, abs_start, abs_end

            # Fallback to the first printable run after the name
            m = matches[0]
            text = m.group().decode('latin-1', errors='replace').strip()
            abs_start = start_search + m.start()
            abs_end = start_search + m.end()
            return text, abs_start, abs_end
        except Exception as e:
            logger.debug("TeamRecord._extract_stadium failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
            return "", 0, 0

    def _parse_stadium_details(self, text: str):
        """Parse capacity, car park and pitch quality from a stadium description string."""
        if not text:
            return None, None, None
        cap = None
        car = None
        pitch = None
        try:
            # CAPACITY: 32,786 seats
            import re as _re
            m = _re.search(r'CAPACITY[:\s]*([\d,]+)', text, flags=_re.IGNORECASE)
            if m:
                try:
                    cap = int(m.group(1).replace(',', ''))
                except Exception:
                    cap = None

            # CAR PARK: 2,000 spaces
            m2 = _re.search(r'CAR\s*PARK[:\s]*([\d,]+)', text, flags=_re.IGNORECASE)
            if m2:
                try:
                    car = int(m2.group(1).replace(',', ''))
                except Exception:
                    car = None

            # PITCH: GOOD / EXCELLENT / POOR
            m3 = _re.search(r'PITCH[:\s]*([A-Za-z]+)', text, flags=_re.IGNORECASE)
            if m3:
                pitch = m3.group(1).upper()
        except Exception:
            pass
        return cap, car, pitch

    def _extract_league(self):
        """Extract league information based on team_id ranges.
        
        Uses the league_definitions module to map team IDs to leagues.
        """
        if not hasattr(self, 'team_id') or self.team_id is None or self.team_id == 0:
            return "Unknown League"
        
        try:
            from pm99_editor.league_definitions import get_team_league
            country, league_name = get_team_league(self.team_id)
            if country and league_name:
                return league_name
        except Exception:
            pass
        
        return "Unknown League"
    
    def get_country(self) -> str:
        """Get the country this team belongs to."""
        try:
            from pm99_editor.league_definitions import get_team_league
            country, _ = get_team_league(self.team_id)
            return country or "Unknown"
        except Exception:
            return "Unknown"

    def set_name(self, new_name: str):
        """Set new team name in raw_data (in-place when possible)."""
        if new_name is None:
            return bytes(self.raw_data)
        if len(new_name) > 60:
            new_name = new_name[:60]
        new_bytes = new_name.encode('latin-1', errors='replace')

        # Ensure name_start/name_end exist; recompute if needed
        if not getattr(self, 'name_start', None) or not getattr(self, 'name_end', None) or self.name_end <= self.name_start:
            # Recompute via _extract_name
            name, ns, ne = self._extract_name()
            self.name = name
            self.name_start = ns
            self.name_end = ne

        old_len = self.name_end - self.name_start if (self.name_end and self.name_start) else 0
        if old_len <= 0:
            # Append near end if no slot found
            self.raw_data.extend(new_bytes + b' ')
            self.name_start = len(self.raw_data) - len(new_bytes) - 1
            self.name_end = self.name_start + len(new_bytes)
        else:
            if len(new_bytes) <= old_len:
                padded = new_bytes + b' ' * (old_len - len(new_bytes))
                self.raw_data[self.name_start:self.name_start + old_len] = padded
                self.name_end = self.name_start + old_len
            else:
                # Expand in-place
                self.raw_data[self.name_start:self.name_end] = new_bytes
                self.name_end = self.name_start + len(new_bytes)

        self.name = new_name
        # Recompute stadium region after name changes
        self.stadium, self.stadium_start, self.stadium_end = self._extract_stadium()
        # Re-parse stadium details
        self.stadium_capacity, self.car_park, self.pitch = self._parse_stadium_details(self.stadium)
        return bytes(self.raw_data)

    def set_stadium_name(self, new_stadium: str):
        """Replace stadium text region (in-place if possible)."""
        if new_stadium is None:
            return bytes(self.raw_data)
        if len(new_stadium) > 120:
            new_stadium = new_stadium[:120]
        new_bytes = new_stadium.encode('latin-1', errors='replace')

        # Ensure stadium region exists; recompute if missing
        if not getattr(self, 'stadium_start', None) or not getattr(self, 'stadium_end', None) or self.stadium_end <= self.stadium_start:
            self.stadium, self.stadium_start, self.stadium_end = self._extract_stadium()

        old_len = (self.stadium_end - self.stadium_start) if (self.stadium_end and self.stadium_start) else 0
        if old_len <= 0:
            # Append after name_end if possible
            pos = self.name_end or len(self.raw_data)
            insert_at = pos
            # Insert a single space separator before stadium
            self.raw_data[insert_at:insert_at] = b' ' + new_bytes + b' '
            self.stadium_start = insert_at + 1
            self.stadium_end = self.stadium_start + len(new_bytes)
        else:
            if len(new_bytes) <= old_len:
                pad = b' ' * (old_len - len(new_bytes))
                self.raw_data[self.stadium_start:self.stadium_start + old_len] = new_bytes + pad
                self.stadium_end = self.stadium_start + old_len
            else:
                # Expand in-place by slice assignment
                self.raw_data[self.stadium_start:self.stadium_end] = new_bytes
                self.stadium_end = self.stadium_start + len(new_bytes)

        self.stadium = new_stadium
        # Re-parse stadium details
        self.stadium_capacity, self.car_park, self.pitch = self._parse_stadium_details(self.stadium)
        return bytes(self.raw_data)

    def set_capacity(self, capacity: int):
        """Update stadium capacity metadata if present in stadium text; otherwise append it."""
        try:
            cap = int(capacity) if capacity is not None else None
        except Exception:
            cap = None
        if cap is None:
            return bytes(self.raw_data)

        # If stadium text contains CAPACITY, replace it; otherwise append a " CAPACITY: X" token
        s = self.stadium or ""
        import re as _re
        if _re.search(r'CAPACITY[:\s]*[\d,]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'CAPACITY[:\s]*[\d,]+', f'CAPACITY: {cap:,}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  CAPACITY: {cap:,}"
            else:
                s2 = f"CAPACITY: {cap:,}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def set_car_park(self, spaces: int):
        """Update car park count in stadium text similarly to capacity."""
        try:
            n = int(spaces) if spaces is not None else None
        except Exception:
            n = None
        if n is None:
            return bytes(self.raw_data)

        s = self.stadium or ""
        import re as _re
        if _re.search(r'CAR\s*PARK[:\s]*[\d,]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'CAR\s*PARK[:\s]*[\d,]+', f'CAR PARK: {n:,}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  CAR PARK: {n:,}"
            else:
                s2 = f"CAR PARK: {n:,}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def set_pitch(self, quality: str):
        """Set pitch quality in stadium text (GOOD / MEDIUM / POOR)."""
        q = (quality or "").strip().upper()
        if not q:
            return bytes(self.raw_data)
        s = self.stadium or ""
        import re as _re
        if _re.search(r'PITCH[:\s]*[A-Za-z]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'PITCH[:\s]*[A-Za-z]+', f'PITCH: {q}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  PITCH: {q}"
            else:
                s2 = f"PITCH: {q}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def to_bytes(self) -> bytes:
        """Return decoded payload suitable for saving (no length-prefix)."""
        raw = bytearray(self.raw_data)
        # If we detected team_id position, write it back
        try:
            if getattr(self, 'team_id', None) is not None and getattr(self, 'team_id_offset', None) is not None:
                struct.pack_into("<H", raw, int(self.team_id_offset), int(self.team_id))
            else:
                # best-effort: write at start if there are at least 2 bytes
                if len(raw) >= 2 and getattr(self, 'team_id', None) is not None:
                    struct.pack_into("<H", raw, 0, int(self.team_id))
        except Exception:
            # best-effort only; don't fail serialization because of this
            pass
        return bytes(raw)


class CoachRecord:
    """Basic coach record parser (managers)"""
    def __init__(self, data: bytes, record_offset: int):
        self.raw_data = bytearray(data)
        self.record_offset = record_offset
        self.coach_id = self._extract_coach_id()
        self.given_name = ""
        self.surname = ""
        self.full_name = self._extract_name()

    def _extract_coach_id(self) -> int:
        """Extract coach ID, assume sequential or from header"""
        return 0

    def _extract_name(self) -> str:
        """Extract coach name using 32-bit XOR decode; fallback to regex-based parser if necessary."""
        try:
            inner_pos = 1
            given, c1 = self._decode_string_32bit(self.raw_data, inner_pos)
            if c1 > 0:
                inner_pos += c1
                surname, c2 = self._decode_string_32bit(self.raw_data, inner_pos)
                if c2 > 0:
                    self.given_name = given
                    self.surname = surname
                    return f"{given} {surname}".strip()
        except Exception as e:
            logger.debug("CoachRecord extraction failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
 
        # Fallback: try the lighter regex-based parser to extract names if structured decode fails
        try:
            from pm99_editor.coach_models import parse_coaches_from_record as _parse
            coaches = _parse(bytes(self.raw_data))
            if coaches:
                c = coaches[0]
                try:
                    self.given_name = getattr(c, 'given_name', '')
                    self.surname = getattr(c, 'surname', '')
                    self.full_name = getattr(c, 'full_name', '') or f"{self.given_name} {self.surname}".strip()
                    return self.full_name
                except Exception:
                    # If coach dataclass doesn't match expected fields, fall through
                    pass
        except Exception as e:
            logger.debug("CoachRecord regex fallback failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
 
        return "Unknown Coach"

    def _decode_string_32bit(self, blob: bytes, offset: int) -> tuple[str, int]:
        """Decode inner 32-bit XOR string"""
        if offset + 2 > len(blob):
            return "", 0

        length = struct.unpack_from("<H", blob, offset)[0]
        if length > 500 or offset + 2 + length > len(blob):
            return "", 0

        encoded = blob[offset+2 : offset+2+length]
        decoded = bytearray()

        p = 0
        while p + 4 <= len(encoded):
            dword = struct.unpack_from("<I", encoded, p)[0]
            decoded.extend(struct.pack("<I", dword ^ 0x61616161))
            p += 4
        if p + 2 <= len(encoded):
            word = struct.unpack_from("<H", encoded, p)[0]
            decoded.extend(struct.pack("<H", word ^ 0x6161))
            p += 2
        if p < len(encoded):
            decoded.append(encoded[p] ^ 0x61)

        if b'\x00' in decoded:
            decoded = decoded[:decoded.index(b'\x00')]

        try:
            return bytes(decoded).decode('cp1252', errors='replace'), 2 + length
        except:
            return "", 2 + length

    def encode_string_32bit(self, text: str) -> bytes:
        """Encode a plain text string into the 32-bit-XOR entry format (length prefixed)."""
        raw = text.encode('cp1252')
        out = bytearray()
        p = 0
        while p + 4 <= len(raw):
            dword = struct.unpack_from("<I", raw, p)[0]
            out.extend(struct.pack("<I", dword ^ 0x61616161))
            p += 4
        if p + 2 <= len(raw):
            word = struct.unpack_from("<H", raw, p)[0]
            out.extend(struct.pack("<H", word ^ 0x6161))
            p += 2
        if p < len(raw):
            out.append(raw[p] ^ 0x61)
        return struct.pack("<H", len(out)) + bytes(out)

    def set_name(self, given_name: str, surname: str) -> bytes:
        """
        Replace the encoded given/surname pair stored after the initial header byte.
        This performs an in-place replacement of the old encoded blocks with newly encoded ones.
        The total decoded payload length may change; callers should use the returned bytes
        from to_bytes() for saving.
        """
        inner_pos = 1
        # Determine the existing consumed lengths so we can replace that slice
        _, c1 = self._decode_string_32bit(bytes(self.raw_data), inner_pos)
        _, c2 = self._decode_string_32bit(bytes(self.raw_data), inner_pos + c1)
        old_total = c1 + c2

        new_given = self.encode_string_32bit(given_name)
        new_surname = self.encode_string_32bit(surname)
        new_block = new_given + new_surname

        # Replace slice (may change total payload length)
        self.raw_data[inner_pos:inner_pos + old_total] = new_block

        self.given_name = given_name
        self.surname = surname
        self.full_name = f"{given_name} {surname}".strip()
        return bytes(self.raw_data)

    def to_bytes(self) -> bytes:
        """Return decoded payload suitable for saving (no length-prefix)."""
        return bytes(self.raw_data)
@dataclass
class PlayerRecord:
    """Player record structure from PM99 FDI files.
    
    Corresponds to the structure parsed by MANAGPRE.EXE.FUN_004afd80().
    """
    # Core identity
    record_id: int = 0
    given_name: str = ""
    surname: str = ""
    name: str = ""  # Full display name (compatibility with legacy code)
    
    # File structure fields (bytes 0-2)
    team_id: int = 0
    squad_number: int = 0
    
    # Codes and identifiers
    initial_char: int = ord('a')  # Single byte character
    initials: bytes = b'aaaaaa'  # 6-byte sequence
    nationality: int = 0
    position_primary: int = 0
    position_secondary: int = 0
    unknown_1c: int = 0
    
    # Birth data
    birth_day: int = 1
    birth_month: int = 1
    birth_year: int = 1975
    
    # Physical attributes
    height: int = 175  # cm
    weight: int = 75   # kg
    
    # Core skill attributes (10 skills, duplicated in two offset locations)
    skills: List[int] = field(default_factory=lambda: [50] * 10)
    
    # Extended fields (version >= 700)
    extended: List[int] = field(default_factory=lambda: [0] * 6)
    
    # Metadata
    region_code: int = 0x1e  # 30 = English
    version: int = 700
    
    # Optional/unknown blocks (preserved as raw bytes)
    contract_data: Optional[bytes] = None
    unknown_blocks: List[bytes] = field(default_factory=list)
    
    # Raw record data for serialization (preserves unknown fields)
    raw_data: Optional[bytes] = None
    # Modification flag used by GUI and saving paths
    modified: bool = False
    # Confidence score (0-100) for heuristics; lower = less certain. GUI can surface suppressed candidates.
    confidence: int = 100
    # Mark records that are low-confidence or suppressed by deduplication heuristics so the UI can hide/show them.
    suppressed: bool = False
    # Internal flag signalling that the raw name bytes need rebuilding before serialization.
    name_dirty: bool = field(default=False, init=False, repr=False)
    
    @classmethod
    def from_bytes(cls, data: bytes, offset: int, version: int = 700) -> 'PlayerRecord':
        """
        Parse a player record from XOR-decoded player record data.
        
        Uses the CORRECT parsing approach based on reverse engineering:
        - Team ID at bytes 0-1 (LE uint16)
        - Squad # at byte 2
        - Name at bytes 5+ (variable length, Latin-1)
        - Name-end marker: 0x61 0x61 0x61 0x61
        - Position at name_end + 7 (double-XOR)
        - Nationality at name_end + 8 (double-XOR)
        - DOB at name_end + 9,10,11 (day/month/year, double-XOR)
        - Height at name_end + 13 (double-XOR)
        - Attributes at FIXED offset from end: len-19 to len-7 (double-XOR)
        
        Args:
            data: XOR-decoded player record bytes (NOT the full file)
            offset: Record offset (used for error reporting)
            version: Database version
            
        Returns:
            PlayerRecord with all fields populated
        """
        try:
            # Extract team ID (bytes 0-1, little-endian)
            team_id = struct.unpack_from("<H", data, 0)[0]
            # Normalize embedded/garbled team IDs (legacy heuristic)
            if team_id > 5000:
                team_id = 0

            # Extract squad number (byte 2)
            squad_num = data[2]
            
            # Extract player name from bytes 5-45 (Latin-1 encoding)
            name = cls._extract_name(data)
            
            # Find name-end marker (0x61 0x61 0x61 0x61)
            name_end = cls._find_name_end(data)
            
            # Extract metadata fields using dynamic offsets from name_end
            if name_end is not None:
                # Position at name_end + 7 (with double-XOR)
                position = cls._extract_position(data, name_end)
                
                # Nationality at name_end + 8 (with double-XOR)
                nationality = data[name_end + 8] ^ 0x61 if (name_end + 8) < len(data) else 0
                
                # DOB at name_end + 9, 10, 11 (day/month/year with double-XOR)
                birth_day = data[name_end + 9] ^ 0x61 if (name_end + 9) < len(data) else 1
                birth_month = data[name_end + 10] ^ 0x61 if (name_end + 10) < len(data) else 1
                
                if (name_end + 12) < len(data):
                    y0 = data[name_end + 11] ^ 0x61
                    y1 = data[name_end + 12] ^ 0x61
                    birth_year = struct.unpack_from("<H", bytes([y0, y1]), 0)[0]
                else:
                    birth_year = 1975
                
                # Height at name_end + 13 (with double-XOR)
                height = data[name_end + 13] ^ 0x61 if (name_end + 13) < len(data) else 175
            else:
                # Fallback if no name-end marker found
                position = 0
                nationality = 0
                birth_day = 1
                birth_month = 1
                birth_year = 1975
                height = 175
            
            # Extract attributes from FIXED offset from end (last 12 bytes with double-XOR)
            skills = []
            attr_start = len(data) - 19
            attr_end = len(data) - 7
            if attr_start >= 0 and attr_end <= len(data):
                for i in range(attr_start, attr_end):
                    if i < len(data):
                        attr_val = data[i] ^ 0x61
                        skills.append(attr_val)
            
            # Pad skills to 12 if needed (legacy records include up to 12 attributes)
            while len(skills) < 12:
                skills.append(50)
            
            # Extract given name and surname from full name
            name_parts = name.split(maxsplit=1)
            given_name = name_parts[0] if len(name_parts) > 0 else "Unknown"
            surname = name_parts[1] if len(name_parts) > 1 else ""
            
            # Validate birth year
            if birth_year < 1900 or birth_year > 1999:
                birth_year = 1975
            
            # Validate height
            if height < 150 or height > 250:
                height = 175
            
            # Construct instance from parsed fields. Preserve raw_data but ensure
            # encoded metadata bytes exist in raw_data for discoverability and tests.
            rec = cls(
                record_id=0,  # Set externally
                given_name=given_name,
                surname=surname,
                name=name,
                team_id=team_id,
                squad_number=squad_num,
                initial_char=ord('a'),
                initials=b'aaaaaa',
                nationality=nationality,
                position_primary=position,
                position_secondary=0,
                unknown_1c=0,
                birth_day=birth_day,
                birth_month=birth_month,
                birth_year=birth_year,
                height=height,
                weight=75,  # Not yet located
                skills=skills[:10],
                extended=[0] * 6,
                region_code=0x1e,
                version=version,
                contract_data=None,
                unknown_blocks=[],
                raw_data=data  # Store original record for serialization (may be patched below)
            )

            # If a name-end marker was found, ensure encoded metadata bytes are present
            # in the stored raw_data so tests and downstream consumers can inspect them.
            if name_end is not None:
                try:
                    raw = bytearray(rec.raw_data if rec.raw_data is not None else data)
                    real_name_end = PlayerRecord._find_name_end_in_data(bytes(raw))
                    if real_name_end is None:
                        real_name_end = name_end

                    pos_off = real_name_end + 7
                    nat_off = real_name_end + 8
                    day_off = real_name_end + 9
                    month_off = real_name_end + 10
                    year_off = real_name_end + 11
                    height_off = real_name_end + 13

                    patched = False

                    # Helper to safely write a single byte
                    def _write_byte_if_needed(buf, idx, val):
                        nonlocal patched
                        if 0 <= idx < len(buf) and buf[idx] != val:
                            buf[idx] = val
                            patched = True

                    # Normalize parsed values and choose safe defaults when parsed values are suspicious.
                    pos_val = position if 0 <= position <= 3 else 0
                    nat_val = nationality if 0 <= nationality <= 255 else 0
                    day_val = birth_day if 1 <= birth_day <= 31 else 1
                    month_val = birth_month if 1 <= birth_month <= 12 else 1
                    year_val = birth_year if 1900 <= birth_year <= 1999 else 1975
                    height_val = height if 50 <= height <= 250 else 175

                    # Write encoded (XOR'd) bytes for each metadata field.
                    _write_byte_if_needed(raw, pos_off, (pos_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, nat_off, (nat_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, day_off, (day_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, month_off, (month_val ^ 0x61) & 0xFF)
                    if year_off + 1 < len(raw):
                        yb = struct.pack("<H", year_val)
                        _write_byte_if_needed(raw, year_off, (yb[0] ^ 0x61) & 0xFF)
                        _write_byte_if_needed(raw, year_off + 1, (yb[1] ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, height_off, (height_val ^ 0x61) & 0xFF)

                    if patched:
                        rec.raw_data = bytes(raw)
                except Exception:
                    # If patching fails for any reason, keep original raw_data unchanged
                    pass

            rec.name_dirty = False
            return rec
            
        except Exception as e:
            logger.debug("Parse error at offset 0x%x: %s", offset, e)
            return cls(
                record_id=0,
                given_name="Parse Error",
                surname="",
                name="Parse Error",
                version=version,
                raw_data=data  # Store even on error for safe serialization
            )
    
    @staticmethod
    def _extract_name(data: bytes) -> str:
        """Extract player name from two length-prefixed XOR-encoded strings.
        
        Format: [uint16 len1][XOR-encoded given name][uint16 len2][XOR-encoded surname]
        """
        from pm99_editor.xor import read_string
        import struct
        
        try:
            # Names start at byte 5 (after team_id and squad_number)
            pos = 5
            
            # Read first string (given name)
            if pos + 2 > len(data):
                return "Parse Error"
            
            given_name, consumed1 = read_string(data, pos)
            pos += consumed1
            
            # Read second string (surname)
            if pos + 2 > len(data):
                # Only got given name
                return given_name if given_name else "Unknown Player"
            
            surname, consumed2 = read_string(data, pos)
            
            # Combine names
            full_name = f"{given_name} {surname}".strip()
            
            # Validate we got something reasonable
            if len(full_name) >= 3:
                return full_name
            
            return "Unknown Player"
            
        except Exception as e:
            logger.debug(f"Name extraction error: {e}")
            # Fallback to old parsing method for backwards compatibility
            try:
                import re
                name_region = data[5:45]
                text = name_region.decode('latin-1', errors='ignore')
                
                # Simple pattern matching as fallback
                patterns = [
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{3,20})'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        return f"{match.group(1)} {match.group(2)}".strip()
                
                return "Unknown Player"
            except:
                return "Parse Error"
    
    @staticmethod
    def _find_name_end(data: bytes) -> Optional[int]:
        """Find the 'aaaa' (0x61 0x61 0x61 0x61) name-end marker."""
        for i in range(20, min(60, len(data) - 20)):
            if i + 3 < len(data) and data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                return i
        return None
    
    @staticmethod
    def _extract_position(data: bytes, name_end: int) -> int:
        """Extract position using dynamic offset from name-end marker."""
        # Try offset +7 first, then +8 as fallback
        attr_limit = len(data) - 19
        for delta in (7, 8):
            pos_offset = name_end + delta
            if pos_offset < attr_limit:
                pos_value = data[pos_offset] ^ 0x61  # Double-XOR
                if 0 <= pos_value <= 3:
                    return pos_value
        return 0
    
    def to_bytes(self) -> bytes:
        """
        Serialize player record to an in-file decoded payload (XOR-decoded, no length prefix).

        This method returns the raw decoded record bytes suitable for XOR encoding
        and length-prefixing by pm99_editor.xor.encode_entry() or by the file_writer.
        If the instance was created via from_bytes() and raw_data is present we base the serialization on the
        original structure (preserving unknown fields). Otherwise we construct
        a reasonable canonical record from the dataclass fields.
        """
        # Build XOR-decoded payload first (decoded = in-file decoded record)
        if self.raw_data is not None:
            if getattr(self, 'name_dirty', False):
                self._rebuild_name_region()

            data = bytearray(self.raw_data)

            # Update team ID (bytes 0-1, little-endian)
            struct.pack_into("<H", data, 0, self.team_id)

            # Update squad number (byte 2)
            data[2] = self.squad_number

            # Compute attribute start limit to avoid overwriting attributes
            attr_start = len(data) - 19

            # Find name-end marker to write metadata back
            name_end = self._find_name_end_in_data(data)

            if name_end is not None:
                # Position (name_end + 7, double-XOR)
                pos_offset = name_end + 7
                if pos_offset < attr_start and 0 <= self.position_primary <= 3:
                    data[pos_offset] = self.position_primary ^ 0x61

                # Nationality (name_end + 8, double-XOR)
                nat_offset = name_end + 8
                if nat_offset < attr_start and 0 <= self.nationality <= 255:
                    data[nat_offset] = self.nationality ^ 0x61

                # DOB: day/month/year (name_end + 9,10,11,12 - year is 2 bytes LE, double-XOR)
                day_offset = name_end + 9
                month_offset = name_end + 10
                year_offset = name_end + 11
                if (year_offset + 1) < attr_start:
                    data[day_offset] = self.birth_day ^ 0x61
                    data[month_offset] = self.birth_month ^ 0x61
                    year_bytes = struct.pack("<H", self.birth_year)
                    data[year_offset] = year_bytes[0] ^ 0x61
                    data[year_offset + 1] = year_bytes[1] ^ 0x61

                # Height (name_end + 13, double-XOR)
                height_offset = name_end + 13
                if height_offset < attr_start and 50 <= self.height <= 250:
                    data[height_offset] = self.height ^ 0x61

            # Update attributes (double-XOR) - fixed offset from end
            attr_end = len(data) - 7
            for i, attr_val in enumerate(list(self.skills)[:12]):  # Max 12 attributes
                offset = attr_start + i
                if 0 <= offset < attr_end and 0 <= attr_val <= 100:
                    data[offset] = attr_val ^ 0x61

            decoded = bytes(data)
            self.raw_data = decoded
        else:
            # Construct a canonical decoded record from fields (sized so attributes align).
            from pm99_editor.xor import write_string
            
            header = struct.pack("<H", self.team_id) + bytes([self.squad_number]) + b'\x00\x00'

            # Encode names as two separate length-prefixed XOR strings (matches game format)
            given = (self.given_name or "Unknown").strip()
            surname = (self.surname or "Player").strip()
            
            given_encoded = write_string(given)
            surname_encoded = write_string(surname)

            # Metadata placeholder (position, nationality, DOB, height, etc.)
            # These will be written properly by the caller or remain zero
            metadata = b'\x00' * 14

            # Attributes: take up to 12, pad to 12, XOR encode
            attrs = list(self.skills)[:12]
            while len(attrs) < 12:
                attrs.append(50)
            attr_encoded = bytes([a ^ 0x61 for a in attrs])

            # Build complete record
            core = header + given_encoded + surname_encoded + metadata + attr_encoded
            
            # Add trailing padding to ensure minimum size
            trailing = b'\x00' * 7
            decoded = core + trailing

        # If this instance was created programmatically (no raw_data) we return a fully-encoded
        # FDI entry (length-prefixed + XOR) because some callers/tests construct files by
        # concatenating the per-record entries returned by to_bytes().
        # If raw_data exists (record read from file) return the decoded payload (no length-prefix).
        if self.raw_data is None:
            return encode_entry(decoded)
        return decoded

    def _update_full_name(self):
        """Synchronise the legacy `name` field with given + surname."""
        self.name = f"{self.given_name} {self.surname}".strip()

    def _mark_name_dirty(self):
        """Mark the record so the raw name bytes are rebuilt on next serialization."""
        self.modified = True
        self.name_dirty = True

    def _rebuild_name_region(self):
        """Rebuild the raw_data name region ensuring metadata/attributes remain aligned.
        
        CRITICAL: Names are stored as TWO separate length-prefixed XOR-encoded strings,
        NOT as a single Latin-1 string with markers. This matches the game's parser.
        """
        if self.raw_data is None:
            self.name_dirty = False
            return

        from pm99_editor.xor import write_string
        
        data = bytearray(self.raw_data)
        
        # Find where names currently end (after both encoded strings)
        name_start = 5
        attr_start = len(data) - 19 if len(data) >= 19 else len(data)
        
        # Encode given name and surname as separate length-prefixed XOR strings
        given = (self.given_name or "").strip()
        surname = (self.surname or "").strip()
        
        # Use CP1252 encoding (game's charset) and XOR encoding
        given_encoded = write_string(given)
        surname_encoded = write_string(surname)
        
        # Find where old name data ended to preserve metadata
        # We need to find the end of the second encoded string
        try:
            # Try to decode current structure to find where names end
            import struct
            pos = name_start
            # Skip first string (given name)
            if pos + 2 <= len(data):
                len1 = struct.unpack_from("<H", data, pos)[0]
                pos += 2 + len1
            # Skip second string (surname)
            if pos + 2 <= len(data):
                len2 = struct.unpack_from("<H", data, pos)[0]
                pos += 2 + len2
            old_names_end = pos
        except:
            # Fallback: assume reasonable space for metadata
            old_names_end = attr_start - 20
        
        # Extract metadata and attributes blocks to preserve
        metadata_start = old_names_end
        metadata_block = data[metadata_start:attr_start]
        attributes_block = data[attr_start:]
        
        # Ensure minimum metadata space (for position, nationality, DOB, height, etc.)
        min_metadata_len = 14
        if len(metadata_block) < min_metadata_len:
            metadata_block = metadata_block + b"\x00" * (min_metadata_len - len(metadata_block))
        
        # Ensure attributes block is complete
        if len(attributes_block) < 19:
            attributes_block = attributes_block + b"\x00" * (19 - len(attributes_block))
        
        # Reconstruct record: header + encoded names + metadata + attributes
        header = data[:name_start]
        
        new_data = bytearray()
        new_data += header
        new_data += given_encoded
        new_data += surname_encoded
        new_data += metadata_block
        new_data += attributes_block
        
        self.raw_data = bytes(new_data)
        self.name_dirty = False

    @staticmethod
    def _find_name_end_in_data(data: bytes) -> Optional[int]:
        """Find the 'aaaa' (0x61 0x61 0x61 0x61) name-end marker in data."""
        for i in range(20, min(60, len(data) - 20)):
            if i + 3 < len(data) and data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                return i
        return None

    # Compatibility and mutator helpers used by GUI and scripts
    @property
    def attributes(self) -> List[int]:
        """Return a 12-element attributes list (compat with legacy code)."""
        attrs = list(self.skills)
        # If extended contains additional attribute-like values, include them after skills
        if getattr(self, 'extended', None):
            attrs.extend(list(self.extended))
        # Pad to 12 with default 50
        while len(attrs) < 12:
            attrs.append(50)
        return attrs

    @attributes.setter
    def attributes(self, vals: List[int]):
        """Set attributes from a 12-element list (or shorter)."""
        if not isinstance(vals, (list, tuple)):
            raise ValueError("attributes must be a list or tuple")
        vals = list(vals)
        # Ensure minimum length of 10 for skills storage
        while len(vals) < 10:
            vals.append(50)
        self.skills = vals[:10]
        # Save extras into extended area (if present)
        extras = vals[10:12]
        if extras:
            # Ensure extended exists with at least len(extras)
            if self.extended is None:
                self.extended = [0] * 6
            for i, v in enumerate(extras):
                if i < len(self.extended):
                    self.extended[i] = v
                else:
                    self.extended.append(v)
        self.modified = True

    def set_attribute(self, index: int, value: int):
        """Set a single attribute by index (0..11)."""
        if not (0 <= index <= 11):
            raise ValueError("Attribute index must be 0-11")
        if not (0 <= value <= 100):
            raise ValueError("Attribute value must be 0-100")
        if index < 10:
            # primary skills region
            if len(self.skills) < 10:
                while len(self.skills) < 10:
                    self.skills.append(50)
            self.skills[index] = value
        else:
            # secondary/extended region
            ext_idx = index - 10
            if self.extended is None:
                self.extended = [0] * 6
            if ext_idx >= len(self.extended):
                # expand if necessary
                while len(self.extended) <= ext_idx:
                    self.extended.append(0)
            self.extended[ext_idx] = value
        self.modified = True

    def set_team_id(self, team_id: int):
        """Set team ID (0-65535)."""
        if not (0 <= team_id <= 65535):
            raise ValueError("Team ID must be 0-65535")
        self.team_id = team_id
        self.modified = True

    def set_squad_number(self, number: int):
        """Set squad number (0-255)."""
        if not (0 <= number <= 255):
            raise ValueError("Squad number must be 0-255")
        self.squad_number = number
        self.modified = True

    def get_position_name(self) -> str:
        """Convert position code to human name."""
        positions = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
        return positions.get(getattr(self, 'position_primary', getattr(self, 'position', 0)), f"Unknown ({getattr(self,'position_primary',0)})")

    def set_position(self, pos_code: int):
        """Set player position (0-3)."""
        if not (0 <= pos_code <= 3):
            raise ValueError("Position must be 0-3")
        self.position_primary = pos_code
        self.modified = True
    
    def set_given_name(self, new_name: str):
        """Set player's given name (first name).

        Args:
            new_name: New given name (1-12 characters, validated by game)
            
        Raises:
            ValueError: If name is empty or too long
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Given name cannot be empty")
        if len(new_name) > 12:
            raise ValueError("Given name too long (max 12 characters)")

        self.given_name = new_name
        self._update_full_name()
        self._mark_name_dirty()
    
    def set_surname(self, new_name: str):
        """Set player's surname (last name).
        
        Args:
            new_name: New surname (1-12 characters, validated by game)
            
        Raises:
            ValueError: If name is empty or too long
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Surname cannot be empty")
        if len(new_name) > 12:
            raise ValueError("Surname too long (max 12 characters)")

        self.surname = new_name
        self._update_full_name()
        self._mark_name_dirty()
    
    def set_name(self, full_name: str):
        """Set player's full name (splits into given name and surname).
        
        Args:
            full_name: Full name in format "Given Surname"
            
        Raises:
            ValueError: If name format is invalid
        """
        full_name = full_name.strip()
        if not full_name:
            raise ValueError("Name cannot be empty")
        
        parts = full_name.split(maxsplit=1)
        if len(parts) < 2:
            raise ValueError("Name must contain both given name and surname")
        
        given, surname = parts[0], parts[1]
        self.given_name = given.strip()
        self.surname = surname.strip()
        self._update_full_name()
        self._mark_name_dirty()

    def set_nationality(self, nat_id: int):
        """Set nationality ID (0-255)."""
        if not (0 <= nat_id <= 255):
            raise ValueError("Nationality ID must be 0-255")
        self.nationality = nat_id
        # Provide backwards-compatible attribute name used elsewhere
        try:
            self.nationality_id = nat_id
        except Exception:
            setattr(self, 'nationality_id', nat_id)
        self.modified = True

    @property
    def dob(self):
        """Return DOB as (day, month, year) tuple."""
        return (self.birth_day, self.birth_month, self.birth_year)

    @dob.setter
    def dob(self, t):
        """Set DOB tuple (day, month, year)."""
        if not (isinstance(t, (list, tuple)) and len(t) == 3):
            raise ValueError("DOB must be a (day, month, year) tuple")
        day, month, year = t
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            raise ValueError("Invalid DOB")
        self.birth_day = day
        self.birth_month = month
        self.birth_year = year
        self.modified = True

    def set_dob(self, day: int, month: int, year: int):
        """Convenience setter for DOB."""
        self.dob = (day, month, year)

    def set_height(self, height_cm: int):
        """Set player's height in cm."""
        if not (50 <= height_cm <= 250):
            raise ValueError("Height must be in cm")
        self.height = height_cm
        self.modified = True

    @property
    def position(self):
        """Alias property for legacy code expecting `position`."""
        return self.position_primary

    @position.setter
    def position(self, value):
        self.set_position(value)

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"Player #{self.record_id}: {self.given_name} {self.surname} "
            f"(Born: {self.birth_day:02d}/{self.birth_month:02d}/{self.birth_year}, "
            f"Pos: {self.position_primary}, Nation: {self.nationality})"
        )


@dataclass
class FDIHeader:
    """FDI file header structure.
    
    Based on MANAGPRE.EXE header parsing and out/struct_notes.md.
    """
    signature: bytes = b'DMFIv1.0'
    record_count: int = 0
    version: int = 2
    max_offset: int = 0
    dir_size: int = 0
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'FDIHeader':
        """Parse FDI header from file bytes."""
        if len(data) < 0x20:
            raise ValueError("File too small for FDI header")
        
        signature = data[0:8]
        if signature != b'DMFIv1.0':
            raise ValueError(f"Invalid signature: {signature}")
        
        record_count = struct.unpack_from("<I", data, 0x10)[0]
        version = struct.unpack_from("<I", data, 0x14)[0]
        max_offset = struct.unpack_from("<I", data, 0x18)[0]
        dir_size = struct.unpack_from("<I", data, 0x1C)[0]
        
        return cls(
            signature=signature,
            record_count=record_count,
            version=version,
            max_offset=max_offset,
            dir_size=dir_size
        )
    
    def to_bytes(self) -> bytes:
        """Serialize header to bytes."""
        header = bytearray(0x20)
        header[0:8] = self.signature
        struct.pack_into("<I", header, 0x10, self.record_count)
        struct.pack_into("<I", header, 0x14, self.version)
        struct.pack_into("<I", header, 0x18, self.max_offset)
        struct.pack_into("<I", header, 0x1C, self.dir_size)
        return bytes(header)


@dataclass
class DirectoryEntry:
    """FDI directory entry (offset table entry).
    
    Each entry is 8 bytes: <uint32 offset, uint16 tag, uint16 index>
    """
    offset: int
    tag: int  # Character code like 'G', 'N', 'L'
    index: int
    
    @classmethod
    def from_bytes(cls, data: bytes, pos: int) -> 'DirectoryEntry':
        """Parse a single directory entry."""
        if pos + 8 > len(data):
            raise ValueError(f"Truncated directory entry at 0x{pos:x}")
        
        offset, tag, index = struct.unpack_from("<IHH", data, pos)
        return cls(offset=offset, tag=tag, index=index)
    
    def to_bytes(self) -> bytes:
        """Serialize to 8-byte directory entry."""
        return struct.pack("<IHH", self.offset, self.tag, self.index)