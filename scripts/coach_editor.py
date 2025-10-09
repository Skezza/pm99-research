"""
Coach Editor for Premier Manager 99
Proof-of-concept demonstrating:
1. Load ENT98030.FDI
2. Extract coach names
3. Allow renaming
4. Save back to file

Usage:
    python coach_editor.py list
    python coach_editor.py rename "Terry EVANS" "John SMITH"
"""
import sys
import struct
from pathlib import Path
from typing import List, Tuple
from pm99_editor.coach_models import Coach, parse_coaches_from_record
from pm99_editor.xor import decode_entry, encode_entry
from pm99_editor.file_writer import create_backup, replace_text_in_decoded, write_fdi_record

COACH_FILE = 'DBDAT/ENT98030.FDI'
COACH_RECORD_OFFSET = 0x026cf6


def load_coaches() -> Tuple[bytes, List[Coach]]:
    """Load and parse coaches from file"""
    data = Path(COACH_FILE).read_bytes()
    
    # Decode the coach record
    decoded, _ = decode_entry(data, COACH_RECORD_OFFSET)
    
    # Parse coaches
    coaches = parse_coaches_from_record(decoded)
    
    return data, coaches


def list_coaches():
    """List all coaches"""
    _, coaches = load_coaches()
    
    print(f"\n=== Coaches in {COACH_FILE} ===\n")
    
    for i, coach in enumerate(coaches, 1):
        print(f"{i}. {coach.full_name}")
        print(f"   Given: {coach.given_name}")
        print(f"   Surname: {coach.surname}")
        print()
    
    print(f"Total: {len(coaches)} coaches\n")


def rename_coach(old_name: str, new_name: str):
    """Rename a coach"""
    data, coaches = load_coaches()
    
    # Find the coach
    coach = None
    for c in coaches:
        if c.full_name.lower() == old_name.lower():
            coach = c
            break
    
    if not coach:
        print(f"❌ Coach '{old_name}' not found!")
        print(f"\nAvailable coaches:")
        for c in coaches:
            print(f"  - {c.full_name}")
        return
    
    print(f"\n🔍 Found: {coach.full_name}")
    print(f"📝 Renaming to: {new_name}")
    
    # Check length compatibility
    if len(old_name) != len(new_name):
        print(f"\n⚠️  Length mismatch!")
        print(f"    Old: {len(old_name)} chars")
        print(f"    New: {len(new_name)} chars")
        print(f"    For safety, names must be same length.")
        print(f"    Pad with spaces if needed: '{new_name:<{len(old_name)}}'")
        return
    
    # Create backup
    print(f"\n💾 Creating backup...")
    backup = create_backup(COACH_FILE)
    print(f"    Backup: {backup}")
    
    # Load and decode the record
    decoded, _ = decode_entry(data, COACH_RECORD_OFFSET)
    
    # Replace the name
    print(f"\n✏️  Replacing text...")
    modified, success = replace_text_in_decoded(decoded, old_name, new_name)
    
    if not success:
        print(f"❌ Failed to replace text!")
        print(f"    Make sure the exact name appears in the file.")
        return
    
    print(f"    ✓ Text replaced in memory")
    
    # Write back to file
    print(f"\n💿 Writing to file...")
    if write_fdi_record(COACH_FILE, COACH_RECORD_OFFSET, modified):
        print(f"    ✓ File updated successfully!")
        print(f"\n🎉 SUCCESS! Coach renamed from '{old_name}' to '{new_name}'")
        print(f"\n📝 Next steps:")
        print(f"    1. Run: python coach_editor.py list")
        print(f"    2. Verify the change")
        print(f"    3. Launch MANAGPRE.EXE to test in-game")
        print(f"\n    If something goes wrong, restore from: {backup}\n")
    else:
        print(f"❌ Failed to write file!")
        print(f"    Your original file is safe.")
        print(f"    Backup available at: {backup}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python coach_editor.py list")
        print("  python coach_editor.py rename 'OLD NAME' 'NEW NAME'")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        list_coaches()
    elif command == 'rename':
        if len(sys.argv) != 4:
            print("Usage: python coach_editor.py rename 'OLD NAME' 'NEW NAME'")
            return
        rename_coach(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        print("Available commands: list, rename")


if __name__ == '__main__':
    main()