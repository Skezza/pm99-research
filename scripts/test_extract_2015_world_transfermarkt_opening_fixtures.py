from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extract_2015_world_transfermarkt_opening_fixtures as extractor


def _fixture_row(
    country: str,
    *,
    club_id: int,
    formation: str | None = "4-3-3",
    lineup_type: str | None = "starting_lineup",
    player_id: int | None = 1,
    number: str | None = "1",
) -> dict[str, object]:
    return {
        "game_id": f"game-{club_id}", "fixture_date": "2015-08-08", "competition_id": f"{club_id}-1",
        "competition_name": "Fixture League", "country_name": country,
        "competition_url": "https://example.test/competition", "game_url": "https://example.test/game",
        "stadium": "Fixture Stadium", "home_club_id": club_id, "home_club_name": f"{country} FC",
        "away_club_id": club_id + 1000, "away_club_name": "Opponent FC", "club_id": club_id,
        "club_name": f"{country} FC", "venue": "home", "club_manager_name": "Fixture Manager",
        "club_formation": formation, "player_id": player_id, "player_name": None if player_id is None else f"Player {player_id}",
        "lineup_type": lineup_type, "position": "Centre-Forward", "number": number, "team_captain": 0,
    }


def _complete_input() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    opening: list[dict[str, object]] = []
    home: list[dict[str, object]] = []
    for index, country in enumerate(sorted(extractor.SUPPORTED_FOREIGN_COUNTRIES), start=1):
        club_id = index * 10
        for player in range(1, 12):
            opening.append(_fixture_row(country, club_id=club_id, player_id=player, number=str(player)))
        opening.append(_fixture_row(country, club_id=club_id, lineup_type="substitutes", player_id=99, number="12"))
        home.append(_fixture_row(country, club_id=club_id, player_id=None, lineup_type=None, number=None))
    return opening, home


def test_receipt_retains_source_facts_without_claiming_a_carrier_or_ground() -> None:
    opening, home = _complete_input()
    receipt = extractor.build_receipt(
        opening_rows=opening,
        first_home_rows=home,
        source={"database_sha256": "a" * 64},
    )
    assert receipt["schema_version"] == extractor.SCHEMA
    assert receipt["summary"]["club_count"] == len(extractor.SUPPORTED_FOREIGN_COUNTRIES)
    assert receipt["summary"]["opening_xi_source_qualified_club_count"] == len(extractor.SUPPORTED_FOREIGN_COUNTRIES)
    club = next(row for row in receipt["clubs"] if row["country_name"] == "Spain")
    assert club["country_catalog"] == "spain"
    assert club["opening_fixture"]["lineup_counts"] == {"starting_lineup": 11, "substitutes": 1}
    assert club["opening_fixture"]["source_status"] == "source-qualified"
    assert club["first_home_fixture_ground_evidence"]["reported_stadium"] == "Fixture Stadium"
    assert "not proof" in club["first_home_fixture_ground_evidence"]["interpretation"]
    assert club["compiler_disposition"] == "source-fact-only; no-pm99-carrier-or-slot-assignment"


def test_receipt_marks_missing_formation_and_short_xi_for_review() -> None:
    opening, home = _complete_input()
    netherlands = [row for row in opening if row["country_name"] == "Netherlands"]
    for row in netherlands:
        row["club_formation"] = None
    opening.remove(next(row for row in netherlands if row["lineup_type"] == "starting_lineup"))
    receipt = extractor.build_receipt(
        opening_rows=opening,
        first_home_rows=home,
        source={"database_sha256": "a" * 64},
    )
    club = next(row for row in receipt["clubs"] if row["country_name"] == "Netherlands")
    assert club["opening_fixture"]["source_status"] == "requires-review"
    assert "missing-declared-formation" in club["opening_fixture"]["source_blockers"]
    assert "expected-11-starting-lineup-got-10" in club["opening_fixture"]["source_blockers"]


def test_receipt_rejects_an_incomplete_country_set() -> None:
    opening, home = _complete_input()
    opening = [row for row in opening if row["country_name"] != "Spain"]
    home = [row for row in home if row["country_name"] != "Spain"]
    with pytest.raises(extractor.SourceReceiptError, match="country coverage changed"):
        extractor.build_receipt(opening_rows=opening, first_home_rows=home, source={"database_sha256": "a" * 64})


def test_generic_receipt_uses_its_explicit_country_mapping() -> None:
    opening, home = _complete_input()
    selected = {"Belgium": "belgium", "Spain": "spain"}
    opening = [row for row in opening if row["country_name"] in selected]
    home = [row for row in home if row["country_name"] in selected]
    receipt = extractor.build_receipt(
        opening_rows=opening,
        first_home_rows=home,
        source={"database_sha256": "b" * 64},
        season="2000",
        country_mapping=selected,
        schema_version=extractor.GENERIC_SCHEMA,
    )
    assert receipt["schema_version"] == extractor.GENERIC_SCHEMA
    assert receipt["season"] == "2000"
    assert {row["country_catalog"] for row in receipt["clubs"]} == {"belgium", "spain"}


def test_country_mapping_rejects_duplicate_pm99_catalogue() -> None:
    with pytest.raises(extractor.SourceReceiptError, match="duplicate PM99 catalogue"):
        extractor.validate_country_mapping({"England": "eng", "Scotland": "eng"})
