"""Check source-role projection against the existing game role-code table."""
from scripts import season_altrincham_2001_role_overlay_v3 as overlay
from scripts.season_historical_role_plan_v1 import ROLE_MAP
from scripts.season_historical_roster_audit_v1 import ROLE_LABELS


def test_four_role_targets_use_the_existing_native_role_map():
    expected = {27011: 'RB', 10959: 'LB', 10955: 'RM', 10962: 'LM'}
    assert set(overlay.ROLE_UPDATES) == set(expected)
    for carrier, source_role in expected.items():
        assert overlay.ROLE_UPDATES[carrier]['after'] == [ROLE_MAP[source_role]]
    assert ROLE_LABELS[overlay.ROLE_UPDATES[10955]['after'][0]] == 'Right Midfielder'
    assert ROLE_MAP['CF'] != ROLE_MAP['RM']
