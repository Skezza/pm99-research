import copy
import json
import pytest
from scripts import combine_original_transfer_history_ledgers_v1 as combine
from scripts.test_original_public_supplement_merges_v1 import history_document


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(combine, 'ROOT', tmp_path)
    monkeypatch.setattr(combine.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(combine.history, 'ROOT', tmp_path)
    document = history_document(tmp_path)
    path = tmp_path / 'history.json'
    path.write_text(json.dumps(document))
    return path, document


def test_verified_identical_originals_are_reused(tmp_path, monkeypatch):
    path, document = prepare(tmp_path, monkeypatch)
    other = tmp_path / 'other.json'
    other.write_text(json.dumps(document))
    result = combine.combine([path, other], tmp_path / 'combined.json')
    assert result['players'] == document['players']
    assert len(result['input_ledgers']) == 2
    assert result['combined_original_ledgers_independently_replayed'] is True


def test_conflicting_original_record_is_not_selected_by_input_order(tmp_path, monkeypatch):
    path, document = prepare(tmp_path, monkeypatch)
    other = tmp_path / 'other.json'
    document['players'][0]['events'][0]['to_club_id'] = 999
    other.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='differs from original'):
        combine.combine([path, other], tmp_path / 'combined.json')
    assert not (tmp_path / 'combined.json').exists()


def test_two_verified_but_different_chronologies_are_refused(tmp_path, monkeypatch):
    path, document = prepare(tmp_path, monkeypatch)
    other = tmp_path / 'other.json'
    original = tmp_path / 'original.json'
    raw = json.loads(original.read_text())
    # Independently valid response for the same person, but a different edge.
    import hashlib
    raw['data']['history']['terminated'][0]['transferDestination']['clubId'] = '999'
    new_raw = tmp_path / 'changed.json'
    new_raw.write_text(json.dumps(raw))
    digest = hashlib.sha256(new_raw.read_bytes()).hexdigest()
    receipt = tmp_path / 'changed.source.json'
    receipt.write_text(json.dumps({'url': document['players'][0]['source_url'], 'sha256': digest}))
    row = document['players'][0]
    row.update(raw_path=new_raw.name, raw_sha256=digest, source_receipt_path=receipt.name,
               events=combine.history.parse(raw, row['player_id']))
    other.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='overlapping original histories disagree'):
        combine.combine([path, other], tmp_path / 'combined.json')


def test_duplicate_input_or_person_is_refused(tmp_path, monkeypatch):
    path, document = prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='distinct'):
        combine.combine([path, path], tmp_path / 'combined.json')
    document['players'].append(copy.deepcopy(document['players'][0]))
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='duplicate player ID'):
        combine.combine([path], tmp_path / 'combined.json')


def test_finished_ledger_is_never_overwritten(tmp_path, monkeypatch):
    path, _ = prepare(tmp_path, monkeypatch)
    output = tmp_path / 'combined.json'
    output.write_text('preserve previous receipt')
    with pytest.raises(ValueError, match='immutable'):
        combine.combine([path], output)
    assert output.read_text() == 'preserve previous receipt'
