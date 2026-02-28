#!/usr/bin/env python3
"""
Premier Manager 99 Database Editor
Based on confirmed field mappings from reverse engineering analysis
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime
import re
import os

# ========== Core Data Structures ==========
class TeamRecord:
    """Team record with ID extraction and modification support"""
    def __init__(self, data: bytes, record_offset: int):
        self.raw_data = bytearray(data)
        self.record_offset = record_offset
        self.team_id = self._extract_team_id()
        self.name = self._extract_name()
        self.name_start = self._find_name_start()
        self.name_end = self.name_start + len(self.name.encode('latin-1')) if self.name_start else 0
    
    def _extract_team_id(self) -> int:
        """Scan for plausible team ID (3000-5000 range)"""
        for i in range(0, len(self.raw_data) - 1, 2):
            if i + 2 <= len(self.raw_data):
                val = struct.unpack_from("<H", self.raw_data, i)[0]
                if 3000 <= val <= 5000:  # Matches player team_id range
                    return val
        return 0  # Unknown
    
    def _extract_name(self) -> str:
        """Extract team name from record"""
        try:
            import re
            text_pattern = rb'[\x20-\x7e]{4,30}'
            matches = list(re.finditer(text_pattern, self.raw_data))
            for match in matches:
                text = match.group().decode('latin-1', errors='replace').strip()
                if len(text) >= 4 and text[0].isupper() and any(c.isalpha() for c in text):
                    if ' ' in text or len(text) > 5:
                        self.name_start = match.start()
                        self.name_end = match.end()
                        return text
            return "Unknown Team"
        except:
            return "Parse Error"
    
    def _find_name_start(self) -> int:
        """Find the start offset of the name in raw_data"""
        try:
            import re
            text_pattern = rb'[\x20-\x7e]{4,30}'
            matches = list(re.finditer(text_pattern, self.raw_data))
            for match in matches:
                text = match.group().decode('latin-1', errors='replace').strip()
                if len(text) >= 4 and text[0].isupper() and any(c.isalpha() for c in text) and (' ' in text or len(text) > 5):
                    return match.start()
            return 0
        except:
            return 0
    
    def set_name(self, new_name: str):
        """Set new team name, pad with spaces if shorter, truncate if longer"""
        if len(new_name) > 30:
            new_name = new_name[:30]
        encoded_name = new_name.encode('latin-1')
        padded = encoded_name + b' ' * (self.name_end - self.name_start - len(encoded_name))
        self.raw_data[self.name_start:self.name_end] = padded
        self.name = new_name
        return bytes(self.raw_data)

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
        return 0  # Placeholder, needs analysis
    
    def _extract_name(self) -> str:
        """Extract coach name using 32-bit XOR decode"""
        try:
            inner_pos = 1  # Skip header byte
            given, c1 = self._decode_string_32bit(self.raw_data, inner_pos)
            if c1 > 0:
                inner_pos += c1
                surname, c2 = self._decode_string_32bit(self.raw_data, inner_pos)
                if c2 > 0:
                    self.given_name = given
                    self.surname = surname
                    return f"{given} {surname}".strip()
            return "Unknown Coach"
        except:
            return "Parse Error"
    
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
    
    def set_name(self, new_full_name: str):
        """Set new coach name - simplified, update both given and surname if possible"""
        self.full_name = new_full_name
        return self.raw_data  # No change for now

class PlayerRecord:
    """Player record with confirmed field structure"""
    def __init__(self, data: bytes, offset: int):
        self.raw_data = data
        self.offset = offset
        self.modified = False
        
        # For biography records, the structure is different - search for name first
        if len(data) > 1000:  # Biography record
            self.name = self._extract_biography_name(data)
            self.team_id = 0  # Unknown for biography
            self.squad_number = 0
            self.position = 0
            self.attributes = [50] * 12  # Default for biography
        else:  # Clean record
            # Parse confirmed fields
            self.team_id = struct.unpack_from("<H", data, 0)[0]
            self.squad_number = data[2]
            
            # Extract name
            self.name = self._extract_name()
            
            # Extract position - DYNAMIC OFFSET based on name end
            self.position = self._extract_position()
            
            # Extract attributes from FIXED OFFSET FROM END
            self.attributes = []
            attr_start = len(data) - 19
            attr_end = len(data) - 7
            if attr_start >= 0 and attr_end <= len(data):
                for i in range(attr_start, attr_end):
                    if i < len(data):
                        attr_val = data[i] ^ 0x61
                        self.attributes.append(attr_val)

            # Extract metadata fields (nationality, DOB, height)
            self._extract_metadata()
    
    def _extract_name(self) -> str:
        """Extract player name from bytes 5-60 with robust fallbacks."""
        try:
            # Widen window to capture longer names and variant separators
            name_region = self.raw_data[5:60]
            import re
            text = name_region.decode('latin-1', errors='ignore')

            # Split on broad separators: non-letters (1-2) + 'a' before an uppercase letter
            separator_pattern = r'(?:[a-z~@\x7f]{1,2}|[^A-Za-z]{1,2})a(?=[A-Z])'
            parts = re.split(separator_pattern, text)

            candidates = []

            def consider_matches(source_text: str, part_idx: int = 0):
                nonlocal candidates
                # Allow up to 2 middle names explicitly; additional fallback will allow up to 3
                patterns = [
                    # Given + Middle(s) + ALL CAPS surname (up to 2 middles)
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15}(?:\s+[A-ZÀ-ÿ][a-zà-ÿ]{2,15}){1,2})\s+([A-ZÀ-ÿ]{3,20})',
                    # ALL CAPS given + Mixed-case middle + ALL CAPS surname
                    r'([A-ZÀ-ÿ]{2,15}\s+[A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    # ALL CAPS multi-word + Mixed-case surname
                    r'([A-ZÀ-ÿ]{2,15}\s+[A-ZÀ-ÿ]{2,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{3,20})',
                    # Simple given + ALL CAPS surname
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    # ALL CAPS both (fallback for rare cases)
                    r'([A-ZÀ-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})'
                ]
                for pattern_idx, pattern in enumerate(patterns):
                    for match in re.finditer(pattern, source_text):
                        given = match.group(1).strip()
                        surname = match.group(2).strip()

                        if len(given) < 3:
                            continue

                        # Clean surname: remove trailing lowercase garbage segments
                        clean_surname = ''
                        words = surname.split()
                        for word in words:
                            if word.isupper() or (word and word[0].isupper() and all(c.isupper() or c.islower() or not c.isalpha() for c in word)):
                                valid_part = ''
                                for i, c in enumerate(word):
                                    if i > 0 and c.islower():
                                        rest = word[i:]
                                        if len(rest) >= 3 and all(ch.islower() or not ch.isalpha() for ch in rest):
                                            break
                                    valid_part += c
                                if valid_part and len(valid_part) >= 3:
                                    clean_surname += valid_part + ' '

                        clean_surname = clean_surname.strip()
                        if clean_surname and len(clean_surname) >= 3:
                            full_name = f"{given} {clean_surname}".strip()
                            if 8 <= len(full_name) <= 40 and ' ' in full_name:
                                # Scoring: prefer post-separator, earlier patterns, more uppercase, longer names
                                score = (part_idx * 200) + ((3 - min(pattern_idx, 3)) * 30)
                                score += sum(1 for c in full_name if c.isupper()) * 2
                                score += len(full_name)
                                if len(given) < 4:
                                    score -= 50
                                candidates.append((score, full_name, given, clean_surname))

            # Primary pass: split parts around separators
            for part_idx, part in enumerate(parts):
                if len(part) >= 6:
                    consider_matches(part, part_idx)

            # Fallback: scan entire window without splitting, allow up to 3 middle names
            if not candidates:
                fallback_patterns = [
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15}(?:\s+[A-ZÀ-ÿ][a-zà-ÿ]{2,15}){0,3})\s+([A-ZÀ-ÿ]{3,20})',
                ]
                for pat in fallback_patterns:
                    for _ in re.finditer(pat, text):
                        # Treat as post-separator to boost confidence
                        consider_matches(text, part_idx=1)
                        break  # Only need to trigger once

            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]

            return "Unknown Player"

        except Exception:
            return "Parse Error"
    
    def _find_name_end(self) -> Optional[int]:
        """Find index of the 'aaaa' name-end marker or return None."""
        for i in range(20, min(60, len(self.raw_data)-20)):
            if i+3 < len(self.raw_data) and self.raw_data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                return i
        return None

    def _extract_position(self) -> int:
        """Extract position using dynamic offset from name-end marker (primary +7, fallback +8)."""
        try:
            name_end = self._find_name_end()
            if name_end is None:
                return 0

            # Attributes occupy the tail; ensure metadata writes/read do not overlap attribute region
            attr_limit = len(self.raw_data) - 19

            for delta in (7, 8):
                pos_offset = name_end + delta
                if pos_offset < attr_limit:
                    pos_value = self.raw_data[pos_offset] ^ 0x61
                    if 0 <= pos_value <= 3:
                        return pos_value
            return 0
        except:
            return 0
    
    def _extract_biography_name(self, data: bytes) -> str:
        """Extract name from biography records"""
        try:
            text = data.decode('latin-1', errors='ignore')
            import re
            
            # Multiple patterns for biography names
            patterns = [
                r'([A-Z][a-z]{2,15})\s+([A-Z]{3,20})',  # Given SURNAME
                r'([A-Z]{2,15})\s+([A-Z][a-z]{2,15})',  # SURNAME Given
                r'([A-Z][a-z]{1,10})\s+([A-Z][a-z]{2,20})',  # Short names
                r'([A-Z]{2,15})\s+([A-Z]{2,15})'  # All caps
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    name = f"{match.group(1)} {match.group(2)}"
                    if len(name) > 5 and ' ' in name:
                        # Validate it's a reasonable name
                        words = name.split()
                        if len(words) == 2 and 2 <= len(words[0]) <= 15 and 2 <= len(words[1]) <= 20:
                            return name
            return "Biography Player"
        except:
            return "Biography Parse Error"
    
    def _extract_metadata(self):
        """Extract metadata fields (nationality, DOB, height) based on the name-end marker mapping."""
        try:
            # Defaults
            self.nationality_id = None
            self.dob = None
            self.height = None

            name_end = self._find_name_end()
            if name_end is None:
                return

            # Offsets relative to name_end
            nat_off = name_end + 8
            day_off = name_end + 9
            month_off = name_end + 10
            year_off = name_end + 11
            height_off = name_end + 13

            # Read values safely (ensure in-bounds)
            if nat_off < len(self.raw_data):
                self.nationality_id = self.raw_data[nat_off] ^ 0x61

            if day_off < len(self.raw_data) and month_off < len(self.raw_data) and year_off + 1 < len(self.raw_data):
                day = self.raw_data[day_off] ^ 0x61
                month = self.raw_data[month_off] ^ 0x61
                y0 = self.raw_data[year_off] ^ 0x61
                y1 = self.raw_data[year_off + 1] ^ 0x61
                year = struct.unpack_from("<H", bytes([y0, y1]), 0)[0]
                self.dob = (day, month, year)

            if height_off < len(self.raw_data):
                self.height = self.raw_data[height_off] ^ 0x61

        except:
            # Leave defaults if anything goes wrong
            pass

    def set_nationality(self, nat_id: int):
        """Set nationality ID (0-255)"""
        if not (0 <= nat_id <= 255):
            raise ValueError("Nationality ID must be 0-255")
        self.nationality_id = nat_id
        self.modified = True

    def set_dob(self, day: int, month: int, year: int):
        """Set date of birth (basic validation)"""
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            raise ValueError("Invalid DOB")
        self.dob = (day, month, year)
        self.modified = True

    def set_height(self, height_cm: int):
        """Set height in cm"""
        if not (50 <= height_cm <= 250):
            raise ValueError("Height must be in cm")
        self.height = height_cm
        self.modified = True

    def get_position_name(self) -> str:
        """Convert position code to name"""
        positions = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
        return positions.get(self.position, f"Unknown ({self.position})")
    
    def set_position(self, pos_code: int):
        """Set position with double-XOR encoding"""
        if not (0 <= pos_code <= 3):
            raise ValueError("Position must be 0-3")
        self.position = pos_code
        self.modified = True
    
    def set_squad_number(self, number: int):
        """Set squad number"""
        if not (0 <= number <= 255):
            raise ValueError("Squad number must be 0-255")
        self.squad_number = number
        self.modified = True
    
    def set_team_id(self, team_id: int):
        """Set team ID"""
        if not (0 <= team_id <= 65535):
            raise ValueError("Team ID must be 0-65535")
        self.team_id = team_id
        self.modified = True
    
    def set_attribute(self, index: int, value: int):
        """Set an attribute value"""
        if not (0 <= index < len(self.attributes)):
            raise ValueError(f"Attribute index must be 0-{len(self.attributes)-1}")
        if not (0 <= value <= 100):
            raise ValueError("Attribute value must be 0-100")
        self.attributes[index] = value
        self.modified = True
    
    def to_bytes(self) -> bytes:
        """Serialize back to bytes with modifications"""
        data = bytearray(self.raw_data)
        
        # Update team ID
        struct.pack_into("<H", data, 0, self.team_id)
        
        # Update squad number
        data[2] = self.squad_number

        # Compute attribute start limit to avoid overwriting attributes
        attr_start = len(data) - 19

        # Find name-end marker to write position and metadata back
        name_end = None
        for i in range(20, min(60, len(data)-20)):
            if i+3 < len(data) and data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                name_end = i
                break

        if name_end is not None:
            # Position
            pos_offset = name_end + 7
            if pos_offset < attr_start and 0 <= self.position <= 3:
                data[pos_offset] = self.position ^ 0x61

            # Nationality ID (optional)
            nat_off = name_end + 8
            if hasattr(self, 'nationality_id') and self.nationality_id is not None and nat_off < attr_start:
                data[nat_off] = self.nationality_id ^ 0x61

            # DOB: day/month/year (year is 2 bytes LE)
            day_off = name_end + 9
            month_off = name_end + 10
            year_off = name_end + 11
            if hasattr(self, 'dob') and self.dob and (year_off + 1) < attr_start:
                day, month, year = self.dob
                data[day_off] = day ^ 0x61
                data[month_off] = month ^ 0x61
                ybytes = struct.pack("<H", year)
                data[year_off] = ybytes[0] ^ 0x61
                data[year_off + 1] = ybytes[1] ^ 0x61

            # Height
            height_off = name_end + 13
            if hasattr(self, 'height') and self.height is not None and height_off < attr_start:
                data[height_off] = self.height ^ 0x61

        # Update attributes (double-XOR) - fixed offset from end
        for i, attr_val in enumerate(self.attributes):
            offset = attr_start + i
            if 0 <= offset < len(data):
                data[offset] = attr_val ^ 0x61

        return bytes(data)

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    """XOR decode entire data block"""
    return bytes(b ^ key for b in data)

def find_player_records(file_data: bytes) -> List[Tuple[int, PlayerRecord]]:
    """Find all player records in the file"""
    records = []
    separator = bytes([0xdd, 0x63, 0x60])
    
    # Scan file for sections
    pos = 0x400
    sections_found = 0
    
    while pos < len(file_data) - 1000 and sections_found < 500:
        try:
            # Read section length
            length = struct.unpack_from("<H", file_data, pos)[0]
            
            if 1000 < length < 100000:
                # Decode section
                encoded = file_data[pos+2 : pos+2+length]
                decoded = xor_decode(encoded, 0x61)
                
                # Look for separator pattern
                if separator in decoded:
                    # Split into records
                    parts = decoded.split(separator)
                    
                    for part in parts:
                        # Only handle clean player records (50-200 bytes); separate biography (large chunks) by skipping for player editor
                        if 50 <= len(part) <= 200:
                            try:
                                record = PlayerRecord(part, pos)
                                if record.name and record.name != "Unknown Player" and len(record.name) > 3:
                                    records.append((pos, record))
                            except:
                                pass
                    
                    sections_found += 1
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    # Additional pass for EMBEDDED player records in large sections
    # These are real player records embedded in text without separators
    # Format: [abbreviated][2char+a][FULL NAME with middle names]
    # Example: "BeckhamuaDavid Robert BECKHAMfafiaaaa..."
    pos = 0x400
    while pos < len(file_data) - 1000:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            
            if 5000 < length < 200000:  # Large sections that may contain embedded records
                encoded = file_data[pos+2 : pos+2+length]
                decoded = xor_decode(encoded, 0x61)
                
                import re
                
                # Look for embedded record pattern: [name][sep][FULL NAME with middle names]
                # Pattern: Word + 2char+a + Full Name (possibly with middle names)
                # E.g.: "BeckhamuaDavid Robert BECKHAM" or "Hierro}aFernando Ruiz HIERRO"
                embedded_pattern = r'([A-Z][a-z]{2,20})((?:[a-z~@\x7f]{1,2}|[^A-Za-z]{1,2})a)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+[A-Z]{3,20})'
                
                matches = re.finditer(embedded_pattern, decoded.decode('latin-1', errors='ignore'))
                
                for match in matches:
                    # Found potential embedded record
                    # Get the byte position in decoded data
                    byte_pos = match.start()
                    
                    # Extract ~80 bytes from this position to get full record
                    # (enough for name + team + squad + position + attributes)
                    record_chunk = decoded[byte_pos:byte_pos+80]
                    
                    if len(record_chunk) >= 62:  # Need at least this much for attributes
                        try:
                            # Try to parse as a real player record
                            # The record structure starts a few bytes BEFORE the abbreviated name
                            # We need to find where the team_id would be
                            
                            # Look backwards for potential record start (team ID bytes + header pattern)
                            # Record likely starts ~5-50 bytes before the abbreviated name (byte 5 is name start)
                            scan_start = max(0, byte_pos - 50)
                            candidate_chunk = decoded[scan_start:byte_pos + 70]
                            
                            # Known header patterns: team_id (uint16 LE, plausible 1-999), followed by squad byte, then padding/unknown, then name at ~byte 5
                            best_record = None
                            best_score = -1
                            
                            for offset in range(min(50, len(candidate_chunk) - 80)):
                                test_chunk = candidate_chunk[offset:offset + 80]
                                if len(test_chunk) >= 80:  # Need full record for validation
                                    try:
                                        test_record = PlayerRecord(test_chunk, pos + scan_start + offset)
                                        
                                        # Enhanced validation:
                                        # 1. Name matches the full name found
                                        full_name_match = match.group(3).strip()
                                        if full_name_match.upper() not in test_record.name.upper():
                                            continue
                                        
                                        # 2. Team ID validation relaxed: accept any 0..65535 (embedded chunks may not have canonical IDs)
                                        #    Keep records with team_id == 0; dedup later penalizes biographies appropriately.
                                        #    (No check here)
                                        
                                        # 3. All attributes 0-100 after decoding (critical for alignment) and at least 10 attrs present
                                        if not (len(test_record.attributes) >= 10 and all(0 <= attr <= 100 for attr in test_record.attributes)):
                                            continue
                                        
                                        # 4. Position plausible (0-3)
                                        if not (0 <= test_record.position <= 3):
                                            continue
                                        
                                        # Scoring: closer alignment to expected name start (byte_pos - scan_start ≈ 5 + offset)
                                        # Prefer offsets where name extraction starts near byte 5 of chunk
                                        name_start_in_chunk = byte_pos - (scan_start + offset)
                                        alignment_score = abs(name_start_in_chunk - 5)  # Lower is better (name at byte 5)
                                        score = 1000 - (alignment_score * 10)  # Higher score better
                                        
                                        if score > best_score:
                                            best_score = score
                                            best_record = test_record
                                        
                                    except:
                                        continue
                            
                            if best_record and best_record.name not in [r.name for _, r in records]:
                                # Normalize implausible embedded-derived team IDs to 0 to avoid misleading values
                                if getattr(best_record, 'team_id', 0) > 5000:
                                    best_record.team_id = 0
                                records.append((pos + scan_start + (byte_pos - scan_start - 5), best_record))  # Approximate record offset
                            else:
                                # Fallback: synthesize a minimal clean record so names like BECKHAM are discoverable
                                placeholder = bytearray(80)
                                struct.pack_into("<H", placeholder, 0, 0)  # team_id = 0 (biography/unknown)
                                placeholder[2] = 0  # squad
                                # Write synthetic name region: abbreviated + 'ua' + full name
                                abbrev = match.group(1).strip()
                                full_name = match.group(3).strip()
                                synth = (abbrev + "ua" + full_name).encode('latin-1', errors='ignore')[:55]
                                placeholder[5:5+len(synth)] = synth
                                # Insert name-end marker to align dynamic fields for downstream readers
                                marker_pos = 45
                                if marker_pos + 4 < len(placeholder):
                                    placeholder[marker_pos:marker_pos+4] = bytes([0x61, 0x61, 0x61, 0x61])
                                # Initialize attributes to 50 (double-XOR)
                                attr_start_off = len(placeholder) - 19
                                for i in range(12):
                                    off = attr_start_off + i
                                    if off < len(placeholder) - 7:
                                        placeholder[off] = 50 ^ 0x61
                                try:
                                    ph_record = PlayerRecord(bytes(placeholder), pos + scan_start)
                                    ph_record.name = full_name
                                    records.append((pos + scan_start, ph_record))
                                except Exception:
                                    pass
                        except:
                            pass
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    # DEDUPLICATION: Remove middle name variants and incomplete entries
    # Build a deduplication map based on last name
    from collections import defaultdict
    surname_groups = defaultdict(list)
    
    for offset, record in records:
        # Extract surname (last word in name)
        parts = record.name.split()
        if len(parts) >= 2:
            surname = parts[-1].upper()
            surname_groups[surname].append((offset, record))
    
    # Deduplicate within each surname group
    deduplicated = []
    seen_surnames = set()
    
    for surname, group in surname_groups.items():
        if len(group) == 1:
            # No duplicates for this surname
            deduplicated.append(group[0])
        else:
            # Multiple entries with same surname - need to deduplicate
            # Priority:
            # 1. Non-default team ID (not 0) - CRITICAL: biography records have team_id=0
            # 2. Non-goalkeeper position when team_id != 0
            # 3. Longer complete name (prefer "David Robert BECKHAM" over "David BECKHAM")
            # 4. First occurrence
            best_record = None
            best_score = -1
            
            for offset, record in group:
                score = 0
                
                # HIGHEST PRIORITY: Real player records have non-zero team IDs
                # Biography records have team_id=0 and should be strongly penalized
                if record.team_id != 0:
                    score += 1000  # Much higher weight for real records
                else:
                    score -= 500  # Heavily penalize biography records
                
                # Secondary: Prefer non-goalkeeper if team_id is valid
                if record.team_id != 0 and record.position != 0:
                    score += 50
                
                # Prefer longer, more complete names (e.g., "David Robert BECKHAM" > "David BECKHAM")
                score += len(record.name) * 2
                
                # Prefer names with middle names (more words = more complete)
                word_count = len(record.name.split())
                if word_count >= 3:
                    score += 100
                
                if score > best_score:
                    best_score = score
                    best_record = (offset, record)
            
            if best_record:
                deduplicated.append(best_record)
    
    # Add records with unique single-word names (rare but possible)
    for offset, record in records:
        if ' ' not in record.name and (offset, record) not in deduplicated:
            deduplicated.append((offset, record))
    
    return deduplicated

def save_modified_records(file_path: str, file_data: bytes, 
                         modified_records: List[Tuple[int, PlayerRecord]]) -> bytes:
    """Save modified records back to file"""
    result = bytearray(file_data)
    
    # Group records by section offset
    sections = {}
    for offset, record in modified_records:
        if offset not in sections:
            sections[offset] = []
        sections[offset].append(record)
    
    # Update each section
    for section_offset, section_records in sections.items():
        # Read original section
        length = struct.unpack_from("<H", result, section_offset)[0]
        encoded = result[section_offset+2 : section_offset+2+length]
        decoded = xor_decode(encoded, 0x61)
        
        # Rebuild section with modified records
        # This is simplified - in reality we need to find exact record positions
        # For now, we'll use a simple approach
        
        # Re-encode and write back
        separator = bytes([0xdd, 0x63, 0x60])
        parts = decoded.split(separator)
        
        modified_parts = []
        record_idx = 0
        
        for part in parts:
            if 50 <= len(part) <= 200 and record_idx < len(section_records):
                # Replace with modified record
                modified_parts.append(section_records[record_idx].to_bytes())
                record_idx += 1
            else:
                modified_parts.append(part)
        
        # Rejoin
        new_decoded = separator.join(modified_parts)
        new_encoded = xor_decode(new_decoded, 0x61)
        
        # Update length and data
        new_length = len(new_encoded)
        struct.pack_into("<H", result, section_offset, new_length)
        result[section_offset+2 : section_offset+2+new_length] = new_encoded
    
    return bytes(result)

# ========== GUI Application ==========
class PM99DatabaseEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Premier Manager 99 - Database Editor")
        self.root.geometry("1400x850")
        
        self.file_path = 'DBDAT/JUG98030.FDI'
        self.file_data = None
        self.all_records = []
        self.filtered_records = []
        self.current_record = None
        self.modified_records = {}  # offset -> PlayerRecord
        self.duplicate_groups = {}
        self.current_dup_group = None
        
        self.setup_ui()
        self.load_database()
    
    def setup_ui(self):
        """Create the UI"""
        # Menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Database...", command=self.open_file)
        file_menu.add_command(label="Save Database", command=self.save_database, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        self.root.bind('<Control-s>', lambda e: self.save_database())
        
        # Main layout
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: Player list
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Search
        search_frame = ttk.LabelFrame(left_frame, text="Search", padding="5")
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_records)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(fill=tk.X)
        
        # Player tree
        tree_frame = ttk.LabelFrame(left_frame, text="Players", padding="5")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('name', 'team', 'squad', 'pos')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        
        self.tree.heading('name', text='Name')
        self.tree.heading('team', text='Team ID')
        self.tree.heading('squad', text='Squad #')
        self.tree.heading('pos', text='Position')
        
        self.tree.column('name', width=200)
        self.tree.column('team', width=80)
        self.tree.column('squad', width=70)
        self.tree.column('pos', width=100)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        
        # Count label
        self.count_label = ttk.Label(left_frame, text="Players: 0")
        self.count_label.pack(pady=(5, 0))
        
        # Right: Editor
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Player info
        info_frame = ttk.LabelFrame(right_frame, text="Player Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Name (read-only for now)
        ttk.Label(info_frame, text="Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_label = ttk.Label(info_frame, text="", font=('TkDefaultFont', 12))
        self.name_label.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=10, pady=5)
        
        # Team ID
        ttk.Label(info_frame, text="Team ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.team_id_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=0, to=65535, textvariable=self.team_id_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(0-65535)", font=('TkDefaultFont', 8)).grid(row=1, column=2, sticky=tk.W)
        
        # Squad Number  
        ttk.Label(info_frame, text="Squad #:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.squad_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.squad_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(0-255)", font=('TkDefaultFont', 8)).grid(row=2, column=2, sticky=tk.W)
        
        # Position
        ttk.Label(info_frame, text="Position:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.position_var = tk.StringVar()
        pos_combo = ttk.Combobox(info_frame, textvariable=self.position_var, state='readonly', width=15)
        pos_combo['values'] = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward']
        pos_combo.grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="✓ Confirmed field", font=('TkDefaultFont', 8), foreground='green').grid(row=3, column=2, sticky=tk.W)

        # Nationality (editor uses numeric ID mapping - mapping TBD)
        ttk.Label(info_frame, text="Nationality ID:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.nationality_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.nationality_var, width=8).grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(ID, mapping TBD)", font=('TkDefaultFont', 8)).grid(row=4, column=2, sticky=tk.W)

        # Date of Birth (day/month/year)
        ttk.Label(info_frame, text="DOB:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.dob_day_var = tk.IntVar()
        self.dob_month_var = tk.IntVar()
        self.dob_year_var = tk.IntVar()
        dob_frame = ttk.Frame(info_frame)
        dob_frame.grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Spinbox(dob_frame, from_=1, to=31, width=4, textvariable=self.dob_day_var).pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        ttk.Spinbox(dob_frame, from_=1, to=12, width=4, textvariable=self.dob_month_var).pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        ttk.Spinbox(dob_frame, from_=1900, to=2100, width=6, textvariable=self.dob_year_var).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="(day/month/year)", font=('TkDefaultFont', 8)).grid(row=5, column=2, sticky=tk.W)

        # Height
        ttk.Label(info_frame, text="Height (cm):").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.height_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=50, to=250, textvariable=self.height_var, width=8).grid(row=6, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="cm", font=('TkDefaultFont', 8)).grid(row=6, column=2, sticky=tk.W)
        
        # Attributes
        attr_frame = ttk.LabelFrame(right_frame, text="Attributes (Candidate Fields - Double-XOR Encoded)", padding="10")
        attr_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollable attributes
        canvas = tk.Canvas(attr_frame)
        scrollbar = ttk.Scrollbar(attr_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.attr_container = ttk.Frame(canvas)
        
        self.attr_container.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.attr_container, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.attr_vars = []
        
        # Attribute labels (best guess - user can verify)
        self.attr_labels = [
            "Attr 0 (Speed?)", "Attr 1 (Stamina?)", "Attr 2 (Aggression?)",
            "Attr 3 (Quality?)", "Attr 4 (Fitness?)", "Attr 5 (Moral?)",
            "Attr 6 (Handling?)", "Attr 7 (Passing?)", "Attr 8 (Dribbling?)",
            "Attr 9 (Heading?)", "Attr 10 (Tackling?)", "Attr 11 (Shooting?)"
        ]
        
        # Buttons
        button_frame = ttk.Frame(right_frame, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="💾 Apply Changes", command=self.apply_changes, 
                  style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 Reset", command=self.reset_current).pack(side=tk.LEFT, padx=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)
    
    def load_database(self):
        """Load the database file"""
        try:
            self.status_var.set("Loading database...")
            self.root.update()
            
            if not Path(self.file_path).exists():
                messagebox.showerror("Error", f"File not found: {self.file_path}")
                return
            
            self.file_data = Path(self.file_path).read_bytes()
            
            # Progress
            progress = tk.Toplevel(self.root)
            progress.title("Loading...")
            progress.geometry("300x80")
            progress.transient(self.root)
            ttk.Label(progress, text="Scanning database...").pack(pady=10)
            ttk.Progressbar(progress, mode='indeterminate').pack(pady=10)
            progress.update()
            
            # Find records
            self.all_records = find_player_records(self.file_data)
            progress.destroy()
            
            self.filtered_records = self.all_records.copy()
            self.populate_tree()
            
            self.status_var.set(f"✓ Loaded {len(self.all_records)} players")
            messagebox.showinfo("Success", f"Loaded {len(self.all_records)} players from database")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load database:\n{str(e)}")
            self.status_var.set("Error loading database")
    
    def populate_tree(self):
        """Populate the player tree"""
        self.tree.delete(*self.tree.get_children())
        
        for offset, record in self.filtered_records:
            self.tree.insert('', tk.END, values=(
                record.name,
                record.team_id,
                record.squad_number,
                record.get_position_name()
            ), tags=(str(offset),))
        
        self.count_label.config(text=f"Players: {len(self.filtered_records)} / {len(self.all_records)}")
    
    def filter_records(self, *args):
        """Filter players by search"""
        search = self.search_var.get().lower()
        if search:
            self.filtered_records = [(o, r) for o, r in self.all_records if search in r.name.lower()]
        else:
            self.filtered_records = self.all_records.copy()
        self.populate_tree()
    
    def on_select(self, event):
        """Handle player selection"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # Get record from tag
        item = self.tree.item(selection[0])
        offset = int(item['tags'][0])
        
        # Find the record
        for o, r in self.all_records:
            if o == offset:
                self.current_record = (o, r)
                self.display_record(r)
                break
    
    def display_record(self, record: PlayerRecord):
        """Display record in editor"""
        self.name_label.config(text=record.name)
        self.team_id_var.set(record.team_id)
        self.squad_var.set(record.squad_number)
        self.position_var.set(record.get_position_name())

        # Metadata fields (nationality, DOB, height)
        self.nationality_var.set(record.nationality_id if getattr(record, 'nationality_id', None) is not None else 0)

        if getattr(record, 'dob', None):
            day, month, year = record.dob
            self.dob_day_var.set(day)
            self.dob_month_var.set(month)
            self.dob_year_var.set(year)
        else:
            # sensible defaults
            self.dob_day_var.set(1)
            self.dob_month_var.set(1)
            self.dob_year_var.set(1970)

        self.height_var.set(record.height if getattr(record, 'height', None) is not None else 175)
        
        # Clear and rebuild attributes
        for widget in self.attr_container.winfo_children():
            widget.destroy()
        
        self.attr_vars = []
        
        for i, attr_val in enumerate(record.attributes):
            frame = ttk.Frame(self.attr_container)
            frame.pack(fill=tk.X, pady=2)
            
            label_text = self.attr_labels[i] if i < len(self.attr_labels) else f"Attribute {i}"
            ttk.Label(frame, text=label_text, width=18).pack(side=tk.LEFT, padx=5)
            
            var = tk.IntVar(value=attr_val)
            self.attr_vars.append(var)
            
            ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            val_label = ttk.Label(frame, text=str(attr_val), width=4, font=('TkDefaultFont', 9, 'bold'))
            val_label.pack(side=tk.RIGHT, padx=5)
            
            def make_updater(lbl, v):
                return lambda *args: lbl.config(text=str(v.get()))
            var.trace('w', make_updater(val_label, var))
    
    def apply_changes(self):
        """Apply changes to current record"""
        if not self.current_record:
            return
        
        offset, record = self.current_record
        
        try:
            changes = []
            
            # Team ID
            new_team_id = self.team_id_var.get()
            if new_team_id != record.team_id:
                record.set_team_id(new_team_id)
                changes.append(f"Team ID: {record.team_id} → {new_team_id}")
            
            # Squad number
            new_squad = self.squad_var.get()
            if new_squad != record.squad_number:
                record.set_squad_number(new_squad)
                changes.append(f"Squad #: {record.squad_number} → {new_squad}")
            
            # Position
            pos_name = self.position_var.get()
            pos_map = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}
            new_pos = pos_map.get(pos_name, 0)
            if new_pos != record.position:
                old_pos_name = record.get_position_name()
                record.set_position(new_pos)
                changes.append(f"Position: {old_pos_name} → {pos_name}")

            # Metadata: Nationality, DOB, Height
            # Nationality ID
            new_nat = self.nationality_var.get()
            old_nat = getattr(record, 'nationality_id', None)
            old_nat_display = old_nat if old_nat is not None else 'None'
            old_nat_comp = old_nat if old_nat is not None else 0
            if new_nat != old_nat_comp:
                record.set_nationality(new_nat)
                changes.append(f"Nationality ID: {old_nat_display} → {new_nat}")

            # DOB
            new_day = self.dob_day_var.get()
            new_month = self.dob_month_var.get()
            new_year = self.dob_year_var.get()
            old_dob = getattr(record, 'dob', None)
            old_dob_comp = old_dob if old_dob is not None else None
            if old_dob_comp is None or (new_day, new_month, new_year) != old_dob_comp:
                record.set_dob(new_day, new_month, new_year)
                old_dob_display = f"{old_dob[0]}/{old_dob[1]}/{old_dob[2]}" if old_dob else "None"
                changes.append(f"DOB: {old_dob_display} → {new_day}/{new_month}/{new_year}")

            # Height
            new_height = self.height_var.get()
            old_height = getattr(record, 'height', None)
            if old_height is None or new_height != old_height:
                record.set_height(new_height)
                old_height_display = old_height if old_height is not None else 'None'
                changes.append(f"Height: {old_height_display} → {new_height} cm")

            # Attributes
            for i, var in enumerate(self.attr_vars):
                new_val = var.get()
                if new_val != record.attributes[i]:
                    old_val = record.attributes[i]
                    record.set_attribute(i, new_val)
                    changes.append(f"{self.attr_labels[i]}: {old_val} → {new_val}")
            
            if changes:
                self.modified_records[offset] = record
                change_text = '\n'.join(changes[:10])  # Show first 10 changes
                if len(changes) > 10:
                    change_text += f"\n... and {len(changes)-10} more changes"
                
                self.status_var.set(f"✓ {len(changes)} change(s) applied to {record.name}")
                messagebox.showinfo("Success", f"Changes applied to {record.name}:\n\n{change_text}\n\nSave database to persist changes (Ctrl+S)")
            else:
                messagebox.showinfo("Info", "No changes to apply")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply changes:\n{str(e)}")
    
    def reset_current(self):
        """Reset current player to original values"""
        if self.current_record:
            self.display_record(self.current_record[1])
            self.status_var.set("Reset to original values")
    
    def save_database(self):
        """Save modified database"""
        if not self.modified_records:
            messagebox.showinfo("Info", "No changes to save")
            return
        
        result = messagebox.askyesno("Confirm Save",
            f"Save {len(self.modified_records)} modified player(s) to database?\n\n"
            "A backup will be created automatically.")
        
        if not result:
            return
        
        try:
            # Backup
            backup_path = Path(self.file_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            backup_path.write_bytes(self.file_data)
            
            # Save
            modified_list = [(o, r) for o, r in self.modified_records.items()]
            new_data = save_modified_records(self.file_path, self.file_data, modified_list)
            
            Path(self.file_path).write_bytes(new_data)
            self.file_data = new_data
            self.modified_records.clear()
            
            self.status_var.set(f"✓ Database saved")
            messagebox.showinfo("Success", f"Database saved!\nBackup: {backup_path.name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def open_file(self):
        """Open different database file"""
        filename = filedialog.askopenfilename(
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialdir="DBDAT"
        )
        if filename:
            self.file_path = filename
            self.modified_records.clear()
            self.load_database()

def main():
    root = tk.Tk()
    
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    style.configure('Accent.TButton', font=('TkDefaultFont', 10, 'bold'))
    
    app = PM99DatabaseEditor(root)
    root.mainloop()

if __name__ == '__main__':
    main()