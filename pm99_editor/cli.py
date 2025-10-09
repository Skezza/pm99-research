"""
Command-line interface for Premier Manager 99 Database Editor
"""

import argparse
from .io import FDIFile
from .models import PlayerRecord
from .file_writer import save_modified_records

def cmd_info(args):
    """Display file information"""
    fdi = FDIFile(args.file)
    fdi.load()
    print(f"File: {args.file}")
    print(f"Records: {len(fdi.records)}")
    print(f"Header: {fdi.header}")

def cmd_list(args):
    """List players"""
    fdi = FDIFile(args.file)
    fdi.load()
    records = fdi.list_players(args.limit)
    for offset, record in records:
        print(f"{offset}: {record.name} ({record.team_id})")

def cmd_search(args):
    """Search players by name"""
    fdi = FDIFile(args.file)
    fdi.load()
    matches = fdi.find_by_name(args.name)
    for offset, record in matches:
        print(f"{offset}: {record.name} ({record.team_id})")

def cmd_rename(args):
    """Rename player by ID"""
    fdi = FDIFile(args.file)
    fdi.load()
    record = fdi.find_by_id(args.id)
    if record:
        record.name = args.name
        fdi.modified_records[args.id] = record
        fdi.save()
        print(f"Renamed player {args.id} to {args.name}")
    else:
        print(f"Player {args.id} not found")

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Premier Manager 99 Database Editor")
    subparsers = parser.add_subparsers(dest="command")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Display file information")
    info_parser.add_argument("file", help="FDI file path")
    info_parser.set_defaults(func=cmd_info)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List players")
    list_parser.add_argument("file", help="FDI file path")
    list_parser.add_argument("--limit", type=int, help="Maximum records to list")
    list_parser.set_defaults(func=cmd_list)
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search players by name")
    search_parser.add_argument("file", help="FDI file path")
    search_parser.add_argument("name", help="Name to search for")
    search_parser.set_defaults(func=cmd_search)
    
    # Rename command
    rename_parser = subparsers.add_parser("rename", help="Rename player by ID")
    rename_parser.add_argument("file", help="FDI file path")
    rename_parser.add_argument("--id", type=int, required=True, help="Player ID")
    rename_parser.add_argument("--name", required=True, help="New name")
    rename_parser.set_defaults(func=cmd_rename)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()