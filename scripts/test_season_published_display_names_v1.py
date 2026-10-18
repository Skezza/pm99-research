import copy
import json
import pytest
from scripts import season_published_display_names_v1 as display
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.test_original_public_supplement_merges_v1 import people_document
from scripts.test_season_duplicate_ownership_delta_v1 import fixture as native_fixture
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6360_player_payload, _dd6361_player_payload


def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(display.people, 'ROOT', tmp_path)
    monkeypatch.setattr(display.registry, 'ROOT', tmp_path)
    document = people_document(tmp_path)
    path = tmp_path / 'people.json'
    path.write_text(json.dumps(document))
    claim = display.claims(path)[10]
    person = document['batches'][0]['people'][0]
    return path, claim, person


def test_only_explicit_original_aliases_not_current_facts_are_available(tmp_path, monkeypatch):
    _, claim, person = prepared(tmp_path, monkeypatch)
    assert display.verify(claim, person) == [{'field': 'shortName', 'name': 'R. Player'}]
    assert set(claim) == {'policy', 'source_player_id', 'birth_date', 'names', 'original_batch'}


@pytest.mark.parametrize('problem', ['person', 'DOB', 'invented-alias', 'field', 'endpoint', 'raw', 'receipt'])
def test_alias_is_independently_replayed_not_trusted_from_plan(tmp_path, monkeypatch, problem):
    _, claim, person = prepared(tmp_path, monkeypatch)
    if problem == 'person': person['source_player_id'] = 99
    if problem == 'DOB': person['birth_date'] = '1970-01-02'
    if problem == 'invented-alias': claim['names'][0]['name'] = 'Invented'
    if problem == 'field': claim['names'][0]['field'] = 'name'
    if problem == 'endpoint': claim['original_batch']['source_url'] = 'https://example.com/fake'
    if problem == 'raw': (tmp_path / claim['original_batch']['raw_path']).write_text('{}')
    if problem == 'receipt': (tmp_path / claim['original_batch']['source_receipt_path']).write_text('{}')
    with pytest.raises(ValueError):
        display.verify(claim, person)


def test_plan_requires_explicit_policy_and_same_original_ledger(tmp_path, monkeypatch):
    path, claim, person = prepared(tmp_path, monkeypatch)
    plan = {'allow_published_display_aliases': True,
        'bindings': {'published_display_policy': display.POLICY,
            'published_person_supplement': {'path': path.name, 'sha256': display.registry.sha256_file(path)}},
        'updates': [{'published_display_names': claim, 'replacement': {'source_person': person}}]}
    display.verify_plan(plan)
    for key in ('allow_published_display_aliases',):
        altered = copy.deepcopy(plan); altered[key] = False
        with pytest.raises(ValueError, match='explicit bound policy'):
            display.verify_plan(altered)
    altered = copy.deepcopy(plan); altered['updates'][0]['published_display_names']['names'].clear()
    with pytest.raises(ValueError, match='not from the bound'):
        display.verify_plan(altered)


def test_source_full_name_survives_capacity_fitting_explicit_alias(tmp_path, monkeypatch):
    _, claim, person = prepared(tmp_path, monkeypatch)
    package, plan = native_fixture('dd6361')
    row = plan['updates'][0]
    row['replacement']['source_person'] = person
    row['replacement']['source_player'].update(name='Retired Player', birth_date=person['birth_date'])
    row['published_display_names'] = claim
    result = delta.updated_package(package, plan)
    original = _indexed_fdi([(1, '', _dd6361_player_payload(1)), (2, '', _dd6361_player_payload(2))])
    real_writer = delta.compiler._patch_indexed_player_variable_name_payload
    def compact_window(payload, current, name):
        if len(name) > 9:
            raise ValueError('native compact surname window')
        return real_writer(payload, current, name)
    monkeypatch.setattr(delta.compiler, '_patch_indexed_player_variable_name_payload', compact_window)
    aliases = delta.fit_display_names(original, result, plan)
    assert aliases[0]['display_name'] == 'R. Player'
    assert aliases[0]['method'] == 'original-explicit-shortName'
    assert result['players'][1]['source_name'] == 'Retired Player'
    assert result['players'][1]['name'] == 'R. Player'


def test_no_automatic_name_truncation_without_published_alias(tmp_path, monkeypatch):
    _, _, person = prepared(tmp_path, monkeypatch)
    package, plan = native_fixture()
    row = plan['updates'][0]
    row['replacement']['source_person'] = person
    row['replacement']['source_player'].update(name='Retired Player', birth_date=person['birth_date'])
    result = delta.updated_package(package, plan)
    original = _indexed_fdi([(2, '', _dd6360_player_payload(2))])
    monkeypatch.setattr(delta.compiler, '_patch_indexed_player_variable_name_payload',
                        lambda *args: (_ for _ in ()).throw(ValueError('native compact window')))
    with pytest.raises(ValueError, match='without losing its surname'):
        delta.fit_display_names(original, result, plan)
