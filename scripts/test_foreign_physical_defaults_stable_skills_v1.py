import copy

import pytest

from scripts import prepare_ofk_2004_private_native_v1 as native
from scripts import prepare_borac_2003_verified_inputs_v1 as inputs


def test_physical_fallbacks_do_not_feed_back_into_skills(monkeypatch):
    club = {'id': 'club', 'roster_player_ids': ['p']}
    package = {'clubs': [club], 'players': [], 'artifacts': []}
    person = {'source_player_id': 1}
    row = {'source_person': person, 'source_player': {'height_cm': 185, 'weight_kg': 80}}
    proposal = {'new_club': 'Borac', 'country': 'serbia', 'season': '2003-04',
        'schema_version': 'pm99-private-original-borac2003-verified-inputs-v1',
        'secondary_fact_review': {'policy': inputs.STABLE_SKILLS_POLICY},
        'first_fixture': {'date': '2003-08-09'}, 'desired_people': [row],
        'allocation': [{'player_id': 'p', 'carrier_id': 1, 'before_recipe': {},
                        'replacement': row, 'display': {'display_name': 'B. Djuric'}}]}
    original = copy.deepcopy(proposal)
    monkeypatch.setattr(native.native, 'validate_allocation', lambda *a: (club, {'p': {}}))
    calls = []

    def updated(package, plan):
        height = plan['updates'][0]['replacement']['source_player']['height_cm']
        calls.append(height)
        result = copy.deepcopy(package)
        result['players'] = [{'id': 'p', 'ratings': {'values': {'heading': 28 if height is None else 29}},
                              'facts': {'height_cm': height}}]
        result['artifacts'] = [{'id': 'proof', 'relative_path': native.delta.plan_filename(plan)}]
        return result

    monkeypatch.setattr(native.delta, 'updated_package', updated)
    result, composition, _ = native.compose_recipe(package, proposal)
    assert calls == [185, None]
    assert result['players'][0]['facts']['height_cm'] == 185
    assert result['players'][0]['ratings']['values']['heading'] == 28
    assert composition['foreign_original_source'] == proposal == original


def test_stable_skills_cannot_be_requested_without_physical_defaults(tmp_path):
    with pytest.raises(ValueError, match='require explicit fallback'):
        inputs.prepare(tmp_path / 'source.json', preserve_skills=True)
