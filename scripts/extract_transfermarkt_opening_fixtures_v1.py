#!/usr/bin/env python3
"""Create a hash-bound first-domestic-fixture receipt for any declared season.

This is the reusable form of the 2015/16 opening-fixture extractor.  Given a
local, immutable Transfermarkt-derived DuckDB snapshot and a reviewable
country mapping, it records the earliest domestic-league match for every club
in scope, with its published XI, bench, declared formation, manager and
match-stadium fact.  It is a source receipt only: it makes no PM99 carrier,
player-slot, rating, kit, portrait or topology decision.

The country map is deliberately a canonical JSON document, not command-line
country text.  That binds a receipt to the exact source-country to PM99
catalogue decision and makes an incomplete all-country run visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extract_2015_world_transfermarkt_opening_fixtures as extractor  # noqa: E402


COUNTRY_MAP_SCHEMA = "pm99-transfermarkt-opening-fixture-country-map-v1"


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_country_map(path: Path) -> tuple[dict[str, str], str]:
    """Load an exact, canonical country scope and return it with its hash."""

    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise extractor.SourceReceiptError(f"cannot read country map: {path}") from exc
    if not isinstance(document, dict) or raw != _canonical_json_bytes(document):
        raise extractor.SourceReceiptError("country map must be canonical JSON")
    if document.get("schema_version") != COUNTRY_MAP_SCHEMA:
        raise extractor.SourceReceiptError(f"country map must have schema {COUNTRY_MAP_SCHEMA}")
    rows = document.get("countries")
    if not isinstance(rows, list) or not rows:
        raise extractor.SourceReceiptError("country map must have a non-empty countries list")
    mapping: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"country_catalog", "source_country"}:
            raise extractor.SourceReceiptError("each country map row must contain only source_country and country_catalog")
        source_country = row["source_country"]
        country_catalog = row["country_catalog"]
        if not isinstance(source_country, str) or not isinstance(country_catalog, str):
            raise extractor.SourceReceiptError("country map names must be strings")
        if source_country in mapping:
            raise extractor.SourceReceiptError(f"country map duplicates source country {source_country!r}")
        mapping[source_country] = country_catalog
    return extractor.validate_country_mapping(mapping), hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="local Transfermarkt-derived DuckDB snapshot")
    parser.add_argument("--season", required=True, help="start year in the source snapshot, e.g. 2000")
    parser.add_argument("--country-map", required=True, type=Path, help="canonical explicit country-scope JSON")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        country_mapping, country_map_sha256 = load_country_map(args.country_map)
        receipt = extractor.extract_receipt(
            database=args.database,
            season=args.season,
            country_mapping=country_mapping,
            schema_version=extractor.GENERIC_SCHEMA,
        )
    except (OSError, extractor.SourceReceiptError) as exc:
        parser.error(str(exc))
    receipt["source"]["country_map"] = {
        "path": str(args.country_map),
        "sha256": country_map_sha256,
        "schema_version": COUNTRY_MAP_SCHEMA,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(receipt))
    print(json.dumps(receipt["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
