import copy
from types import SimpleNamespace
import sys

import pytest
from scripts import season_cross_period_birth_years_v1 as biography
from scripts import season_pipeline_v2 as pipeline
from scripts.test_season_number_label_names_v2 import example


def fixture(tmp_path, monkeypatch, dates=('2004-11-16',)):
    jug, numeric = example()
    game = tmp_path / 'game'
    dbdat = game / 'DBDAT'
    dbdat.mkdir(parents=True)
    (dbdat / 'JUG98030.FDI').write_bytes(jug)
    (dbdat / 'EQ98030.FDI').write_bytes(b'eq')
    (game / 'MANAGPRE.EXE').write_bytes(b'exe')
    original = tmp_path / 'original.html'
    original.write_bytes(b'original published biography')
    person = copy.deepcopy(numeric['updates'][0]['before_player'])
    person['club_id'] = 'club'
    package = dict(players=[person], clubs=[dict(id='club', carrier_id=324, division='League Two')], artifacts=[])
    package_path = tmp_path / 'package.json'
    pipeline.write_canonical_json(package_path, package)
    release = SimpleNamespace(game_path=game, package_path=package_path, season='2024-25', release_id='baseline')
    monkeypatch.setattr(biography.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(biography.registry, 'supported_seasons', lambda: ['2023-24', '2024-25'])
    monkeypatch.setattr(biography.order, 'native_owners', lambda raw: {2: {324}})
    monkeypatch.setitem(sys.modules, 'player_birth_year_guard', SimpleNamespace(patch_native_birth_year_guard=lambda raw: (raw, {})))
    captures = [dict(club_name='Other club', players=[dict(name='John de la Cruz', birth_date=day)]) for day in dates]
    monkeypatch.setattr(biography.audit, 'load_sources', lambda season: (captures if season == '2023-24' else [], []))
    class Checker:
        def __init__(self, *args, **kwargs): pass
        def verify(self, capture):
            return dict(status='raw-source-reparsed', local_path='original.html', source_sha256=biography.registry.sha256_file(original))
    monkeypatch.setattr(biography.audit, 'SourceVerifier', Checker)
    return release, captures


def test_original_other_period_birthday_is_biography_not_roster(tmp_path, monkeypatch):
    release, _ = fixture(tmp_path, monkeypatch)
    plan = biography.prepare(release)
    assert len(plan['updates']) == 1
    row = plan['updates'][0]
    assert row['name'] == '#4 John de la Cruz'
    assert row['native_name'].startswith('#4')
    assert row['birth_date'] == '2004-11-16'
    assert all(not w['approves_current_club_ownership'] for w in row['witnesses'])
    biography.verify(release, plan)
    before = pipeline.read_json_file(release.package_path)
    after = biography.bind(before, plan)
    assert after['players'] == before['players']
    assert after['clubs'] == before['clubs']
    changed, rows = biography.apply((release.game_path / 'DBDAT/JUG98030.FDI').read_bytes(), plan)
    assert rows
    assert biography.apply(changed, plan) == (changed, [])


@pytest.mark.parametrize('dates', [('2005-11-16',), ('2004-11-16', '1994-11-16')])
def test_wrong_recipe_and_namesakes_are_not_forced_into_conformance(tmp_path, monkeypatch, dates):
    release, _ = fixture(tmp_path, monkeypatch, dates)
    assert not biography.prepare(release)['updates']


def test_duplicate_original_rows_refuse_identity(tmp_path, monkeypatch):
    release, captures = fixture(tmp_path, monkeypatch)
    captures[0]['players'].append(copy.deepcopy(captures[0]['players'][0]))
    assert not biography.prepare(release)['updates']


def test_shared_native_carrier_refuses_biography_update(tmp_path, monkeypatch):
    release, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(biography.order, 'native_owners', lambda raw: {2: {324, 350}})
    assert not biography.prepare(release)['updates']


def test_exact_real_name_not_initial_or_accent_guess(tmp_path, monkeypatch):
    release, captures = fixture(tmp_path, monkeypatch)
    captures[0]['players'][0]['name'] = 'J. de la Cruz'
    assert not biography.prepare(release)['updates']


def test_bound_original_hash_corruption_stops(tmp_path, monkeypatch):
    release, _ = fixture(tmp_path, monkeypatch)
    checker = biography.audit.SourceVerifier
    class CorruptChecker(checker):
        def verify(self, capture):
            result = super().verify(capture)
            result['source_sha256'] = 'forged'
            return result
    monkeypatch.setattr(biography.audit, 'SourceVerifier', CorruptChecker)
    with pytest.raises(ValueError, match='original biography bytes changed'):
        biography.prepare(release)


def test_factory_cannot_drop_biography_evidence():
    with pytest.raises(ValueError, match='must not discard'):
        biography.reject_factory_recipe(dict(artifacts=[dict(id=biography.PREFIX+'2024-25')]))
