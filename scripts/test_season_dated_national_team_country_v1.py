import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_dated_national_team_country_v1 as subject
from scripts import season_source_verified_player_changes_v1 as changes


URL = ('https://datencenter.dfb.de/competitions/uefa-european-championship/'
       'seasons/2008-2009/teams/germany')
NAME = 'Bastian Example'
DOB = '1980-01-02'
HEADING = 'Squad 2008'


def roster_html(*, canonical=URL, rows=None, country='Germany', heading=HEADING):
    rows = rows if rows is not None else [(NAME, DOB)]
    body_rows = ''.join(
        '<tr class="c-Table-body-row"><td>1</td><td>' + name + '</td><td>' + dob + '</td></tr>'
        for name, dob in rows)
    return f'''<html><head><link rel="canonical" href="{canonical}"></head><body>
      <h2>{country}</h2><h3>{heading}</h3><table>{body_rows}</table></body></html>'''.encode()


def source(*, url=URL, year=2008, country='Germany', heading=HEADING, body=None):
    return dict(url=url, year=year, country_label=country, squad_heading=heading,
                path='unused.html', sha256='test', body=body or roster_html())


def parse(monkeypatch, value, *, season='2008-09', name=NAME, birthday=DOB):
    monkeypatch.setattr(subject.exchange, 'original', lambda _: SimpleNamespace(
        read_bytes=lambda: value['body']))
    return subject.national_row(value, season, name, birthday)


def test_dated_national_roster_requires_exact_full_identity_and_returns_single_year_country(monkeypatch):
    parsed = parse(monkeypatch, source())
    assert parsed == dict(country_label='Germany', year=2008, full_name=NAME,
                          birth_date=DOB, original_rows=['1 Bastian Example 1980-01-02'])


@pytest.mark.parametrize('fault', [
    'wrong-season', 'wrong-source-year', 'wrong-country-url', 'foreign-host',
    'canonical-url', 'country-heading', 'squad-heading', 'wrong-name',
    'initials-only', 'wrong-dob', 'same-name-conflicting-dob',
])
def test_roster_identity_date_country_and_raw_url_binding_fail_closed(monkeypatch, fault):
    value = source()
    season, name, birthday = '2008-09', NAME, DOB
    if fault == 'wrong-season':
        season = '2009-10'
    elif fault == 'wrong-source-year':
        value['year'] = 2009
    elif fault == 'wrong-country-url':
        value['url'] = URL.replace('/germany', '/france')
    elif fault == 'foreign-host':
        value['url'] = URL.replace('datencenter.dfb.de', 'example.org')
    elif fault == 'canonical-url':
        value['body'] = roster_html(canonical=URL + '-other')
    elif fault == 'country-heading':
        value['body'] = roster_html(country='France')
    elif fault == 'squad-heading':
        value['body'] = roster_html(heading='Squad 2009')
    elif fault == 'wrong-name':
        name = 'Bastian Different'
    elif fault == 'initials-only':
        value['body'] = roster_html(rows=[('B. Example', DOB)])
    elif fault == 'wrong-dob':
        birthday = '1980-01-03'
    elif fault == 'same-name-conflicting-dob':
        value['body'] = roster_html(rows=[(NAME, DOB), (NAME, '1981-01-02')])
    with pytest.raises(ValueError):
        parse(monkeypatch, value, season=season, name=name, birthday=birthday)


def test_repeated_identical_rows_collapse_but_a_different_name_is_not_a_witness(monkeypatch):
    value = source(body=roster_html(rows=[(NAME, DOB), (NAME, DOB)]))
    parsed = parse(monkeypatch, value)
    assert len(parsed['original_rows']) == 1
    value['body'] = roster_html(rows=[('Bastian Other', DOB)])
    with pytest.raises(ValueError, match='person absent'):
        parse(monkeypatch, value)


def mask_plan():
    return dict(schema=changes.SCHEMA, kind=subject.KIND, updates=[dict(
        carrier_id=7, before={}, values={'nationality': 'GER'}, field_mask=['nationality'],
        native_masks=[dict(file='DBDAT/JUG98030.FDI', record_offset=20,
                           file_offset=120, before=33, after=44)],
        evidence={}, expected_owner=9)])


def test_country_mask_admits_only_distinct_one_byte_country_changes():
    subject.validate_mask(mask_plan())


@pytest.mark.parametrize('fault', [
    'extra-field', 'wrong-mask', 'empty', 'duplicate-carrier', 'duplicate-offset',
    'wrong-file', 'boolean-offset', 'negative-offset', 'byte-overflow', 'same-byte',
])
def test_country_mask_rejects_expanded_or_ambiguous_native_authority(fault):
    value = mask_plan()
    row = value['updates'][0]
    mask = row['native_masks'][0]
    if fault == 'extra-field':
        row['ratings'] = {}
    elif fault == 'wrong-mask':
        row['field_mask'] = ['nationality', 'name']
    elif fault == 'empty':
        value['updates'] = []
    elif fault == 'duplicate-carrier':
        value['updates'].append(copy.deepcopy(row))
    elif fault == 'duplicate-offset':
        duplicate = copy.deepcopy(row)
        duplicate['carrier_id'] = 8
        value['updates'].append(duplicate)
    elif fault == 'wrong-file':
        mask['file'] = 'DBDAT/EQ98030.FDI'
    elif fault == 'boolean-offset':
        mask['file_offset'] = True
    elif fault == 'negative-offset':
        mask['record_offset'] = -1
    elif fault == 'byte-overflow':
        mask['after'] = 256
    elif fault == 'same-byte':
        mask['after'] = mask['before']
    with pytest.raises(ValueError):
        subject.validate_mask(value)


def test_dispatcher_routes_explicit_national_team_kind_to_specialized_helper(monkeypatch, tmp_path):
    request_path = tmp_path / 'request.json'
    request = dict(schema=changes.INPUT_SCHEMA, kind=subject.KIND,
                   season='2008-09', release_id='parent', changes=[{}])
    sentinel = {'specialized': True}
    monkeypatch.setattr(changes, 'original_path', lambda _: request_path)
    monkeypatch.setattr(changes.registry, 'relative_workspace_path', lambda _: 'request.json')
    monkeypatch.setattr(changes.pipeline, 'read_json_file', lambda _: request)
    monkeypatch.setattr(subject, 'prepare', lambda base, path, value: sentinel)
    result = changes.prepare(SimpleNamespace(), request_path)
    assert result is sentinel


def test_dispatcher_does_not_route_another_kind_to_national_helper(monkeypatch, tmp_path):
    request_path = tmp_path / 'request.json'
    request = dict(schema=changes.INPUT_SCHEMA, kind=changes.KIND,
                   season='2008-09', release_id='parent', changes=[])
    monkeypatch.setattr(changes, 'original_path', lambda _: request_path)
    monkeypatch.setattr(changes.registry, 'relative_workspace_path', lambda _: 'request.json')
    monkeypatch.setattr(changes.pipeline, 'read_json_file', lambda _: request)
    monkeypatch.setattr(subject, 'prepare', lambda *args: pytest.fail('wrong dispatcher route'))
    with pytest.raises(ValueError, match='explicit supported field-change'):
        changes.prepare(SimpleNamespace(season='2008-09', release_id='parent'), request_path)


def test_mask_dispatcher_uses_national_team_policy(monkeypatch):
    value = mask_plan()
    calls = []
    monkeypatch.setattr(subject, 'validate_mask', lambda plan: calls.append(plan))
    changes.validate_mask(value)
    assert calls == [value]


TOKIC_REQUEST = (subject.exchange.registry.ROOT /
    '.local/consolidated-audit-20261009/Tokic2004-dated-country-v1/request-v1.json')


@pytest.fixture
def tokic_case(tmp_path, monkeypatch):
    if not TOKIC_REQUEST.is_file():
        pytest.skip('retained Tokic national-country request unavailable')
    request = json.loads(TOKIC_REQUEST.read_text(encoding='utf-8'))
    base = changes.registry.load_registered_release(request['season'], request['release_id'])
    original_binding = changes.binding
    monkeypatch.setattr(changes, 'binding', lambda path: original_binding(TOKIC_REQUEST))
    return base, request, tmp_path


def prepare_copy(base, request, tmp_path):
    request_path = tmp_path / 'request-copy.json'
    request_path.write_text(json.dumps(request), encoding='utf-8')
    return subject.prepare(base, request_path, request)


def test_retained_tokic_request_replays_through_complete_prepare_binding_chain(tokic_case):
    base, request, tmp_path = tokic_case
    plan = prepare_copy(base, request, tmp_path)
    assert plan['kind'] == subject.KIND
    assert len(plan['updates']) == 1
    row = plan['updates'][0]
    assert row['carrier_id'] == 11560
    assert row['values'] == {'nationality': 'CRO'}
    assert row['evidence']['parsed_national_roster']['full_name'] == 'Mario Tokić'
    assert row['native_masks'][0]['file'] == 'DBDAT/JUG98030.FDI'


@pytest.mark.parametrize('fault', ['before', 'provider-id', 'profile-name', 'profile-dob',
    'profile-country', 'owner', 'national-roster-hash'])
def test_tokic_prepare_rejects_adversarial_request_copies(tokic_case, monkeypatch, fault):
    base, original_request, tmp_path = tokic_case
    request = copy.deepcopy(original_request)
    selection = request['changes'][0]
    if fault == 'before':
        selection['before']['name'] = 'Mario Other'
    elif fault == 'provider-id':
        selection['profile']['provider_player_id'] = 4995
    elif fault in ('profile-name', 'profile-dob', 'profile-country'):
        real_reader = subject.exchange.read_transfermarkt_profile
        def altered_profile(profile, pid):
            parsed = real_reader(profile, pid)
            if fault == 'profile-name':
                parsed['published_full_name'] = 'Mario Other'
            elif fault == 'profile-dob':
                parsed['published_birth_date'] = '1975-07-24'
            else:
                parsed['published_nationality_label'] = 'Slovenia'
            return parsed
        monkeypatch.setattr(subject.exchange, 'read_transfermarkt_profile', altered_profile)
    elif fault == 'owner':
        monkeypatch.setattr(changes.ownership, 'native_owners',
            lambda eq: {11560: {9999}})
    elif fault == 'national-roster-hash':
        original = subject.exchange.original
        original_roster = selection['national_roster']
        copied_path = tmp_path / 'changed-national-roster.html'
        source_path = changes.registry.ROOT / original_roster['path']
        copied_path.write_bytes(source_path.read_bytes() + b'<!-- altered retained bytes -->')
        selection['national_roster']['path'] = str(copied_path)
        def original_with_tmp_copy(value):
            path = Path(value['path'])
            if path == copied_path:
                if changes.registry.sha256_file(path) != value['sha256']:
                    raise ValueError('opening exchange retained source changed')
                return path
            return original(value)
        monkeypatch.setattr(subject.exchange, 'original', original_with_tmp_copy)
    with pytest.raises(ValueError):
        prepare_copy(base, request, tmp_path)
