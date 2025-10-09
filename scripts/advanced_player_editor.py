"""
Advanced Player Editor - Edit names AND stats
Based on separator pattern analysis (dd 63 60) and attribute byte positions.
"""
import struct
from pathlib import Path
from typing import List, Tuple, Dict, Any
import sys

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def find_records_by_separator(decoded_data: bytes) -> List[int]:
    """Find record starts using separator pattern (dd 63 60)"""
    separators = []
    pattern = bytes([0xdd, 0x63, 0x60])
    
    pos = 0
    while pos < len(decoded_data) - 3:
        if decoded_data[pos:pos+3] == pattern:
            separators.append(pos)
            pos += 3
        else:
            pos += 1
    
    return separators

def extract_player_name(decoded_data: bytes, record_start: int, record_end: int) -> Tuple[str, int]:
    """
    Extract plaintext player name from record.
    Returns (name, name_offset_in_record)
    """
    # Search for capital letter followed by lowercase (start of Given name)
    chunk = decoded_data[record_start:record_end]
    
    for i in range(len(chunk) - 10):
        # Look for pattern like "Daniel SURNAME" or "Marc VANGRONSVELD"
        if (chunk[i] >= 65 and chunk[i] <= 90 and  # Capital letter
            i + 1 < len(chunk) and
            chunk[i+1] >= 97 and chunk[i+1] <= 122):  # Lowercase letter
            
            # Extract name
            name_end = i
            while name_end < len(chunk):
                c = chunk[name_end]
                if (65 <= c <= 90 or 97 <= c <= 122 or c == 32 or c > 127):
                    name_end += 1
                else:
                    break
            
            name = chunk[i:name_end].decode('latin1', errors='replace').strip()
            # Valid player names are usually 8-30 chars
            if 8 <= len(name) <= 40 and ' ' in name:
                return name, record_start + i
    
    return "", 0

def extract_attributes(decoded_data: bytes, name_end: int, record_end: int) -> List[int]:
    """
    Extract potential attribute bytes after the name.
    Look for bytes in 0-100 range (typical for game stats).
    """
    attrs = []
    chunk = decoded_data[name_end:record_end]
    
    for i, byte_val in enumerate(chunk[:40]):  # Check 40 bytes after name
        if 0 <= byte_val <= 100 and byte_val != 96:  # 96 (0x60) is padding
            attrs.append((name_end + i, byte_val))
    
    return attrs

class PlayerRecord:
    def __init__(self, section_offset: int, record_start: int, record_end: int, 
                 name: str, name_offset: int, attributes: List[Tuple[int, int]]):
        self.section_offset = section_offset
        self.record_start = record_start
        self.record_end = record_end
        self.name = name
        self.name_offset = name_offset
        self.attributes = attributes  # List of (offset, value) tuples
    
    def __str__(self):
        attr_str = ', '.join([f"{v}" for _, v in self.attributes[:10]])
        return f"{self.name} [Attrs: {attr_str}]"

def parse_section_into_records(section_offset: int, decoded_data: bytes) -> List[PlayerRecord]:
    """Parse a decoded section into individual player records"""
    separators = find_records_by_separator(decoded_data)
    records = []
    
    for i, sep in enumerate(separators):
        # Record spans from this separator to next (or end of section)
        record_end = separators[i+1] if i+1 < len(separators) else len(decoded_data)
        
        # Extract name
        name, name_offset = extract_player_name(decoded_data, sep, record_end)
        if name:
            # Extract attributes
            attrs = extract_attributes(decoded_data, name_offset + len(name), record_end)
            
            record = PlayerRecord(
                section_offset=section_offset,
                record_start=sep,
                record_end=record_end,
                name=name,
                name_offset=name_offset,
                attributes=attrs[:10]  # Keep first 10 as likely stats
            )
            records.append(record)
    
    return records

def find_all_player_records(file_data: bytes) -> List[PlayerRecord]:
    """Find all player records in the entire file"""
    all_records = []
    
    # Find sections with player data (those with separator patterns)
    pos = 0x400  # Start after header
    sections_scanned = 0
    
    while pos < len(file_data) - 1000 and sections_scanned < 500:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            if 1000 < length < 100000:  # Reasonable section size
                # Decode section
                encoded = file_data[pos+2 : pos+2+length]
                decoded = bytes(b ^ 0x61 for b in encoded)
                
                # Check if it has separator patterns
                if bytes([0xdd, 0x63, 0x60]) in decoded:
                    records = parse_section_into_records(pos, decoded)
                    all_records.extend(records)
                    sections_scanned += 1
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    print(f"Scanned {sections_scanned} sections, found {len(all_records)} player records")
    return all_records

def modify_player_attribute(file_data: bytes, record: PlayerRecord, attr_index: int, new_value: int) -> bytes:
    """
    Modify a specific attribute of a player.
    attr_index: 0-9 for the first 10 attributes
    new_value: 0-100
    """
    if attr_index >= len(record.attributes):
        raise ValueError(f"Attribute index {attr_index} out of range (max {len(record.attributes)-1})")
    
    if not (0 <= new_value <= 100):
        raise ValueError(f"Attribute value must be 0-100, got {new_value}")
    
    # Get the attribute offset in the decoded data
    attr_offset_in_section, old_value = record.attributes[attr_index]
    
    # Decode the section
    decoded, _ = decode_xor61(file_data, record.section_offset)
    
    # Modify the byte
    modified = bytearray(decoded)
    modified[attr_offset_in_section] = new_value
    
    # Encode back
    encoded = bytes(b ^ 0x61 for b in modified)
    length_prefix = struct.pack("<H", len(encoded))
    
    # Write back to file
    file_data_modified = bytearray(file_data)
    file_data_modified[record.section_offset:record.section_offset+2] = length_prefix
    file_data_modified[record.section_offset+2:record.section_offset+2+len(encoded)] = encoded
    
    return bytes(file_data_modified)

# ========== CLI Interface ==========

PLAYER_FILE = 'DBDAT/JUG98030.FDI'

def cmd_list(args):
    """List players with their attributes"""
    limit = int(args[0]) if args else 20
    
    data = Path(PLAYER_FILE).read_bytes()
    records = find_all_player_records(data)
    
    print(f"\n=== Found {len(records)} players ===\n")
    
    for i, rec in enumerate(records[:limit], 1):
        attrs = [str(v) for _, v in rec.attributes[:10]]
        print(f"{i:4d}. {rec.name:<30} Stats: [{', '.join(attrs)}]")
    
    if len(records) > limit:
        print(f"\n... and {len(records) - limit} more")

def cmd_show(args):
    """Show detailed info for a specific player"""
    if not args:
        print("Usage: show 'Player Name'")
        return
    
    search_name = args[0]
    data = Path(PLAYER_FILE).read_bytes()
    records = find_all_player_records(data)
    
    matches = [r for r in records if search_name.lower() in r.name.lower()]
    
    if not matches:
        print(f"No player found matching '{search_name}'")
        return
    
    for rec in matches:
        print(f"\n{'='*60}")
        print(f"Player: {rec.name}")
        print(f"{'='*60}")
        print(f"Section offset: 0x{rec.section_offset:08x}")
        print(f"Record range: {rec.record_start} - {rec.record_end}")
        print(f"\nAttributes:")
        for i, (offset, value) in enumerate(rec.attributes):
            print(f"  [{i}] @ +{offset:5d}: {value:3d}")

def cmd_modify(args):
    """Modify a player's attribute"""
    if len(args) != 3:
        print("Usage: modify 'Player Name' <attr_index> <new_value>")
        print("Example: modify 'Daniel KIMONI' 0 90")
        return
    
    player_name, attr_idx, new_val = args[0], int(args[1]), int(args[2])
    
    # Load file
    data = Path(PLAYER_FILE).read_bytes()
    records = find_all_player_records(data)
    
    # Find player
    matches = [r for r in records if player_name.lower() == r.name.lower()]
    
    if not matches:
        print(f"Player '{player_name}' not found")
        return
    
    record = matches[0]
    
    if attr_idx >= len(record.attributes):
        print(f"Attribute index {attr_idx} out of range (max {len(record.attributes)-1})")
        return
    
    old_val = record.attributes[attr_idx][1]
    
    print(f"\nModifying {record.name}")
    print(f"Attribute {attr_idx}: {old_val} → {new_val}")
    
    # Backup
    backup_path = Path(PLAYER_FILE + '.backup')
    if not backup_path.exists():
        backup_path.write_bytes(data)
        print(f"Created backup: {backup_path}")
    
    # Modify
    try:
        modified_data = modify_player_attribute(data, record, attr_idx, new_val)
        Path(PLAYER_FILE).write_bytes(modified_data)
        print(f"✓ Success! Modified attribute {attr_idx} to {new_val}")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    if len(sys.argv) < 2:
        print("Advanced Player Editor - Edit stats and abilities")
        print("\nCommands:")
        print("  list [limit]               - List players with stats")
        print("  show 'Player Name'         - Show detailed player info")
        print("  modify 'Name' idx val      - Modify attribute (0-9)")
        print("\nExamples:")
        print("  python advanced_player_editor.py list 30")
        print("  python advanced_player_editor.py show 'Daniel'")
        print("  python advanced_player_editor.py modify 'Daniel KIMONI' 0 90")
        return
    
    cmd = sys.argv[1].lower()
    args = sys.argv[2:]
    
    if cmd == 'list':
        cmd_list(args)
    elif cmd == 'show':
        cmd_show(args)
    elif cmd == 'modify':
        cmd_modify(args)
    else:
        print(f"Unknown command: {cmd}")

if __name__ == '__main__':
    main()