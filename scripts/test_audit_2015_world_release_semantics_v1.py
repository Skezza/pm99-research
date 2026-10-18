"""Focused tests for post-compile 2015 world semantic release QA."""

from __future__ import annotations

from scripts import audit_2015_world_release_semantics_v1 as qa


def test_written_manager_expectations_bind_only_explicit_written_managers() -> None:
    package = {
        "managers": [
            {"carrier_id": 27, "id": "manager-27", "name": "Historical Manager", "policy": "write"},
            {"carrier_id": 28, "id": "manager-28", "name": "Native Manager", "policy": "preserve"},
        ],
        "clubs": [
            {"carrier_id": 36, "name": "Example FC", "manager_id": "manager-27"},
            {"carrier_id": 37, "name": "Native FC", "manager_id": "manager-28"},
        ],
    }
    assert qa._written_manager_expectations(package) == [{
        "manager_record_id": 27,
        "canonical_manager_name": "Historical Manager",
        "manager_name": "Historical Manager",
        "expected_clubs": [{"carrier_id": 36, "club_name": "Example FC"}],
    }]


def test_manager_expectations_keep_identity_separate_from_explicit_native_alias():
    package = {'managers': [{'id': 'manager-27', 'carrier_id': 27, 'name': 'Louis van Gaal',
                            'policy': 'write', 'native_names': {'surname': 'van Gaal', 'display_name': 'van Gaal'}}],
               'clubs': [{'carrier_id': 36, 'name': 'Example FC', 'manager_id': 'manager-27'}]}
    row = qa._written_manager_expectations(package)[0]
    assert row['canonical_manager_name'] == 'Louis van Gaal'
    assert row['manager_name'] == 'van Gaal'


def test_outfield_handling_policy_is_not_confused_with_ball_control() -> None:
    rows = list(qa._ledger_player_rows([{
        "record_id": 1, "name": "Example Midfielder", "club": "Example FC", "position": "M",
        "family": "dd6361", "handling_basis": "source-ball-control", "visible_skills": {"handling": 81},
    }]))
    assert rows == [{
        "record_id": 1, "name": "Example Midfielder", "club": "Example FC", "position": "M",
        "family": "dd6361", "handling": 81, "handling_basis": "source-ball-control",
        "source": "english-player-ledger",
    }]
    assert qa.OUTFIELD_HANDLING_MAXIMUM == 20


def test_kit_review_requires_explicit_approvals() -> None:
    assert qa._reviewed_carriers(None) == set()
    assert qa._reviewed_carriers({
        "schema_version": qa.KIT_REVIEW_SCHEMA,
        "rows": [{"carrier_id": 36, "approved": True}, {"carrier_id": 37, "approved": False}],
    }) == {36}
