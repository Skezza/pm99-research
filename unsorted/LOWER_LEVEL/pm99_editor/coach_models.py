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
    
    # Pattern 1: Given SURNAME (all caps surname)
    pattern1 = rb'([A-Z][a-z]+)\s+([A-Z]{3,})'
    
    # Pattern 2: Given Surname (mixed case)
    pattern2 = rb'([A-Z][a-z]+)\s+([A-Z][a-z]{2,})'
    
    for pattern in [pattern1, pattern2]:
        matches = re.finditer(pattern, decoded_data)
        
        for match in matches:
            try:
                given_name = match.group(1).decode('latin1')  # Use latin1 for accented chars
                surname = match.group(2).decode('latin1')
                
                # Skip if too short
                if len(given_name) < 3 or len(surname) < 3:
                    continue
                
                # Skip common non-name words
                skip_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM']
                if surname.upper() in skip_words:
                    continue
                
                full_name = f"{given_name} {surname}"
                
                # Avoid duplicates
                if full_name in seen_names:
                    continue
                
                seen_names.add(full_name)
                
                coach = Coach(
                    surname=surname,
                    given_name=given_name,
                    full_name=full_name
                )
                
                coaches.append(coach)
            except:
                continue
    
    return coaches