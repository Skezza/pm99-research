#!/usr/bin/env python3
"""CLI wrapper for bulk player rename reversion (Milestone 1)."""

import argparse

from app.bulk_rename import revert_player_file, revert_player_renames

# Backwards-compatible alias for earlier test/import callers.
revert_file = revert_player_file


def main():
    parser = argparse.ArgumentParser(description="Revert PM99 bulk player renames from a mapping CSV.")
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to directory containing JUG*.FDI player database files.",
    )
    parser.add_argument(
        "--map-input",
        required=True,
        help="Path to the mapping CSV produced by bulk_rename_players.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the mapping against current data without writing changes.",
    )
    parser.add_argument(
        "--skip-integrity-checks",
        action="store_true",
        help="Skip additional mapping consistency checks.",
    )
    args = parser.parse_args()
    revert_player_renames(
        data_dir=args.data_dir,
        map_input=args.map_input,
        dry_run=args.dry_run,
        integrity_checks=not args.skip_integrity_checks,
    )


if __name__ == "__main__":
    main()
