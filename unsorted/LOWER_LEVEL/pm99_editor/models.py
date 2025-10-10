"""Data models for PM99 database records.

Implements Python dataclasses matching the binary structures from MANAGPRE.EXE.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import struct

from .xor import decode_entry, encode_entry, read_string, write_string


@dataclass
class PlayerRecord:
    """Player record structure from PM99 FDI files.
    
    Corresponds to the structure parsed by MANAGPRE.EXE.FUN_004afd80().
    """
    # Core identity
    record_id: int = 0
    given_name: str = ""
    surname: str = ""
    
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
            
            # Pad skills to 10 if needed
            while len(skills) < 10:
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
            
            return cls(
                record_id=0,  # Set externally
                given_name=given_name,
                surname=surname,
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
                raw_data=data  # Store original record for serialization
            )
            
        except Exception as e:
            print(f"Parse error at offset 0x{offset:x}: {e}")
            return cls(
                record_id=0,
                given_name="Parse Error",
                surname="",
                version=version,
                raw_data=data  # Store even on error for safe serialization
            )
    
    @staticmethod
    def _extract_name(data: bytes) -> str:
        """Extract player name from bytes 5-45 using Latin-1 encoding."""
        import re
        try:
            name_region = data[5:45]
            text = name_region.decode('latin-1', errors='ignore')
            
            # Pattern: [abbreviated]<separator>[FULL NAME]
            # Separators: 2 chars like }a, ta, ua, va, wa, xa, ya, za
            separator_pattern = r'[a-z~@\x7f]{1,2}a(?=[A-Z])'
            parts = re.split(separator_pattern, text)
            
            candidates = []
            for part_idx, part in enumerate(parts):
                if len(part) < 8:
                    continue
                
                # Multiple name patterns
                patterns = [
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15}\s+[A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ]{3,15}\s+[A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ]{3,15}\s+[A-ZÀ-ÿ]{3,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{3,20})'
                ]
                
                for pattern_idx, pattern in enumerate(patterns):
                    for match in re.finditer(pattern, part):
                        given = match.group(1).strip()
                        surname = match.group(2).strip()
                        
                        if len(given) < 3:
                            continue
                        
                        # Clean surname
                        clean_surname = ''
                        for word in surname.split():
                            if word.isupper() or (word[0].isupper() and all(c.isupper() or c.islower() or not c.isalpha() for c in word)):
                                valid_part = ''
                                for i, c in enumerate(word):
                                    if i > 0 and c.islower():
                                        rest = word[i:]
                                        if len(rest) >= 3 and all(c.islower() or not c.isalpha() for c in rest):
                                            break
                                    valid_part += c
                                if valid_part and len(valid_part) >= 3:
                                    clean_surname += valid_part + ' '
                        
                        clean_surname = clean_surname.strip()
                        if clean_surname and len(clean_surname) >= 3:
                            full_name = f"{given} {clean_surname}".strip()
                            if 8 <= len(full_name) <= 40 and ' ' in full_name and len(given) >= 3:
                                score = (part_idx * 200) + ((3 - pattern_idx) * 30)
                                score += sum(1 for c in full_name if c.isupper()) * 2
                                score += len(full_name)
                                if len(given) < 4:
                                    score -= 50
                                candidates.append((score, full_name))
            
            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]
            
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
        Serialize player record back to XOR-decoded format.
        
        Uses the GUI's raw_data preservation approach: start with original record
        and only modify specific known offsets. This preserves all unknown fields.
        
        NOTE: This returns the XOR-decoded record data that should be written
        using file_writer.write_fdi_record(), NOT a complete FDI entry.
        
        Structure modifications:
        - Team ID (bytes 0-1, LE uint16)
        - Squad # (byte 2)
        - Position at name_end + 7 (double-XOR)
        - Nationality at name_end + 8 (double-XOR)
        - DOB at name_end + 9,10,11 (double-XOR)
        - Height at name_end + 13 (double-XOR)
        - Attributes at len-19 to len-7 (double-XOR)
        
        Returns:
            XOR-decoded player record bytes (ready for XOR encoding and writing)
        """
        if self.raw_data is None:
            raise ValueError(
                "Cannot serialize PlayerRecord without raw_data. "
                "Record must be created using from_bytes() to preserve original structure."
            )
        
        # Start with mutable copy of original record (preserves unknown fields)
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
        for i, attr_val in enumerate(self.skills[:12]):  # Max 12 attributes
            offset = attr_start + i
            if 0 <= offset < attr_end and 0 <= attr_val <= 100:
                data[offset] = attr_val ^ 0x61
        
        return bytes(data)
    
    @staticmethod
    def _find_name_end_in_data(data: bytes) -> Optional[int]:
        """Find the 'aaaa' (0x61 0x61 0x61 0x61) name-end marker in data."""
        for i in range(20, min(60, len(data) - 20)):
            if i + 3 < len(data) and data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                return i
        return None
    
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