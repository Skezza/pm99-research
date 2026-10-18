from __future__ import annotations

from scripts import derive_transfermarkt_opening_player_additions_v1 as additions


def test_derive_keeps_a_profiled_opening_fixture_addition_explicit() -> None:
    source_sha = "a" * 64
    lineup_sha = "b" * 64
    evidence_sha = "c" * 64
    selector = {"country_catalog": "eng", "competition_catalog": "d1", "club_name": "Example"}
    lineup = {"schema_version": additions.LINEUP_SCHEMA, "clubs": [{
        "source_selector": selector,
        "first_league_fixture_date": "2000-08-12",
        "lineup_source_url": "https://example.test/match",
        "source_match_id": "1",
        "starting_xi": [{"display_name": "Short Name", "source_player_id": "9", "source_slug": "full-name", "source_url": "https://example.test/player/9"}],
    }]}
    reconciliation = {"schema_version": additions.RECONCILIATION_SCHEMA, "sources": {
        "source_capture_sha256": source_sha, "lineup_capture_sha256": lineup_sha, "person_evidence_sha256": evidence_sha,
    }, "clubs": [{"source_selector": selector, "unresolved_first_fixture_players": [
        {"reason": "ambiguous-or-missing-dated-squad-player", "source_player_id": "9"},
        {"reason": "expected-eleven-reconciled-players", "actual": 10},
    ]}]}
    evidence = {"schema_version": additions.PERSON_EVIDENCE_SCHEMA, "source": {"lineup_capture_sha256": lineup_sha}, "players": [{
        "source_selector": selector, "source_player_id": "9", "published_full_name": "Full Name", "published_birth_date": "1980-01-02", "source_url": "https://example.test/player/9",
    }]}
    result = additions.derive(
        source_capture_sha256=source_sha, lineup_capture=lineup, lineup_capture_sha256=lineup_sha,
        reconciliation=reconciliation, reconciliation_sha256="d" * 64,
        person_evidence=evidence, person_evidence_sha256=evidence_sha,
    )
    assert result["summary"] == {
        "opening_fixture_addition_count": 1, "club_count": 1,
        "profiled_person_count": 1, "profile_facts_pending_count": 0,
    }
    assert result["rows"][0]["published_full_name"] == "Full Name"
    assert result["rows"][0]["profile_status"] == "opening-fixture-person-profiled"


def test_derive_rejects_a_reconciliation_bound_to_different_person_evidence() -> None:
    try:
        additions.derive(
            source_capture_sha256="a" * 64,
            lineup_capture={"schema_version": additions.LINEUP_SCHEMA, "clubs": []},
            lineup_capture_sha256="b" * 64,
            reconciliation={"schema_version": additions.RECONCILIATION_SCHEMA, "sources": {
                "source_capture_sha256": "a" * 64, "lineup_capture_sha256": "b" * 64, "person_evidence_sha256": "wrong",
            }, "clubs": []},
            reconciliation_sha256="d" * 64,
            person_evidence={"schema_version": additions.PERSON_EVIDENCE_SCHEMA, "source": {"lineup_capture_sha256": "b" * 64}, "players": []},
            person_evidence_sha256="c" * 64,
        )
    except additions.AdditionQueueError as error:
        assert "person evidence" in str(error)
    else:
        raise AssertionError("expected a source-binding failure")
