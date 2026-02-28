#!/usr/bin/env python3
"""CLI wrapper for deterministic bulk player rename (Milestone 1)."""

import argparse

from app.bulk_rename import (
    MAPPING_FIELDNAMES,
    bulk_rename_players,
    compute_new_name,
    get_display_name,
    process_player_file,
)

# Backwards-compatible alias for earlier test/import callers.
process_file = process_player_file


def main():
    parser = argparse.ArgumentParser(description="Bulk rename PM99 players deterministically.")
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to directory containing JUG*.FDI player database files.",
    )
    parser.add_argument(
        "--map-output",
        required=True,
        help="Path to write the rename mapping CSV.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and write the mapping CSV without modifying any FDI files.",
    )
    parser.add_argument(
        "--skip-integrity-checks",
        action="store_true",
        help="Skip additional mapping consistency checks.",
    )
    args = parser.parse_args()
    bulk_rename_players(
        data_dir=args.data_dir,
        map_output=args.map_output,
        dry_run=args.dry_run,
        integrity_checks=not args.skip_integrity_checks,
    )


if __name__ == "__main__":
    main()
