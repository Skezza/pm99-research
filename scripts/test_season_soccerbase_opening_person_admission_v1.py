"""Source crosswalk, role and dispatch checks; optional retained-source replay."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_soccerbase_opening_person_admission_v1 as admission
from scripts import season_opening_identity_exchange_v1 as exchange


def bound(path, root):
    return {'path': str(path.relative_to(root)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def club_case(tmp_path, monkeypatch):
    monkeypatch.setattr(admission.registry, 'ROOT', tmp_path)
    source = tmp_path / 'original.txt'
    source.write_text('Retained club selector evidence')
    group = {'provider_team_id': 7, 'club_name': 'Example'}
    destination = {'id': 'club-8', 'carrier_id': 8, 'name': 'Example Town'}
    payload = dict(schema=admission.CLUB_REVIEW_SCHEMA,
        status='reviewed-source-club-equivalence', review_id='club-example',
        reviewer='fixture', season='2000-01', provider='soccerbase',
        provider_team_id=7, provider_club_name='Example',
        native_club_id='club-8', native_club_carrier_id=8,
        native_club_name='Example Town', supporting_sources=[bound(source, tmp_path)])
    path = tmp_path / 'crosswalk.json'
    path.write_text(json.dumps(payload))
    selection = {'club_review': {'source': bound(path, tmp_path)}}
    return selection, group, destination


def test_exact_source_and_native_club_crosswalk(club_case):
    selection, group, destination = club_case
    result = admission._verify_club_review(selection, '2000-01', group, destination)
    assert result['provider_team_id'] == 7
    assert result['native_club_carrier_id'] == 8


@pytest.mark.parametrize('fault', ['provider_id', 'provider_name', 'native_id',
                                  'native_name', 'season', 'boolean_provider'])
def test_crosswalk_cannot_authorise_another_club(club_case, fault):
    selection, group, destination = club_case
    group, destination = copy.deepcopy(group), copy.deepcopy(destination)
    season = '2000-01'
    if fault == 'provider_id': group['provider_team_id'] = 9
    elif fault == 'provider_name': group['club_name'] = 'Different'
    elif fault == 'native_id': destination['carrier_id'] = 9
    elif fault == 'native_name': destination['name'] = 'Different'
    elif fault == 'season': season = '2001-02'
    else: group['provider_team_id'] = True
    with pytest.raises(ValueError, match='crosswalk'):
        admission._verify_club_review(selection, season, group, destination)


@pytest.fixture
def role_case(tmp_path, monkeypatch):
    monkeypatch.setattr(admission.registry, 'ROOT', tmp_path)
    person = {'source_player_id': 'soccerbase:99', 'name': 'Ada Example',
              'birth_date': '1980-01-02'}
    payload = dict(schema=admission.ROLE_SCHEMA, status='reviewed',
        review_id='example-role', reviewer='fixture', season='2000-01',
        source_player_id=person['source_player_id'], full_name=person['name'],
        birth_date=person['birth_date'], broad_position='D', fine_roles=[4],
        source_profile_sha256='a' * 64,
        claim_scope='editorial-fine-role-selection-not-a-published-historical-role')
    path = tmp_path / 'role.json'
    path.write_text(json.dumps(payload))
    selection = {'role_review': {'policy': admission.ROLE_POLICY,
        'profile_sha256': 'a' * 64, 'source': bound(path, tmp_path)}}
    return selection, person, path, payload


def test_editorial_role_is_explicit_and_source_bound(role_case):
    selection, person, _, _ = role_case
    roles, review = admission._verify_role_review(selection, '2000-01', person, 'D')
    assert roles == [4]
    assert review['claim_scope'].startswith('editorial-')


@pytest.mark.parametrize('fault', ['secondary_role', 'wrong_person', 'wrong_profile', 'test_status'])
def test_role_review_cannot_change_person_or_add_unrelated_role(role_case, fault):
    selection, person, path, payload = role_case
    if fault == 'secondary_role': payload['fine_roles'] = [4, 12]
    elif fault == 'wrong_person': payload['source_player_id'] = 'soccerbase:100'
    elif fault == 'wrong_profile': payload['source_profile_sha256'] = 'b' * 64
    else: payload['status'] = 'test-fixture-only'
    path.write_text(json.dumps(payload))
    selection['role_review']['source'] = bound(path, path.parent)
    with pytest.raises(ValueError):
        admission._verify_role_review(selection, '2000-01', person, 'D')


def test_exchange_dispatch_keeps_legacy_and_routes_explicit_soccerbase(monkeypatch):
    monkeypatch.setattr(exchange, '_canonical_new_person', lambda *a: {'kind': 'legacy'})
    monkeypatch.setattr(admission, 'new_person',
        lambda selection, **kwargs: {'kind': 'soccerbase', 'season': kwargs['season']})
    assert exchange.new_person({}, {}) == {'kind': 'legacy'}
    assert exchange.new_person({'admission_policy': admission.POLICY}, {},
        season='2000-01', club={'id': 'club-8'}) == {'kind': 'soccerbase', 'season': '2000-01'}
    with pytest.raises(ValueError, match='exact target'):
        exchange.new_person({'admission_policy': admission.POLICY}, {})


def test_requested_native_role_cannot_override_reviewed_source_projection(role_case, monkeypatch):
    selection, person, _, _ = role_case
    selection['fine_roles'] = [12]
    monkeypatch.setattr(admission, '_candidate', lambda *a, **kw:
        ({'source_person': person, 'source_player': {'position': 'D'}}, {}))
    with pytest.raises(ValueError, match='requested Native fine roles'):
        admission.new_person(selection, season='2000-01', destination_club={})


@pytest.mark.parametrize('pid', [92681, 209119, 107787, 151558, 107033, 145311])
def test_retained_real_sources_replay_through_canonical_dispatch(pid):
    root = admission.registry.ROOT
    folder = root / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/crawley-soccerbase-canonical-admission-root-v1'
    path = folder / f'selection-{pid}.json'
    if not path.exists(): pytest.skip('retained original Soccerbase captures unavailable')
    selection = json.loads(path.read_text())
    from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
    base = registry.load_registered_release('2025-26', 'sourced-colwyn-opening-manager-2025-26-20261104-r651a')
    club = next(c for c in pipeline.read_json_file(base.package_path)['clubs']
                if c['id'] == selection['club_id'])
    result = exchange.new_person(selection, {}, season='2025-26', club=club)
    assert result['source_person']['source_player_id'] == f'soccerbase:{pid}'
    assert result['source_person']['name'] == selection['name']
    assert result['source_person']['birth_date'] == selection['birth_date']
    assert result['raw_evidence']['fine_roles'] == selection['fine_roles']
    assert admission.source_bindings(selection)


@pytest.mark.parametrize('fault', ['date', 'game', 'person', 'body_hash', 'display'])
def test_retained_sources_reject_mutated_membership_claim(fault):
    root = admission.registry.ROOT
    folder = root / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/crawley-soccerbase-canonical-admission-root-v1'
    path = folder / 'selection-209119.json'
    if not path.exists(): pytest.skip('retained original Soccerbase captures unavailable')
    selection = json.loads(path.read_text())
    witness = selection['membership_basis']['witness']
    if fault == 'date': witness['date'] = '2025-09-12'
    elif fault == 'game': witness['game_id'] = 99999999
    elif fault == 'person': selection['provider_player_id'] = 99999999
    elif fault == 'body_hash': witness['match']['sha256'] = '0' * 64
    else: selection['native_display_name'] = 'Invented Alias'
    destination = {'id': 'english-club-372', 'carrier_id': 372, 'name': 'Crawley Town'}
    with pytest.raises(ValueError):
        exchange.new_person(selection, {}, season='2025-26', club=destination)
