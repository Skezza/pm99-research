from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import join_2015_world_opening_fixture_facts as join  # noqa: E402


def _sha(value: dict[str, object]) -> str:
    return hashlib.sha256(join.canonical_json_bytes(value)).hexdigest()


def _club(*, name: str = "FC Example", country: str = "spain") -> dict[str, object]:
    return {
        "country_catalog": country,
        "competition_catalog": "laliga",
        "club_name": name,
        "source_path": f"{country}/2015-2016/laliga/example.txt",
        "source_sha256": "a" * 64,
        "players": [{"name": "José Player"}],
    }


def _receipt_club(*, name: str = "Example", country: str = "spain", qualified: bool = True) -> dict[str, object]:
    blockers = [] if qualified else ["expected-11-starting-lineup-got-0", "missing-declared-formation"]
    return {
        "country_catalog": country,
        "source_club": {"id": 1, "name": name},
        "opening_fixture": {
            "date": "2015-08-08", "declared_manager": "Fixture Manager" if qualified else None,
            "declared_formation": "4-3-3" if qualified else None,
            "reported_match_stadium": "Fixture Stadium", "source_game_id": "game-1",
            "source_status": "source-qualified" if qualified else "requires-review",
            "source_url": "https://example.test/game-1", "source_blockers": blockers,
            "lineup_counts": {"starting_lineup": 1 if qualified else 0, "substitutes": 1 if qualified else 0},
            "starting_lineup": ([{"name": "Jose Player", "shirt_number": "8", "position": "Central Midfield", "player_id": 55, "team_captain": False}] if qualified else []),
            "substitutes": ([{"name": "Bench Player", "shirt_number": "12", "position": "Goalkeeper", "player_id": 56, "team_captain": False}] if qualified else []),
        },
        "first_home_fixture_ground_evidence": {
            "reported_stadium": "Fixture Stadium",
            "interpretation": "reported stadium for the first home domestic fixture; not proof of a persistent club ground or capacity",
        },
    }


def _inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    source_club = _club()
    capture = {"schema_version": join.SOURCE_CAPTURE_SCHEMA, "clubs": [source_club]}
    selector = {field: source_club[field] for field in join.SELECTOR_FIELDS}
    draft = {
        "schema_version": join.DRAFT_SCHEMA, "source_capture_sha256": _sha(capture),
        "proposals": [{"carrier_id": 9, "status": "source-squad-ready", "source_selector": selector}],
    }
    reconciliation = {
        "schema_version": join.RECONCILIATION_SCHEMA,
        "sources": {"source_capture_sha256": _sha(capture), "source_draft_sha256": _sha(draft)},
        "carrier_plans": [{"carrier_id": 9, "rows": [{
            "source_player": {"name": "José Player"}, "source_squad_index": 4,
            "slot_index": 2, "player_carrier_id": 101, "fifa16": {"status": "fifa16-exact-name-and-birth-date"},
        }]}],
    }
    receipt = {"schema_version": join.FIXTURE_RECEIPT_SCHEMA, "source": {"database_sha256": "b" * 64}, "clubs": [_receipt_club()]}
    return capture, draft, reconciliation, receipt


def test_join_keeps_opening_facts_and_only_links_strict_identities() -> None:
    capture, draft, reconciliation, receipt = _inputs()
    result = join.build_source_join(
        source_capture=capture, source_draft=draft, player_reconciliation=reconciliation, opening_fixture_receipt=receipt
    )

    assert result["coverage"]["strict_footballsquads_club_identity_match_count"] == 1
    club = result["clubs"][0]
    assert club["strict_club_identity"]["status"] == "strict-footballsquads-club-identity-match"
    assert club["opening_fixture_facts"]["declared_manager"] == "Fixture Manager"
    assert club["opening_fixture_facts"]["starting_lineup"][0]["shirt_number"] == "8"
    assert club["opening_fixture_facts"]["starting_lineup"][0]["player_reconciliation"]["status"] == "strict-normalised-source-name-unique"
    assert club["opening_fixture_facts"]["substitutes"][0]["player_reconciliation"]["status"] == "requires-review-no-strict-source-player-name-match"
    assert "capacity" not in club["first_home_fixture_ground_evidence"]
    assert "not a persistent" in club["opening_fixture_facts"]["reported_match_stadium_interpretation"]


def test_join_queues_unmatched_clubs_and_incomplete_fixtures_without_fuzzy_mapping() -> None:
    capture, draft, reconciliation, receipt = _inputs()
    receipt["clubs"].append(_receipt_club(name="Different Expanded Club", country="spain"))
    receipt["clubs"].append(_receipt_club(name="Dutch Example", country="netherl", qualified=False))
    result = join.build_source_join(
        source_capture=capture, source_draft=draft, player_reconciliation=reconciliation, opening_fixture_receipt=receipt
    )

    assert result["coverage"]["unmatched_strict_club_identity_count"] == 2
    assert result["coverage"]["incomplete_opening_fixture_fact_count"] == 1
    assert result["coverage"]["review_queue_count"] == 3
    kinds = [row["kind"] for row in result["review_queue"]]
    assert kinds.count("unmatched-strict-club-identity") == 2
    assert "incomplete-opening-fixture-facts" in kinds
    unmatched = next(row for row in result["clubs"] if row["transfermarkt_source_club"]["name"] == "Different Expanded Club")
    assert unmatched["source_draft_reference"]["status"] == "not-attempted-no-strict-footballsquads-club-identity-match"


def test_join_rejects_reconciliation_not_hash_bound_to_draft() -> None:
    capture, draft, reconciliation, receipt = _inputs()
    reconciliation["sources"]["source_draft_sha256"] = "f" * 64
    with pytest.raises(join.JoinError, match="not bound"):
        join.build_source_join(
            source_capture=capture, source_draft=draft, player_reconciliation=reconciliation, opening_fixture_receipt=receipt
        )
