#!/usr/bin/env python3
"""Capture the published FIFA 16 FUT player-id index used for dated faces."""

from __future__ import annotations

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
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = storage_io.resolve(Path(__file__)).parents[1]
SOURCE_URL = (
    "https://fifa15.content.easports.com/fifa/fltOnlineAssets/"
    "B488919F-23B5-497F-9FC0-CACFB38863D0/2016/fut/items/web/players.json"
)
DEFAULT_OUTPUT = ROOT / ".local/season-2015-16/fifa16-ea-player-meta.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    request = Request(SOURCE_URL, headers={"User-Agent": "pm99-research/2015-16-source-capture"})
    with urlopen(request, timeout=60) as response:
        raw = response.read()
    decoded = json.loads(raw)
    rows = list(decoded.get("Players") or [])
    if len(rows) < 10_000 or not all(isinstance(row, dict) and row.get("id") for row in rows):
        raise RuntimeError("FIFA 16 FUT metadata response was not a complete player index")
    output = {
        "schema_version": "pm99-fifa16-fut-player-meta-v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "source_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "players": [{key: row.get(key) for key in ("id", "r", "f", "l", "c")} for row in rows],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_text(args.output, json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({"output": str(args.output), "players": len(rows), "source_sha256": output["source_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
