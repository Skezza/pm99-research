#!/usr/bin/env python3
"""Apply small cited corrections to a world opening-manager ledger."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import unicodedata
from pathlib import Path


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character.casefold() for character in text if character.isalnum() and not unicodedata.combining(character))


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--overrides", required=True, type=Path)
    parser.add_argument("--output-ledger", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args()
    if any(path.exists() for path in (args.output_ledger, args.output_audit)):
        parser.error("refusing to overwrite an existing output")
    ledger_raw, override_raw = args.ledger.read_bytes(), args.overrides.read_bytes()
    ledger = copy.deepcopy(json.loads(ledger_raw.decode("utf-8")))
    overrides = json.loads(override_raw.decode("utf-8"))
    season = f"{int(ledger['season_start_year']):04d}/{(int(ledger['season_start_year']) + 1) % 100:02d}"
    if overrides.get("schema_version") != "pm99-english-manager-overrides-v1" or overrides.get("season") != season:
        parser.error("override schema or season does not match the ledger")
    rows = {}
    for row in ledger.get("managers") or []:
        selector = row.get("source_selector") if isinstance(row, dict) else None
        club = selector.get("club_name") if isinstance(selector, dict) else None
        if club:
            rows.setdefault(_normalise(club), []).append(row)
    applied = []
    override_sha = hashlib.sha256(override_raw).hexdigest()
    for correction in overrides.get("corrections") or []:
        club = str(correction.get("club") or "")
        candidates = rows.get(_normalise(club), [])
        if len(candidates) != 1:
            parser.error(f"override club is absent or ambiguous: {club}")
        row = candidates[0]
        expected = str(correction.get("expected_incorrect_manager") or "")
        if expected and _normalise(row.get("manager_name")) != _normalise(expected):
            parser.error(f"override is stale for {club}: {row.get('manager_name')!r}")
        manager = str(correction.get("manager_name") or "").strip()
        source_url = str(correction.get("source_url") or "").strip()
        if not manager or not source_url:
            parser.error(f"override is incomplete: {club}")
        previous = row.get("manager_name")
        row["manager_name"] = manager
        row["resolution_method"] = "source-cited-editorial-correction"
        row["evidence"] = {
            "source_name": "reviewed opening-manager correction",
            "source_url": source_url,
            "source_snapshot_sha256": override_sha,
            "reason": str(correction.get("reason") or "reviewed correction"),
        }
        applied.append({"club": club, "before": previous, "after": manager, "source_url": source_url})
    args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
    args.output_ledger.write_bytes(_canonical(ledger))
    audit = {
        "schema_version": "pm99-opening-manager-ledger-override-audit-v1",
        "season": season,
        "input_ledger_sha256": hashlib.sha256(ledger_raw).hexdigest(),
        "overrides_sha256": override_sha,
        "output_ledger_sha256": hashlib.sha256(args.output_ledger.read_bytes()).hexdigest(),
        "applied": applied,
    }
    args.output_audit.write_bytes(_canonical(audit))
    print(json.dumps({"applied_correction_count": len(applied)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
