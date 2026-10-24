"""Tests for the annual source-row identity adapter.

The synthetic source-subject and legacy receipt tests run in a public clone.
Tests requiring retained local release/source artifacts skip explicitly when
those artifacts are unavailable.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_adjudicated_player_facts_v1 as adjudicated
from scripts import season_annual_row_identity_guard_v1 as annual_identity
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as changes


ROOT = Path(__file__).resolve().parents[1]
LOCAL_CASES = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/annual-row-identity-witness-v1/canonical-adapter-prototype-v1'
LOCAL_INPUTS = {
    '2002-03': LOCAL_CASES / '2002-03-annual-nationality-input-v2.json',
    '2003-04': LOCAL_CASES / '2003-04-annual-nationality-input-v2.json',
}


def _body_binding(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def _inter_fixture(tmp_path):
    url = 'https://www.inter.it/it/archivio_giocatore/G0683'
    body = (
        '<html><head><title>Javier Zanetti | Giocatori | F.C. Internazionale | inter.it</title></head>'
        '<body><div class="spec-giocatore"><h6>Nato a Buenos Aires il 10-08-1973</h6>'
        '<h6>Nazionalità: Argentina</h6></div></body></html>')
    path, digest = _body_binding(tmp_path, 'inter.html', body)
    source = {'profile_family': 'inter-archive-player-v1',
              'body': {'path': path.name, 'sha256': digest}, 'sha256': digest, 'url': url}
    official = [
        {'provider': 'inter-player-archive-v1', 'path': path.name, 'url': url, 'sha256': digest},
        {'provider': 'premier-league-sdp-player-api', 'nationality': {'code': 'ARG'}},
    ]
    return source, official


def _madrid_fixture(tmp_path, *, extra_subject=False):
    url = 'https://www.realmadrid.com/en-US/the-club/history/football-legends/clarence-seedorf/'
    extra = ('<li><div class="rm-web-legend-detail__header__card--item-text">'
             '<small>Full name</small><span>Another Subject</span></div></li>'
             '<li><div class="rm-web-legend-detail__header__card--item-text">'
             '<small>Date of birth</small><span>02/03/1975</span></div></li>') if extra_subject else ''
    body = (
        '<html><head><title>Clarence Seedorf - History | Official Real Madrid</title></head><body>'
        '<section class="rm-web-legend-detail__header__wrapper"><h1>Seedorf</h1>'
        '<ul class="rm-web-legend-detail__header__card">'
        '<li><div class="rm-web-legend-detail__header__card--item-text">'
        '<small>Full name</small><span>Clarence Seedorf</span></div></li>'
        '<li><div class="rm-web-legend-detail__header__card--item-text">'
        '<small>Date of birth</small><span>01/04/1976</span></div></li>'
        f'{extra}</ul></section></body></html>')
    path, digest = _body_binding(tmp_path, 'madrid.html', body)
    source = {'profile_family': 'realmadrid-legend-profile-v1',
              'body': {'path': path.name, 'sha256': digest}, 'sha256': digest, 'url': url}
    official = [{'path': path.name, 'url': url, 'sha256': digest}]
    return source, official


def test_synthetic_inter_named_profile_and_literal_country_code(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    source, official = _inter_fixture(tmp_path)
    parsed = annual_identity._profile_context(source, 'Javier Zanetti', '1973-08-10', official)
    assert parsed['nationality_literal'] == 'Argentina'
    assert parsed['nationality_code'] == 'ARG'

    forged = copy.deepcopy(official)
    forged[1]['nationality']['code'] = 'ITA'
    with pytest.raises(ValueError, match='literal/code conflicts'):
        annual_identity._profile_context(source, 'Javier Zanetti', '1973-08-10', forged)


def test_synthetic_realmadrid_profile_requires_unique_subject_and_dob(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    source, official = _madrid_fixture(tmp_path)
    parsed = annual_identity._profile_context(source, 'Clarence Seedorf', '1976-04-01', official)
    assert parsed['birth_date'] == '1976-04-01'

    source, official = _madrid_fixture(tmp_path, extra_subject=True)
    with pytest.raises(ValueError, match='unique labeled full name and DOB'):
        annual_identity._profile_context(source, 'Clarence Seedorf', '1976-04-01', official)


def test_synthetic_profile_body_hash_mutation_rejects(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    source, official = _madrid_fixture(tmp_path)
    source['sha256'] = '0' * 64
    source['body']['sha256'] = '0' * 64
    official[0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='retained file digest differs'):
        annual_identity._profile_context(source, 'Clarence Seedorf', '1976-04-01', official)


def test_annual_request_must_match_exact_selected_release_and_slot():
    annual = {'season': '2003-04', 'release_id': 'r184a', 'carrier_id': 20953, 'club_id': 'club-201'}
    witness = {'identity_policy': 'annual-source-row-person-identity-v1',
               'annual_identity': annual, 'person_id': 'person-source-seedorf'}
    actor = {'club_id': 'club-201', 'person_id': 'person-source-seedorf'}
    base = SimpleNamespace(season='2003-04', release_id='r184a')
    adjudicated.verify_annual_request_binding(base, 20953, actor, witness)

    invalids = [
        (SimpleNamespace(season='2002-03', release_id='r184a'), 20953, actor),
        (SimpleNamespace(season='2003-04', release_id='other'), 20953, actor),
        (base, 20954, actor),
        (base, 20953, {'club_id': 'club-other', 'person_id': 'person-source-seedorf'}),
        (base, 20953, {'club_id': 'club-201', 'person_id': 'person-other'}),
    ]
    for bad_base, carrier, bad_actor in invalids:
        with pytest.raises(ValueError, match='selected request actor or exact registered parent'):
            adjudicated.verify_annual_request_binding(bad_base, carrier, bad_actor, witness)


def _legacy_sources(tmp_path, *, envelope=False):
    body = '<html><body>Javier Zanetti Date of birth 10 August 1973</body></html>'
    digest = hashlib.sha256(body.encode()).hexdigest()
    sources = []
    for index, host in enumerate(('club.example', 'reference.example')):
        body_path = tmp_path / f'legacy-{index}.html'
        body_path.write_text(body, encoding='utf-8')
        receipt_path = tmp_path / f'legacy-{index}.json'
        exact = {'url': f'https://{host}/zanetti', 'raw_sha256': digest}
        receipt = {'sources': [exact]} if envelope else exact
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        sources.append({'url': exact['url'], 'path': body_path, 'sha256': digest,
                        'receipt': {'path': receipt_path},
                        'birth_date': {'label': 'Date of birth', 'literal': '10 August 1973',
                                       'format': '%d %B %Y'}})
    return sources


def test_legacy_receipt_contract_remains_exact_not_envelope(tmp_path, monkeypatch):
    monkeypatch.setattr(adjudicated, 'verify_historical_identity', lambda _witness: 7321)
    monkeypatch.setattr(adjudicated, 'checked', lambda binding: binding['path'])
    witness = {'full_name': 'Javier Zanetti', 'values': {'birth_date': '1973-08-10'},
               'official_sources': _legacy_sources(tmp_path)}
    assert adjudicated._adjudicate_official_sources(witness) == {'birth_date': '1973-08-10'}

    witness['official_sources'] = _legacy_sources(tmp_path, envelope=True)
    with pytest.raises(ValueError, match='original URL/SHA receipt differs'):
        adjudicated._adjudicate_official_sources(witness)


def _local_witness(season):
    path = LOCAL_INPUTS[season]
    if not path.is_file():
        pytest.skip(f'retained {season} source/release evidence is unavailable in this checkout')
    request = pipeline.read_json_file(path)
    witness = request['changes'][0]['witness']
    annual = witness.get('annual_identity', {})
    bindings = [annual.get(key) for key in ('preallocation', 'source_intake', 'package',
                                             'native_jug', 'native_eq', 'native_textos')]
    bindings += [source for source in witness.get('official_sources', [])]
    bindings += [source.get('receipt') for source in witness.get('official_sources', [])]
    bindings += [source.get('body') for source in witness.get('official_subject_contexts', [])]
    missing = []
    for binding in bindings:
        if (not isinstance(binding, dict) or not isinstance(binding.get('path'), str)
                or not (ROOT / binding['path']).is_file()):
            missing.append(binding.get('path') if isinstance(binding, dict) else None)
    if missing:
        pytest.skip(f'retained {season} evidence files are unavailable: {missing!r}')
    _optional_registered_release(request['season'], request['release_id'])
    return path, request, witness


def _optional_registered_release(season, release_id):
    locator = registry.locator_path(season, release_id)
    if not locator.is_file():
        pytest.skip(f'registered locator is unavailable: {locator}')
    # Once a locator exists, malformed/stale release data is a test failure,
    # never an optional-evidence skip.
    return registry.load_registered_release(season, release_id)


def test_optional_release_skips_only_when_locator_is_absent(tmp_path, monkeypatch):
    locator = tmp_path / 'missing' / 'locator.json'
    monkeypatch.setattr(registry, 'locator_path', lambda _season, _release: locator)
    with pytest.raises(pytest.skip.Exception, match='locator is unavailable'):
        _optional_registered_release('2003-04', 'r184a')

    locator.parent.mkdir()
    locator.write_text('{"not":"a valid release locator"}', encoding='utf-8')
    def invalid_registered_release(_season, _release):
        raise registry.RegistryError('invalid existing release locator')
    monkeypatch.setattr(registry, 'load_registered_release', invalid_registered_release)
    with pytest.raises(registry.RegistryError, match='invalid existing'):
        _optional_registered_release('2003-04', 'r184a')


@pytest.mark.parametrize('season', ['2002-03', '2003-04'])
def test_optional_retained_annual_identity_and_tamper_guards(season):
    _, _, witness = _local_witness(season)
    assert annual_identity.verify(witness)['person_id'] == witness['person_id']

    forged = copy.deepcopy(witness)
    forged['annual_identity']['source_row_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='resolve exactly once'):
        annual_identity.verify(forged)

    forged = copy.deepcopy(witness)
    forged['person_id'] = 'person-source-forged'
    with pytest.raises(ValueError, match='person identity does not derive'):
        annual_identity.verify(forged)

    forged = copy.deepcopy(witness)
    forged['annual_identity']['preallocation']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='retained file digest differs'):
        annual_identity.verify(forged)


@pytest.mark.parametrize('season', ['2002-03', '2003-04'])
def test_optional_canonical_prepare_verify_bind_apply(season):
    input_path, request, _ = _local_witness(season)
    base = registry.load_registered_release(request['season'], request['release_id'])
    plan = changes.prepare(base, input_path)
    changes.verify(base, plan)
    parent = pipeline.read_json_file(base.package_path)
    bound = changes.bind(parent, plan)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    post, post_eq = changes.apply(jug, eq, plan)
    again, again_eq = changes.apply(post, post_eq, plan)
    selected = request['changes'][0]['carrier_id']
    before_actors = {row['carrier_id']: row for row in parent['players']}
    after_actors = {row['carrier_id']: row for row in bound['players']}
    assert post != jug and post_eq == eq
    assert again == post and again_eq == post_eq
    assert all(before_actors[key] == after_actors[key] for key in before_actors if key != selected)
