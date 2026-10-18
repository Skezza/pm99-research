"""Lead's negative tests for the independently implemented identity path."""

import copy

import pytest

from scripts import compose_season_source_captures_v1 as compose
from scripts import materialise_opening_squad_preallocation_v1 as opening
from scripts import pm99_season_qa_v1 as qa
from scripts import season_player_identity_v1 as identity
from scripts import season_source_package_builder_v1 as builder
from scripts.merge_footballsquads_captures import MergeError
from scripts.test_compose_season_source_captures_v1 import capture


@pytest.mark.parametrize("href", [
    "/person/profil/spieler/7garbage",
    "/person/profil/spieler/7;not-an-id",
    "/person/profil/spieler/007",
    "https://example.org/person/profil/spieler/7",
    "https://transfermarkt.com.example.org/person/profil/spieler/7",
    "https://user@www.transfermarkt.com/person/profil/spieler/7",
    "javascript:/person/profil/spieler/7",
    "/other?next=/person/profil/spieler/7",
])
def test_profile_identity_rejects_noncanonical_or_foreign_links(href):
    assert identity.profile_id_from_href(href) is None


@pytest.mark.parametrize("href", [
    "/person/profil/spieler/7",
    "/person/profil/spieler/7/saison/1990",
    "https://www.transfermarkt.com/person/profil/spieler/7?x=1",
    "//www.transfermarkt.de/person/profil/spieler/7",
])
def test_profile_identity_accepts_explicit_provider_and_relative_paths(href):
    assert identity.profile_id_from_href(href) == "7"


def test_explicit_null_is_malformed_not_unknown_in_ordinary_qa():
    report = qa.audit_player_identities({"players": [
        {"id": "a", "name": "Unknown", "facts": {}},
        {"id": "b", "name": "Malformed", "facts": {}, "source_identity": None},
    ]})
    assert report["coverage"]["missing_provider_identity"] == 1
    assert report["counts"]["malformed_identities"] == 1
    blockers, _warnings = qa.player_identity_issues(report)
    assert "player-identity-metadata-malformed" in {item["code"] for item in blockers}


def test_composition_rejects_explicit_null_identity():
    first = capture("one", "A")
    first["clubs"][0]["players"] = [{"name": "Player", "source_identity": None}]
    with pytest.raises(MergeError, match="malformed"):
        compose.compose(inputs=[("a", first, "1" * 64), ("b", capture("two", "B"), "2" * 64)],
                        catalog="1990-1991", label="1990/91")


def _addition():
    return {
        "profile_status": "opening-fixture-person-profiled", "source_player_id": "7",
        "published_full_name": "Sourced Player", "published_profile_position": "Defender",
        "profile_url": "https://www.transfermarkt.com/player/profil/spieler/7",
    }


def test_profiled_opening_addition_keeps_explicit_identity_and_matches_annual_key():
    source = _addition()
    before = copy.deepcopy(source)
    projected = opening._addition_player(source, 0)
    expected = {"provider": "transfermarkt", "player_id": "7"}
    assert projected["facts"]["source_identity"] == expected
    annual = {"facts": {"name": "Sourced Player", "source_identity": expected}}
    assert builder._person_candidate(projected) == builder._person_candidate(annual)
    assert source == before


def test_profiled_opening_addition_refuses_conflicting_numeric_id():
    source = _addition()
    source["source_player_id"] = "8"
    with pytest.raises(opening.PreallocationError, match="disagree"):
        opening._addition_player(source, 0)


def test_legacy_opening_profile_does_not_infer_provider_from_numeric_id():
    source = _addition()
    source["profile_url"] = "https://example.test/player/7"
    assert "source_identity" not in opening._addition_player(source, 0)["facts"]
