#!/usr/bin/env python3
"""Test that player name renaming doesn't corrupt the database."""

import struct
from app.models import PlayerRecord
from app.xor import write_string, read_string

def test_name_encoding_roundtrip():
    """Test that we can rename a player and read it back correctly."""
    
    # Create a simple test record with encoded names
    team_id = 3001
    squad_num = 10
    
    # Build a minimal valid player record
    header = struct.pack("<H", team_id) + bytes([squad_num]) + b'\x00\x00'
    
    # Encode names using the game's format
    given_encoded = write_string("David")
    surname_encoded = write_string("Beckham")
    
    # Add minimal metadata (14 bytes)
    metadata = bytes([
        0x61,  # position (0 XOR 0x61)
        0x61,  # nationality (0 XOR 0x61)
        (1 ^ 0x61) & 0xFF,  # birth_day
        (1 ^ 0x61) & 0xFF,  # birth_month
        (1975 & 0xFF) ^ 0x61,  # birth_year low byte
        ((1975 >> 8) & 0xFF) ^ 0x61,  # birth_year high byte
        (175 ^ 0x61) & 0xFF,  # height
    ] + [0x61] * 7)  # padding
    
    # Add attributes (12 bytes, XOR encoded)
    attrs = bytes([50 ^ 0x61] * 12)
    
    # Trailing padding
    trailing = b'\x00' * 7
    
    # Build complete record
    test_data = header + given_encoded + surname_encoded + metadata + attrs + trailing
    
    print(f"Original record size: {len(test_data)} bytes")
    print(f"Given name encoded: {given_encoded.hex()}")
    print(f"Surname encoded: {surname_encoded.hex()}")
    
    # Parse the record
    player = PlayerRecord.from_bytes(test_data, 0, 700)
    print(f"\nParsed player: {player.given_name} {player.surname}")
    print(f"Full name: {player.name}")
    
    assert player.given_name == "David", f"Expected 'David', got '{player.given_name}'"
    assert player.surname == "Beckham", f"Expected 'Beckham', got '{player.surname}'"
    
    # Now rename the player
    print("\n--- Renaming player to 'Michael Jordan' ---")
    player.set_given_name("Michael")
    player.set_surname("Jordan")
    
    print(f"After rename: {player.given_name} {player.surname}")
    print(f"Name dirty flag: {player.name_dirty}")
    
    # Serialize back to bytes
    serialized = player.to_bytes()
    print(f"\nSerialized size: {len(serialized)} bytes")
    
    # Parse it again to verify
    player2 = PlayerRecord.from_bytes(serialized, 0, 700)
    print(f"\nRe-parsed player: {player2.given_name} {player2.surname}")
    print(f"Full name: {player2.name}")
    
    # Verify the rename worked
    assert player2.given_name == "Michael", f"Expected 'Michael', got '{player2.given_name}'"
    assert player2.surname == "Jordan", f"Expected 'Jordan', got '{player2.surname}'"
    
    # Verify other fields preserved
    assert player2.team_id == team_id, f"Team ID changed: {player2.team_id}"
    assert player2.squad_number == squad_num, f"Squad number changed: {player2.squad_number}"
    
    print("\n✅ TEST PASSED: Name encoding/decoding roundtrip works correctly!")
    return True

def test_name_parsing():
    """Test that we can correctly parse the two encoded strings."""
    
    # Create test data with two encoded strings
    given_str = "Test"
    surname_str = "Player"
    
    given_enc = write_string(given_str)
    surname_enc = write_string(surname_str)
    
    print(f"Given encoded: {given_enc.hex()}")
    print(f"Surname encoded: {surname_enc.hex()}")
    
    # Try to read them back
    pos = 0
    given_back, consumed1 = read_string(given_enc + surname_enc, pos)
    pos += consumed1
    surname_back, consumed2 = read_string(given_enc + surname_enc, pos)
    
    print(f"Read back: '{given_back}' '{surname_back}'")
    
    assert given_back == given_str, f"Expected '{given_str}', got '{given_back}'"
    assert surname_back == surname_str, f"Expected '{surname_str}', got '{surname_back}'"
    
    print("✅ String parsing works correctly!")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Player Name Encoding Fix")
    print("=" * 60)
    
    try:
        test_name_parsing()
        print()
        test_name_encoding_roundtrip()
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
