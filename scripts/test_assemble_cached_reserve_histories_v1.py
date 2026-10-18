import json
import pytest
from scripts import assemble_cached_reserve_histories_v1 as cache
from scripts.test_original_public_supplement_merges_v1 import history_document


def test_not_yet_fetched_is_not_an_empty_chronology(tmp_path):
    assert cache.cached_record(10, tmp_path) is None


def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(cache.history, 'ROOT', tmp_path)
    folder = tmp_path / 'history'
    folder.mkdir()
    doc = history_document(folder)
    (folder / 'original.json').rename(folder / '10.json')
    (folder / 'original.source.json').rename(folder / '10.source.json')
    return folder


def test_complete_original_person_history_can_be_read_while_other_requests_are_pending(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch)
    row = cache.cached_record(10, tmp_path)
    assert row['status'] == 'raw-history-parsed'
    assert row['player_id'] == 10 and len(row['events']) == 1
    assert cache.cached_record(11, tmp_path) is None


def test_changed_receipt_is_a_hard_failure_not_unfetched(tmp_path, monkeypatch):
    folder = prepared(tmp_path, monkeypatch)
    p = folder / '10.source.json'
    receipt = json.loads(p.read_text()); receipt['url'] = 'https://example.com/fake'
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='URL/SHA differs'):
        cache.cached_record(10, tmp_path)
