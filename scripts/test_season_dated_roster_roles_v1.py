import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_dated_roster_roles_v1 as subject
from scripts import season_source_verified_player_changes_v1 as dispatch


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / '.local/consolidated-audit-20261009/Werder2013-opening-review-v1/kroos-dated-role-input-v1.json'
DFB_PATH = ROOT / '.local/consolidated-audit-20261009/Werder2013-opening-review-v1/source/club/dfb-werder-2013-14.html'


def synthetic_row(tmp_path, monkeypatch, *, title='Werder Bremen, Bundesliga 2013/14',
                  provider_id=111528, name='Felix Kroos', birthday='12.03.1991',
                  section='Mittelfeld', heading='Kader Bundesliga 2013/2014'):
    path = tmp_path / 'roster.html'
    path.write_text(f'''<!doctype html><h3>{heading}</h3>
      <table><thead><tr><th>{section}</th></tr></thead><tbody><tr>
      <td>18</td><td><a href="https://datencenter.dfb.de/profil/{provider_id}?historize_title={title.replace(' ', '+').replace(',', '%2C')}&amp;historize_url=">{name}</a></td>
      <td>{birthday}</td></tr></tbody></table>''')
    monkeypatch.setattr(subject.exchange, 'original', lambda value: path)
    return path


def period_value(url='https://datencenter.dfb.de/competitions/bundesliga/seasons/2013-2014/teams/werder-bremen',
                 provider_id=111528):
    return {'url': url, 'provider_player_id': provider_id, 'path': 'synthetic.html', 'sha256': 'unused'}


def read_row(value):
    return subject.period_row(value, '2013-14', 'Felix Kroos', '1991-03-12', 'Werder Bremen')


def test_synthetic_dated_row_yields_only_broad_midfield(tmp_path, monkeypatch):
    synthetic_row(tmp_path, monkeypatch)
    row = read_row(period_value())
    assert row == {'name': 'Felix Kroos', 'birth_date': '1991-03-12',
                   'primary_position': 'M', 'section': 'Mittelfeld',
                   'provider_player_id': 111528}


@pytest.mark.parametrize('fault', ['origin', 'scheme', 'season_path', 'heading', 'row_id',
                                  'person_name', 'club_context', 'context_season', 'birthday', 'section'])
def test_dated_row_rejects_wrong_source_or_identity(tmp_path, monkeypatch, fault):
    if fault == 'row_id':
        synthetic_row(tmp_path, monkeypatch, provider_id=999)
    elif fault == 'person_name':
        synthetic_row(tmp_path, monkeypatch, name='Felix Kroos Jr')
    elif fault == 'club_context':
        synthetic_row(tmp_path, monkeypatch, title='Bayern München, Bundesliga 2013/14')
    elif fault == 'context_season':
        synthetic_row(tmp_path, monkeypatch, title='Werder Bremen, Bundesliga 2012/13')
    elif fault == 'birthday':
        synthetic_row(tmp_path, monkeypatch, birthday='13.03.1991')
    elif fault == 'section':
        synthetic_row(tmp_path, monkeypatch, section='Torwart')
    elif fault == 'heading':
        synthetic_row(tmp_path, monkeypatch, heading='Kader Bundesliga 2012/2013')
    else:
        synthetic_row(tmp_path, monkeypatch)
    value = period_value()
    if fault == 'origin':
        value['url'] = value['url'].replace('datencenter.dfb.de', 'example.org')
    elif fault == 'scheme':
        value['url'] = value['url'].replace('https:', 'http:')
    elif fault == 'season_path':
        value['url'] = value['url'].replace('2013-2014', '2012-2013')
    with pytest.raises(ValueError):
        read_row(value)


def test_dated_row_rejects_duplicate_exact_provider_rows(tmp_path, monkeypatch):
    path = synthetic_row(tmp_path, monkeypatch)
    html = path.read_text()
    row = html[html.index('<tr>', html.index('<tbody>')):html.index('</tr>', html.index('<tbody>')) + 5]
    path.write_text(html.replace('</tbody>', row + '</tbody>'))
    with pytest.raises(ValueError, match='one exact'):
        read_row(period_value())


def profile_fixture(tmp_path, monkeypatch, *, provider_id=31910, name='Felix Kroos',
                    canonical_id=None, birthday='Mar 12, 1991'):
    canonical_id = provider_id if canonical_id is None else canonical_id
    path = tmp_path / 'profile.html'
    path.write_text(f'''<link rel="canonical" href="https://www.transfermarkt.co.uk/felix-kroos/profil/spieler/{canonical_id}">
      <h1 class="data-header__headline-wrapper">{name}</h1>
      <span itemprop="birthDate">{birthday} (35)</span>
      <span itemprop="nationality">Germany</span>
      <span class="data-header__label">Position:<span class="data-header__content">Central Midfield</span></span>''')
    monkeypatch.setattr(subject.exchange, 'original', lambda value: path)
    return path


def profile_value(provider_id=31910):
    return {'path': 'synthetic-profile.html', 'sha256': 'unused',
            'url': f'https://www.transfermarkt.co.uk/felix-kroos/profil/spieler/{provider_id}',
            'provider_player_id': provider_id}


@pytest.mark.parametrize('fault', ['request_id', 'canonical_id', 'name', 'birthday', 'origin', 'url_id'])
def test_profile_identity_dob_and_origin_are_bound(tmp_path, monkeypatch, fault):
    profile_fixture(tmp_path, monkeypatch)
    value = profile_value()
    expected_id = 31910
    if fault == 'request_id':
        value['provider_player_id'] = 12
        value['url'] = 'https://www.transfermarkt.co.uk/felix-kroos/profil/spieler/12'
        expected_id = 12
    elif fault == 'canonical_id':
        profile_fixture(tmp_path, monkeypatch, canonical_id=12)
    elif fault == 'name':
        profile_fixture(tmp_path, monkeypatch, name='Someone Else')
    elif fault == 'birthday':
        profile_fixture(tmp_path, monkeypatch, birthday='Mar 13, 1991')
    elif fault == 'origin':
        value['url'] = value['url'].replace('www.transfermarkt.co.uk', 'example.org')
    elif fault == 'url_id':
        value['url'] = value['url'].replace('/spieler/31910', '/spieler/12')
    if fault in ('request_id', 'canonical_id', 'origin', 'url_id'):
        with pytest.raises(ValueError):
            subject.exchange.read_transfermarkt_profile(value, expected_id)
    else:
        facts = subject.exchange.read_transfermarkt_profile(value, expected_id)
        if fault == 'name':
            assert facts['published_full_name'] == 'Someone Else'
        else:
            assert facts['published_full_name'] == 'Felix Kroos'
        if fault == 'birthday':
            assert facts['published_birth_date'] == '1991-03-13'
        else:
            assert facts['published_birth_date'] == '1991-03-12'


def role_plan():
    masks = []
    offsets = [12, 13, 14, 15, 16, 17, 21]
    values = [10, 0, 0, 0, 0, 0, 2]  # fine role 9; broad M
    for offset, after in zip(offsets, values):
        masks.append({'file': 'DBDAT/JUG98030.FDI', 'record_offset': offset,
                      'file_offset': 100 + offset, 'before': 77, 'after': after})
    return {'schema': dispatch.SCHEMA, 'kind': subject.KIND, 'updates': [{
        'carrier_id': 11344, 'before': {}, 'values': {'primary_position': 'M', 'fine_roles': [9]},
        'field_mask': ['primary_position', 'fine_roles'], 'native_masks': masks,
        'evidence': {}, 'expected_owner': 403}]}


def test_role_mask_admits_only_dated_broad_and_compatible_fine_role():
    subject.validate_mask(role_plan())


@pytest.mark.parametrize('fault', ['wrong_schema', 'wrong_kind', 'extra_field', 'wrong_broad',
                                  'incompatible_fine', 'boolean_fine', 'role_bytes',
                                  'broad_byte', 'wrong_file', 'duplicate_offset', 'mixed_offsets'])
def test_role_mask_rejects_unapproved_or_mixed_writes(fault):
    plan = role_plan()
    row = plan['updates'][0]
    if fault == 'wrong_schema': plan['schema'] = 'other'
    elif fault == 'wrong_kind': plan['kind'] = dispatch.KIND
    elif fault == 'extra_field': row['values']['nationality'] = 'GER'
    elif fault == 'wrong_broad': row['values']['primary_position'] = 'G'
    elif fault == 'incompatible_fine': row['values']['fine_roles'] = [0]
    elif fault == 'boolean_fine': row['values']['fine_roles'] = [True]
    elif fault == 'role_bytes': row['native_masks'][1]['after'] = 1
    elif fault == 'broad_byte': row['native_masks'][-1]['after'] = 3
    elif fault == 'wrong_file': row['native_masks'][0]['file'] = 'DBDAT/EQ98030.FDI'
    elif fault == 'duplicate_offset': row['native_masks'][1]['file_offset'] = row['native_masks'][0]['file_offset']
    elif fault == 'mixed_offsets': row['native_masks'][1]['record_offset'] += 1
    with pytest.raises(ValueError):
        subject.validate_mask(plan)


def test_dispatch_routes_new_kind_without_changing_existing_kind_validation(monkeypatch, tmp_path):
    request_path = tmp_path / 'request.json'
    request_path.write_text('{}')
    monkeypatch.setattr(dispatch, 'original_path', lambda value: request_path)
    monkeypatch.setattr(dispatch.registry, 'relative_workspace_path', lambda value: 'synthetic/request.json')
    monkeypatch.setattr(dispatch.pipeline, 'read_json_file', lambda value: {'kind': subject.KIND})
    sentinel = object()
    monkeypatch.setattr(subject, 'prepare', lambda base, path, request: sentinel)
    assert dispatch.prepare(object(), request_path) is sentinel
    # Existing single-field plan validation still runs through its original branch.
    legacy = {'schema': dispatch.SCHEMA, 'kind': dispatch.KIND, 'updates': [{
        'carrier_id': 1, 'before': {}, 'nationality': 'ENG', 'field_mask': ['nationality'],
        'native_mask': {'file': 'DBDAT/JUG98030.FDI', 'record_offset': 8, 'file_offset': 108,
                        'before': 1, 'after': 2}, 'source_identity': {}, 'source': {},
        'source_receipt': {}, 'expected_owner': 3}]}
    dispatch.validate_mask(legacy)


def test_native_apply_rejects_mixed_preimage_when_two_fields_change(monkeypatch, tmp_path):
    game = tmp_path / 'DBDAT'
    game.mkdir()
    before = bytearray([77] * 200)
    plan = role_plan()
    masks = plan['updates'][0]['native_masks']
    for mask in masks:
        mask['before'] = mask['after']
        before[mask['file_offset']] = mask['before']
    masks[0]['before'] = 11
    masks[-1]['before'] = 3
    before[masks[0]['file_offset']] = 11
    before[masks[-1]['file_offset']] = 3
    (game / 'JUG98030.FDI').write_bytes(before)
    eq = b'unchanged EQ'
    plan.update(season='2013-14', release_id='parent', eq_sha256=dispatch.digest(eq))
    monkeypatch.setattr(dispatch.registry, 'load_registered_release',
                        lambda *args: SimpleNamespace(game_path=tmp_path))
    monkeypatch.setattr(dispatch, 'verify', lambda *args: None)
    result, result_eq = dispatch.apply(bytes(before), eq, plan)
    assert result_eq == eq
    changed = [i for i, (a, b) in enumerate(zip(before, result)) if a != b]
    assert changed == [masks[0]['file_offset'], masks[-1]['file_offset']]
    mixed = bytearray(result)
    mixed[masks[0]['file_offset']] = masks[0]['before']
    with pytest.raises(ValueError, match='pre/postimages'):
        dispatch.apply(bytes(mixed), eq, plan)


@pytest.fixture
def retained_role_plan():
    if not INPUT.is_file() or not DFB_PATH.is_file():
        pytest.skip('retained Werder source witnesses unavailable')
    request = dispatch.pipeline.read_json_file(INPUT)
    if request['changes'][0]['period_source']['sha256'] != dispatch.registry.sha256_file(DFB_PATH):
        pytest.skip('retained DFB source hash differs from fixture')
    try:
        base = dispatch.registry.load_registered_release(request['season'], request['release_id'])
        plan = subject.prepare(base, INPUT, request)
    except (FileNotFoundError, ValueError, KeyError):
        pytest.skip('registered Werder parent/candidate not available for optional native integration')
    return base, request, plan


def test_retained_kroos_dfb_period_and_profile_witnesses(retained_role_plan):
    _, request, plan = retained_role_plan
    update = plan['updates'][0]
    assert update['values'] == {'primary_position': 'M', 'fine_roles': [9]}
    assert update['evidence']['parsed_period'] == {
        'name': 'Felix Kroos', 'birth_date': '1991-03-12', 'primary_position': 'M',
        'section': 'Mittelfeld', 'provider_player_id': 111528}
    assert update['evidence']['parsed_profile']['source_player_id'] == '31910'
    assert update['evidence']['parsed_profile']['published_profile_position'] == 'Central Midfield'
    assert plan['updates'][0]['before'] == request['changes'][0]['before']


@pytest.mark.parametrize('fault', ['profile_id', 'profile_name', 'profile_dob', 'dfb_url', 'dfb_hash'])
def test_retained_prepare_rejects_tampered_source_identity_or_binding(retained_role_plan, monkeypatch, fault):
    base, request, _ = retained_role_plan
    request = copy.deepcopy(request)
    if fault == 'profile_id':
        request['changes'][0]['profile']['provider_player_id'] = 12
    elif fault == 'dfb_url':
        request['changes'][0]['period_source']['url'] = request['changes'][0]['period_source']['url'].replace(
            '2013-2014', '2012-2013')
    elif fault == 'dfb_hash':
        request['changes'][0]['period_source']['sha256'] = '0' * 64
    else:
        original_read = subject.exchange.read_transfermarkt_profile

        def altered(profile, provider_id):
            facts = original_read(profile, provider_id)
            if fault == 'profile_name':
                facts['published_full_name'] = 'Felix Kroos Jr'
            else:
                facts['published_birth_date'] = '1991-03-13'
            return facts
        monkeypatch.setattr(subject.exchange, 'read_transfermarkt_profile', altered)
    with pytest.raises(ValueError):
        subject.prepare(base, INPUT, request)


def test_retained_native_role_apply_is_exact_idempotent_and_preserves_other_bytes(retained_role_plan):
    base, _, plan = retained_role_plan
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    from app.fdi_indexed import IndexedFDIFile
    from app.indexed_jug_roles import read_indexed_native_roles
    from scripts.season_historical_roster_audit_v1 import native_player

    jug_path = base.game_path / 'DBDAT/JUG98030.FDI'
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    before = jug_path.read_bytes()
    after, after_eq = dispatch.apply(before, eq, plan)
    assert after_eq == eq
    permitted = {mask['file_offset'] for row in plan['updates'] for mask in row['native_masks']
                 if mask['before'] != mask['after']}
    assert {i for i, (a, b) in enumerate(zip(before, after)) if a != b} == permitted
    carrier = plan['updates'][0]['carrier_id']
    assert native_facts(after, carrier)['position'] == 'M'
    entry = next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id == carrier)
    payload = entry.decode_payload(after)
    assert read_indexed_native_roles(payload, carrier)[1] == [9, 98, 98, 98, 98, 98]
    assert native_player(payload, carrier)['name'].casefold() == 'felix kroos'
    assert dispatch.apply(after, eq, plan) == (after, eq)
    unrelated = bytearray(before)
    unrelated[-1] ^= 1
    with pytest.raises(ValueError, match='pre/postimages'):
        dispatch.apply(bytes(unrelated), eq, plan)
