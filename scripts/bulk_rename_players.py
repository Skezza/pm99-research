#!/usr/bin/env python3
"""
Bulk rename players in all JUG*.FDI files for Premier Manager 99.

This script performs a deterministic, length‑preserving rename of every player
record in the specified data directory. A mapping CSV is produced to allow
reversion of the changes.

Usage:
    python bulk_rename_players.py --data-dir DBDAT --map-output rename_map.csv
"""

import argparse
import csv
from pathlib import Path

from app.io import FDIFile


def compute_new_name(index: int, length: int) -> str:
    """
    Compute a deterministic token for the given record index and desired length.
    Tokens begin with 'Z' followed by zero‑padded digits of the index.
    If the token is longer than the desired length it is truncated; if shorter
    it is padded with 'Z'.
    """
    token = f"Z{index:08d}"
    if len(token) >= length:
        return token[:length]
    return token.ljust(length, 'Z')


def process_file(file_path: Path, rows: list):
    fdi = FDIFile(str(file_path))
    fdi.load()
    players = fdi.list_players()
    for idx, (offset, rec) in enumerate(players):
        # Determine original name
        orig_name = getattr(rec, 'name', '') or (
            f"{getattr(rec, 'given_name', '')} {getattr(rec, 'surname', '')}".strip()
        )
        if not orig_name:
            continue
        new_name = compute_new_name(idx, len(orig_name))
        if new_name == orig_name:
            continue
        # Mutate record
        rec.name = new_name
        setattr(rec, 'name_dirty', True)
        # Track modification
        fdi.modified_records[offset] = rec
        rows.append({
            'record_index': idx,
            'team_id': rec.team_id,
            'squad_no': rec.squad_number,
            'original_name': orig_name,
            'new_name': new_name,
            'file': file_path.name,
        })
    # Write back changes
    if fdi.modified_records:
        fdi.save()


def main():
    parser = argparse.ArgumentParser(description="Bulk rename PM99 players deterministically.")
    parser.add_argument(
        '--data-dir',
        required=True,
        help='Path to directory containing JUG*.FDI player database files.'
    )
    parser.add_argument(
        '--map-output',
        required=True,
        help='Path to write the rename mapping CSV.'
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        raise SystemExit(f"Not a directory: {data_dir}")
    rows = []
    # Process each JUG*.FDI file deterministically
    for f in sorted(data_dir.glob('JUG*.FDI')):
        process_file(f, rows)
    # Write mapping CSV
    out_path = Path(args.map_output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=['record_index','team_id','squad_no','original_name','new_name','file']
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
