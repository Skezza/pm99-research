import hashlib
import json

import pytest

from scripts import capture_source_bound_people_v1 as capture
from scripts.test_season_published_person_identity_v1 import fixture


def setup_cache(tmp_path, monkeypatch, document=None):
    monkeypatch.setattr(capture.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(capture.people, 'ROOT', tmp_path)
    source = tmp_path / 'opening.json'
    source.write_text('{}')
    inputs = [dict(path='opening.json', sha256=capture.registry.sha256_file(source))]
    url = capture.people.url([10])
    key = hashlib.sha256(url.encode()).hexdigest()
    raw_path = tmp_path / 'cache' / 'people' / (key + '.json')
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps(document or fixture()))
    raw_path.with_suffix('.source.json').write_text(json.dumps(dict(
        url=url, sha256=capture.registry.sha256_file(raw_path))))
    monkeypatch.setattr(capture, 'urlopen', lambda *a, **kw: pytest.fail('retained source refetched'))
    return inputs, source, raw_path


def test_cached_original_replayed_without_network_or_current_facts(tmp_path, monkeypatch):
    inputs, _, _ = setup_cache(tmp_path, monkeypatch)
    output = tmp_path / 'out.json'
    saved = capture.capture_ids([10, 10], tmp_path / 'cache', output, inputs)
    assert saved['batches'][0]['requested_ids'] == [10]
    person = saved['batches'][0]['people'][0]
    assert person['birth_date'] == '1960-01-02'
    assert not set(person) & {'clubAssignments', 'attributes', 'portraitUrl', 'nationalityDetails'}
    assert capture.people.merge({}, saved)[1]['accepted_player_ids'] == [10]
    with pytest.raises(ValueError, match='immutable'):
        capture.capture_ids([10], tmp_path / 'cache', output, inputs)


@pytest.mark.parametrize('ids', [[], [True], [0], [-1], ['10']])
def test_unbound_or_non_integer_ids_rejected(tmp_path, ids):
    with pytest.raises(ValueError, match='positive'):
        capture.capture_ids(ids, tmp_path, tmp_path / 'out.json', [])


def test_source_change_before_acquisition_refused(tmp_path, monkeypatch):
    inputs, source, _ = setup_cache(tmp_path, monkeypatch)
    source.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='source changed'):
        capture.capture_ids([10], tmp_path / 'cache', tmp_path / 'out.json', inputs)
    assert not (tmp_path / 'out.json').exists()


def test_source_change_during_reparse_refused(tmp_path, monkeypatch):
    inputs, source, _ = setup_cache(tmp_path, monkeypatch)
    original = capture.people.parse
    def mutate(document, ids):
        source.write_text('changed')
        return original(document, ids)
    monkeypatch.setattr(capture.people, 'parse', mutate)
    with pytest.raises(ValueError, match='during acquisition'):
        capture.capture_ids([10], tmp_path / 'cache', tmp_path / 'out.json', inputs)
    assert not (tmp_path / 'out.json').exists()


def test_stale_original_receipt_refused(tmp_path, monkeypatch):
    inputs, _, raw = setup_cache(tmp_path, monkeypatch)
    raw.write_text('{}')
    with pytest.raises(ValueError, match='URL/hash differs'):
        capture.capture_ids([10], tmp_path / 'cache', tmp_path / 'out.json', inputs)


def test_unpublished_dob_remains_gap(tmp_path, monkeypatch):
    document = fixture()
    document['data'][0]['lifeDates']['isDateOfBirthUnknown'] = True
    inputs, _, _ = setup_cache(tmp_path, monkeypatch, document)
    saved = capture.capture_ids([10], tmp_path / 'cache', tmp_path / 'out.json', inputs)
    assert not saved['batches'][0]['people']
    assert saved['batches'][0]['gaps'][0]['reason'] == 'original-DOB-unpublished-or-unconfirmed'


@pytest.mark.parametrize('kind', ['redirect', 'oversize'])
def test_bad_download_refused_before_caching(tmp_path, monkeypatch, kind):
    inputs, _, raw = setup_cache(tmp_path, monkeypatch)
    raw.unlink()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def geturl(self):
            return 'https://wrong.invalid/' if kind == 'redirect' else capture.people.url([10])
        def read(self, limit):
            assert limit == 3 * 1024 * 1024 + 1
            return b' ' * limit
    monkeypatch.setattr(capture, 'urlopen', lambda *a, **kw: Response())
    with pytest.raises(ValueError, match='redirected|bounded size'):
        capture.capture_ids([10], tmp_path / 'cache', tmp_path / 'out.json', inputs)
    assert not raw.exists() and not (tmp_path / 'out.json').exists()
