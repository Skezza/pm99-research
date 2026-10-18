import json
from types import SimpleNamespace
import pytest

from scripts import season_paired_whole_club_reconstruction_v1 as replay


def save(path, value):
    path.write_text(json.dumps(value))


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(replay.registry, 'ROOT', tmp_path)
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    native = game / 'DBDAT/JUG98030.FDI'
    native.write_bytes(b'bound original output')
    package = tmp_path / 'package.json'
    save(package, {'editorial': 'preserve this'})
    receipt = tmp_path / 'receipt.json'
    save(receipt, dict(season='2017-18', paired_asset_stage={'grounds': []},
        native_hashes={'JUG98030.FDI': replay.registry.sha256_file(native)}))
    inventory = tmp_path / 'inventory.json'
    save(inventory, replay.pipeline.build_tree_inventory(game))
    compiler = tmp_path / 'compiler.json'
    save(compiler, dict(compilation_mode=replay.MODE,
        season_package_sha256=replay.registry.canonical_document_sha256(package),
        candidate_receipt_sha256=replay.registry.sha256_file(receipt)))
    return SimpleNamespace(season='2017-18', compiler_receipt_path=compiler,
        game_path=game, package_path=package, inventory_path=inventory,
        locator=dict(paired_whole_club_candidate_receipt_path='receipt.json',
            paired_whole_club_candidate_receipt_sha256=replay.registry.sha256_file(receipt)))


def test_non_coupled_current_release_keeps_its_existing_build_path(tmp_path):
    assert replay.bound_receipt(SimpleNamespace()) is None
    p = tmp_path / 'compiler.json'
    save(p, {'compilation_mode': 'known-good-baseline-manager-name-delta'})
    assert replay.bound_receipt(SimpleNamespace(compiler_receipt_path=p)) is None


def test_exact_source_package_and_game_pass_preflight(tmp_path, monkeypatch):
    previous = setup(tmp_path, monkeypatch)
    path, receipt = replay.bound_receipt(previous)
    assert path == tmp_path / 'receipt.json'
    assert receipt['season'] == '2017-18'


@pytest.mark.parametrize('changed', ['package', 'receipt', 'native'])
def test_no_edited_recipe_or_game_is_silently_replaced(tmp_path, monkeypatch, changed):
    previous = setup(tmp_path, monkeypatch)
    path = {'package': previous.package_path, 'receipt': tmp_path / 'receipt.json',
            'native': previous.game_path / 'DBDAT/JUG98030.FDI'}[changed]
    path.write_bytes(path.read_bytes() + b' ')
    if changed == 'package':
        save(path, {'editorial': 'my new change'})
    with pytest.raises((ValueError, replay.pipeline.PipelineError)):
        replay.bound_receipt(previous)
    assert not (tmp_path / '.local').exists()


def test_latest_complete_club_dispatch_precedes_inherited_player_locator(monkeypatch):
    from scripts import build_registered_quality_release_v1 as build
    previous = SimpleNamespace(locator={'sourced_profile_assignment_plan_path': 'old-layer'},
                               compiler_receipt_path=None)
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda _: previous)
    monkeypatch.setattr(replay, 'reconstruction', lambda *a: {'complete_club_replayed': True})
    monkeypatch.setattr(build, '_build_manager_reconstruction', lambda *a, **k:
        pytest.fail('inherited transactions must not hide the latest whole-club layer'))
    assert build.build('2017-18', release_id='replay') == {'complete_club_replayed': True}


def test_non_coupled_release_keeps_the_current_manager_dispatch(monkeypatch):
    from scripts import build_registered_quality_release_v1 as build
    previous=SimpleNamespace(locator={},compiler_receipt_path=None)
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda _:previous)
    monkeypatch.setattr(replay,'reconstruction',lambda *args:None)
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *args,**kwargs:dict(manager_replayed=True))
    assert build.build('2017-18',release_id='replay')==dict(manager_replayed=True)


def test_invalid_newest_complete_club_never_falls_back_to_an_ancestor(monkeypatch):
    from scripts import build_registered_quality_release_v1 as build
    previous=SimpleNamespace(locator={},compiler_receipt_path=None)
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda _:previous)
    def reject(*args):raise ValueError('newest complete-club recipe changed')
    monkeypatch.setattr(replay,'reconstruction',reject)
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *args,**kwargs:
        pytest.fail('must not discard an invalid latest layer by replaying an ancestor'))
    with pytest.raises(ValueError,match='newest complete-club recipe changed'):
        build.build('2017-18',release_id='replay')
