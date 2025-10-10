"""
Command-line interface for Premier Manager 99 Database Editor
"""

import argparse
import sys
from pathlib import Path
from .io import FDIFile
from .models import PlayerRecord
from .file_writer import save_modified_records
from .pkf_searcher import PKFSearcher

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

def cmd_pkf_search(args):
    """Search for strings/patterns across PKF files"""
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"Error: Directory '{directory}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Create searcher
    searcher = PKFSearcher(
        directory=directory,
        recursive=not args.no_recursive,
        file_pattern=args.file_pattern,
        max_results=args.limit,
        context_size=args.context,
    )
    
    # Find PKF files
    pkf_files = searcher.find_pkf_files()
    if not pkf_files:
        print(f"No PKF files found in {directory}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Searching in: {directory}")
    print(f"Found {len(pkf_files)} PKF file(s)")
    print(f"Pattern: {args.query}")
    print()
    
    # Perform search based on mode
    try:
        if args.mode == "hex":
            results = searcher.search_hex(args.query, use_parallel=not args.no_parallel)
        elif args.mode == "regex":
            results = searcher.search_regex(args.query, encoding=args.encoding, use_parallel=not args.no_parallel)
        elif args.xor is not None:
            xor_key = int(args.xor, 16) if args.xor.startswith('0x') else int(args.xor)
            results = searcher.search_with_xor(args.query, xor_key, encoding=args.encoding, use_parallel=not args.no_parallel)
        else:
            results = searcher.search_text(args.query, case_sensitive=args.case_sensitive,
                                          encoding=args.encoding, use_parallel=not args.no_parallel)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Display results
    if not results:
        print("No matches found.")
        return
    
    print(f"Found {len(results)} match(es) across {len(set(r.file_path for r in results))} file(s):\n")
    
    # Group results by file
    by_file = {}
    for result in results:
        if result.file_path not in by_file:
            by_file[result.file_path] = []
        by_file[result.file_path].append(result)
    
    # Display grouped results
    for file_path, file_results in by_file.items():
        print(f"File: {file_path.relative_to(directory) if file_path.is_relative_to(directory) else file_path}")
        
        for result in file_results:
            print(f"  Entry {result.entry_index} @ 0x{result.entry_offset:08X} (offset in entry: 0x{result.match_offset:04X}):")
            
            # Show hex preview
            preview = result.format_preview(width=16)
            for line in preview.split('\n'):
                print(f"    {line}")
            
            # Show decoded text if applicable
            if result.encoding and result.encoding != "raw":
                try:
                    text = result.get_match_text(result.encoding)
                    if text and not text.startswith("<binary"):
                        print(f"    Text: {text}")
                except Exception:
                    pass
            
            print()
    
    # Export if requested
    if args.export:
        export_path = Path(args.export)
        if export_path.suffix.lower() == '.json':
            _export_json(results, export_path, directory)
        else:
            _export_csv(results, export_path, directory)
        print(f"Results exported to: {export_path}")

def _export_csv(results, output_path, base_dir):
    """Export results to CSV format"""
    import csv
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['File', 'Entry', 'Entry Offset', 'Match Offset', 'Absolute Offset',
                        'Match (Hex)', 'Match (Text)', 'Encoding', 'XOR Key'])
        
        for result in results:
            rel_path = result.file_path.relative_to(base_dir) if result.file_path.is_relative_to(base_dir) else result.file_path
            match_text = result.get_match_text(result.encoding or 'utf-8')
            
            writer.writerow([
                str(rel_path),
                result.entry_index,
                f"0x{result.entry_offset:08X}",
                f"0x{result.match_offset:04X}",
                f"0x{result.absolute_offset:08X}",
                result.match_bytes.hex(),
                match_text,
                result.encoding or '',
                f"0x{result.xor_key:02X}" if result.xor_key is not None else '',
            ])

def _export_json(results, output_path, base_dir):
    """Export results to JSON format"""
    import json
    
    data = []
    for result in results:
        rel_path = result.file_path.relative_to(base_dir) if result.file_path.is_relative_to(base_dir) else result.file_path
        
        data.append({
            'file': str(rel_path),
            'entry_index': result.entry_index,
            'entry_offset': f"0x{result.entry_offset:08X}",
            'match_offset': f"0x{result.match_offset:04X}",
            'absolute_offset': f"0x{result.absolute_offset:08X}",
            'match_hex': result.match_bytes.hex(),
            'match_text': result.get_match_text(result.encoding or 'utf-8'),
            'context_before_hex': result.context_before.hex(),
            'context_after_hex': result.context_after.hex(),
            'encoding': result.encoding,
            'xor_key': f"0x{result.xor_key:02X}" if result.xor_key is not None else None,
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'results': data, 'total': len(data)}, f, indent=2)

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
    
    # PKF Search command
    pkf_search_parser = subparsers.add_parser("pkf-search", help="Search for strings/patterns in PKF files")
    pkf_search_parser.add_argument("directory", help="Directory containing PKF files")
    pkf_search_parser.add_argument("query", help="Search query (text, regex, or hex)")
    pkf_search_parser.add_argument("--mode", choices=["text", "regex", "hex"], default="text",
                                   help="Search mode (default: text)")
    pkf_search_parser.add_argument("--encoding", default="utf-8",
                                   choices=["utf-8", "cp1252", "latin1", "raw"],
                                   help="Text encoding (default: utf-8)")
    pkf_search_parser.add_argument("--case-sensitive", action="store_true",
                                   help="Enable case-sensitive search")
    pkf_search_parser.add_argument("--xor", metavar="KEY",
                                   help="XOR key for decoding (hex or decimal)")
    pkf_search_parser.add_argument("--context", type=int, default=32,
                                   help="Context bytes before/after match (default: 32)")
    pkf_search_parser.add_argument("--no-recursive", action="store_true",
                                   help="Don't search subdirectories")
    pkf_search_parser.add_argument("--file-pattern", default="*.pkf",
                                   help="PKF file pattern (default: *.pkf)")
    pkf_search_parser.add_argument("--limit", type=int, default=1000,
                                   help="Maximum results (default: 1000)")
    pkf_search_parser.add_argument("--export", metavar="FILE",
                                   help="Export results to CSV or JSON file")
    pkf_search_parser.add_argument("--no-parallel", action="store_true",
                                   help="Disable parallel processing")
    pkf_search_parser.set_defaults(func=cmd_pkf_search)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()