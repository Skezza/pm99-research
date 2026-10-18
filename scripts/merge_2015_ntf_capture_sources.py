#!/usr/bin/env python3
"""Merge disjoint dated NTF capture batches without reallocating carriers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "pm99-footballsquads-season-capture-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def merge(captures: list[dict[str, Any]]) -> dict[str, Any]:
    clubs: list[dict[str, Any]] = []
    selectors: set[tuple[str, str, str, str, str]] = set()
    carriers: set[int] = set()
    inputs: list[dict[str, Any]] = []
    for capture in captures:
        if capture.get("schema_version") != SCHEMA:
            raise ValueError("all captures must use the canonical squad schema")
        inputs.append({"source_sha256": hashlib.sha256(canonical_bytes(capture)).hexdigest(), "club_count": len(capture.get("clubs", []))})
        for club in capture.get("clubs", []):
            selector = tuple(str(club.get(key) or "") for key in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))
            if not all(selector) or selector in selectors:
                raise ValueError(f"duplicate or incomplete source selector: {selector}")
            selectors.add(selector)
            candidate = club.get("candidate_carrier_id")
            if isinstance(candidate, int) and candidate in carriers:
                raise ValueError(f"candidate carrier appears in more than one capture: {candidate}")
            if isinstance(candidate, int):
                carriers.add(candidate)
            clubs.append(dict(club))
    clubs.sort(key=lambda club: (str(club["country_catalog"]), str(club["club_name"]), str(club["source_path"])))
    return {"schema_version": SCHEMA, "source": {"title": "National Football Teams historical capture batches", "repository": "https://www.national-football-teams.com", "revision": "2015-dated-pages-content-addressed-v1", "license": "public web factual source; URL and content hash retained", "inputs": inputs}, "season": {"catalog": "2015-world-ntf-batches", "label": "2015/16 plus 2015 calendar-year leagues"}, "clubs": clubs, "summary": {"club_count": len(clubs), "player_count": sum(len(c.get("players") or []) for c in clubs), "candidate_carrier_count": len(carriers)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    captures = [json.loads(path.read_text(encoding="utf-8")) for path in args.capture]
    result = merge(captures)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
