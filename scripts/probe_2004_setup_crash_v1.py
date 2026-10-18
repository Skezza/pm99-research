#!/usr/bin/env python3
"""Create small, unregistered controls for the 2004/05 setup failure.

Never edits a source game. Mixed-year controls are not playable releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "upstream/pm99-skezmod-db-editor")]
from app.fdi_indexed import IndexedFDIFile
from scripts.season_package_compiler_v2 import _append_indexed_fdi_records, _rebuild_indexed, _source_roster_owners


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("players03", "clubs03", "clubs-subset03", "calendar-half", "may8-weekdays", "fixture-weekdays", "revert-day-override"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int, default=427)
    parser.add_argument("--addresses", nargs="*", help="Optional exact year-operand addresses to correct")
    parser.add_argument("--club-mode", type=int, choices=(0, 1))
    parser.add_argument("--added-player-ids", nargs="*", type=int)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("output must not already exist")
    if not out.is_relative_to(ROOT / ".local/crash04-diagnostics-v1"):
        parser.error("output must be within the local crash diagnostic directory")
    roots = {s: ROOT / f".local/season-runtime-candidates-v1/{s}/rc-quality-20260913-r1/game"
             for s in ("2003-04", "2004-05")}
    receipt = {"diagnostic_only": True, "mode": args.mode, "output": str(out)}
    if args.mode in ("clubs03", "clubs-subset03"):
        previous_eq = (roots["2003-04"] / "DBDAT/EQ98030.FDI").read_bytes()
        eq = previous_eq
        if args.mode == "clubs-subset03":
            eq = (roots["2004-05"] / "DBDAT/EQ98030.FDI").read_bytes()
            indexed = IndexedFDIFile.from_bytes(eq)
            old_eq_entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(previous_eq).entries}
            _, _, modes = _source_roster_owners(eq)
            ids = sorted(entry.record_id for entry in indexed.entries
                         if args.club_mode is None or modes.get(entry.record_id) == args.club_mode)
            ids = ids[args.first:args.last]
            eq = _rebuild_indexed(eq, indexed, {pid: old_eq_entries[pid].decode_payload(previous_eq) for pid in ids})
            receipt["replaced_club_ids"] = ids
        jug = (roots["2004-05"] / "DBDAT/JUG98030.FDI").read_bytes()
        previous = (roots["2003-04"] / "DBDAT/JUG98030.FDI").read_bytes()
        old_entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(previous).entries}
        ids = {entry.record_id for entry in IndexedFDIFile.from_bytes(jug).entries}
        # Include the complete small missing-ID set so every subsequent subset
        # control has the same JUG file and differs only in its EQ payloads.
        owners, _, _ = _source_roster_owners(previous_eq)
        missing = sorted(set(owners) - ids)
        if args.added_player_ids is not None:
            missing = args.added_player_ids
        jug = _append_indexed_fdi_records(original=jug, records=[
            (pid, old_entries[pid].key, old_entries[pid].decode_payload(previous)) for pid in missing])
        candidate_owners, _, _ = _source_roster_owners(eq)
        if set(candidate_owners) - {entry.record_id for entry in IndexedFDIFile.from_bytes(jug).entries}:
            raise ValueError("control loses an active roster player")
        out.mkdir(parents=True)
        for name in ("ENT98030.FDI", "MINIFOTO.PKF", "BIGCAMP.PKF", "BIGESC.PKF",
                     "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
            (out / name).hardlink_to(roots["2004-05"] / "DBDAT" / name)
        (out / "EQ98030.FDI").write_bytes(eq)
        (out / "JUG98030.FDI").write_bytes(jug)
        candidate = eq
        receipt["added_missing_player_ids"] = missing
        receipt["player_file_sha256"] = hashlib.sha256(jug).hexdigest()
    elif args.mode == "players03":
        current = (roots["2004-05"] / "DBDAT/JUG98030.FDI").read_bytes()
        previous = (roots["2003-04"] / "DBDAT/JUG98030.FDI").read_bytes()
        old_entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(previous).entries}
        indexed = IndexedFDIFile.from_bytes(current)
        replacements = {entry.record_id: old_entries[entry.record_id].decode_payload(previous)
                        for entry in indexed.entries if entry.record_id in old_entries}
        candidate = _rebuild_indexed(current, indexed, replacements)
        owners, _, _ = _source_roster_owners((roots["2004-05"] / "DBDAT/EQ98030.FDI").read_bytes())
        ids = {entry.record_id for entry in IndexedFDIFile.from_bytes(candidate).entries}
        if set(owners) - ids:
            raise ValueError("control loses an active roster player")
        out.mkdir(parents=True)
        for name in ("EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF", "BIGCAMP.PKF",
                     "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
            (out / name).hardlink_to(roots["2004-05"] / "DBDAT" / name)
        (out / "JUG98030.FDI").write_bytes(candidate)
        receipt["replaced_player_count"] = len(replacements)
    elif args.mode == "calendar-half":
        receipt_path = ROOT / ".local/calendar-v1/2004-05/calendar-receipt.json"
        patches = json.loads(receipt_path.read_text())["patches"]
        if not 0 <= args.first < args.last <= len(patches):
            raise ValueError("invalid calendar operand range")
        candidate = bytearray((roots["2003-04"] / "MANAGPRE.EXE").read_bytes())
        good = bytes(candidate)
        bad = (roots["2004-05"] / "MANAGPRE.EXE").read_bytes()
        for patch in patches[args.first:args.last]:
            offset = int(patch["file_offset"], 16)
            count = len(bytes.fromhex(patch["after"]))
            candidate[offset:offset + count] = bad[offset:offset + count]
            if patch["instruction_va"] == "0x004EFE73":
                candidate[offset + 7] = bad[offset + 7]
        out.mkdir(parents=True)
        candidate = bytes(candidate)
        (out / "MANAGPRE.EXE").write_bytes(candidate)
        receipt.update(first=args.first, last=args.last, total=len(patches),
                       changed_byte_count=sum(a != b for a, b in zip(good, candidate)))
    elif args.mode == "revert-day-override":
        patches = json.loads((ROOT / ".local/calendar-v1/2004-05/calendar-receipt.json").read_text())["patches"]
        patch = next(row for row in patches if row["instruction_va"] == "0x004EFE73")
        candidate = bytearray((roots["2004-05"] / "MANAGPRE.EXE").read_bytes())
        offset = int(patch["file_offset"], 16)
        if candidate[offset:offset + 8] != bytes.fromhex("d5 07 00 00 6a 05 6a 07"):
            raise ValueError("unexpected single-day calendar correction")
        candidate[offset + 7] = 8
        out.mkdir(parents=True)
        candidate = bytes(candidate)
        (out / "MANAGPRE.EXE").write_bytes(candidate)
        receipt["restored_day_literal_va"] = "0x004EFE7A"
    elif args.mode == "fixture-weekdays":
        patches = json.loads((ROOT / ".local/calendar-v1/2004-05/calendar-receipt.json").read_text())["patches"]
        candidate = bytearray((roots["2004-05"] / "MANAGPRE.EXE").read_bytes())
        changes = []
        for patch in patches:
            offset = int(patch["file_offset"], 16)
            # Fingerprinted rollover date constructor followed by fixture
            # insertion, not an opening clock, DOB or arbitrary scalar.
            window = candidate[offset:offset + 50]
            if (patch["before"] != "cf 07 00 00" or candidate[offset - 1] != 0x68
                    or window[4] != 0x6a or window[6] != 0x6a):
                continue
            month, day = window[5], window[7]
            try:
                source_day = 8 if patch["instruction_va"] == "0x004EFE73" else day
                source = datetime.date(1999, month, source_day)
                target = datetime.date(2005, month, source_day)
            except ValueError:
                continue
            options = []
            for delta in range(-6, 7):
                possible = target + datetime.timedelta(days=delta)
                if possible.year == 2005 and possible.month == month and possible.weekday() == source.weekday():
                    options.append((abs(delta), delta, possible.day))
            after_day = min(options)[2]
            if after_day != day:
                candidate[offset + 7] = after_day
                changes.append({"va": patch["instruction_va"], "month": month, "before": day, "after": after_day})
        out.mkdir(parents=True)
        candidate = bytes(candidate)
        (out / "MANAGPRE.EXE").write_bytes(candidate)
        receipt["fixture_weekday_changes"] = changes
    else:
        patches = json.loads((ROOT / ".local/calendar-v1/2004-05/calendar-receipt.json").read_text())["patches"]
        candidate = bytearray((roots["2004-05"] / "MANAGPRE.EXE").read_bytes())
        changes = []
        for patch in patches:
            if args.addresses is not None and patch["instruction_va"] not in args.addresses:
                continue
            offset = int(patch["file_offset"], 16)
            if candidate[offset:offset + 8] == bytes.fromhex("d5 07 00 00 6a 05 6a 08"):
                candidate[offset + 7] = 7
                changes.append(patch["instruction_va"])
        if args.addresses is not None and set(changes) != set(args.addresses):
            raise ValueError("requested date literal is not a verified 8 May 2005")
        if not changes:
            raise ValueError("no date changes")
        out.mkdir(parents=True)
        candidate = bytes(candidate)
        (out / "MANAGPRE.EXE").write_bytes(candidate)
        receipt["day_literal_changes"] = changes
    receipt["candidate_sha256"] = hashlib.sha256(candidate).hexdigest()
    (out / "diagnostic.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
