"""Focused tests for the explicit full-roster identity label opt-in."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_historical_club_label_full_cohort_optin_v2 as optin
from scripts import season_historical_club_label_plan_v1 as label_plan
from scripts import season_historical_club_label_review_v1 as label_review
from scripts import season_release_registry_v1 as registry
from scripts import season_source_package_builder_v1 as source_builder

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'pm99-private-full-cohort-label-manager-optin-candidates-v2'
ARTIFACT_ID = 'opening-squad-preallocation-2000-01'


def _row(name: str, digest: str, index: int):
    return {
        'facts': {'name': name, 'birth_date': '2000-01-01'},
        'source_row_index': index,
        'source_row_sha256': digest * 64,
    }


def _synthetic_case(tmp_path, monkeypatch, *, target_country='portugal', target_provider=2521,
                    wrong_person_id=False, wrong_actor_proof=False, duplicate_exact_selector=False,
                    duplicate_full_cohort=False, owners_override=None):
    source_root = tmp_path / 'source'
    season_root = source_root / '2000-01'
    season_root.mkdir(parents=True)
    target_selector = {
        'club_name': 'FC Alverca', 'competition_catalog': 'PO1',
        'country_catalog': target_country,
        'source_path': f'squad/2000/PO1/{target_provider}.html',
        'source_sha256': 'a' * 64,
    }
    prior_selector = {
        'club_name': 'FC Porto', 'competition_catalog': 'PO1',
        'country_catalog': 'portugal', 'source_path': 'squad/2000/PO1/720.html',
        'source_sha256': 'b' * 64,
    }
    target_row = _row('Target Player', 'c', 0)
    prior_row = _row('Prior Player', 'd', 1)
    target_source = {'selector': target_selector, 'opening_fixture_date': '2000-08-19',
                     'opening_source_match_id': 'm-target', 'players': [target_row]}
    prior_source = {'selector': prior_selector, 'opening_fixture_date': '2000-08-19',
                    'opening_source_match_id': 'm-prior', 'players': [prior_row]}
    source_clubs = [target_source, prior_source]
    if duplicate_exact_selector:
        source_clubs.append(copy.deepcopy(target_source))
    if duplicate_full_cohort:
        other = copy.deepcopy(target_source)
        other['selector'] = {**target_selector, 'club_name': 'Alternate provider duplicate',
                             'source_path': 'squad/2000/PO1/2999.html', 'source_sha256': 'e' * 64}
        source_clubs.append(other)
    preallocation = {'schema_version': 'synthetic', 'season': '2000-01', 'source_clubs': source_clubs}
    pre_path = season_root / 'opening-squad-preallocation.json'
    pre_path.write_text(json.dumps(preallocation, sort_keys=True, separators=(',', ':')))
    artifact_sha = hashlib.sha256(pre_path.read_bytes()).hexdigest()

    artifact_id = ARTIFACT_ID
    target_person_id = source_builder._source_person_id(target_row)
    prior_person_id = source_builder._source_person_id(prior_row)
    if wrong_person_id:
        target_person_id += '-wrong'
    target_proof = 'wrong-artifact' if wrong_actor_proof else artifact_id
    package = {
        'schema_version': 'synthetic',
        'artifacts': [{'id': artifact_id, 'kind': 'season-input', 'sha256': artifact_sha}],
        'clubs': [
            {'id': 'club-623', 'carrier_id': 623, 'name': 'Old Alverca label',
             'division': 'preserve-existing-mode1-membership', 'roster_player_ids': ['player-100']},
            {'id': 'club-603', 'carrier_id': 603, 'name': 'FC Porto',
             'division': 'preserve-existing-mode1-membership', 'roster_player_ids': ['player-200']},
        ],
        'players': [
            {'id': 'player-100', 'carrier_id': 100, 'club_id': 'club-623',
             'person_id': target_person_id, 'name': 'Target Player', 'source_name': 'Target Player',
             'facts': {'birth_date': '2000-01-01'}, 'proof': {'artifact_id': target_proof}},
            {'id': 'player-200', 'carrier_id': 200, 'club_id': 'club-603',
             'person_id': prior_person_id, 'name': 'Prior Player', 'source_name': 'Prior Player',
             'facts': {'birth_date': '2000-01-01'}, 'proof': {'artifact_id': artifact_id}},
        ],
    }
    package_path = tmp_path / 'season-package.json'
    package_path.write_text(json.dumps(package, sort_keys=True, separators=(',', ':')))
    game_path = tmp_path / 'game'
    (game_path / 'DBDAT').mkdir(parents=True)
    eq_path = game_path / 'DBDAT/EQ98030.FDI'
    eq_path.write_bytes(b'synthetic indexed EQ placeholder')
    release = SimpleNamespace(release_id='synthetic-r1', package_path=package_path, game_path=game_path)

    owners = owners_override if owners_override is not None else {
        100: [{'team_carrier_id': 623, 'flag': 0}, {'team_carrier_id': 777, 'flag': 1}],
        200: [{'team_carrier_id': 603, 'flag': 0}],
    }
    monkeypatch.setattr(optin.registry, 'load_preferred_release', lambda _season: release)
    monkeypatch.setattr(optin.registry, 'relative_workspace_path', lambda path: str(path))
    monkeypatch.setattr(optin, '_native_owner_index', lambda _bytes: (None, owners))
    return {'source_root': source_root, 'preallocation': preallocation,
            'target_selector': target_selector, 'prior_selector': prior_selector,
            'target_row': target_row, 'target_person_id': target_person_id,
            'package': package, 'release': release, 'owners': owners}


def _create(case):
    return optin.create_witness(season='2000-01', source_root=case['source_root'], carrier_id=623,
        expected_source_selector=case['target_selector'],
        prior_label_source_selector=case['prior_selector'], collision_carrier_id=603)


def test_synthetic_exact_selector_provider_country_person_and_artifact_guards(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    witness = _create(case)
    assert witness['target_provider_club_id'] == 2521
    assert witness['prior_provider_club_id'] == 720
    assert witness['roster_bindings'][0]['source_person_id'] == witness['roster_bindings'][0]['person_id']
    assert witness['roster_bindings'][0]['native_active_owner_carrier_id'] == 623
    # A dormant reference in another EQ team is allowed; the active owner is unique.
    assert witness['opening_xi_certified'] is False

    wrong_country = _synthetic_case(tmp_path / 'wrong-country', monkeypatch, target_country='switzerland')
    with pytest.raises(ValueError, match='source country'):
        _create(wrong_country)

    same_provider = _synthetic_case(tmp_path / 'same-provider', monkeypatch, target_provider=720)
    with pytest.raises(ValueError, match='share one provider club ID'):
        _create(same_provider)

    wrong_person = _synthetic_case(tmp_path / 'wrong-person', monkeypatch, wrong_person_id=True)
    with pytest.raises(ValueError, match='exact source identity'):
        _create(wrong_person)

    wrong_proof = _synthetic_case(tmp_path / 'wrong-proof', monkeypatch, wrong_actor_proof=True)
    with pytest.raises(ValueError, match='current preallocation artifact'):
        _create(wrong_proof)


def test_synthetic_native_owner_and_source_candidate_guards(tmp_path, monkeypatch):
    bad_owner = {100: [{'team_carrier_id': 623, 'flag': 1}],
                 200: [{'team_carrier_id': 603, 'flag': 0}]}
    case = _synthetic_case(tmp_path / 'inactive', monkeypatch, owners_override=bad_owner)
    with pytest.raises(ValueError, match='active native EQ owner'):
        _create(case)

    duplicate_active = {100: [{'team_carrier_id': 623, 'flag': 0}, {'team_carrier_id': 777, 'flag': 0}],
                        200: [{'team_carrier_id': 603, 'flag': 0}]}
    case = _synthetic_case(tmp_path / 'duplicate-active', monkeypatch, owners_override=duplicate_active)
    with pytest.raises(ValueError, match='active native EQ owner'):
        _create(case)

    case = _synthetic_case(tmp_path / 'ambiguous', monkeypatch, duplicate_full_cohort=True)
    with pytest.raises(ValueError, match='another complete source-cohort candidate'):
        _create(case)

    case = _synthetic_case(tmp_path / 'duplicate-selector', monkeypatch, duplicate_exact_selector=True)
    with pytest.raises(ValueError, match='selector has 2 matches'):
        _create(case)


def test_synthetic_full_cohort_row_requires_single_owned_manager_and_dated_sources(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    witness = _create(case)
    with pytest.raises(ValueError, match='uniquely-owned'):
        optin.proposed_review_row(witness, manager_after='Manager A', manager_carrier_id=2032,
            manager_owner_count=2, native_manager_before='Manager before',
            manager_source_evidence=[{'path':'missing.html','sha256':'0'*64,'source_date':'2000-01-01','url':'https://example.test'}])
    with pytest.raises(ValueError, match='dated URL/path/hash'):
        optin.proposed_review_row(witness, manager_after='Manager A', manager_carrier_id=2032,
            manager_owner_count=1, native_manager_before='Manager before', manager_source_evidence=[{'sha256':'0'*64}])


def test_manager_sources_bind_named_coach_and_target_club_text(tmp_path):
    source_path = tmp_path / 'manager-source.html'
    source_path.write_text('''<!doctype html><html><head><title>Historical appointment</title>
      <style>.hidden{content:"Wrong Coach"}</style></head><body>
      <main><h1>Coach Name appointed at Target Club</h1></main>
      <script>Wrong Club Wrong Coach</script></body></html>''')
    source = {'path': str(source_path), 'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'source_date': '2000-06-01', 'url': 'https://example.test/dated-manager'}
    row = {'after': 'Target Club', 'manager_after': 'Coach Name',
        'evidence': {'manager': 'Coach Name', 'manager_source_evidence': [source]}}
    assert optin.verify_manager_sources(row) is True

    wrong_coach = copy.deepcopy(row)
    wrong_coach['manager_after'] = wrong_coach['evidence']['manager'] = 'Wrong Coach'
    with pytest.raises(ValueError, match='does not contain the named coach and target club'):
        optin.verify_manager_sources(wrong_coach)

    wrong_club = copy.deepcopy(row)
    wrong_club['after'] = 'Wrong Club'
    with pytest.raises(ValueError, match='does not contain the named coach and target club'):
        optin.verify_manager_sources(wrong_club)

    tampered = copy.deepcopy(row)
    tampered['evidence']['manager_source_evidence'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='manager source bytes changed'):
        optin.verify_manager_sources(tampered)


def _actual_optin_bundle(tmp_path):
    """Build a two-season, mixed-parent input from registered source releases."""
    candidate_path = (ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/'
        'source-club-label-scan-v1/full-cohort-optin-v1/first-three-full-cohort-optin-candidates-v2.json')
    source_root = ROOT / '.local/transfermarkt-opening-plans-current-v1'
    manager_path = (ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/'
        'source-club-label-scan-v1/first-five-history/first-five-manager-fact-review-v1.json')
    if not (candidate_path.is_file() and manager_path.is_file()):
        pytest.skip('local source-club opt-in corpus is unavailable')
    doc = json.loads(candidate_path.read_text())
    by_case = {c['candidate_id']: c for c in doc['candidates']}
    required = ['2000-01:1111', '2001-02:1352']
    if any(key not in by_case for key in required):
        pytest.skip('local full-cohort candidate rows are unavailable')
    manager_doc = json.loads(manager_path.read_text())
    manager_by_case = {(r['season'], r['carrier_id']): r for r in manager_doc['cases']}
    cases = [
        ('2000-01', 1111, 1112, 'FC Zürich', 'FC Lausanne-Sport',
         'sourced-blackpool-lambert-opening-20261024-r240a'),
        ('2001-02', 1352, 1357, 'Molde FK', 'IK Start',
         'sourced-kit-seed-remap-20261024-r239a'),
    ]
    # Explicitly require these immutable registered parents, even if a later
    # child is preferred or the local registry has advanced again.
    for season, _carrier, _prior, _target_name, _prior_name, release_id in cases:
        if not registry.locator_path(season, release_id).is_file():
            pytest.skip(f'registered source parent unavailable: {season} {release_id}')
        # Existing malformed/stale registered evidence is a failure, not an
        # optional-corpus skip.
        release = registry.load_registered_release(season, release_id)
        pre_path = source_root / season / 'opening-squad-preallocation.json'
        if not (release.package_path.is_file() and pre_path.is_file() and (release.game_path/'DBDAT/EQ98030.FDI').is_file()):
            pytest.skip(f'required source/game files unavailable for {season} {release_id}')
    result = {'schema_version': SCHEMA, 'candidates': []}
    for season, carrier, prior, target_name, prior_name, release_id in cases:
        source_doc = json.loads((source_root / season / 'opening-squad-preallocation.json').read_text())
        selectors = {row['selector']['club_name']: row['selector'] for row in source_doc['source_clubs']}
        witness = optin.create_witness(season=season, source_root=source_root, carrier_id=carrier,
            expected_source_selector=selectors[target_name], prior_label_source_selector=selectors[prior_name],
            collision_carrier_id=prior, source_release_id=release_id)
        case = by_case[f'{season}:{carrier}']
        manager = manager_by_case[(season, carrier)]
        review_row = optin.proposed_review_row(witness,
            manager_after=manager['proposed_manager_write'],
            manager_carrier_id=manager['active_manager_id'], manager_owner_count=1,
            native_manager_before=manager['current_native_manager']['name'],
            manager_source_evidence=manager['source_evidence'])
        # Preserve only fields consumed by review; witness is freshly bound to
        # the explicitly registered r240/r239 parent above.
        result['candidates'].append({'candidate_id':f'{season}:{carrier}','review_row':review_row})
    path = tmp_path / 'mixed-season-optin-v2.json'
    path.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n')
    return source_root, path, cases


def test_actual_review_to_plan_for_registered_r240_r239_and_mixed_season_bundle(tmp_path, monkeypatch):
    # Plans store workspace-relative audit paths. Temp test outputs live outside
    # the repo in pytest's tmp_path, so expose their exact paths to this test.
    monkeypatch.setattr(registry, 'relative_workspace_path', lambda path: str(path))
    source_root, witness_path, cases = _actual_optin_bundle(tmp_path)
    opening_root = source_root
    reuse_root = tmp_path / 'no-reuse'
    reuse_root.mkdir()
    out = tmp_path / 'review'

    # The no-opt-in call follows the old strict route and never emits the new status.
    season, carrier, _prior, _target, _old, release_id = cases[0]
    default_summary = label_review.review(season, source_root, opening_root, reuse_root,
        out / 'default', source_release_id=release_id, carrier_ids={carrier})
    default_row = json.loads((out/'default'/season/'club-label-review.json').read_text())['clubs'][0]
    assert default_row['status'] != 'source-supported-full-cohort-club-label-mismatch'
    assert default_row['automatic_change_authorised'] is False

    for season, carrier, _prior, expected_after, _old, release_id in cases:
        before_release = registry.load_registered_release(season, release_id)
        game_paths = [before_release.package_path, before_release.game_path/'DBDAT/EQ98030.FDI',
                      before_release.game_path/'DBDAT/ENT98030.FDI']
        before_hashes = {p:registry.sha256_file(p) for p in game_paths}
        summary = label_review.review(season, source_root, opening_root, reuse_root,
            out / 'optin', source_release_id=release_id, carrier_ids={carrier},
            full_cohort_witness_path=witness_path)
        audit_path = out / 'optin' / season / 'club-label-review.json'
        audit = json.loads(audit_path.read_text())
        assert audit['clubs'][0]['status'] == 'source-supported-full-cohort-club-label-mismatch'
        assert audit['clubs'][0]['full_cohort_witness']['release_id'] == release_id
        club_plan, manager_plan = label_plan.plan(season, audit_path, source_release_id=release_id)
        updates = [r for r in club_plan['updates'] if r['carrier_id'] == carrier]
        paired = [r for r in manager_plan['updates'] if r['club_carrier_id'] == carrier]
        if season == '2000-01':
            # The existing global manager-name collision guard correctly
            # refuses Gress while Basel's current manager carrier also has
            # that display name; this is not an opt-in identity failure.
            unresolved = [r for r in club_plan['unresolved'] if r.get('club_id') == audit['clubs'][0]['club_id']]
            assert not updates and len(unresolved) == 1
            assert 'ambiguous target club/coach' in unresolved[0]['reason']
            assert not paired
        else:
            assert len(updates) == 1 and updates[0]['after'] == expected_after, (
                season, carrier, club_plan.get('unresolved'), club_plan.get('updates'))
            assert len(paired) == 1 and paired[0]['after'] == audit['clubs'][0]['manager_after']
        assert {p:registry.sha256_file(p) for p in game_paths} == before_hashes
        # The bundle intentionally contains the other season's row too; review
        # must filter it by season while rejecting duplicate selected carriers.


def test_named_source_manager_proof_does_not_claim_a_first_xi():
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts.test_season_package_v2 import _valid_package
    package = _valid_package()
    before = package['managers'][0]
    manager = {'source_method': 'dated-source-cohort-manager-evidence-v1',
               'updates': [{'club_id': 'club-100', 'club_carrier_id': 100,
                            'manager_id': before['id'], 'carrier_id': before['carrier_id'],
                            'before': before['name'], 'before_policy': before.get('policy'),
                            'after': 'Source Coach', 'native_after': 'Coach'}]}
    result = publisher.updated_package(package, {'season': '2015-16', 'updates': []}, manager_plan=manager)
    proof = next(row for row in result['proofs'] if row['id'].startswith('proof-historical-managers-'))
    assert proof['covers'] == ['dated-named-manager-source-and-exclusive-native-owner']
    assert result['players'] == package['players'] and result['clubs'] == package['clubs']
