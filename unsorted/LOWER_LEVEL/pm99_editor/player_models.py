"""
Player data models for Premier Manager 99
Based on analysis of JUG98030.FDI
"""
from dataclasses import dataclass
from typing import List, Tuple
import re

@dataclass
class Player:
    """Represents a player in the database"""
    given_name: str = ""
    surname: str = ""
    full_name: str = ""
    section_offset: int = 0  # Offset of the section containing this player
    name_offset: int = 0     # Offset within decoded section where name appears
    
    def __str__(self) -> str:
        return self.full_name if self.full_name else f"{self.given_name} {self.surname}".strip()

def find_player_sections(data: bytes) -> List[Tuple[int, int]]:
    """
    Find all sections in the file that contain player names.
    Returns list of (offset, size) tuples.
    """
    import struct
    
    sections = []
    pos = 0x400  # Start after header
    
    while pos < len(data) - 100:
        try:
            length = struct.unpack_from("<H", data, pos)[0]
            if 100 < length < 100000:  # Reasonable section size
                # Decode and check for player names
                encoded = data[pos+2 : pos+2+length]
                decoded = bytes(b ^ 0x61 for b in encoded)
                
                # Quick check: does it contain name patterns?
                if re.search(rb'[A-Z][a-z]{2,15}\s+[A-Z]{3,20}', decoded):
                    sections.append((pos, length + 2))  # Include length prefix
                    pos += length + 2
                    continue
            pos += 1
        except:
            pos += 1
    
    return sections

def parse_players_from_section(decoded_data: bytes, section_offset: int = 0) -> List[Player]:
    """
    Parse players from a decoded section.
    After XOR decode, player names appear as plaintext.
    
    Pattern: [metadata] surname_encoded [0x61] Given SURNAME [more data]
    
    Args:
        decoded_data: XOR-decoded section bytes
        section_offset: File offset where this section starts (for tracking)
        
    Returns:
        List of Player objects
    """
    players = []
    seen_names = set()
    
    # Pattern 1: Given SURNAME (all caps surname) - most common
    pattern1 = rb'([A-Z][a-z]{2,15})\s+([A-Z]{3,20})'
    
    # Pattern 2: Given Surname (mixed case) - less common
    pattern2 = rb'([A-Z][a-z]{2,15})\s+([A-Z][a-z]{2,20})'
    
    for pattern in [pattern1, pattern2]:
        matches = re.finditer(pattern, decoded_data)
        
        for match in matches:
            try:
                given_name = match.group(1).decode('latin1')
                surname = match.group(2).decode('latin1')
                
                # Skip if too short
                if len(given_name) < 3 or len(surname) < 3:
                    continue
                
                # Skip common non-name words
                skip_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 
                             'WHEN', 'WHERE', 'TEAM', 'CLUB', 'GAME']
                if surname.upper() in skip_words:
                    continue
                
                # Skip if first name looks like a common word
                if given_name.upper() in ['NATIONAL', 'OLYMPIC', 'SOUTH', 'NORTH']:
                    continue
                
                full_name = f"{given_name} {surname}"
                
                # Avoid duplicates
                if full_name in seen_names:
                    continue
                
                seen_names.add(full_name)
                
                player = Player(
                    given_name=given_name,
                    surname=surname,
                    full_name=full_name,
                    section_offset=section_offset,
                    name_offset=match.start()
                )
                
                players.append(player)
            except:
                continue
    
    return players

def parse_all_players(file_data: bytes) -> List[Player]:
    """
    Parse all players from the entire JUG98030.FDI file.
    
    Args:
        file_data: Complete FDI file contents
        
    Returns:
        List of all Player objects found
    """
    import struct
    
    all_players = []
    
    # Find all sections with player data
    sections = find_player_sections(file_data)
    
    print(f"Found {len(sections)} sections with player data")
    
    for section_offset, section_size in sections:
        # Decode section
        length = struct.unpack_from("<H", file_data, section_offset)[0]
        encoded = file_data[section_offset+2 : section_offset+2+length]
        decoded = bytes(b ^ 0x61 for b in encoded)
        
        # Parse players from this section
        players = parse_players_from_section(decoded, section_offset)
        all_players.extend(players)
    
    return all_players