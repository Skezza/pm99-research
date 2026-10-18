import copy
import hashlib
import json
import pytest
from scripts import season_published_person_identity_v1 as identity
from scripts import season_published_transfer_history_v1 as history
from scripts.test_season_published_person_identity_v1 import fixture as people_fixture
from scripts.test_season_published_transfer_history_v1 import fixture as history_fixture


def raw(tmp_path, payload, url):
    path = tmp_path / 'original.json'
    path.write_text(json.dumps(payload))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = tmp_path / 'original.source.json'
    receipt.write_text(json.dumps({'url': url, 'sha256': sha}))
    return {'raw_path': path.name, 'raw_sha256': sha, 'source_receipt_path': receipt.name, 'source_url': url}


def people_document(tmp_path):
    people, gaps = identity.parse(people_fixture(), [10])
    row = dict(raw(tmp_path, people_fixture(), identity.url([10])), status='original-entities-parsed',
               requested_ids=[10], people=people, gaps=gaps)
    return {'schema_version': identity.SCHEMA, 'policy': identity.POLICY, 'batches': [row]}


def test_independent_published_short_name_is_added_without_initial_guess(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    supplement = people_document(tmp_path)
    index, report = identity.merge({}, supplement)
    assert index[('rplayer', '1960-01-02')][10]['name'] == 'Retired Player'
    assert report['current_attributes_or_ownership_used'] is False


def test_conflicting_pinned_dob_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    supplement = people_document(tmp_path)
    index = {('retiredplayer', '1970-01-02'): {10: {'source_player_id': 10, 'birth_date': '1970-01-02'}}}
    original = copy.deepcopy(index)
    result, report = identity.merge(index, supplement)
    assert result == index == original and report['refused']


def test_published_homonym_keeps_both_ids_and_cannot_choose_one(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    index = {('retiredplayer', '1960-01-02'): {99: {'source_player_id': 99, 'birth_date': '1960-01-02'}}}
    result, _ = identity.merge(index, people_document(tmp_path))
    assert set(result[('retiredplayer', '1960-01-02')]) == {10, 99}


def test_declared_person_claim_cannot_differ_from_original_entity(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    supplement = people_document(tmp_path)
    supplement['batches'][0]['people'][0]['name'] = 'Invented Player'
    with pytest.raises(ValueError, match='do not reproduce'):
        identity.merge({}, supplement)


def history_document(tmp_path):
    row = dict(raw(tmp_path, history_fixture(), history.BASE + '10'), status='raw-history-parsed',
               player_id=10, events=history.parse(history_fixture(), 10))
    return {'schema_version': history.SCHEMA, 'policy': history.POLICY, 'players': [row]}


def test_additional_original_chronology_can_fill_missing_pinned_events(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'ROOT', tmp_path)
    result, report = history.merge({}, history_document(tmp_path))
    assert result[10][0]['to_club_id'] == 2 and report['accepted_player_ids'] == [10]


def test_contradicting_pinned_edge_is_not_silently_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'ROOT', tmp_path)
    index = {10: [{'date': '2005-07-01', 'from_club_id': 1, 'to_club_id': 99}]}
    before = copy.deepcopy(index)
    result, report = history.merge(index, history_document(tmp_path))
    assert result == index == before and report['refused']


def test_transfer_claim_cannot_differ_from_raw_response(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'ROOT', tmp_path)
    supplement = history_document(tmp_path)
    supplement['players'][0]['events'][0]['to_club_id'] = 99
    with pytest.raises(ValueError, match='differs from original'):
        history.merge({}, supplement)


def test_person_source_url_cannot_be_relabelled_as_another_publisher(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, 'ROOT', tmp_path)
    supplement = people_document(tmp_path)
    supplement['batches'][0]['source_url'] = 'https://example.com/fake'
    with pytest.raises(ValueError, match='endpoint'):
        identity.merge({}, supplement)
