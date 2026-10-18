from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_2015_world_full_roster_carrier_drafts as full  # noqa: E402


def _row(slot: int, *, rated: bool) -> dict[str, object]:
    values = {
        "rating": 70, "sprint_speed": 71, "stamina": 72, "aggression": 73, "short_pass": 74,
        "stand_tackle": 75, "heading": 76, "finishing": 77, "dribbling": 78, "gk_handling": 10,
    } if rated else {}
    fifa: dict[str, object] = {"status": "fifa16-exact-name-and-birth-date", "fifa16_player_id": slot + 10, "fifa16_headshot_url": f"https://example.test/{slot}.png"}
    if rated:
        fifa["fifa16_values"] = values
    return {
        "slot_index": slot, "player_carrier_id": 100 + slot, "player_family": "dd6360", "immutable_row_flag": 0,
        "source_squad_index": slot + 1,
        "source_player": {"name": f"Player {slot}", "birth_date": "1990-01-02", "nationality": "ESP", "height_cm": 180, "weight_kg": 75, "position": "M", "shirt_number": slot + 1, "unresolved_fields": []},
        "fifa16": fifa,
    }


def _inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    reconciliation = {"schema_version": full.RECONCILIATION_SCHEMA, "carrier_plans": [{"carrier_id": 1, "rows": [_row(0, rated=True), _row(1, rated=False)]}]}
    join = {
        "schema_version": full.JOIN_SCHEMA,
        "sources": {
            "strict_player_reconciliation_sha256": hashlib.sha256(full.canonical_json_bytes(reconciliation)).hexdigest(),
            "footballsquads_capture_sha256": "a" * 64,
            "transfermarkt_opening_fixture_receipt_sha256": "b" * 64,
        },
        "clubs": [{
            "source_draft_reference": {"status": "source-draft-and-strict-player-reconciliation-linked", "draft_carrier_id": 1},
            "strict_club_identity": {"status": "strict-footballsquads-club-identity-match", "strict_club_key": "fixture"},
            "transfermarkt_source_club": {"id": 1, "name": "Fixture FC"},
            "first_home_fixture_ground_evidence": {"reported_stadium": "Fixture Stadium", "interpretation": "not proof of a persistent club ground or capacity"},
            "opening_fixture_facts": {
                "date": "2015-08-08", "declared_manager": "Fixture Manager", "declared_formation": "4-3-3", "reported_match_stadium": "Fixture Stadium",
                "reported_match_stadium_interpretation": "fixture fact only; not a persistent club-ground or capacity claim",
                "source_game_id": "g1", "source_status": "source-qualified", "source_blockers": [], "lineup_counts": {"starting_lineup": 1, "substitutes": 0}, "source_url": "https://example.test/g1",
                "starting_lineup": [{"name": "Player 0", "shirt_number": "8", "player_reconciliation": {"status": "strict-normalised-source-name-unique", "player_reconciliation_row": {"slot_index": 0, "player_carrier_id": 100}}}],
                "substitutes": [],
            },
        }],
    }
    assets = {"schema_version": full.ASSET_SCHEMA, "clubs": [{"carrier_id": 1, "kit": {"status": "blocked-no-reviewed-2015-kit", "action": "no-write"}, "players": [{"slot_index": 0, "player_carrier_id": 100, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "reviewed"}]}]}
    return join, reconciliation, assets


def test_full_roster_draft_keeps_all_slots_and_marks_missing_ratings_for_editorial_fallback() -> None:
    join, reconciliation, assets = _inputs()
    result = full.build_full_roster_drafts(source_join=join, reconciliation=reconciliation, asset_dispositions=assets)

    draft = result["carrier_drafts"][0]
    assert len(draft["players"]) == 2
    assert draft["players"][0]["rating_disposition"]["status"] == "fifa16-complete-candidate"
    assert draft["players"][0]["opening_fixture_presence"]["lineup_role"] == "starting_lineup"
    assert draft["players"][0]["portrait_disposition"]["status"] == "native-no-photo"
    assert draft["players"][1]["rating_disposition"]["status"] == "editorial-fallback-required"
    assert draft["players"][1]["opening_fixture_presence"]["status"] == "not-in-strictly-reconciled-opening-xi-or-bench"
    assert draft["status"] == "blocked"
    assert "player-rating-editorial-fallback-required" in draft["blockers"]


def test_full_roster_draft_rejects_a_join_bound_to_another_reconciliation() -> None:
    join, reconciliation, _assets = _inputs()
    join["sources"]["strict_player_reconciliation_sha256"] = "f" * 64
    with pytest.raises(full.FullRosterDraftError, match="not bound"):
        full.build_full_roster_drafts(source_join=join, reconciliation=reconciliation)
