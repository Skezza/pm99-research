"""Tests for the source-tail target-membership planner."""

from scripts.plan_2015_source_tail_replacements_v1 import build_plan


def test_plan_reserves_an_unclaimed_target_and_preserves_a_partial_source() -> None:
    membership = {
        "schema_version": "pm99-world-2015-top-flight-membership-v1",
        "leagues": [{"family": "test", "teams": [
            {"name": "Alpha", "article_title": "FC Alpha", "article_path": "/wiki/Alpha"},
            {"name": "Beta", "article_title": "FC Beta", "article_path": "/wiki/Beta"},
            {"name": "Gamma", "article_title": "FC Gamma", "article_path": "/wiki/Gamma"},
        ]}],
    }
    draft = {"proposals": [
        {"carrier_id": 1, "group": "test", "baseline_name": "Alpha", "source_club_name": "FC Alpha", "status": "source-squad-ready"},
    ]}
    dispositions = {"schema_version": "pm99-world-2015-unresolved-carrier-dispositions-v1", "dispositions": [
        {"carrier_id": 2, "group": "test", "baseline_name": "Old", "fixed_roster_slot_count": 18, "release_disposition": "genuinely-unresolved-no-dated-source"},
        {"carrier_id": 3, "group": "test", "baseline_name": "Partial", "fixed_roster_slot_count": 19, "release_disposition": "partial-sourced-prefix-preserved-native-tail", "source_selector": {"club_name": "Gamma"}},
    ]}
    result = build_plan(draft=draft, dispositions=dispositions, membership=membership)
    assert result["assignments"][0]["proposed_target"]["name"] == "Beta"
    assert result["assignments"][1]["status"] == "retain-declared-target-club-needs-capacity-source"


def test_plan_does_not_guess_an_unclassified_carrier_family() -> None:
    result = build_plan(
        draft={"proposals": []},
        dispositions={"schema_version": "pm99-world-2015-unresolved-carrier-dispositions-v1", "dispositions": [
            {"carrier_id": 99, "group": None, "baseline_name": "Unknown", "fixed_roster_slot_count": 1, "release_disposition": "genuinely-unresolved-no-dated-source"},
        ]},
        membership={"schema_version": "pm99-world-2015-top-flight-membership-v1", "leagues": []},
    )
    assert result["assignments"] == [{
        "carrier_id": 99, "family": None, "baseline_name": "Unknown", "fixed_roster_slot_count": 1,
        "prior_release_disposition": "genuinely-unresolved-no-dated-source",
        "status": "requires-carrier-family-classification",
        "next_action": "derive the fixed carrier's intended competition family before selecting any 2015 club",
    }]


def test_plan_retains_a_legacy_name_that_is_a_real_target_member() -> None:
    result = build_plan(
        draft={"proposals": []},
        dispositions={"schema_version": "pm99-world-2015-unresolved-carrier-dispositions-v1", "dispositions": [
            {"carrier_id": 99, "group": "test", "baseline_name": "Alpha", "fixed_roster_slot_count": 1, "release_disposition": "genuinely-unresolved-no-dated-source"},
        ]},
        membership={"schema_version": "pm99-world-2015-top-flight-membership-v1", "leagues": [
            {"family": "test", "teams": [{"name": "Alpha", "article_title": "FC Alpha", "article_path": "/wiki/Alpha"}]},
        ]},
    )
    assignment = result["assignments"][0]
    assert assignment["status"] == "retain-baseline-target-membership-awaiting-capacity-source"
    assert assignment["target_membership"]["article_path"] == "/wiki/Alpha"


def test_plan_replaces_a_partial_source_that_is_not_in_target_membership() -> None:
    result = build_plan(
        draft={"proposals": []},
        dispositions={"schema_version": "pm99-world-2015-unresolved-carrier-dispositions-v1", "dispositions": [
            {"carrier_id": 99, "group": "test", "baseline_name": "Old", "fixed_roster_slot_count": 1,
             "release_disposition": "partial-sourced-prefix-preserved-native-tail", "source_selector": {"club_name": "Old FC"}},
        ]},
        membership={"schema_version": "pm99-world-2015-top-flight-membership-v1", "leagues": [
            {"family": "test", "teams": [{"name": "New", "article_title": "FC New", "article_path": "/wiki/New"}]},
        ]},
    )
    assignment = result["assignments"][0]
    assert assignment["status"] == "proposed-target-membership-club-awaiting-capacity-source"
    assert assignment["displaced_partial_source_selector"]["club_name"] == "Old FC"
