import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from scripts import build_registered_quality_release_v1 as build
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.test_season_package_compiler_v2 import _native_package


def test_latest_manager_receipt_precedes_inherited_donor_role_locator(monkeypatch):
    from scripts import season_donor_keeper_role_delta_v1 as donor
    previous=SimpleNamespace(locator={'sourced_profile_assignment_plan_path':'older-donor-role.json'})
    monkeypatch.setattr(build.registry,'load_preferred_release',lambda _:previous)
    monkeypatch.setattr(build,'_build_manager_reconstruction',lambda *a,**k:{'latest_manager_replayed':True})
    monkeypatch.setattr(donor,'reconstruction',lambda *a:pytest.fail('old donor role layer must not hide latest manager transaction'))
    assert build.build('2000-01',release_id='proof')=={'latest_manager_replayed':True}


def test_latest_manager_layer_precedes_inherited_player_locator(monkeypatch):
    from scripts.test_build_registered_italian_reconstruction_v1 import isolate_newer_dispatchers
    isolate_newer_dispatchers(monkeypatch)
    from scripts import season_profile_assignment_pruning_layer_v1 as assignments
    previous = SimpleNamespace(locator={'sourced_profile_assignment_plan_path': 'older-player-layer.json'})
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda _: previous)
    monkeypatch.setattr(build, '_build_manager_reconstruction', lambda p, **k: {'latest_manager_replayed': True})
    monkeypatch.setattr(assignments, 'reconstruction', lambda *a: pytest.fail('old player layer must not hide latest manager transaction'))
    assert build.build('2002-03', release_id='proof') == {'latest_manager_replayed': True}


def setup(tmp_path, monkeypatch):
    releases = []
    for identity in ('baseline', 'candidate', 'rebuilt'):
        folder = tmp_path / identity; folder.mkdir()
        game = folder / 'game'; (game / 'DBDAT').mkdir(parents=True)
        (game / 'DBDAT/JUG98030.FDI').write_bytes(b'unchanged-player-bytes')
        for name in ('inventory.json', 'compiler.json', 'chain.json', 'manifest.json'):
            (folder / name).write_text('{}')
        releases.append(SimpleNamespace(season='2005-06', release_id=identity,
            package_path=folder/'season-package.json', game_path=game,
            inventory_path=folder/'inventory.json', compiler_receipt_path=folder/'compiler.json',
            build_chain_path=folder/'chain.json', release_manifest_path=folder/'manifest.json'))
    source, candidate, rebuilt = releases
    package = _native_package(); source.package_path.write_text(json.dumps(package))
    manager = package['managers'][0]; club = next(c for c in package['clubs'] if c['manager_id'] == manager['id'])
    plan = {'season': '2005-06', 'updates': [{'club_id': club['id'], 'manager_id': manager['id'],
        'carrier_id': manager['carrier_id'], 'club_carrier_id': club['carrier_id'],
        'before': manager['name'], 'before_policy': manager.get('policy'),
        'after': 'Luigi Del Neri', 'native_after': 'Del Neri'}]}
    descriptor = {'season': source.season, 'release_id': source.release_id,
        'package_sha256': build.registry.sha256_file(source.package_path),
        'jug_sha256': build.registry.sha256_file(source.game_path/'DBDAT/JUG98030.FDI'),
        'updates': [], 'unresolved': []}
    folder = candidate.package_path.parent
    (folder/'role-delta-input.json').write_text(json.dumps(descriptor))
    (folder/'manager-plan.json').write_text(json.dumps(plan))
    expected = publisher.updated_package(package, descriptor, manager_plan=plan)
    candidate.package_path.write_text(json.dumps(expected))
    rebuilt.package_path.write_text(json.dumps(expected))
    receipt = {'compilation_mode': 'known-good-baseline-manager-name-delta',
        'manager_plan_sha256': build.registry.sha256_file(folder/'manager-plan.json'),
        'source_season_package_sha256': build.registry.canonical_document_sha256(source.package_path),
        'source_compiler_receipt_sha256': build.registry.sha256_file(source.compiler_receipt_path),
        'source_build_chain_sha256': build.registry.sha256_file(source.build_chain_path)}
    candidate.compiler_receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setattr(build.registry, 'load_registered_release', lambda season, identity:
                        source if identity == 'baseline' else rebuilt)
    calls=[]; checks=[]
    monkeypatch.setattr(publisher, 'publish', lambda *args, **kwargs: calls.append((args,kwargs)))
    monkeypatch.setattr(build.pipeline, 'assert_tree_matches_inventory', lambda game, inventory: checks.append(game))
    return source,candidate,rebuilt,calls,checks


def test_manager_reconstruction_reuses_explicit_source_and_whole_inventory(tmp_path, monkeypatch):
    source,candidate,rebuilt,calls,checks=setup(tmp_path,monkeypatch)
    result=build._build_manager_reconstruction(candidate,release_id='rebuilt')
    assert result['complete_game_inventory_identical']
    assert calls[0][1]['source_release_id']=='baseline'
    assert calls[0][1]['register'] is False
    assert checks==[source.game_path,candidate.game_path,rebuilt.game_path]


@pytest.mark.parametrize('bad', ['recipe', 'descriptor', 'plan', 'source-receipt', 'source-chain'])
def test_unbound_edits_refuse_before_reconstruction(tmp_path,monkeypatch,bad):
    source,candidate,rebuilt,calls,checks=setup(tmp_path,monkeypatch)
    paths={'recipe':candidate.package_path,'descriptor':candidate.package_path.parent/'role-delta-input.json',
           'plan':candidate.package_path.parent/'manager-plan.json',
           'source-receipt':source.compiler_receipt_path,'source-chain':source.build_chain_path}
    path=paths[bad]; data=json.loads(path.read_text());data['unexpected']='do not discard';path.write_text(json.dumps(data))
    with pytest.raises(build.QualityBuildError):
        build._build_manager_reconstruction(candidate,release_id='rebuilt')
    assert not calls


def test_other_compilation_mode_is_not_manager_replay(tmp_path,monkeypatch):
    source,candidate,rebuilt,calls,checks=setup(tmp_path,monkeypatch)
    candidate.compiler_receipt_path.write_text(json.dumps({'compilation_mode':'other'}))
    assert build._build_manager_reconstruction(candidate,release_id='rebuilt') is None
    assert not calls


def test_latest_club_and_manager_layer_replays_before_inherited_player_layer(tmp_path, monkeypatch):
    source,candidate,rebuilt,calls,checks=setup(tmp_path,monkeypatch)
    descriptor=json.loads((candidate.package_path.parent/'role-delta-input.json').read_text())
    package=json.loads(source.package_path.read_text());club=package['clubs'][0]
    labels={'updates':[dict(club_id=club['id'],carrier_id=club['carrier_id'],before=club['name'],
        before_full=club.get('full_name'),after='Correct Club',identity_after='historical-correct-club')]}
    path=candidate.package_path.parent/'club-plan.json';path.write_text(json.dumps(labels))
    managers=json.loads((candidate.package_path.parent/'manager-plan.json').read_text())
    expected=publisher.updated_package(package,descriptor,manager_plan=managers,club_plan=labels)
    candidate.package_path.write_text(json.dumps(expected))
    rebuilt.package_path.write_text(json.dumps(expected))
    receipt=json.loads(candidate.compiler_receipt_path.read_text())
    receipt.update(compilation_mode='known-good-baseline-club-and-manager-name-delta',club_plan_sha256=build.registry.sha256_file(path))
    candidate.compiler_receipt_path.write_text(json.dumps(receipt))
    result=build._build_manager_reconstruction(candidate,release_id='rebuilt')
    assert calls[0][1]['club_plan_path']==path
    assert result['compilation_mode']=='source-bound-club-and-manager-reconstruction-not-factory-compile'
    path.write_text('{}')
    with pytest.raises(build.QualityBuildError,match='source plan changed'):
        build._build_manager_reconstruction(candidate,release_id='another')


@pytest.mark.parametrize('extra', [{'register':True}, {'modern_birth_dates':True},
    {'nationality_plan_path':'other'}, {'profile_assignment_plan_path':'other'}])
def test_explicit_club_manager_source_rejects_registration_or_other_write_lanes(monkeypatch,extra):
    monkeypatch.setattr(publisher.registry,'load_registered_release',lambda *a:SimpleNamespace())
    with pytest.raises(ValueError):
        publisher.publish('2012-13',None,release_id='proof',club_plan_path='club',
            manager_plan_path='manager',source_release_id='source',**extra)


def test_explicit_club_manager_source_requires_inert_player_input(tmp_path,monkeypatch):
    monkeypatch.setattr(publisher.registry,'load_registered_release',lambda *a:SimpleNamespace())
    path=tmp_path/'input';path.write_text(json.dumps({'updates':[{'carrier_id':1}]}))
    with pytest.raises(ValueError,match='inert player descriptor'):
        publisher.publish('2012-13',path,release_id='proof',club_plan_path='club',
            manager_plan_path='manager',source_release_id='source')


@pytest.mark.parametrize('extra', [{'register':True}, {'modern_birth_dates':True},
                                  {'nationality_plan_path':'other.json'},
                                  {'ownership_plan_path':'other.json'}])
def test_explicit_manager_source_cannot_register_or_mix_other_edit_lanes(monkeypatch, extra):
    monkeypatch.setattr(publisher.registry,'load_registered_release',lambda *args:SimpleNamespace())
    with pytest.raises(ValueError,match='unregistered Italian or manager-only replay'):
        publisher.publish('2005-06',None,release_id='proof',manager_plan_path='manager.json',
                          source_release_id='baseline',**extra)


def test_explicit_manager_source_refuses_player_updates(tmp_path,monkeypatch):
    monkeypatch.setattr(publisher.registry,'load_registered_release',lambda *args:SimpleNamespace())
    path=tmp_path/'control.json';path.write_text(json.dumps({'updates':[{'carrier_id':1}]}))
    with pytest.raises(ValueError,match='inert player descriptor'):
        publisher.publish('2005-06',path,release_id='proof',manager_plan_path='manager.json',
                          source_release_id='baseline')


@pytest.mark.parametrize('bad', [None, 'wrong-name', 'duplicate'])
def test_hashed_plan_uses_canonical_name_but_raw_receipt_hash(tmp_path,monkeypatch,bad):
    source,candidate,rebuilt,calls,checks=setup(tmp_path,monkeypatch)
    folder=candidate.package_path.parent
    plan=json.loads((folder/'manager-plan.json').read_text())
    encoded=build.pipeline.canonical_json_bytes(plan)
    canonical_sha=hashlib.sha256(encoded).hexdigest()
    path=folder/('manager-update-'+canonical_sha+'.json')
    path.write_bytes(encoded+b'\n')
    receipt=json.loads(candidate.compiler_receipt_path.read_text())
    receipt['manager_plan_sha256']=build.registry.sha256_file(path)
    candidate.compiler_receipt_path.write_text(json.dumps(receipt))
    if bad=='wrong-name': path.rename(folder/('manager-update-'+'f'*64+'.json'))
    if bad=='duplicate': (folder/('manager-update-'+'f'*64+'.json')).write_bytes(path.read_bytes())
    if bad:
        with pytest.raises(build.QualityBuildError):
            build._build_manager_reconstruction(candidate,release_id='rebuilt')
        assert not calls
    else:
        build._build_manager_reconstruction(candidate,release_id='rebuilt')
        assert calls[0][1]['manager_plan_path']==path
