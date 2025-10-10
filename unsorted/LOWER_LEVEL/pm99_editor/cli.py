"""Command-line interface for PM99 database editor."""

import argparse
from pathlib import Path
import sys

from .io import FDIFile


def cmd_list(args):
    """List players in database."""
    fdi = FDIFile(args.file)
    fdi.load()
    
    players = fdi.list_players(limit=args.limit)
    for player in players:
        print(player)
    
    print(f"\nTotal: {len(fdi.records)} players")


def cmd_search(args):
    """Search for players by name."""
    fdi = FDIFile(args.file)
    fdi.load()
    
    matches = fdi.find_by_name(args.query)
    
    if not matches:
        print(f"No players found matching '{args.query}'")
        return
    
    print(f"Found {len(matches)} player(s):")
    for player in matches:
        print(f"  {player}")


def cmd_rename(args):
    """Rename a player by record ID."""
    fdi = FDIFile(args.file)
    fdi.load()
    
    # Find player
    try:
        player = fdi.find_by_id(args.id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    print(f"Current name: {player.given_name} {player.surname}")
    
    # Parse new name
    name_parts = args.name.strip().split(maxsplit=1)
    if len(name_parts) == 1:
        # Only one name provided, assume it's the surname
        new_given = player.given_name
        new_surname = name_parts[0]
    else:
        new_given, new_surname = name_parts
    
    # Update record
    player.given_name = new_given
    player.surname = new_surname
    
    print(f"New name: {player.given_name} {player.surname}")
    
    # Save changes
    output = Path(args.output) if args.output else None
    fdi.save(output_path=output, backup=not args.no_backup)
    
    print("Player renamed successfully!")


def cmd_info(args):
    """Display database information."""
    fdi = FDIFile(args.file)
    fdi.load()
    
    print(f"File: {fdi.path}")
    print(f"Signature: {fdi.header.signature.decode('ascii')}")
    print(f"Version: {fdi.header.version}")
    print(f"Record Count: {fdi.header.record_count}")
    print(f"Max Offset: 0x{fdi.header.max_offset:08x}")
    print(f"Directory Size: 0x{fdi.header.dir_size:04x} ({fdi.header.dir_size} bytes)")
    print(f"Directory Entries: {len(fdi.directory)}")
    print(f"Parsed Players: {len(fdi.records)}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PM99 Database Editor - Modify Premier Manager 99 player databases",
        epilog="Examples:\n"
               "  %(prog)s list DBDAT/JUG98030.FDI\n"
               "  %(prog)s search DBDAT/JUG98030.FDI \"Ronaldo\"\n"
               "  %(prog)s rename DBDAT/JUG98030.FDI --id 123 --name \"Cristiano Ronaldo\"\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True
    
    # List command
    parser_list = subparsers.add_parser('list', help='List all players')
    parser_list.add_argument('file', type=Path, help='FDI file path')
    parser_list.add_argument('--limit', type=int, help='Maximum players to display')
    parser_list.set_defaults(func=cmd_list)
    
    # Search command
    parser_search = subparsers.add_parser('search', help='Search players by name')
    parser_search.add_argument('file', type=Path, help='FDI file path')
    parser_search.add_argument('query', help='Name to search for')
    parser_search.set_defaults(func=cmd_search)
    
    # Rename command
    parser_rename = subparsers.add_parser('rename', help='Rename a player')
    parser_rename.add_argument('file', type=Path, help='FDI file path')
    parser_rename.add_argument('--id', type=int, required=True, help='Player record ID')
    parser_rename.add_argument('--name', required=True, help='New name (e.g. "First Last")')
    parser_rename.add_argument('--output', type=Path, help='Output file (default: overwrite original)')
    parser_rename.add_argument('--no-backup', action='store_true', help='Skip backup creation')
    parser_rename.set_defaults(func=cmd_rename)
    
    # Info command
    parser_info = subparsers.add_parser('info', help='Display database information')
    parser_info.add_argument('file', type=Path, help='FDI file path')
    parser_info.set_defaults(func=cmd_info)
    
    # Parse and execute
    args = parser.parse_args()
    
    try:
        args.func(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()