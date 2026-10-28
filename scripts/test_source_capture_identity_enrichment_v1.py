import copy
import pytest
from scripts.season_historical_roster_audit_v1 import captured_players_match

ORIGINAL = dict(name='Example Player', birth_date=None, nationality='NED',
                position='G', height_cm=None, unresolved_fields=['birth_date'])
PARSED = {**ORIGINAL, 'source_identity': {'provider': 'transfermarkt', 'player_id': '123'}}


def matches(parsed, original=None, allow=True):
    return captured_players_match([parsed], [original or ORIGINAL],
                                  allow_added_transfermarkt_identity=allow)


def test_frozen_facts_accept_only_known_additive_identity_metadata():
    assert matches(PARSED)
    assert not matches(PARSED, allow=False)
    assert matches(ORIGINAL, allow=False)


@pytest.mark.parametrize('field,value', [('name', 'Someone Else'),
    ('birth_date', '1980-01-01'), ('nationality', 'GER'), ('position', 'D'),
    ('height_cm', 188), ('unresolved_fields', [])])
def test_any_original_fact_change_is_still_refused(field, value):
    assert not matches({**PARSED, field: value})


@pytest.mark.parametrize('identity', [None, {}, {'provider': 'other', 'player_id': '123'},
    {'provider': 'transfermarkt', 'player_id': '0'},
    {'provider': 'transfermarkt', 'player_id': 123},
    {'provider': 'transfermarkt', 'player_id': '123', 'extra': 'value'}])
def test_unrecognised_or_unbounded_metadata_is_refused(identity):
    assert not matches({**ORIGINAL, 'source_identity': identity})


def test_existing_identity_mismatch_and_roster_changes_are_not_enrichments():
    previous = copy.deepcopy(PARSED)
    previous['source_identity']['player_id'] = '456'
    assert not matches(PARSED, previous)
    assert not captured_players_match([PARSED, PARSED], [ORIGINAL],
                                     allow_added_transfermarkt_identity=True)
