"""Debug utility — eagerly loads PM99 FDI/PKF files into memory and prints a summary.

Usage:
    python scripts/debug_eager_load.py --db-root DBDAT --max-bytes 200000000
"""
import argparse
import logging
import sys
from pathlib import Path
from pm99_editor.datastore import DataStore

LOG_FORMAT = "%(levelname)s: %(message)s"


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Eager-load PM99 DB files and print summary")
    parser.add_argument("--db-root", help="Path to DB root (overrides PM99_DB_ROOT env)", default=None)
    parser.add_argument("--max-bytes", type=int, help="Eager load byte cap (overrides PM99_EAGER_MAX_BYTES env)", default=None)
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT)

    try:
        ds = DataStore(db_root=args.db_root, eager_max_bytes=args.max_bytes)
    except Exception as e:
        logging.error("Failed to resolve DB root: %s", e)
        sys.exit(2)

    try:
        ds.load_all()
    except MemoryError as me:
        logging.error("Memory cap reached during eager load: %s", me)
    except Exception as e:
        logging.exception("Unexpected error during eager load: %s", e)

    num_files, total = ds.summary()
    print(f"Loaded {num_files} files, total {total} bytes ({human_bytes(total)}) from {ds.db_root}")

    # counts per extension
    counts = {}
    for k in ds.keys():
        ext = Path(k).suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1
    for ext, cnt in sorted(counts.items(), key=lambda x: x[0]):
        print(f"{ext}: {cnt}")

    print("\nTop largest files:")
    for k, size in ds.top_n_largest(10):
        print(f" - {k}: {size} bytes ({human_bytes(size)})")


if __name__ == "__main__":
    main()