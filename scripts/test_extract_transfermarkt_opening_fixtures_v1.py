from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extract_transfermarkt_opening_fixtures_v1 as generic
from scripts.extract_2015_world_transfermarkt_opening_fixtures import SourceReceiptError


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def test_load_country_map_is_hash_bound_and_explicit(tmp_path: Path) -> None:
    path = tmp_path / "countries.json"
    document = {
        "schema_version": generic.COUNTRY_MAP_SCHEMA,
        "countries": [
            {"source_country": "England", "country_catalog": "eng"},
            {"source_country": "Spain", "country_catalog": "spain"},
        ],
    }
    _write_canonical(path, document)
    mapping, digest = generic.load_country_map(path)
    assert mapping == {"England": "eng", "Spain": "spain"}
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_country_map_rejects_noncanonical_or_duplicate_rows(tmp_path: Path) -> None:
    path = tmp_path / "countries.json"
    path.write_text('{"schema_version":"pm99-transfermarkt-opening-fixture-country-map-v1", "countries":[]}', encoding="utf-8")
    with pytest.raises(SourceReceiptError, match="canonical JSON"):
        generic.load_country_map(path)

    _write_canonical(path, {
        "schema_version": generic.COUNTRY_MAP_SCHEMA,
        "countries": [
            {"source_country": "England", "country_catalog": "eng"},
            {"source_country": "England", "country_catalog": "england"},
        ],
    })
    with pytest.raises(SourceReceiptError, match="duplicates source country"):
        generic.load_country_map(path)
