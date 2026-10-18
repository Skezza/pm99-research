from __future__ import annotations

from scripts.materialise_english_opening_manager_layers_v1 import materialise as materialise_opening
from scripts.materialise_english_rating_layer_v1 import materialise
from scripts.season_english_fixed_carrier_authoring_v1 import build_authoring
from scripts.test_materialise_english_opening_manager_layers_v1 import _evidence_documents, _sha


def test_rating_adapter_passes_full_english_authoring_gate() -> None:
    preallocation, reconciliation, managers, selector_map, kits, _ = _evidence_documents()
    openings, manager_layer, _ = materialise_opening(
        preallocation=preallocation, preallocation_sha256=_sha(preallocation),
        reconciliation=reconciliation, reconciliation_sha256=_sha(reconciliation),
        managers=managers, managers_sha256=_sha(managers),
    )
    ratings, rating_audit = materialise(preallocation=preallocation, preallocation_sha256=_sha(preallocation))
    assert rating_audit["coverage"]["english_club_count"] == 92
    assert rating_audit["coverage"]["rated_player_count"] == 1840
    assert rating_audit["coverage"]["missing_primary_position_count"] == 0
    assert max(value for row in ratings["rows"] for player in row["players"] for value in player["ratings"].values()) > 20
    audit, compiler_input = build_authoring(
        source=preallocation, selector_map=selector_map, openings=openings,
        managers=manager_layer, kits=kits, ratings=ratings,
    )
    assert audit["status"] == "compiler-input-ready"
    assert compiler_input is not None


def test_missing_primary_position_remains_explicit() -> None:
    preallocation, *_ = _evidence_documents()
    player = preallocation["source_clubs"][0]["players"][0]
    player["facts"]["position"] = None
    ratings, audit = materialise(preallocation=preallocation, preallocation_sha256=_sha(preallocation))
    assert audit["coverage"]["missing_primary_position_count"] == 1
    assert audit["gaps"][0]["reason"] == "primary-position-required-for-editorial-rating"
    club_name = preallocation["source_clubs"][0]["selector"]["club_name"]
    row = next(row for row in ratings["rows"] if row["club"] == club_name)
    assert len(row["players"]) == 19
