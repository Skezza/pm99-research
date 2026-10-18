#!/usr/bin/env python3
"""Fetch a provenance-recorded FIFA 17 backfill for 2015/16 identity gaps.

FIFA 16 remains the season baseline.  This file exists only for people who
were not represented in FIFA 16's release data (principally lower-league and
academy players), but do appear in FIFA 17.  It gives a close-era EA/SoFIFA id
and individual attributes without mislabelling the result as FIFA 16 data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import requests


SOURCE_URL_TEMPLATE = "https://raw.githubusercontent.com/AMRYB/FIFA-Dashboard/main/players_{edition}.csv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", type=int, default=17, choices=(15, 17, 18, 19, 20))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    values = parser.parse_args()

    output = values.output or Path(f".local/season-2015-16/fifa{values.edition}-sofifa-backfill.csv")
    receipt_path = values.receipt or Path(f".local/season-2015-16/fifa{values.edition}-sofifa-backfill-receipt.json")
    source_url = SOURCE_URL_TEMPLATE.format(edition=values.edition)

    response = requests.get(source_url, timeout=60)
    response.raise_for_status()
    raw = response.content
    rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    required = {"sofifa_id", "short_name", "dob", "overall", "club", "player_positions"}
    observed = set(rows[0]) if rows else set()
    if len(rows) < 15_000 or not required <= observed:
        raise SystemExit(f"unexpected FIFA 17 source shape: rows={len(rows)} missing={sorted(required - observed)}")
    if not all(str(row.get("sofifa_id") or "").strip().isdigit() for row in rows[:100]):
        raise SystemExit("FIFA 17 source does not have numeric player ids")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    receipt = {
        "schema": "pm99-fifa-close-era-backfill-v1",
        "edition": values.edition,
        "purpose": "close-era identity/attribute backfill only where FIFA 16 has no safe record",
        "source_url": source_url,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(rows),
        "columns": list(rows[0]),
        "output": str(output.resolve()),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
