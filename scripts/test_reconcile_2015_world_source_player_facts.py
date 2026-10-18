from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import reconcile_2015_world_source_player_facts as reconcile


def _club(*, name: str = "Example", player_name: str = "José Player", birth_date: str = "1990-01-02") -> dict[str, object]:
    return {
        "country_catalog": "spain", "competition_catalog": "laliga", "club_name": name,
        "source_path": "spain/2015-2016/laliga/example.txt", "source_sha256": "a" * 64,
        "players": [{"name": player_name, "birth_date": birth_date, "nationality": "ESP", "height_cm": 180, "weight_kg": 75, "position": "M", "shirt_number": 8, "unresolved_fields": []}],
    }


def _inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    registry = {"carriers": [{"carrier_id": 1, "roster_slots": [{"slot_index": 0, "player_carrier_id": 101, "family": "dd6360", "flag": 7}]}]}
    capture = {"schema_version": reconcile.SOURCE_SCHEMA, "clubs": [_club()]}
    draft = {
        "schema_version": reconcile.DRAFT_SCHEMA,
        "registry_sha256": __import__("hashlib").sha256(reconcile.canonical_json_bytes(registry)).hexdigest(),
        "source_capture_sha256": __import__("hashlib").sha256(reconcile.canonical_json_bytes(capture)).hexdigest(),
        "proposals": [{"carrier_id": 1, "status": "source-squad-ready", "source_selector": {key: _club()[key] for key in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")}}],
    }
    return registry, draft, capture


def test_reconciliation_retains_fixed_slot_and_exact_fifa_source() -> None:
    registry, draft, capture = _inputs()
    output = reconcile.build_reconciliation(
        registry=registry, draft=draft, source_capture=capture,
        fifa_rows=[{"player_id": "55", "name": "Jose Player", "birthdate": "1990-01-02", "nationality": "Spain", "club": "FC Example", "rating": "82", "headshot_url": "https://example.test/55.png", "sprint_speed": "80", "stamina": "81", "aggression": "70", "short_pass": "85", "stand_tackle": "40", "heading": "55", "finishing": "64", "dribbling": "82", "gk_handling": "12", "preferred_positions": "CM", "club_kit_number": "8"}],
        fifa_sha256="b" * 64,
    )
    row = output["carrier_plans"][0]["rows"][0]
    assert row["player_carrier_id"] == 101
    assert row["immutable_row_flag"] == 7
    assert row["fifa16"]["status"] == "fifa16-exact-name-and-birth-date"
    assert row["fifa16"]["fifa16_values"]["gk_handling"] == 12


def test_reconciliation_keeps_ambiguous_names_out_of_the_rating_lane() -> None:
    registry, draft, capture = _inputs()
    output = reconcile.build_reconciliation(
        registry=registry, draft=draft, source_capture=capture,
        fifa_rows=[
            {"player_id": "55", "name": "Jose Player", "birthdate": "1989-01-02", "nationality": "Spain", "club": "A", "rating": "82", "headshot_url": "a"},
            {"player_id": "56", "name": "Jose Player", "birthdate": "1988-01-02", "nationality": "Spain", "club": "B", "rating": "80", "headshot_url": "b"},
        ],
        fifa_sha256="b" * 64,
    )
    assert output["carrier_plans"][0]["rows"][0]["fifa16"] == {"status": "fifa16-ambiguous-name", "candidate_fifa16_player_ids": [55, 56]}


def test_reconciliation_accepts_a_unique_short_fifa_name_only_with_matching_birth_date() -> None:
    registry, draft, capture = _inputs()
    output = reconcile.build_reconciliation(
        registry=registry, draft=draft, source_capture=capture,
        fifa_rows=[{"player_id": "55", "name": "Player", "birthdate": "1990-01-02", "nationality": "Spain", "club": "A", "rating": "82", "headshot_url": "a"}],
        fifa_sha256="b" * 64,
    )
    assert output["carrier_plans"][0]["rows"][0]["fifa16"]["status"] == "fifa16-unique-surname-and-birth-date"


def test_reconciliation_rejects_draft_from_another_source_capture() -> None:
    registry, draft, capture = _inputs()
    draft["source_capture_sha256"] = "f" * 64
    with pytest.raises(reconcile.ReconciliationError, match="not bound"):
        reconcile.build_reconciliation(registry=registry, draft=draft, source_capture=capture, fifa_rows=[], fifa_sha256="b" * 64)
