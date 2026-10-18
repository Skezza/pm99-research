import copy
import sys
from types import SimpleNamespace

import pytest

from scripts import season_original_person_birth_years_v1 as original
from scripts import season_pipeline_v2 as pipeline
from scripts.test_season_cross_period_birth_years_v1 import fixture as native_fixture


def fixture(tmp_path, monkeypatch):
    release, _ = native_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(original.biographies, 'ROOT', tmp_path)
    ids = [77]
    payload = dict(success=True, data=[dict(id=77, name='John de la Cruz',
        relativeUrl='/john-de-la-cruz/profil/spieler/77',
        lifeDates=dict(dateOfBirth='2004-11-16', isDateOfBirthUnknown=False))])
    path = tmp_path / 'people.json'
    receipt = tmp_path / 'people.source.json'
    pipeline.write_canonical_json(path, payload)
    url = original.biographies.url(ids)
    sha = original.registry.sha256_file(path)
    pipeline.write_canonical_json(receipt, dict(url=url, sha256=sha))
    people, gaps = original.biographies.parse(payload, ids)
    query = tmp_path / 'original.html'
    doc = dict(schema_version=original.biographies.SCHEMA, policy=original.biographies.POLICY,
        historical_opening_inputs=[dict(path='original.html', sha256=original.registry.sha256_file(query))],
        batches=[dict(status='original-entities-parsed', requested_ids=ids, source_url=url,
            raw_path='people.json', raw_sha256=sha, source_receipt_path='people.source.json',
            people=people, gaps=gaps)])
    document = tmp_path / 'document.json'
    pipeline.write_canonical_json(document, doc)
    return release, document, doc


def test_original_entity_corrects_only_year_not_recipe_or_other_fields(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    plan = original.prepare(release, document)
    assert len(plan['updates']) == 1
    row = plan['updates'][0]
    assert row['name'] == '#4 John de la Cruz'
    assert row['birth_date'] == '2004-11-16'
    assert not row['witnesses'][0]['approves_current_club_ownership']
    raw = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    patched, changes = original.apply(raw, plan)
    assert 0 < sum(a != b for a, b in zip(raw, patched)) <= 2
    assert original.apply(patched, plan) == (patched, [])
    package = pipeline.read_json_file(release.package_path)
    bound = original.bind(package, plan)
    assert bound['players'] == package['players'] and bound['clubs'] == package['clubs']
    with pytest.raises(ValueError, match='already exists'):
        original.bind(bound, plan)


def test_current_club_or_initials_never_supply_an_identity():
    doc = dict(batches=[dict(people=[dict(name='John de la Cruz', birth_date='2004-11-16')])])
    assert not original.witnesses(doc, 'J. de la Cruz', '2004-11-16')
    assert not original.witnesses(doc, 'de la Cruz', '2004-11-16')
    assert not original.witnesses(doc, 'John de la Cruz', '2004-11-15')
    assert original.witnesses(doc, '#4 JOHN DE LA CRÚZ', '2004-11-16')


def test_conflicting_or_duplicate_same_name_entity_refused():
    person = dict(name='John de la Cruz', birth_date='2004-11-16')
    for duplicate in (copy.deepcopy(person), dict(person, birth_date='2004-11-15')):
        assert not original.witnesses(dict(batches=[dict(people=[person, duplicate])]),
            'John de la Cruz', '2004-11-16')


def test_shared_native_owner_not_cleared_by_biography(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(original.order, 'native_owners', lambda raw: {2: {324, 350}})
    plan = original.prepare(release, document)
    assert not plan['updates']
    assert 'exclusive' in plan['unresolved'][0]['reason']


@pytest.mark.parametrize('fault', ['raw', 'receipt', 'query-input', 'saved-birthday'])
def test_source_mutation_or_forged_saved_entity_stops(tmp_path, monkeypatch, fault):
    release, document, doc = fixture(tmp_path, monkeypatch)
    if fault == 'raw':
        (tmp_path / 'people.json').write_bytes(b'changed')
    elif fault == 'receipt':
        (tmp_path / 'people.source.json').write_bytes(pipeline.canonical_json_bytes(dict(url='other', sha256='forged')))
    elif fault == 'query-input':
        (tmp_path / 'original.html').write_bytes(b'changed')
    else:
        doc['batches'][0]['people'][0]['birth_date'] = '2000-01-01'
        document.write_bytes(pipeline.canonical_json_bytes(doc))
    with pytest.raises(ValueError):
        original.prepare(release, document)


def test_missing_executable_guard_stops(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'player_birth_year_guard',
        SimpleNamespace(patch_native_birth_year_guard=lambda raw: (b'changed', {})))
    with pytest.raises(ValueError, match='executable guard'):
        original.prepare(release, document)


def test_factory_must_not_drop_original_entity_proof():
    with pytest.raises(ValueError, match='must not discard'):
        original.reject_factory_recipe(dict(artifacts=[dict(id=original.PREFIX+'2024-25')]))


def test_incremental_transaction_preserves_prior_evidence(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    legacy = original.prepare(release, document)
    assert 'transaction_id' not in legacy
    assert original.filename(legacy) == original.FILENAME
    transaction = original.registry.sha256_file(document)[:12]
    plan = original.prepare(release, document, transaction_id=transaction)
    original.verify(release, plan)
    assert plan['updates'] == legacy['updates']
    package = pipeline.read_json_file(release.package_path)
    first = original.bind(package, legacy)
    second = original.bind(first, plan)
    assert second['players'] == package['players']
    assert first['artifacts'][0] in second['artifacts']
    assert len({a['relative_path'] for a in second['artifacts']}) == 2


@pytest.mark.parametrize('transaction', ['../unsafe', 'ffffffffffff', 123, 'abcd'])
def test_transaction_id_cannot_be_arbitrary_or_unsafe(tmp_path, monkeypatch, transaction):
    release, document, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='bound biography hash'):
        original.prepare(release, document, transaction_id=transaction)
