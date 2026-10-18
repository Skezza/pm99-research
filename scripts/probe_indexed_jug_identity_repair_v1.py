#!/usr/bin/env python3
"""Create a bounded, unregistered identity repair; preserve all other bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "upstream/pm99-skezmod-db-editor"))
from app.indexed_jug_identity import repair_indexed_player_identities as repair


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(ROOT / ".local/crash04-diagnostics-v1"):
        parser.error("requires fresh diagnostic output")
    source = (args.dbdat / "JUG98030.FDI").read_bytes()
    candidate, rows = repair(source)
    args.output.mkdir(parents=True)
    for file in args.dbdat.iterdir():
        if file.is_file() and file.name != "JUG98030.FDI":
            (args.output / file.name).hardlink_to(file)
    (args.output / "JUG98030.FDI").write_bytes(candidate)
    receipt = {"diagnostic_only": True, "before_sha256": hashlib.sha256(source).hexdigest(),
               "after_sha256": hashlib.sha256(candidate).hexdigest(), "repaired": rows}
    (args.output.parent / "identity-repair.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"count": len(rows), "after_sha256": receipt["after_sha256"]}))
