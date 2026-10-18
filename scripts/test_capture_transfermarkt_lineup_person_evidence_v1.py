from __future__ import annotations

import pytest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_lineup_person_evidence_v1 as evidence


def test_profile_facts_parses_a_published_birth_date() -> None:
    result = evidence._profile_facts(
        b'''<h1 class="data-header__headline-wrapper">First <strong>Last</strong></h1>
        <span itemprop="birthDate">16/06/1968 (58)</span>
        <span itemprop="nationality">England</span>
        <li class="data-header__label">Position:<span class="data-header__content">Centre-Back</span></li>
        <li class="data-header__label">Height:<span class="data-header__content">6 ft 1 in</span></li>''',
        player={"source_player_id": "12", "display_name": "Example", "source_url": "https://example.test/12", "source_selector": {}},
    )
    assert result["published_birth_date"] == "1968-06-16"
    assert result["published_full_name"] == "First Last"
    assert result["published_nationality_label"] == "England"
    assert result["published_profile_position"] == "Centre-Back"
    assert result["published_height_cm"] == 185


def test_profile_facts_removes_a_rendered_squad_number_from_the_profile_headline() -> None:
    result = evidence._profile_facts(
        b'<h1 class="data-header__headline-wrapper">#8 Sam Morsy</h1>'
        b'<span itemprop="birthDate">10/09/1991</span>',
        player={"source_player_id": "123551"},
    )
    assert result["published_full_name"] == "Sam Morsy"


def test_profile_facts_keeps_a_named_profile_when_birth_date_is_unpublished() -> None:
    result = evidence._profile_facts(
        b'<h1 class="data-header__headline-wrapper">Dirk Lehmann</h1>'
        b'<span class="info-table__content info-table__content--bold">Goalkeeper</span>',
        player={"source_player_id": "3107"},
    )

    assert result["published_full_name"] == "Dirk Lehmann"
    assert result["published_birth_date"] is None
    assert result["profile_status"] == "source-qualified-with-explicit-gaps"
    assert result["profile_blockers"] == ["no-published-birth-date"]


def test_soccerbase_profile_facts_are_parsed_from_published_profile() -> None:
    payload = b'''<html><head><meta name="description" content="Full Name. (Born 14 Nov, 1975) Defender. Stats." /></head><body>
    <h1>Full Name</h1><table class="clubInfo"><tr><th>Age</th><td>50 (Born 14 Nov, 1975)</td></tr>
    <tr><th>Height</th><td>5ft 10in (1.78m)</td></tr><tr><th>Nationality</th><td>England</td></tr></table></body></html>'''
    row = evidence._profile_facts(payload, player={"source_player_id": "soccerbase:7", "source_url": "https://example/7"})
    assert row["published_full_name"] == "Full Name"
    assert row["published_birth_date"] == "1975-11-14"
    assert row["published_profile_position"] == "Defender"
    assert row["published_height_cm"] == 178
    assert row["published_nationality_label"] == "England"


def test_wikipedia_permanent_revision_profile_facts_are_parsed() -> None:
    payload = b'''<h1>Dean Holness</h1><table class="infobox">
    <tr><th>Full name</th><td>Dean Thomas Holness</td></tr>
    <tr><th>Date of birth</th><td><span class="bday">1976-07-25</span></td></tr>
    <tr><th>Position</th><td>Midfielder</td></tr></table>'''
    row = evidence._wikipedia_profile_facts(
        payload, player={"source_player_id": "soccerbase:26968", "source_url": "https://example/oldid=1"},
    )
    assert row["published_full_name"] == "Dean Thomas Holness"
    assert row["published_birth_date"] == "1976-07-25"
    assert row["published_profile_position"] == "Midfielder"


def test_profile_source_override_requires_a_permanent_revision() -> None:
    with pytest.raises(evidence.PersonEvidenceError, match="immutable Wikipedia oldid"):
        evidence._supplement_index({
            "schema_version": evidence.SUPPLEMENT_SCHEMA,
            "rows": [{
                "source_selector": {"country_catalog": "eng", "competition_catalog": "d3", "club_name": "Southend United"},
                "source_player_id": "soccerbase:26968", "parser": "wikipedia-infobox-v1",
                "source_url": "https://en.wikipedia.org/wiki/Dean_Holness",
            }],
        })


def test_height_parser_supports_metric_and_preserves_an_unpublished_height_as_none() -> None:
    assert evidence._height_cm("1.83 m") == 183
    assert evidence._height_cm("") is None


def test_candidate_players_uses_only_unresolved_first_fixture_rows() -> None:
    lineup = {"schema_version": evidence.LINEUP_SCHEMA, "clubs": [{
        "source_selector": {"country_catalog": "eng", "competition_catalog": "d1", "club_name": "Example"},
        "starting_xi": [{"source_player_id": "12", "display_name": "Example", "source_url": "https://example.test/12"}],
    }]}
    reconciliation = {"sources": {"lineup_capture_sha256": "a" * 64}, "clubs": [{
        "source_selector": {"country_catalog": "eng", "competition_catalog": "d1", "club_name": "Example"},
        "unresolved_first_fixture_players": [{"reason": "ambiguous-or-missing-dated-squad-player", "source_player_id": "12"}, {"reason": "expected-eleven-reconciled-players", "actual": 10}],
    }]}
    assert evidence._candidate_players(lineup, reconciliation) == [{
        "source_selector": {"country_catalog": "eng", "competition_catalog": "d1", "club_name": "Example"},
        "source_player_id": "12", "display_name": "Example", "source_url": "https://example.test/12",
    }]


def test_candidate_players_profiles_a_name_collision_discarded_as_a_duplicate() -> None:
    selector = {"country_catalog": "brazil", "competition_catalog": "seriea", "club_name": "Vasco"}
    lineup = {"schema_version": evidence.LINEUP_SCHEMA, "clubs": [{
        "source_selector": selector,
        "starting_xi": [{"source_player_id": "479587", "display_name": "Raul", "source_url": "https://example.test/479587"}],
    }]}
    reconciliation = {"sources": {"lineup_capture_sha256": "a" * 64}, "clubs": [{
        "source_selector": selector,
        "unresolved_first_fixture_players": [{
            "reason": "duplicate-resolved-player", "source_name": "Raúl Cáceres",
            "display_name": "Raul", "source_player_id": "479587",
        }],
    }]}

    assert evidence._candidate_players(lineup, reconciliation)[0]["source_player_id"] == "479587"


def test_capture_rejects_a_reconciliation_from_a_different_lineup_receipt(tmp_path: Path) -> None:
    with pytest.raises(evidence.PersonEvidenceError, match="not bound"):
        evidence.capture(
            lineup_capture={"schema_version": evidence.LINEUP_SCHEMA, "clubs": []}, lineup_capture_sha256="a" * 64,
            reconciliation={"sources": {"lineup_capture_sha256": "b" * 64}, "clubs": []},
            cache=evidence.SnapshotCache(tmp_path, offline=True, delay=0),
        )
