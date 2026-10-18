from __future__ import annotations

import pytest

from scripts.promote_historical_squad_capture_v1 import _without_capture_clubs


def club(name: str, source_hash: str) -> dict[str, object]:
    return {
        "club_name": name,
        "competition_catalog": "league",
        "country_catalog": "country",
        "players": [],
        "source_path": f"provider/{name}",
        "source_sha256": source_hash,
    }


def test_without_capture_clubs_removes_only_exact_bound_selectors() -> None:
    old = club("Same Name", "old")
    other_provider = club("Same Name", "other")
    survivor = club("Survivor", "survivor")
    source = {"clubs": [old, other_provider, survivor], "schema_version": "capture"}

    result = _without_capture_clubs(source, {"clubs": [old]})

    assert result["clubs"] == [other_provider, survivor]
    assert source["clubs"] == [old, other_provider, survivor]


def test_without_capture_clubs_refuses_unbound_replacement() -> None:
    with pytest.raises(ValueError, match="1 source selectors are absent"):
        _without_capture_clubs({"clubs": [club("Existing", "one")]}, {"clubs": [club("Missing", "two")]})
