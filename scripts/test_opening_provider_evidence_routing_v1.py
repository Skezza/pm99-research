"""Prevent cross-provider witness leakage and silent legacy overrides."""
import pytest

from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_new_person_dispatch_v1 as dispatch


def test_row_local_witnesses_reach_only_the_selected_provider(monkeypatch):
    keys = {'city_annual', 'tm_entity', 'soccerbase', 'city_role',
            'uefa_country', 'city_august_match'}
    witnesses = {key: {'sha256': key} for key in keys}
    selection = dict(carrier_id=9142, club_id='english-club-310',
        editorial_role_policy=dispatch.POLICY, _provider_evidence=witnesses)
    calls = []
    monkeypatch.setattr(dispatch, 'new_person',
        lambda actor, evidence: calls.append((actor, evidence)) or 'admitted')
    assert exchange.new_person(selection, {'unrelated_retirement': {}}) == 'admitted'
    assert calls == [({'editorial_role_policy': dispatch.POLICY}, witnesses)]
    assert '_provider_evidence' in selection


def test_typed_provider_refuses_another_providers_witness_map():
    with pytest.raises(ValueError, match='source map differs'):
        exchange.new_person(dict(editorial_role_policy=dispatch.POLICY,
            _provider_evidence={'rm_annual': {}}), {})


def test_legacy_row_cannot_override_source_witnesses():
    with pytest.raises(ValueError, match='reviewed typed admission'):
        exchange.new_person({'_provider_evidence': {}}, {})


def test_ordinary_legacy_row_keeps_its_existing_reader(monkeypatch):
    selection = dict(provider_player_id=123)
    evidence = {'profile': {'sha256': 'unchanged'}}
    monkeypatch.setattr(exchange, '_canonical_new_person',
        lambda actor, sources: (actor, sources))
    assert exchange.new_person(selection, evidence) == (selection, evidence)
