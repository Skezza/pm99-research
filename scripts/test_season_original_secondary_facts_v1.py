import copy
from types import SimpleNamespace
import pytest
from scripts import season_original_secondary_facts_v1 as layer
from scripts import season_pipeline_v2 as pipeline
from scripts.test_season_original_person_birth_years_v1 import fixture as original_fixture


def fixture(tmp_path, monkeypatch):
    release, document, doc = original_fixture(tmp_path, monkeypatch)
    package = pipeline.read_json_file(release.package_path)
    person = package['players'][0]
    person['facts']['birth_date'] = '2000-07-01'
    person['fact_fallbacks'] = [dict(field='birth_date', method='deterministic-default', value='2000-07-01'),
        dict(field='height_cm', method='deterministic-default', value=180)]
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    monkeypatch.setattr(layer.compiler, '_extract_country_codes_from_textos', lambda p: {'XXX': 250, 'ENGLAND': 3, 'SPAIN': 7})
    return release, document, doc


def test_explicit_default_full_date_only_four_bytes(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    plan = layer.prepare(release, document, {'2': ['birth_date']})
    assert len(plan['updates']) == 1 and not plan['unresolved']
    assert plan['updates'][0]['birth_date'] == '2004-11-16'
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: release)
    before = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after, eq = layer.apply(before, b'eq', plan)
    assert 0 < sum(a != b for a, b in zip(before, after)) <= 4
    assert layer.apply(after, eq, plan) == (after, eq)
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    package = pipeline.read_json_file(release.package_path)
    bound = layer.bind(package, plan)
    person = bound['players'][0]
    assert person['facts']['birth_date'] == '2004-11-16'
    assert person['fact_fallbacks'] == [package['players'][0]['fact_fallbacks'][1]]
    expected = copy.deepcopy(package['players'])
    expected[0]['facts']['birth_date'] = '2004-11-16'
    expected[0]['fact_fallbacks'] = [package['players'][0]['fact_fallbacks'][1]]
    assert bound['players'] == expected
    for key in ('clubs',):
        assert bound[key] == package[key]
    with pytest.raises(ValueError, match='whole recipe preimage'):
        layer.bind(bound, plan)


@pytest.mark.parametrize('fault', ['not-default', 'not-placeholder', 'shared-owner', 'namesake', 'initial'])
def test_person_or_default_ambiguity_never_authorises_dates(tmp_path, monkeypatch, fault):
    release, document, doc = fixture(tmp_path, monkeypatch)
    package = pipeline.read_json_file(release.package_path)
    if fault == 'not-default':
        package['players'][0]['fact_fallbacks'][0]['method'] = 'source'
    elif fault == 'not-placeholder':
        package['players'][0]['facts']['birth_date'] = '2003-07-01'
        package['players'][0]['fact_fallbacks'][0]['value'] = '2003-07-01'
    elif fault == 'shared-owner':
        monkeypatch.setattr(layer.original.order, 'native_owners', lambda raw: {2: {324, 350}})
    elif fault == 'namesake':
        monkeypatch.setattr(layer.original.biographies, 'merge', lambda *a: ({}, {}))
        doc['batches'][0]['people'].append(dict(doc['batches'][0]['people'][0], birth_date='1994-11-16'))
        document.write_bytes(pipeline.canonical_json_bytes(doc))
    else:
        package['players'][0]['source_name'] = 'J. de la Cruz'
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    assert not layer.prepare(release, document, {'2': ['birth_date']})['updates']


@pytest.mark.parametrize('targets', [{}, {'2': ['role']}, {'2': ['birth_date', 'birth_date']},
    {'2': ['birth_date'], '02': ['nationality']}])
def test_scope_and_duplicate_target_aliases_refused(tmp_path, monkeypatch, targets):
    release, document, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        layer.prepare(release, document, targets)


def test_original_person_forgery_refused(tmp_path, monkeypatch):
    release, document, doc = fixture(tmp_path, monkeypatch)
    doc['batches'][0]['people'][0]['birth_date'] = '2005-11-16'
    document.write_bytes(pipeline.canonical_json_bytes(doc))
    with pytest.raises(ValueError):
        layer.prepare(release, document, {'2': ['birth_date']})


@pytest.mark.parametrize('fault', [None, 'unwitnessed-date', 'wrong-club', 'missing-period', 'wrong-period-date', 'field-scope'])
def test_namesakes_need_independent_biography_and_original_period_club(tmp_path, monkeypatch, fault):
    from scripts import original_namesake_birthday_witness_v1 as witness
    release, document, doc = fixture(tmp_path, monkeypatch)
    raw_path = tmp_path / 'people.json'
    raw = pipeline.read_json_file(raw_path)
    extra = copy.deepcopy(raw['data'][0])
    extra.update(id=78, relativeUrl='/john-de-la-cruz/profil/spieler/78')
    extra['lifeDates']['dateOfBirth'] = '1994-11-16'
    raw['data'].append(extra)
    raw_path.write_bytes(pipeline.canonical_json_bytes(raw))
    batch = doc['batches'][0]
    ids = [77, 78]
    batch.update(requested_ids=ids, source_url=layer.original.biographies.url(ids),
        raw_sha256=layer.registry.sha256_file(raw_path))
    batch['people'], batch['gaps'] = layer.original.biographies.parse(raw, ids)
    (tmp_path / 'people.source.json').write_bytes(pipeline.canonical_json_bytes(
        dict(url=batch['source_url'], sha256=batch['raw_sha256'])))
    document.write_bytes(pipeline.canonical_json_bytes(doc))
    package = pipeline.read_json_file(release.package_path)
    package['clubs'][0]['name'] = 'Sample'
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    independent = tmp_path / 'independent.json'
    independent.write_bytes(b'original independent witness fixture')
    biography = dict(name='John de la Cruz', birth_date='2004-11-16', historical_club='Sample')
    if fault == 'unwitnessed-date': biography['birth_date'] = '2005-11-16'
    if fault == 'wrong-club': biography['historical_club'] = 'Another club'
    monkeypatch.setattr(witness, 'load', lambda p: {2: biography})
    rows = [dict(country_catalog='eng', club_name='Sample',
        players=[dict(name='John de la Cruz', birth_date=None)])]
    if fault == 'wrong-period-date': rows[0]['players'][0]['birth_date'] = '1994-11-16'
    monkeypatch.setattr(layer.original.audit, 'load_sources', lambda s: ([] if fault == 'missing-period' else rows, []))
    targets = {'2': ['nationality'] if fault == 'field-scope' else ['birth_date']}
    if fault in ('wrong-club', 'field-scope'):
        with pytest.raises(ValueError):
            layer.prepare(release, document, targets, identity_document_path=independent)
    else:
        plan = layer.prepare(release, document, targets, identity_document_path=independent)
        if fault is None:
            assert len(plan['updates']) == 1 and not plan['unresolved']
            assert plan['updates'][0]['source_person']['source_player_id'] == 77
            assert plan['updates'][0]['birth_date'] == '2004-11-16'
            layer.verify(release, plan)
        else:
            assert not plan['updates']


@pytest.mark.parametrize('compact', [False, True])
def test_period_and_entity_year_only_preserves_all_recipe_facts(tmp_path, monkeypatch, compact):
    from app.fdi_indexed import IndexedFDIFile
    from app.xor import xor_encode
    release, document, _ = original_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(layer.compiler, '_extract_country_codes_from_textos', lambda p: {'XXX': 250})
    package = pipeline.read_json_file(release.package_path)
    row = dict(club_name='Other period club', players=[dict(name='John de la Cruz', birth_date='2004-11-16')])
    monkeypatch.setattr(layer.original.audit, 'load_sources', lambda s: ([row], []))
    if compact:
        path = release.game_path / 'DBDAT/JUG98030.FDI'
        before = path.read_bytes()
        entry = next(e for e in IndexedFDIFile.from_bytes(before).entries if e.record_id == 2)
        payload = bytearray(entry.decode_payload(before))
        payload[4] = 0x60
        raw = bytearray(before)
        raw[entry.payload_offset:entry.payload_offset+entry.payload_length] = xor_encode(bytes(payload))
        path.write_bytes(raw)
    plan = layer.prepare(release, document, {'2': ['native_birth_year']})
    assert len(plan['updates']) == 1 and not plan['unresolved']
    assert not plan['updates'][0]['birth_year_evidence'][0]['approves_current_club_ownership']
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: release)
    before = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after, _ = layer.apply(before, b'eq', plan)
    assert 0 < sum(a != b for a, b in zip(before, after)) <= 2
    forged = copy.deepcopy(plan)
    forged['updates'][0]['birth_date'] = '2004-11-17'
    with pytest.raises(ValueError, match='year-only scope'):
        layer.apply(before, b'eq', forged)
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    bound = layer.bind(package, plan)
    assert bound['players'] == package['players'] and bound['clubs'] == package['clubs']


@pytest.mark.parametrize('fault', ['missing', 'conflict', 'duplicate', 'initial', 'hash', 'mixed'])
def test_year_only_period_or_scope_ambiguity_refused(tmp_path, monkeypatch, fault):
    release, document, _ = original_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(layer.compiler, '_extract_country_codes_from_textos', lambda p: {'XXX': 250})
    row = dict(club_name='Other club', players=[dict(name='John de la Cruz', birth_date='2004-11-16')])
    if fault == 'conflict': row['players'].append(dict(name='John de la Cruz', birth_date='1994-11-16'))
    if fault == 'duplicate': row['players'].append(copy.deepcopy(row['players'][0]))
    if fault == 'initial': row['players'][0]['name'] = 'J. de la Cruz'
    monkeypatch.setattr(layer.original.audit, 'load_sources', lambda s: ([] if fault == 'missing' else [row], []))
    targets = {'2': ['native_birth_year', 'birth_date'] if fault == 'mixed' else ['native_birth_year']}
    if fault == 'hash':
        checker = layer.original.audit.SourceVerifier
        class WrongHash(checker):
            def verify(self, row):
                return dict(super().verify(row), source_sha256='wrong')
        monkeypatch.setattr(layer.original.audit, 'SourceVerifier', WrongHash)
    if fault in ('mixed', 'hash'):
        with pytest.raises(ValueError): layer.prepare(release, document, targets)
    else:
        assert not layer.prepare(release, document, targets)['updates']


def test_native_partial_edit_refused(tmp_path, monkeypatch):
    release, document, _ = fixture(tmp_path, monkeypatch)
    plan = layer.prepare(release, document, {'2': ['birth_date']})
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: release)
    before = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    with pytest.raises(ValueError, match='whole native'):
        layer.apply(before + b'other edit', b'eq', plan)
    with pytest.raises(ValueError, match='whole-club'):
        layer.apply(before, b'edited eq', plan)


@pytest.mark.parametrize('fault',[None,'id','period','club','dob','mixed'])
def test_direct_exact_period_person_witness_disambiguates_year_only_without_legacy_owner_row(tmp_path,monkeypatch,fault):
    from scripts import original_namesake_birthday_witness_v1 as witness
    release,document,_=original_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(layer.compiler,'_extract_country_codes_from_textos',lambda p:{'XXX':250})
    package=pipeline.read_json_file(release.package_path);package['clubs'][0]['name']='Sample'
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    independent=tmp_path/'independent.json';independent.write_bytes(b'original exact-period witness')
    bio=dict(name='John de la Cruz',birth_date='2004-11-16',historical_club='Sample',
        source_period=release.season,period_person_source_id=77,
        original_binding={'path':'original.html','sha256':layer.registry.sha256_file(tmp_path/'original.html')})
    if fault=='id':bio['period_person_source_id']=78
    if fault=='period':bio['source_period']='2023-24'
    if fault=='club':bio['historical_club']='Other club'
    if fault=='dob':bio['birth_date']='1994-11-16'
    monkeypatch.setattr(witness,'load',lambda p:{2:bio})
    monkeypatch.setattr(layer.original.audit,'load_sources',lambda s:([],[]))
    targets={'2':['native_birth_year','nationality'] if fault=='mixed' else ['native_birth_year']}
    if fault in ('id','club','mixed'):
        with pytest.raises(ValueError):layer.prepare(release,document,targets,identity_document_path=independent)
    else:
        plan=layer.prepare(release,document,targets,identity_document_path=independent)
        if fault is None:
            assert len(plan['updates'])==1 and not plan['unresolved']
            assert plan['updates'][0]['birth_year_evidence'][0]['source_period']==release.season
        else:assert not plan['updates']


def test_builder_dispatch_and_factory_proof_retention(tmp_path, monkeypatch):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path = tmp_path / 'plan.json'
    monkeypatch.setattr(reserve.pipeline, 'read_json_file', lambda p: {'schema': layer.SCHEMA} if p == path else {})
    monkeypatch.setattr(layer, 'reconstruction', lambda *a: {'secondary_fact_replay': True})
    previous = SimpleNamespace(package_path=tmp_path/'package', locator={'sourced_profile_assignment_plan_path': str(path)})
    assert reserve.reconstruction(previous, 'replay') == {'secondary_fact_replay': True}
    with pytest.raises(ValueError, match='must not discard'):
        layer.reject_factory_recipe(dict(artifacts=[dict(id=layer.PREFIX+'2025-26-example')]))


@pytest.mark.parametrize('conflict', [False, True])
def test_nationality_requires_unique_exact_dob_original_period_flag(tmp_path, monkeypatch, conflict):
    release, document, _ = fixture(tmp_path, monkeypatch)
    package = pipeline.read_json_file(release.package_path)
    person = package['players'][0]
    person['facts']['birth_date'] = '2004-11-16'
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    # Put the already corrected literal date in native before country-only work.
    year_plan = layer.original.prepare(release, document)
    raw = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    raw, _ = layer.original.apply(raw, year_plan)
    (release.game_path / 'DBDAT/JUG98030.FDI').write_bytes(raw)
    release.package_path.write_bytes(pipeline.canonical_json_bytes(package))
    rows = [dict(club_name='Other club', players=[dict(name='John de la Cruz',
        birth_date='2004-11-16', nationality='ESP')])]
    if conflict:
        rows[0]['players'][0]['nationalities'] = ['Spain', 'England']
    monkeypatch.setattr(layer.original.audit, 'load_sources', lambda season: (rows, []))
    class Checker:
        def __init__(self, season): pass
        def verify(self, source):
            return dict(status='raw-source-reparsed', local_path='original.html', source_sha256='hash')
    monkeypatch.setattr(layer.original.audit, 'SourceVerifier', Checker)
    plan = layer.prepare(release, document, {'2': ['nationality']})
    if conflict:
        assert not plan['updates']
    else:
        assert len(plan['updates']) == 1
        row = plan['updates'][0]
        assert row['nationality'] == 'ESP'
        assert not row['nationality_evidence'][0]['approves_current_club_ownership']
        monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: release)
        after, _ = layer.apply(raw, b'eq', plan)
        assert sum(a != b for a, b in zip(raw, after)) == 1
