"""
Player Editor for Premier Manager 99
Demonstrates:
1. Load JUG98030.FDI
2. Extract player names
3. Allow renaming
4. Save back to file

Usage:
    python player_editor.py list
    python player_editor.py search "Mikel"
    python player_editor.py rename "Mikel LASA" "Peter LASA"
"""
import sys
from pathlib import Path
from typing import List
from pm99_editor.player_models import Player, parse_all_players
from pm99_editor.file_writer import create_backup, replace_text_in_decoded, write_fdi_record
from pm99_editor.xor import decode_entry

PLAYER_FILE = 'DBDAT/JUG98030.FDI'


def load_players() -> List[Player]:
    """Load and parse all players from file"""
    data = Path(PLAYER_FILE).read_bytes()
    
    print("Loading players from JUG98030.FDI...")
    players = parse_all_players(data)
    print(f"Loaded {len(players)} players\n")
    
    return players


def list_players(limit: int = 50):
    """List players (with optional limit)"""
    players = load_players()
    
    print(f"=== Players in {PLAYER_FILE} ===\n")
    
    display_count = min(limit, len(players))
    
    for i, player in enumerate(players[:display_count], 1):
        print(f"{i:4d}. {player.full_name}")
        if i % 25 == 0:
            print()  # Blank line every 25 players
    
    if len(players) > display_count:
        print(f"\n... and {len(players) - display_count} more players")
    
    print(f"\nTotal: {len(players)} players")
    print(f"Use 'python player_editor.py search NAME' to find specific players")


def search_players(search_term: str):
    """Search for players by name"""
    players = load_players()
    
    search_lower = search_term.lower()
    matches = [p for p in players if search_lower in p.full_name.lower()]
    
    if not matches:
        print(f"❌ No players found matching '{search_term}'")
        return
    
    print(f"=== Found {len(matches)} player(s) matching '{search_term}' ===\n")
    
    for i, player in enumerate(matches, 1):
        print(f"{i}. {player.full_name}")
        print(f"   Section: 0x{player.section_offset:08x}")
        print(f"   Offset:  +{player.name_offset}")
        print()


def rename_player(old_name: str, new_name: str):
    """Rename a player"""
    players = load_players()
    
    # Find the player
    player = None
    for p in players:
        if p.full_name.lower() == old_name.lower():
            player = p
            break
    
    if not player:
        print(f"❌ Player '{old_name}' not found!")
        print(f"\nTry searching first:")
        print(f"  python player_editor.py search \"{old_name.split()[0]}\"")
        return
    
    print(f"\n🔍 Found: {player.full_name}")
    print(f"   Section: 0x{player.section_offset:08x}")
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
    backup = create_backup(PLAYER_FILE)
    print(f"    Backup: {backup}")
    
    # Load the file
    data = Path(PLAYER_FILE).read_bytes()
    
    # Decode the section containing this player
    decoded, _ = decode_entry(data, player.section_offset)
    
    # Replace the name
    print(f"\n✏️  Replacing text in section...")
    modified, success = replace_text_in_decoded(decoded, old_name, new_name)
    
    if not success:
        print(f"❌ Failed to replace text!")
        print(f"    The name might not appear exactly as shown.")
        return
    
    print(f"    ✓ Text replaced in memory")
    
    # Write back to file
    print(f"\n💿 Writing to file...")
    if write_fdi_record(PLAYER_FILE, player.section_offset, modified):
        print(f"    ✓ File updated successfully!")
        print(f"\n🎉 SUCCESS! Player renamed from '{old_name}' to '{new_name}'")
        print(f"\n📝 Next steps:")
        print(f"    1. Run: python player_editor.py search \"{new_name.split()[0]}\"")
        print(f"    2. Verify the change")
        print(f"    3. Launch MANAGPRE.EXE to test in-game")
        print(f"\n    If something goes wrong, restore from: {backup}\n")
    else:
        print(f"❌ Failed to write file!")
        print(f"    Your original file is safe.")
        print(f"    Backup available at: {backup}\n")


def main():
    if len(sys.argv) < 2:
        print("Premier Manager 99 - Player Editor")
        print("\nUsage:")
        print("  python player_editor.py list [limit]")
        print("  python player_editor.py search 'NAME'")
        print("  python player_editor.py rename 'OLD NAME' 'NEW NAME'")
        print("\nExamples:")
        print("  python player_editor.py list 100")
        print("  python player_editor.py search 'Mikel'")
        print("  python player_editor.py rename 'Mikel LASA' 'Peter LASA'")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        list_players(limit)
    elif command == 'search':
        if len(sys.argv) != 3:
            print("Usage: python player_editor.py search 'NAME'")
            return
        search_players(sys.argv[2])
    elif command == 'rename':
        if len(sys.argv) != 4:
            print("Usage: python player_editor.py rename 'OLD NAME' 'NEW NAME'")
            return
        rename_player(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        print("Available commands: list, search, rename")


if __name__ == '__main__':
    main()