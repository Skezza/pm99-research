import json
from types import SimpleNamespace

import pytest

from scripts import season_historical_manager_plan_v1 as manager


def setup_review(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, 'ROOT', tmp_path)
    monkeypatch.setattr(manager.registry, 'ROOT', tmp_path)
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    for file in ('EQ98030.FDI', 'ENT98030.FDI'): (game / 'DBDAT' / file).write_bytes(b'native-fixture')
    package = {'clubs': [{'id': 'club-1', 'carrier_id': 1, 'manager_id': 'manager-1', 'name': 'Club',
                          'division': 'preserve-existing-mode1-membership'}],
               'managers': [{'id': 'manager-1', 'carrier_id': 1, 'name': 'Wrong Era Coach', 'policy': 'write'}]}
    path = tmp_path / 'package.json'; path.write_text(json.dumps(package))
    release = SimpleNamespace(release_id='known-release', package_path=path, game_path=game)
    monkeypatch.setattr(manager.registry, 'load_preferred_release', lambda season: release)
    evidence = tmp_path / 'original.html'; evidence.write_bytes(b'original dated coach evidence')
    row = {'club_id': 'club-1', 'club': 'Club', 'status': 'original-first-fixture-reparsed', 'playable': False,
           'native_manager_carrier_id': 1, 'native_manager_owner_count': 1, 'native_manager': 'Wrong Era Coach',
           'evidence': {'source_club_id': 55, 'date': '2000-08-01', 'manager': 'Correct Era Coach',
                        'raw_sources': [{'path': 'original.html', 'sha256': manager.registry.sha256_file(evidence)}]}}
    report = {'schema_version': manager.opening.SCHEMA, 'season': '2000-01', 'clubs': [row],
              'bindings': {'release_id': 'known-release', 'package_sha256': manager.registry.sha256_file(path),
                           'eq_sha256': manager.registry.sha256_file(game / 'DBDAT/EQ98030.FDI'),
                           'ent_sha256': manager.registry.sha256_file(game / 'DBDAT/ENT98030.FDI')}}
    audit = tmp_path / 'review.json'; audit.write_text(json.dumps(report))
    return audit, report, evidence


def test_source_bound_manager_plan_and_changed_original_rejection(tmp_path, monkeypatch):
    audit, report, evidence = setup_review(tmp_path, monkeypatch)
    result = manager.plan('2000-01', audit)
    assert result['updates'][0]['after'] == 'Correct Era Coach'
    assert result['summary']['native_name_corrections'] == 1
    evidence.write_bytes(b'different source')
    with pytest.raises(ValueError, match='source bytes changed'):
        manager.plan('2000-01', audit)


def test_shared_native_manager_is_not_renamed(tmp_path, monkeypatch):
    audit, report, _ = setup_review(tmp_path, monkeypatch)
    report['clubs'][0]['native_manager_owner_count'] = 2
    audit.write_text(json.dumps(report))
    result = manager.plan('2000-01', audit)
    assert result['updates'] == []
    assert 'shared' in result['unresolved'][0]['reason']


def test_two_foreign_slots_for_same_historical_club_are_not_guessed(tmp_path, monkeypatch):
    audit, report, _ = setup_review(tmp_path, monkeypatch)
    report['clubs'].append({**report['clubs'][0], 'club_id': 'club-2'})
    audit.write_text(json.dumps(report))
    result = manager.plan('2000-01', audit)
    assert result['updates'] == []
    assert all('multiple native carriers' in row['reason'] for row in result['unresolved'])


def test_snapshot_review_requires_same_hash_bound_manager_proof(tmp_path, monkeypatch):
    audit, report, evidence = setup_review(tmp_path, monkeypatch)
    report['schema_version'] = manager.SNAPSHOT_SCHEMA
    audit.write_text(json.dumps(report))
    assert manager.plan('2000-01', audit)['updates'][0]['after'] == 'Correct Era Coach'
    evidence.write_bytes(b'changed snapshot')
    with pytest.raises(ValueError, match='source bytes changed'):
        manager.plan('2000-01', audit)


@pytest.mark.parametrize('country', ['brazil', 'ireland', 'norway', 'sweden', 'finland'])
def test_calendar_manager_rejects_next_year_even_with_valid_original_evidence(tmp_path, monkeypatch, country):
    audit, report, _ = setup_review(tmp_path, monkeypatch)
    monkeypatch.setattr(manager, 'club_group', lambda club: country)
    report['clubs'][0]['evidence']['date'] = '2001-02-14'
    audit.write_text(json.dumps(report))
    refused = manager.plan('2000-01', audit)
    assert refused['updates'] == []
    assert 'outside season start year' in refused['unresolved'][0]['reason']
    report['clubs'][0]['evidence']['date'] = '2000-08-04'
    audit.write_text(json.dumps(report))
    assert manager.plan('2000-01', audit)['updates'][0]['after'] == 'Correct Era Coach'
