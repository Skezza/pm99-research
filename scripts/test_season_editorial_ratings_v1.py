from __future__ import annotations

import copy

import pytest

from scripts import season_editorial_ratings_v1 as ratings


def _sourced_values() -> dict[str, int]:
    return {field: 71 + index for index, field in enumerate(ratings.RATING_FIELDS)}


def _input() -> dict:
    return {
        "schema_version": ratings.INPUT_SCHEMA,
        "snapshot_date": "2000-08-12",
        "hierarchy": {
            "schema_version": ratings.HIERARCHY_SCHEMA,
            "snapshot_date": "2000-08-12",
            "clubs": [
                {"club_id": "club-alpha", "strength": 68, "source_ids": ["source-table"]},
                {"club_id": "club-beta", "strength": 54, "source_ids": ["source-table"]},
            ],
        },
        "players": [
            {
                "player_id": "player-carrier-901",
                "person_id": "person-alice-example-19780304",
                "club_id": "club-alpha",
                "position": "M",
                "birth_date": "1978-03-04",
                "height_cm": 173,
                "squad_status": "starting_xi",
            },
            {
                "player_id": "player-carrier-902",
                "person_id": "person-bob-keeper-19751201",
                "club_id": "club-alpha",
                "position": "G",
                "birth_date": "1975-12-01",
                "height_cm": 190,
                "squad_status": "starting_xi",
            },
            {
                "player_id": "player-carrier-903",
                "person_id": "person-cara-sourced-19800101",
                "club_id": "club-beta",
                "position": "F",
                "birth_date": "1980-01-01",
                "height_cm": 181,
                "squad_status": "substitute",
                "sourced_ratings": {
                    "profile": ratings.RATING_PROFILE,
                    "values": _sourced_values(),
                    "provenance": {
                        "method": "FIFA 2001 source transform",
                        "proof_grade": "source-captured",
                        "source_ids": ["source-fifa-2001"],
                    },
                },
            },
        ],
    }


def _by_person(output: dict) -> dict[str, dict]:
    return {row["person_id"]: row for row in output["player_ratings"]}


def test_is_deterministic_and_independent_of_input_carrier_and_row_order() -> None:
    first_input = _input()
    first = ratings.build_rating_output(first_input)
    reordered = copy.deepcopy(first_input)
    reordered["players"].reverse()
    reordered["hierarchy"]["clubs"].reverse()
    for index, player in enumerate(reordered["players"], start=40):
        player["carrier_id"] = index
        player["slot"] = 99 - index
    second = ratings.build_rating_output(reordered)
    first_rows = _by_person(first)
    second_rows = _by_person(second)
    for person_id in first_rows:
        assert first_rows[person_id]["ratings"] == second_rows[person_id]["ratings"]


def test_sourced_ratings_are_preserved_byte_for_byte_as_a_document() -> None:
    payload = _input()
    supplied = copy.deepcopy(payload["players"][2]["sourced_ratings"])
    output = ratings.build_rating_output(payload)
    row = _by_person(output)["person-cara-sourced-19800101"]
    assert row["ratings"] == supplied
    assert row["resolution"] == {
        "status": "sourced-ratings-preserved",
        "sourced_ratings_sha256": ratings.document_sha256(supplied),
    }


def test_one_player_fact_change_does_not_change_other_rating_rows() -> None:
    before = ratings.build_rating_output(_input())
    changed = _input()
    changed["players"][0]["height_cm"] = 194
    after = ratings.build_rating_output(changed)
    before_rows = _by_person(before)
    after_rows = _by_person(after)
    assert before_rows["person-alice-example-19780304"] != after_rows["person-alice-example-19780304"]
    assert before_rows["person-bob-keeper-19751201"] == after_rows["person-bob-keeper-19751201"]
    assert before_rows["person-cara-sourced-19800101"] == after_rows["person-cara-sourced-19800101"]


def test_handling_is_position_plausible_and_provenance_is_hashed() -> None:
    output = ratings.build_rating_output(_input())
    rows = _by_person(output)
    midfielder = rows["person-alice-example-19780304"]["ratings"]
    keeper = rows["person-bob-keeper-19751201"]["ratings"]
    assert 1 <= midfielder["values"]["handling"] <= 20
    assert keeper["values"]["handling"] >= keeper["values"]["quality"] - 12
    provenance = midfielder["provenance"]
    assert provenance["model_sha256"] == ratings.MODEL_SHA256
    assert provenance["hierarchy_sha256"] == output["hierarchy_sha256"]
    assert len(provenance["player_context_sha256"]) == 64
    assert provenance["snapshot_date"] == "2000-08-12"


def test_rejects_missing_stable_person_identity_and_unpinned_hierarchy() -> None:
    payload = _input()
    payload["players"][0]["person_id"] = ""
    with pytest.raises(ratings.EditorialRatingError, match="immutable person IDs"):
        ratings.build_rating_output(payload)
    payload = _input()
    payload["hierarchy"]["snapshot_date"] = "2000-08-13"
    with pytest.raises(ratings.EditorialRatingError, match="must equal snapshot_date"):
        ratings.build_rating_output(payload)

