"""Synthetic SOURCE and dispatch tests; no proprietary game inputs."""
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import rewrite_indexed_native_roles
from scripts import season_sourced_goalkeeper_roles_v1 as subject
from scripts import season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload


def write_fixture(path, value):
    # Deliberate synthetic corruption/initialisation, never release evidence.
    path.write_bytes(pipeline.canonical_json_bytes(value))


@pytest.fixture
def replay_case(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(publisher.package_v2, 'validate_package', lambda _: None)
    payload = bytearray(_dd6361_player_payload(2, role=3))
    end = subject.audit.native_player(bytes(payload), 2)['name_end']
    payload[end + 11] = 0 ^ 0x61
    original = _indexed_fdi([(2, '', bytes(payload))])
    corrected, _ = rewrite_indexed_native_roles(original, {2: [0]})
    player = dict(id='keeper', carrier_id=2, name='Synthetic Keeper',
                  facts=dict(birth_date='1980-01-01', primary_position='G', fine_roles=[3]))
    package = dict(players=[player], artifacts=[], proofs=[])
    plan = dict(policy=subject.POLICY, season='2000-01', release_id='parent',
        updates=[dict(player_id='keeper', carrier_id=2, name=player['name'],
                      birth_date='1980-01-01', fine_roles=[0])], unresolved=[])
    plan_path = tmp_path / 'role-plan.json'
    write_fixture(plan_path, plan)
    current = publisher.updated_package(package, plan)
    releases = {}
    for name, raw, document in [('parent', original, package), ('child', corrected, current)]:
        root = tmp_path / name
        (root / 'game/DBDAT').mkdir(parents=True)
        (root / 'game/DBDAT/JUG98030.FDI').write_bytes(raw)
        (root / 'game/DBDAT/EQ98030.FDI').write_bytes(b'unchanged synthetic roster')
        for filename, value in [('package.json', document), ('compiler.json', {}), ('chain.json', {})]:
            write_fixture(root / filename, value)
        write_fixture(root / 'inventory.json', pipeline.build_tree_inventory(root / 'game'))
        releases[name] = NS(season='2000-01', release_id=name, game_path=root / 'game',
            package_path=root / 'package.json', compiler_receipt_path=root / 'compiler.json',
            build_chain_path=root / 'chain.json', inventory_path=root / 'inventory.json',
            locator=dict(historical_role_plan_path='role-plan.json'))
    base, child = releases['parent'], releases['child']
    receipt = dict(compilation_mode='known-good-baseline-role-only-delta',
        plan_sha256=subject.registry.sha256_file(plan_path),
        source_season_package_sha256=subject.registry.canonical_document_sha256(base.package_path),
        source_compiler_receipt_sha256=subject.registry.sha256_file(base.compiler_receipt_path),
        source_build_chain_sha256=subject.registry.sha256_file(base.build_chain_path))
    write_fixture(child.compiler_receipt_path, receipt)
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda season, name: releases[name])
    monkeypatch.setattr(subject.registry, 'validate_preferred_release', lambda *a, **k: dict(valid=True))
    verified, published = [], []
    monkeypatch.setattr(subject, 'verify', lambda base, value: verified.append(base.release_id))

    def publish(season, path, **kwargs):
        published.append(kwargs)
        releases[kwargs['release_id']] = child

    monkeypatch.setattr(publisher, 'publish', publish)
    return NS(base=base, child=child, plan=plan, path=plan_path, receipt=receipt,
              verified=verified, published=published)


def test_exact_replay_uses_recorded_parent_not_factory(replay_case):
    result = subject.reconstruction(replay_case.child, 'replayed')
    assert result['complete_game_inventory_identical'] and result['complete_recipe_identical']
    assert result['clean_machine_parent_reconstruction'] is False
    assert replay_case.verified == ['parent']
    assert replay_case.published == [dict(release_id='replayed', source_release_id='parent')]


@pytest.mark.parametrize('drift', ['recipe', 'role', 'other-native', 'asset', 'plan-hash',
                                  'parent-package', 'parent-compiler', 'parent-chain',
                                  'empty', 'unresolved', 'source-proof'])
def test_preflight_drift_refuses_before_publish(replay_case, drift, monkeypatch):
    c = replay_case
    if drift == 'recipe':
        document = pipeline.read_json_file(c.child.package_path)
        document['players'][0]['facts']['birth_date'] = '1981-01-01'
        write_fixture(c.child.package_path, document)
    elif drift in ('role', 'other-native'):
        path = c.child.game_path / 'DBDAT/JUG98030.FDI'
        raw = bytearray(path.read_bytes())
        entry = IndexedFDIFile.from_bytes(raw).entries[0]
        end = subject.audit.native_player(entry.decode_payload(raw), 2)['name_end']
        raw[entry.payload_offset + end + (2 if drift == 'role' else 12)] ^= 1
        path.write_bytes(raw)
    elif drift == 'asset':
        path = c.child.game_path / 'DBDAT/EQ98030.FDI'
        path.write_bytes(b'mutated roster')
        write_fixture(c.child.inventory_path, pipeline.build_tree_inventory(c.child.game_path))
    elif drift == 'source-proof':
        monkeypatch.setattr(subject, 'verify', lambda *a: (_ for _ in ()).throw(ValueError('source refuses')))
    else:
        receipt = copy.deepcopy(c.receipt)
        if drift == 'plan-hash':
            receipt['plan_sha256'] = 'wrong'
        elif drift.startswith('parent-'):
            key = {'parent-package': 'source_season_package_sha256',
                   'parent-compiler': 'source_compiler_receipt_sha256',
                   'parent-chain': 'source_build_chain_sha256'}[drift]
            receipt[key] = 'wrong'
        else:
            plan = copy.deepcopy(c.plan)
            plan['updates' if drift == 'empty' else 'unresolved'] = [] if drift == 'empty' else ['conflict']
            write_fixture(c.path, plan)
            receipt['plan_sha256'] = subject.registry.sha256_file(c.path)
        write_fixture(c.child.compiler_receipt_path, receipt)
    with pytest.raises(ValueError):
        subject.reconstruction(c.child, 'replayed')
    assert c.published == []


@pytest.mark.parametrize('mode', ['known-good-baseline-manager-name-delta', 'artwork', 'unknown'])
def test_other_current_receipt_never_replays_keeper_ancestor(replay_case, mode):
    receipt = dict(replay_case.receipt, compilation_mode=mode)
    write_fixture(replay_case.child.compiler_receipt_path, receipt)
    assert subject.reconstruction(replay_case.child, 'replayed') is None
    assert replay_case.published == []


@pytest.mark.parametrize('selected', range(4))
def test_dispatch_newer_artwork_composition_before_keeper(monkeypatch, selected):
    from scripts import build_registered_quality_release_v1 as builder
    names = ['season_owned_club_composition_v1', 'season_visual_patch_reconstruction_v1',
             'season_paired_whole_club_reconstruction_v1', 'season_sourced_goalkeeper_roles_v1']
    calls = []
    monkeypatch.setattr(builder.registry, 'load_preferred_release', lambda _: object())
    for index, name in enumerate(names):
        def reconstruct(*args, index=index):
            calls.append(index)
            return dict(stage=index) if index == selected else None
        monkeypatch.setattr(importlib.import_module('scripts.' + name), 'reconstruction', reconstruct)
    assert builder.build('2000-01', release_id='replay') == dict(stage=selected)
    assert calls == list(range(selected + 1))


@pytest.mark.parametrize('extra', [None, 'register', 'modern_birth_dates',
    'nationality_plan_path', 'manager_plan_path', 'club_plan_path', 'ownership_plan_path',
    'visibility_plan_path', 'mode1_keeper_plan_path', 'birth_year_plan_path',
    'mode1_opening_plan_path', 'italian_opening_plan_path', 'trabzon_opening_plan_path',
    'name_only_plan_path', 'profile_assignment_plan_path', 'resume_unregistered_assignment',
    'empty', 'unresolved', 'foreign-policy'])
def test_explicit_keeper_publisher_gate_is_narrow_and_reverifies(tmp_path, monkeypatch, extra):
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    native = game / 'DBDAT/JUG98030.FDI'
    native.write_bytes(b'synthetic input; verification stops before native writer')
    package = tmp_path / 'package.json'
    package.write_text('{}')
    base = NS(release_id='parent', game_path=game, package_path=package)
    monkeypatch.setattr(publisher.registry, 'load_registered_release', lambda *a: base)
    plan = dict(policy=subject.POLICY, season='2000-01', release_id='parent', updates=[{}],
                unresolved=[], package_sha256=subject.registry.sha256_file(package),
                jug_sha256=subject.registry.sha256_file(native))
    kwargs = {}
    if extra == 'empty':
        plan['updates'] = []
    elif extra == 'unresolved':
        plan['unresolved'] = ['not approved']
    elif extra == 'foreign-policy':
        plan['policy'] = 'unreviewed-role-policy'
    elif extra:
        kwargs[extra] = True if extra in ('register', 'modern_birth_dates', 'resume_unregistered_assignment') else tmp_path / 'unrelated.json'
    path = tmp_path / 'plan.json'
    write_fixture(path, plan)
    verified = []

    class FreshVerificationReached(Exception):
        pass

    def verify(*args):
        verified.append(True)
        raise FreshVerificationReached

    monkeypatch.setattr(subject, 'verify', verify)
    if extra is None:
        with pytest.raises(FreshVerificationReached):
            publisher.publish('2000-01', path, release_id='replay', source_release_id='parent')
        assert verified == [True]
    else:
        with pytest.raises(ValueError):
            publisher.publish('2000-01', path, release_id='replay', source_release_id='parent', **kwargs)
        assert verified == []
