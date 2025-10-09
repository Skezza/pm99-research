"""
Data loaders for Premier Manager 99 FDI files.

This module provides shared loading logic for coaches and teams,
applying strict validation filters to reject corrupted entries.
The FDI directory structures are corrupted, so these loaders use
sequential scanning instead.
"""

from pathlib import Path
from typing import List, Tuple, Any
from pm99_editor.xor import xor_decode
from pm99_editor.models import TeamRecord
from pm99_editor.coach_models import parse_coaches_from_record


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


def load_teams(file_path: str) -> List[Tuple[int, TeamRecord]]:
    """
    Load teams from EQ98030.FDI file.
    
    Teams are stored in XOR-encoded sections with separator-delimited records.
    
    Args:
        file_path: Path to the teams FDI file
        
    Returns:
        List of (offset, TeamRecord) tuples for valid teams
    """
    parsed = []
    
    try:
        data = Path(file_path).read_bytes()
        
        # Known team sections in the file (from analysis scripts)
        # These are length-prefixed XOR-encoded sections
        known_sections = [
            0x201,   # Section 1: ~11KB
            0x2f04,  # Section 2: ~42KB (main team data)
        ]
        
        seen_names = set()
        separator = bytes([0x61, 0xdd, 0x63])  # Team record separator
        
        for section_offset in known_sections:
            try:
                # Read length prefix (2 bytes, little-endian)
                length = int.from_bytes(data[section_offset:section_offset+2], 'little')
                
                # Decode XOR-encoded section
                encoded = data[section_offset + 2 : section_offset + 2 + length]
                decoded = bytes(b ^ 0x61 for b in encoded)
                
                # Find separator positions
                positions = []
                pos = 0
                while pos < len(decoded):
                    pos = decoded.find(separator, pos)
                    if pos == -1:
                        break
                    positions.append(pos)
                    pos += 3
                
                # Extract team records between separators
                for i in range(len(positions)):
                    sep_pos = positions[i]
                    next_sep = positions[i+1] if i+1 < len(positions) else len(decoded)
                    
                    # Extract record data (from separator to next separator)
                    record_data = decoded[sep_pos:next_sep]
                    
                    try:
                        team = TeamRecord(record_data, section_offset + sep_pos)
                        name = getattr(team, 'name', None)
                        
                        # Basic validation
                        if not name or name in ("Unknown Team", "Parse Error", ""):
                            continue
                        
                        # Length check
                        if len(name) < 3 or len(name) > 60:
                            continue
                        
                        # Must start with uppercase
                        if not name[0].isupper():
                            continue
                        
                        # Must have letters
                        if not any(c.isalpha() for c in name):
                            continue
                        
                        # Deduplicate
                        if name in seen_names:
                            continue
                        
                        seen_names.add(name)
                        parsed.append((section_offset + sep_pos, team))
                        
                    except Exception:
                        pass
                        
            except Exception as e:
                print(f"[TEAM LOADER] Error processing section at 0x{section_offset:x}: {e}")
                continue
                
    except Exception as e:
        print(f"[TEAM LOADER] Error loading teams: {e}")
    
    print(f"[TEAM LOADER] Loaded {len(parsed)} teams")
    return parsed


def load_coaches(file_path: str) -> List[Tuple[int, Any]]:
    """
    Load coaches from ENT98030.FDI file with strict validation filtering.
    
    Skips the corrupted directory and uses sequential scanning.
    Applies multiple validation filters to reject garbage entries.
    
    Args:
        file_path: Path to the coaches FDI file
        
    Returns:
        List of (offset, CoachRecord) tuples for valid coaches
    """
    parsed_coaches = []
    
    try:
        data = Path(file_path).read_bytes()
        pos = 0x400  # Skip header
        seen_names = set()
        
        while pos < len(data) - 1000:
            length = 0
            try:
                decoded, length = decode_entry(data, pos)
                
                # Length validation
                if length < 100 or length > 50000:
                    pos += 2
                    continue
                
                try:
                    coaches = parse_coaches_from_record(decoded) or []
                    
                    for c in coaches:
                        name = getattr(c, 'full_name', '')
                        
                        # Basic checks
                        if not name or len(name) < 6 or len(name) > 40:
                            continue
                        
                        if not name[0].isupper() or ' ' not in name:
                            continue
                        
                        # Split into parts
                        parts = name.split()
                        if len(parts) < 2:
                            continue
                        
                        # Reject common non-name patterns (teams, stadiums, locations, phrases, job titles, players)
                        common_phrases = [
                            # Known player names (not coaches)
                            'boa morte', 'rui barros', 'mark hatelely', 'stan collymore',
                            'jamie redknapp', 'bobby moore', 'bryan robson', 'nick barmby',
                            'darren huckerby', 'michael gray', 'asa harford', 'john wark',
                            'ian rush', 'dave beasant', 'steve simonsen', 'fabrizio ravanelli',
                            'roberto baggio', 'marcus stewart', 'wayne allison', 'delroy facey',
                            'darren eadie', 'keith gillespie', 'pal lydersen', 'john jensen',
                            'peter hill', 'steve gibson', 'don megson', 'billy bonds',
                            'mick buxton', 'frank worthington', 'don givens', 'archie gemmil',
                            'willie johnston', 'alan buckley', 'billy hamilton', 'bob lord',
                            'jock stein', 'andy roxburgh', 'dave basset', 'dennis smith',
                            'viv anderson', 'steve gritt', 'alan smith', 'dave sexton',
                            'terry fenwick', 'colin todd', 'peter robinson', 'roy evans',
                            'bill shankly', 'stan ternent', 'bobby robson', 'lou macari',
                            'archie knox', 'roy hodgson', 'john reames', 'jeff wood',
                            
                            # Leagues and divisions
                            'premier league', 'first division', 'second division', 'third division', 'fourth division',
                            'first divis', 'second divsion', 'third divison', 'italian second', 'italian championship',
                            'scottish first', 'scottish second', 'french fifth', 'norwegian first', 'norwegian premier',
                            'norwegian champions', 'league championsh', 'danish football', 'swiss first', 'swedish olympic',
                            'norwegian olympic', 'swedish national', 'norway olympic', 'sweden under', 'sweden olympic',
                            'vauxhall conference', 'french league', 'spanish league', 'italian league', 'german league',
                            'football league', 'scottish league', 'english league', 'north american', 'soccer league',
                            
                            # Cups and competitions
                            'league cup', 'european cup', 'world cup', 'french cup', 'spanish cup', 'italian cup', 'japan cup',
                            'cup winner', 'cup winners', 'champions league', 'uefa cup', 'scottish cup', 'irish cup',
                            'cup champion', 'winners cup', 'charity shield', 'european championship', 'intercontinental cup',
                            'european supercup', 'dutch league', 'dutch cup', 'italian supercup', 'dutch first',
                            'european champions', 'european champion', 'cup title', 'league champion', 'twice league',
                            'auto windscreen', 'auto windscreens', 'twin towers', 'amateur cup', 'systems cup', 'cup usa',
                            'olympic games', 'world champions', 'european player', 'european super',
                            
                            # Stadium names
                            'old trafford', 'san siro', 'goodison park', 'highbury arsenal', 'elland road',
                            'white hart', 'upton park', 'loftus road', 'stamford bridge', 'maine road',
                            'selhurst park', 'burnden park', 'the dell', 'ewood park',
                            
                            # Team names (common ones that appear in biographies)
                            'real madrid', 'manchester utd', 'manchester uniyed', 'queens park', 'preston north',
                            'oldham ahtletic', 'liverpool sch', 'sheffield wednesday', 'west brom', 'port vale',
                            'paris saint', 'werder bremen', 'borussia', 'bayern munich', 'grasshopper zurich',
                            'bristol rov', 'doncaster rov', 'plymouth argyle', 'meadowbank thistle',
                            'seattle sounders', 'vancouver whitecaps', 'fort lauderdale',
                            'atlético madrid', 'viking stavanger', 'real sociedad', 'south liverpool',
                            
                            # Locations and schools
                            'the england', 'durham school', 'east durham', 'north londoners', 'east london',
                            'witton gilbert', 'east stirling', 'liverpool university', 'united school',
                            
                            # Generic phrases and nicknames
                            'the scottish', 'the gallic', 'the french', 'the hornets', 'red devils',
                            'the hammers', 'the dutchman', 'the samp', 'the bald eagle', 'the rams',
                            'captain marvel', 'bald eagle', 'fergie babes',
                            
                            # Job titles and positions
                            'head coach', 'technical advisor', 'national team', 'segundo entrenador',
                            'union coach', 'norwegian coach',
                            
                            # Common bio phrases
                            'although harry', 'although robson', 'although john', 'under gordon', 'under ron',
                            'after bobby', 'eventually leicester', 'eventually portsmouth', 'considered arsenal',
                            'replaced howard', 'around december',
                            
                            # Tournament/achievement phrases
                            'division champion', 'division runner', 'league championship', 'quarter finals',
                            'cup runner', 'british championship', 'league champions',
                            
                            # Nationalities and descriptors (with space to avoid partial matches)
                            'belgian ', 'liberian ', 'yugoslavian ', 'frenchman ', 'german ', 'argentinian ',
                            'united states', 'northern ireland', 'soviet union',
                            
                            # Time/conditional phrases
                            'when ', 'with ', 'from ', 'new year', 'second jun',
                            
                            # Specific problematic patterns
                            'monaco arsene', 'european parliament',
                            
                            # Generic descriptors
                            'scottish footballer', 'french football', 'french federation',
                            'second world',
                            
                            # Stadium/Location names
                            'highfield road', 'shepshed charterhouse', 'filbert street'
                        ]
                        
                        name_lower = name.lower()
                        if any(phrase in name_lower for phrase in common_phrases):
                            continue
                        
                        # Each part must be reasonable
                        valid = True
                        for part in parts:
                            if len(part) < 2 or len(part) > 20:
                                valid = False
                                break
                            
                            # First char must be uppercase
                            if not part[0].isupper():
                                valid = False
                                break
                            
                            # Reject obvious garbage suffix patterns (ends with 'aa', 'ba', 'ca', etc.)
                            # But allow normal name endings like "an", "en", "on", "in"
                            if len(part) > 3:
                                last_two = part[-2:].lower()
                                # Reject if ends with repeated vowel + 'a' pattern (common garbage)
                                if last_two in ['aa', 'ba', 'ca', 'da', 'ea', 'fa', 'ga', 'ha', 'ia', 'ja', 'ka', 'la', 'ma', 'na', 'oa', 'pa', 'qa', 'ra', 'sa', 'ta', 'ua', 'va', 'wa', 'xa', 'ya', 'za']:
                                    # Exception for valid suffixes
                                    if part.lower() not in ['da', 'de', 'van', 'von', 'del', 'di', 'el', 'la']:
                                        valid = False
                                        break
                        
                        if not valid:
                            continue
                        
                        # ASCII ratio
                        ascii_ratio = sum(1 for ch in name if 32 <= ord(ch) < 127) / len(name)
                        if ascii_ratio < 0.85:
                            continue
                        
                        # Reject garbage patterns
                        if name.count('a') > len(name) * 0.6:
                            continue
                        
                        # Deduplicate
                        if name in seen_names:
                            continue
                        
                        seen_names.add(name)
                        parsed_coaches.append((pos, c))
                        
                except Exception:
                    pass
                    
            except Exception:
                pass
                
            pos += 2 + length if length > 0 else 1
            
    except Exception as e:
        print(f"[COACH LOADER] Error loading coaches: {e}")
    
    return parsed_coaches