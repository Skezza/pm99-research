"""
Coach data models for Premier Manager 99
Based on analysis of ENT98030.FDI
"""
from dataclasses import dataclass
from typing import List
import struct

@dataclass
class Coach:
    """Represents a coach in the database"""
    surname: str = ""
    given_name: str = ""
    full_name: str = ""
    
    def __str__(self) -> str:
        return self.full_name if self.full_name else f"{self.given_name} {self.surname}".strip()
    
    def to_bytes(self) -> bytes:
        """
        Fallback serialization for Coach objects that aren't wrapped in EditableCoachRecord.
        
        This should not normally be called - coaches should be loaded as EditableCoachRecord
        which has proper serialization. This is just a safety fallback that returns
        a minimal valid entry.
        """
        # Return a minimal encoded entry with just the name
        # Format: length-prefixed Latin-1 encoded name
        name_bytes = self.full_name.encode('latin-1', errors='replace')
        # Simple XOR encoding with 0x61
        encoded = bytes(b ^ 0x61 for b in name_bytes)
        return encoded
    
    def set_name(self, given_name: str, surname: str):
        """Update coach name fields."""
        self.given_name = given_name
        self.surname = surname
        self.full_name = f"{given_name} {surname}".strip()

def parse_coaches_from_record(decoded_data: bytes) -> List[Coach]:
    """
    Parse coaches from the decoded record at 0x026cf6.
    After XOR decode, names are plaintext separated by specific markers.

    Pattern: [metadata] surname [sep] [metadata] given full_name [padding]

    Args:
        decoded_data: XOR-decoded coach record bytes

    Returns:
        List of Coach objects
    """
    import re

    coaches = []
    seen_names = set()

    # Common team name suffixes/words to skip (to avoid parsing team names as coaches)
    team_suffixes = {
        'FC', 'UNITED', 'CITY', 'TOWN', 'ATHLETIC', 'ROVERS', 'WANDERERS', 'HOTSPUR',
        'ALBION', 'VILLA', 'RANGERS', 'WOLVES', 'COUNTY', 'FOREST', 'PALACE', 'HAM',
        'SPURS', 'BLUES', 'EAGLES', 'LIONS', 'TIGERS', 'BEARS', 'HAWKS', 'FALCONS',
        'SHARKS', 'STARS', 'WARRIORS', 'KNIGHTS', 'DRAGONS', 'PHOENIX', 'GLADIATORS'
    }

    # Decode the data to string for regex matching
    try:
        text_data = decoded_data.decode('cp1252', errors='replace')
    except Exception:
        text_data = decoded_data.decode('latin1', errors='replace')

    # Pattern 1: Given SURNAME (all caps surname)
    pattern1 = r'([A-ZÀ-Ý][a-zà-ÿ]+)\s+([A-ZÀ-Ý]{3,})'

    # Pattern 2: Given Surname (mixed case)
    pattern2 = r'([A-ZÀ-Ý][a-zà-ÿ]+)\s+([A-ZÀ-Ý][a-zà-ÿ]{2,})'

    # Pattern 3: Given Surname with more flexible matching
    pattern3 = r'([A-ZÀ-Ý][a-zà-ÿ]+)\s+([A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)*)'

    for pattern in [pattern1, pattern2, pattern3]:
        matches = re.finditer(pattern, text_data)

        for match in matches:
            try:
                given_name = match.group(1).strip()
                surname = match.group(2).strip()

                # Clean up surname by removing trailing non-letter sequences
                import re as _re
                # Remove trailing characters that are not letters, accents, or spaces
                surname = _re.sub(r'[^A-Za-zÀ-ÿ\s]+$', '', surname).strip()
                
                # Normalize to title case EARLY for consistency and proper deduplication
                # This ensures "George GRAHAM", "George Graham", and "george graham" all become "George Graham"
                given_name = given_name.title()
                surname = surname.title()

                # Skip if too short after cleaning
                if len(given_name) < 3 or len(surname) < 3:
                    continue

                # Skip if surname is too long (likely includes garbage)
                if len(surname) > 20:
                    continue

                # Skip common non-name words
                skip_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM']
                if surname.upper() in skip_words:
                    continue

                # Skip if surname looks like a team suffix
                if surname.upper() in team_suffixes:
                    continue

                # Build full name AFTER normalization for proper deduplication
                full_name = f"{given_name} {surname}"
                if len(full_name.split()) > 2:
                    continue

                # Avoid duplicates using case-insensitive comparison
                # Use uppercase for the deduplication key to catch any remaining case variations
                full_name_key = full_name.upper()
                if full_name_key in seen_names:
                    continue

                seen_names.add(full_name_key)

                coach = Coach(
                    surname=surname,
                    given_name=given_name,
                    full_name=full_name
                )

                coaches.append(coach)
            except:
                continue

    return coaches

class EditableCoachRecord:
    """
    Wrapper for a decoded coach record that allows editing a parsed coach name
    and producing an updated decoded payload suitable for saving.

    This is intentionally conservative: it replaces the first exact occurrence
    of the original parsed full name in the decoded bytes. If no exact match is
    found it falls back to the first printable-run replacement, padding or
    truncating as needed.
    """
    def __init__(self, decoded_data: bytes, record_offset: int, given_name: str, surname: str):
        self.decoded = bytearray(decoded_data)
        self.record_offset = record_offset
        self.given_name = given_name or ""
        self.surname = surname or ""
        self.full_name = f"{self.given_name} {self.surname}".strip()

    def set_name(self, given_name: str, surname: str) -> bytes:
        """Replace the stored name in the decoded blob and update internal fields."""
        new_full = f"{given_name} {surname}".strip()
        # Use latin-1 to match parsing behaviour
        old_bytes = (self.full_name or "").encode('latin-1', errors='ignore')
        new_bytes = new_full.encode('latin-1', errors='ignore')

        # Try exact byte match first
        decoded_bytes = bytes(self.decoded)
        idx = decoded_bytes.find(old_bytes) if old_bytes else -1

        if idx != -1 and old_bytes:
            # Replace the slice (may change length; file_writer handles delta)
            self.decoded[idx:idx + len(old_bytes)] = new_bytes
        else:
            # Fallback: replace first printable ASCII/Latin-1 run found
            import re
            m = re.search(rb'[\x20-\x7e]{4,60}', decoded_bytes)
            if m:
                start, end = m.start(), m.end()
                # If new name is shorter, pad with spaces to preserve surrounding structure
                if len(new_bytes) <= (end - start):
                    padded = new_bytes + b' ' * ((end - start) - len(new_bytes))
                    self.decoded[start:end] = padded
                else:
                    # If longer, expand in-place (file_writer will accept length changes)
                    self.decoded[start:end] = new_bytes

        self.given_name = given_name
        self.surname = surname
        self.full_name = new_full
        return bytes(self.decoded)

    def to_bytes(self) -> bytes:
        """Return the full decoded payload (no length prefix)."""
        return bytes(self.decoded)

    def __str__(self) -> str:
        return self.full_name or f"{self.given_name} {self.surname}".strip()