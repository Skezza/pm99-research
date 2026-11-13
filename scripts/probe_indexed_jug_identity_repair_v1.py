#!/usr/bin/env python3
"""Create a bounded, unregistered identity repair; preserve all other bytes."""
try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = storage_io.resolve(Path(__file__)).parents[1]
sys.path.insert(0, str(ROOT / "upstream/pm99-skezmod-db-editor"))
from app.indexed_jug_identity import repair_indexed_player_identities as repair


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if storage_io.exists(args.output) or not storage_io.resolve(args.output).is_relative_to(ROOT / ".local/crash04-diagnostics-v1"):
        parser.error("requires fresh diagnostic output")
    source = storage_io.read_bytes(args.dbdat / 'JUG98030.FDI')
    candidate, rows = repair(source)
    args.output.mkdir(parents=True)
    for file in args.dbdat.iterdir():
        if storage_io.is_file(file) and file.name != "JUG98030.FDI":
            (args.output / file.name).hardlink_to(file)
    storage_io.write_bytes(args.output / 'JUG98030.FDI', candidate)
    receipt = {"diagnostic_only": True, "before_sha256": hashlib.sha256(source).hexdigest(),
               "after_sha256": hashlib.sha256(candidate).hexdigest(), "repaired": rows}
    storage_io.write_text(args.output.parent / 'identity-repair.json', json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({"count": len(rows), "after_sha256": receipt["after_sha256"]}))
