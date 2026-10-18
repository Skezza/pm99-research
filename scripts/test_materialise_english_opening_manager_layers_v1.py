from __future__ import annotations

import hashlib

import pytest

from scripts.materialise_english_opening_manager_layers_v1 import (
    LayerAdapterError,
    canonical_json_bytes,
    materialise,
)
from scripts.season_english_fixed_carrier_authoring_v1 import build_authoring
from scripts.test_season_english_fixed_carrier_authoring_v1 import _documents


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _evidence_documents():
    source, selector_map, _, _, kits, ratings = _documents()
    lineup_sha = "1" * 64
    reconciliation_clubs = []
    preallocation_clubs = []
    manager_rows = []
    for source_club in source["clubs"]:
        selector = {
            "country_catalog": source_club["country_catalog"],
            "competition_catalog": source_club["competition_catalog"],
            "club_name": source_club["club_name"],
            "source_path": source_club["source_path"],
            "source_sha256": source_club["source_sha256"],
        }
        players = []
        for order, facts in enumerate(source_club["players"]):
            row_hash = hashlib.sha256(f"{source_club['club_name']}|{order}".encode()).hexdigest()
            row = {"source_row_index": order, "source_row_sha256": row_hash, "facts": facts}
            if order < 11:
                row["opening_xi_order"] = order + 1
            players.append(row)
        preallocation_clubs.append({
            "selector": selector, "competition_name": source_club["competition_name"],
            "opening_fixture_date": "2000-08-12", "opening_source_match_id": "99",
            "opening_xi_complete": True, "opening_xi_player_count": 11,
            "opening_xi_blockers": [], "players": players,
        })
        reconciliation_clubs.append({
            "source_selector": selector, "first_league_fixture_date": "2000-08-12",
            "source_match_id": "99", "lineup_source_url": "https://example.test/match/99",
            "formation": "4-4-2", "starting_xi": [],
        })
        manager_rows.append({
            "source_selector": selector, "opening_fixture_date": "2000-08-12",
            "manager_name": f"Manager {source_club['club_name']}", "resolution_method": "dated-source-supplement",
            "evidence": {"source_url": "https://example.test/manager", "source_snapshot_sha256": "2" * 64},
        })
    reconciliation = {
        "schema_version": "pm99-transfermarkt-opening-lineup-reconciliation-v1",
        "sources": {"lineup_capture_sha256": lineup_sha, "source_capture_sha256": "3" * 64},
        "clubs": reconciliation_clubs,
    }
    preallocation = {
        "schema_version": "pm99-opening-squad-preallocation-v1", "season": source["season"],
        "sources": {"opening_reconciliation_sha256": _sha(reconciliation), "opening_lineup_sha256": lineup_sha, "source_capture_sha256": "3" * 64},
        "source_clubs": preallocation_clubs,
    }
    managers = {
        "schema_version": "pm99-opening-manager-ledger-v1",
        "sources": {"opening_lineup_receipt_sha256": lineup_sha, "squad_source_capture_sha256": "3" * 64},
        "managers": manager_rows,
    }
    return preallocation, reconciliation, managers, selector_map, kits, ratings


def test_adapter_layers_pass_english_authoring_end_to_end() -> None:
    preallocation, reconciliation, managers, selector_map, kits, ratings = _evidence_documents()
    openings, manager_layer, adapter_audit = materialise(
        preallocation=preallocation, preallocation_sha256=_sha(preallocation),
        reconciliation=reconciliation, reconciliation_sha256=_sha(reconciliation),
        managers=managers, managers_sha256=_sha(managers),
    )
    assert adapter_audit["coverage"] == {"english_source_club_count": 92, "opening_layer_club_count": 92, "manager_layer_club_count": 92, "gap_count": 0}
    audit, compiler_input = build_authoring(
        source=preallocation, selector_map=selector_map, openings=openings,
        managers=manager_layer, kits=kits, ratings=ratings,
    )
    assert audit["status"] == "compiler-input-ready"
    assert compiler_input is not None and len(compiler_input["clubs"]) == 92


def test_adapter_infers_formation_from_sourced_xi_positions() -> None:
    preallocation, reconciliation, managers, *_ = _evidence_documents()
    reconciliation["clubs"][0]["formation"] = None
    inferred_positions = ["G"] + ["D"] * 4 + ["M"] * 4 + ["F"] * 2
    for player, position in zip(preallocation["source_clubs"][0]["players"][:11], inferred_positions, strict=True):
        player["facts"]["position"] = position
    preallocation["sources"]["opening_reconciliation_sha256"] = _sha(reconciliation)
    openings, _, audit = materialise(
        preallocation=preallocation, preallocation_sha256=_sha(preallocation),
        reconciliation=reconciliation, reconciliation_sha256=_sha(reconciliation),
        managers=managers, managers_sha256=_sha(managers),
    )
    row = next(row for row in openings["clubs"] if row["club"] == reconciliation["clubs"][0]["source_selector"]["club_name"])
    assert row["formation"] == "4-4-2"
    assert row["formation_method"] == "deterministic-inference-from-sourced-xi"


def test_adapter_rejects_stale_reconciliation() -> None:
    preallocation, reconciliation, managers, *_ = _evidence_documents()
    with pytest.raises(LayerAdapterError, match="not bound"):
        materialise(
            preallocation=preallocation, preallocation_sha256=_sha(preallocation),
            reconciliation=reconciliation, reconciliation_sha256="0" * 64,
            managers=managers, managers_sha256=_sha(managers),
        )
