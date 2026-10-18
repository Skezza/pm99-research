from __future__ import annotations

import json

import pytest

from scripts.capture_ntf_historical_carrier_squads_v1 import Cache, canonical_player


def test_canonical_player_turns_unknown_nationality_into_explicit_gap() -> None:
    row = {"shirt_number": None, "name": "Player", "nationality": "UNK", "position": "M",
           "height_cm": None, "weight_kg": None, "birth_date": "1978-01-02",
           "unresolved_fields": ["nationality_code"]}
    result = canonical_player(row)
    assert result["nationality"] is None
    assert result["unresolved_fields"] == ["shirt_number", "nationality", "height_cm", "weight_kg"]


def test_cache_never_reuses_bytes_for_a_different_url(tmp_path) -> None:
    path = tmp_path / "index/example.html"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old source")
    receipt = {"sha256": __import__("hashlib").sha256(b"old source").hexdigest(), "url": "https://example.test/old"}
    path.with_suffix(".html.source.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="URL-bound snapshot missing"):
        Cache(tmp_path, offline=True, delay=0).get("https://example.test/new", "index/example.html")
