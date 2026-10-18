import json

import pytest

from scripts import season_public_identity_and_history_inputs_v1 as binder
from scripts import season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as identity
from scripts import season_published_transfer_history_v1 as history
from scripts.test_original_public_supplement_merges_v1 import people_document, history_document


def bound_document(tmp_path, monkeypatch, module, factory):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    document = factory(tmp_path)
    path = tmp_path / 'supplement.json'
    path.write_text(json.dumps(document))
    return path, binder.binding(path, module.POLICY)


def test_absent_optional_inputs_preserve_original_objects():
    people, events = {}, {}
    merged_people, merged_events, report = binder.merge_bound(people, events, {})
    assert merged_people is people and merged_events is events and report == {}


@pytest.mark.parametrize('module,factory,key', [
    (identity, people_document, 'published_person_supplement'),
    (history, history_document, 'published_transfer_supplement'),
])
def test_bound_inputs_replay_raw_publisher_data(tmp_path, monkeypatch, module, factory, key):
    _, binding = bound_document(tmp_path, monkeypatch, module, factory)
    people, events, report = binder.merge_bound({}, {}, {key: binding})
    assert report[key]['accepted_player_count'] == 1
    assert not report[key]['refused']
    if module is identity:
        assert people[('rplayer', '1960-01-02')][10]['name'] == 'Retired Player'
    else:
        assert events[10][0]['to_club_id'] == 2


@pytest.mark.parametrize('problem', ['changed-file', 'unknown-policy', 'forged-claim'])
def test_bound_inputs_refuse_changed_or_forged_evidence(tmp_path, monkeypatch, problem):
    path, binding = bound_document(tmp_path, monkeypatch, identity, people_document)
    if problem == 'changed-file':
        path.write_text('{}')
        message = 'immutable public source supplement changed'
    elif problem == 'unknown-policy':
        binding['policy'] = 'unknown-policy'
        message = 'unsupported original person input policy'
    else:
        document = json.loads(path.read_text())
        document['batches'][0]['people'][0]['name'] = 'Invented Player'
        path.write_text(json.dumps(document))
        binding = binder.binding(path, identity.POLICY)
        message = 'do not reproduce'
    with pytest.raises(ValueError, match=message):
        binder.merge_bound({}, {}, {'published_person_supplement': binding})
