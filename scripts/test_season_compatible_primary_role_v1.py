import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_compatible_primary_role_v1 as subject
from scripts import season_source_verified_player_changes_v1 as dispatch


ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_INPUT = ROOT / '.local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/2004-05-compatible-role-input-v1.json'


def role_plan():
    before = [4, 5, 3, 15, 0, 0]  # Sweeper, Centre-Back, Left-Back, Defensive Midfield, empty, empty.
    after = [13, 0, 0, 0, 0, 0]  # Published Centre-Forward => historical role code 12.
    masks = [dict(file='DBDAT/JUG98030.FDI', record_offset=30 + i, file_offset=100 + 30 + i,
                  before=value, after=after[i]) for i, value in enumerate(before)]
    return {'schema': dispatch.SCHEMA, 'kind': subject.KIND, 'updates': [{
        'carrier_id': 1790, 'before': {}, 'values': {'fine_roles': [12]}, 'field_mask': ['fine_roles'],
        'native_masks': masks, 'evidence': {}, 'expected_owner': 123}]}


def test_exact_conflicting_role_set_mask_is_admitted():
    subject.validate_mask(role_plan())


@pytest.mark.parametrize('fault', ['wrong_schema', 'wrong_kind', 'extra_value', 'wrong_field_mask',
                                  'multiple_roles', 'boolean_role', 'role_range', 'wrong_window',
                                  'wrong_after', 'wrong_file', 'duplicate_offset', 'mixed_offsets',
                                  'boolean_before', 'out_of_range_before', 'extra_mask_key'])
def test_role_set_mask_rejects_out_of_scope_bytes_or_values(fault):
    plan = role_plan()
    row = plan['updates'][0]
    if fault == 'wrong_schema': plan['schema'] = 'other'
    elif fault == 'wrong_kind': plan['kind'] = dispatch.KIND
    elif fault == 'extra_value': row['values']['primary_position'] = 'M'
    elif fault == 'wrong_field_mask': row['field_mask'] = ['fine_roles', 'primary_position']
    elif fault == 'multiple_roles': row['values']['fine_roles'] = [12, 8]
    elif fault == 'boolean_role': row['values']['fine_roles'] = [True]
    elif fault == 'role_range': row['values']['fine_roles'] = [18]
    elif fault == 'wrong_window': row['native_masks'][3]['record_offset'] += 1
    elif fault == 'wrong_after': row['native_masks'][1]['after'] = 1
    elif fault == 'wrong_file': row['native_masks'][0]['file'] = 'DBDAT/EQ98030.FDI'
    elif fault == 'duplicate_offset': row['native_masks'][2]['file_offset'] = row['native_masks'][1]['file_offset']
    elif fault == 'mixed_offsets': row['native_masks'][1]['file_offset'] += 1
    elif fault == 'boolean_before': row['native_masks'][0]['before'] = True
    elif fault == 'out_of_range_before': row['native_masks'][0]['before'] = 19
    elif fault == 'extra_mask_key': row['native_masks'][0]['other_offset'] = 99
    with pytest.raises(ValueError):
        subject.validate_mask(plan)


def test_dispatch_routes_new_kind_and_keeps_old_single_field_contract(monkeypatch, tmp_path):
    path = tmp_path / 'request.json'
    path.write_text('{}')
    monkeypatch.setattr(dispatch.registry, 'relative_workspace_path', lambda value: 'synthetic/request.json')
    monkeypatch.setattr(dispatch, 'original_path', lambda value: path)
    monkeypatch.setattr(dispatch.pipeline, 'read_json_file', lambda value: {'kind': subject.KIND})
    sentinel = object()
    monkeypatch.setattr(subject, 'prepare', lambda base, source, request: sentinel)
    assert dispatch.prepare(object(), path) is sentinel
    old_plan = {'schema': dispatch.SCHEMA, 'kind': dispatch.KIND, 'updates': [{
        'carrier_id': 1, 'before': {}, 'nationality': 'ENG', 'field_mask': ['nationality'],
        'native_mask': {'file': 'DBDAT/JUG98030.FDI', 'record_offset': 8, 'file_offset': 108,
                        'before': 1, 'after': 2}, 'source_identity': {}, 'source': {},
        'source_receipt': {}, 'expected_owner': 3}]}
    dispatch.validate_mask(old_plan)


def test_writer_changes_only_six_role_bytes_is_idempotent_and_rejects_mixed_image(monkeypatch, tmp_path):
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    plan = role_plan()
    masks = plan['updates'][0]['native_masks']
    before = bytearray([77] * 220)
    for mask in masks:
        before[mask['file_offset']] = mask['before']
    (dbdat / 'JUG98030.FDI').write_bytes(before)
    eq = b'unchanged native EQ'
    plan.update(season='2004-05', release_id='synthetic-parent', eq_sha256=dispatch.digest(eq))
    monkeypatch.setattr(dispatch.registry, 'load_registered_release',
                        lambda *args: SimpleNamespace(game_path=tmp_path))
    monkeypatch.setattr(dispatch, 'verify', lambda *args: None)
    after, after_eq = dispatch.apply(bytes(before), eq, plan)
    assert after_eq == eq
    assert {i for i, (a, b) in enumerate(zip(before, after)) if a != b} == {
        mask['file_offset'] for mask in masks if mask['before'] != mask['after']}
    assert dispatch.apply(after, eq, plan) == (after, eq)
    mixed = bytearray(after)
    changed = next(mask for mask in masks if mask['before'] != mask['after'])
    mixed[changed['file_offset']] = changed['before']
    with pytest.raises(ValueError, match='pre/postimages'):
        dispatch.apply(bytes(mixed), eq, plan)


def _mock_prepare(monkeypatch, tmp_path, *, old_roles=(3, 4, 2, 14, 98, 98),
                  published_name='Henrik Larsson', published_dob='1971-09-20', profile_id=3514):
    carrier, end = 1790, 10
    package_path = tmp_path / 'package.json'
    game = tmp_path / 'game'
    data = game / 'DBDAT'
    data.mkdir(parents=True)
    actor = {'carrier_id': carrier, 'id': 'player-1790', 'name': 'Henrik Larsson',
             'person_id': 'person-transfermarkt-3514',
             'source_name': 'Henrik Larsson', 'club_id': 'club-123',
             'facts': {'birth_date': '1971-09-20', 'primary_position': 'F',
                       'fine_roles': {'policy': 'preserve-existing-mode1'}}, 'ratings': {'values': {}}}
    package = {'players': [copy.deepcopy(actor)], 'clubs': [{'id': 'club-123', 'carrier_id': 123, 'name': 'Celtic'}]}
    package_path.write_text(json.dumps(package))
    jug = bytearray([44] * 150)
    encoded_old = [role + 1 if role != 98 else 0 for role in old_roles]
    jug[end + 2:end + 8] = bytes(encoded_old)
    eq = b'exact test EQ'
    (data / 'JUG98030.FDI').write_bytes(jug)
    (data / 'EQ98030.FDI').write_bytes(eq)
    base = SimpleNamespace(season='2004-05', release_id='r153a-test', package_path=package_path, game_path=game)

    class Entry:
        record_id = carrier
        payload_offset = 0
        payload_length = len(jug)

        @staticmethod
        def decode_payload(raw):
            return raw

    monkeypatch.setattr(subject.IndexedFDIFile, 'from_bytes', staticmethod(lambda raw: SimpleNamespace(entries=[Entry()])))
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: package)
    monkeypatch.setattr(subject.ownership, 'native_owners', lambda raw: {carrier: {123}})
    monkeypatch.setattr(subject, 'native_facts', lambda raw, rec: {
        'name': 'Henrik Larsson', 'birth_date': '1971-09-20', 'position': 'F'})
    monkeypatch.setattr(subject, 'read_indexed_native_roles', lambda payload, rec: (
        end, [value - 1 if value else 98 for value in payload[end + 2:end + 8]]))
    monkeypatch.setattr(subject.exchange, 'read_transfermarkt_profile', lambda profile, pid: {
        'source_player_id': str(pid), 'published_full_name': published_name,
        'published_birth_date': published_dob, 'published_profile_position': 'Centre-Forward'})
    request = {'schema': dispatch.INPUT_SCHEMA, 'kind': subject.KIND, 'season': base.season,
               'release_id': base.release_id, 'changes': [{'carrier_id': carrier, 'before': copy.deepcopy(actor),
                   'field_mask': ['fine_roles'], 'profile': {'provider_player_id': profile_id,
                   'url': f'https://www.transfermarkt.co.uk/henrik-larsson/profil/spieler/{profile_id}',
                   'path': 'synthetic/profile.html', 'sha256': 'synthetic'}}]}
    witness = ROOT / '.local/consolidated-audit-20261009/Scotland2000-label-manager-v1/larsson-facts/source-admission.json'
    return base, witness, request


def test_prepare_refuses_a_compatible_existing_primary_role(monkeypatch, tmp_path):
    base, path, request = _mock_prepare(monkeypatch, tmp_path, old_roles=(12, 98, 98, 98, 98, 98))
    with pytest.raises(ValueError, match='conflicting first role'):
        subject.prepare(base, path, request)


@pytest.mark.parametrize('fault', ['full_name', 'dob', 'provider_id'])
def test_prepare_refuses_false_biography_identity(monkeypatch, tmp_path, fault):
    args = {'published_name': 'Wrong Person', 'published_dob': '1971-09-19', 'profile_id': 3515}
    if fault == 'full_name': args.update(published_name='Wrong Person', published_dob='1971-09-20', profile_id=3514)
    elif fault == 'dob': args.update(published_name='Henrik Larsson', published_dob='1971-09-19', profile_id=3514)
    else: args.update(published_name='Henrik Larsson', published_dob='1971-09-20', profile_id=3515)
    base, path, request = _mock_prepare(monkeypatch, tmp_path, **args)
    with pytest.raises(ValueError, match='biography/native identity'):
        subject.prepare(base, path, request)


def test_profile_reader_rejects_a_noncanonical_profile_id(tmp_path, monkeypatch):
    html = tmp_path / 'profile.html'
    html.write_text('''<link rel="canonical" href="https://www.transfermarkt.co.uk/henrik-larsson/profil/spieler/3514">
      <h1 class="data-header__headline-wrapper">Henrik Larsson</h1>
      <span itemprop="birthDate">Sep 20, 1971 (55)</span>
      <span itemprop="nationality">Sweden</span>
      <span class="data-header__label">Position:<span class="data-header__content">Centre-Forward</span></span>''')
    monkeypatch.setattr(subject.exchange, 'original', lambda value: html)
    profile = {'path': 'synthetic.html', 'sha256': 'unused',
               'url': 'https://www.transfermarkt.co.uk/henrik-larsson/profil/spieler/3515'}
    with pytest.raises(ValueError, match='canonical'):
        subject.exchange.read_transfermarkt_profile(profile, 3515)


def _parent_artifact_fixture(tmp_path, monkeypatch, *, provider_ids=(3514,), witness_person='source-row-1',
                             witness_name='Henrik Larsson', actor_facts=None):
    from scripts import season_adjudicated_player_facts_v1 as adjudicated

    package_dir = tmp_path / 'parent'
    package_dir.mkdir()
    package_path = package_dir / 'season-package.json'
    package_path.write_text('{}')
    actor = {'carrier_id': 1790, 'person_id': witness_person, 'source_name': 'Henrik Larsson',
             'facts': actor_facts or {'birth_date': '1971-09-20', 'nationality': 'SWE'}}
    artifact_rows = []
    for index, provider_id in enumerate(provider_ids):
        filename = f'adjudicated-{index}.json'
        artifact_path = package_dir / filename
        witness = {'person_id': witness_person, 'full_name': witness_name,
                   'historical_identity': {'provider_player_id': provider_id}}
        plan = {'kind': adjudicated.KIND, 'updates': [{'carrier_id': 1790, 'witness': witness}]}
        raw = json.dumps(plan, sort_keys=True).encode()
        artifact_path.write_bytes(raw)
        artifact_rows.append({'id': f'source-backed-player-changes-{index}',
                              'relative_path': filename, 'sha256': hashlib.sha256(raw).hexdigest()})
    base = SimpleNamespace(package_path=package_path)
    package = {'artifacts': artifact_rows}
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda path: json.loads(Path(path).read_text()))
    monkeypatch.setattr(adjudicated, 'adjudicate', lambda witness: {
        'birth_date': '1971-09-20', 'nationality': 'SWE'})
    return base, package, actor


def test_parent_artifact_revalidates_hash_bound_identity_before_provider_id(tmp_path, monkeypatch):
    base, package, actor = _parent_artifact_fixture(tmp_path, monkeypatch)
    assert subject.historical_provider_id(base, package, actor) == 3514


@pytest.mark.parametrize('fault', ['hash', 'unavailable', 'carrier', 'person', 'name', 'facts', 'path_escape'])
def test_parent_artifact_rejects_unavailable_or_misbound_identity(tmp_path, monkeypatch, fault):
    base, package, actor = _parent_artifact_fixture(tmp_path, monkeypatch)
    artifact = package['artifacts'][0]
    if fault == 'hash':
        artifact['sha256'] = '0' * 64
    elif fault == 'unavailable':
        artifact['relative_path'] = 'missing-adjudicated.json'
    elif fault == 'carrier':
        path = base.package_path.parent / artifact['relative_path']
        plan = json.loads(path.read_text())
        plan['updates'][0]['carrier_id'] = 999
        path.write_text(json.dumps(plan, sort_keys=True))
        artifact['sha256'] = subject.registry.sha256_file(path)
    elif fault == 'person':
        path = base.package_path.parent / artifact['relative_path']
        plan = json.loads(path.read_text())
        plan['updates'][0]['witness']['person_id'] = 'different-source-row'
        path.write_text(json.dumps(plan, sort_keys=True))
        artifact['sha256'] = subject.registry.sha256_file(path)
    elif fault == 'name':
        path = base.package_path.parent / artifact['relative_path']
        plan = json.loads(path.read_text())
        plan['updates'][0]['witness']['full_name'] = 'Different Person'
        path.write_text(json.dumps(plan, sort_keys=True))
        artifact['sha256'] = subject.registry.sha256_file(path)
    elif fault == 'facts':
        from scripts import season_adjudicated_player_facts_v1 as adjudicated
        monkeypatch.setattr(adjudicated, 'adjudicate', lambda witness: {
            'birth_date': '1971-09-19', 'nationality': 'SWE'})
    elif fault == 'path_escape':
        artifact['relative_path'] = '../outside.json'
        (base.package_path.parent.parent / 'outside.json').write_text('{}')
        artifact['sha256'] = subject.registry.sha256_file(base.package_path.parent.parent / 'outside.json')
    with pytest.raises((ValueError, FileNotFoundError)):
        subject.historical_provider_id(base, package, actor)


def test_parent_artifact_rejects_ambiguous_historical_provider_ids(tmp_path, monkeypatch):
    base, package, actor = _parent_artifact_fixture(tmp_path, monkeypatch, provider_ids=(3514, 9914))
    with pytest.raises(ValueError, match='one independent historical provider ID'):
        subject.historical_provider_id(base, package, actor)


@pytest.fixture
def retained_primary_role_plan():
    if not OPTIONAL_INPUT.is_file():
        pytest.skip('retained 2004/05 primary-role input not prepared yet')
    request = dispatch.pipeline.read_json_file(OPTIONAL_INPUT)
    base = dispatch.registry.load_registered_release(request['season'], request['release_id'])
    plan = subject.prepare(base, OPTIONAL_INPUT, request)
    return base, request, plan


def test_retained_larsson_repair_is_complete_and_exact(retained_primary_role_plan):
    base, _, plan = retained_primary_role_plan
    from app.fdi_indexed import IndexedFDIFile
    from app.indexed_jug_roles import read_indexed_native_roles
    from scripts.season_within_club_reserve_repair_v1 import native_facts

    assert len(plan['updates']) == 1
    update = plan['updates'][0]
    assert update['carrier_id'] == 1790
    assert update['values'] == {'fine_roles': [12]}
    path = base.game_path / 'DBDAT/JUG98030.FDI'
    before = path.read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after, after_eq = dispatch.apply(before, eq, plan)
    assert after_eq == eq
    masks = update['native_masks']
    assert {i for i, (a, b) in enumerate(zip(before, after)) if a != b} == {
        m['file_offset'] for m in masks if m['before'] != m['after']}
    entry = next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id == 1790)
    assert read_indexed_native_roles(entry.decode_payload(after), 1790)[1] == [12, 98, 98, 98, 98, 98]
    assert native_facts(after, 1790)['position'] == 'F'
    assert dispatch.apply(after, eq, plan) == (after, eq)
    assert dispatch.apply(before, eq, plan) == (after, eq)
