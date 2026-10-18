"""Adversarial unit checks for the explicit Italian opening repair layer.

Small native-boundary spies exercise layer validation without reparsing the
large proprietary corpus. Canonical writers keep their own native tests.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import season_italian_opening_layer_v1 as layer
from scripts import season_package_compiler_v2 as compiler


def order_fixture(monkeypatch):
    ids = list(range(1, 17))
    rows = [(id, 0) for id in ids]
    orders = [dict(carrier_id=id, player_id=f'p{id}', native_name=f'Player {id}',
                   birth_date='1980-01-01', position='G' if id == 1 else 'M',
                   before=id + 30, factory_before=id + 60, after=id)
              for id in ids]
    plan = dict(schema_version=layer.SCHEMA, club_carrier_id=223,
                before_rows=rows + [(99, 0)], after_rows=rows,
                removed_player_ids=[99], starting_xi=ids[:11], orders=orders)
    native = {row['carrier_id']: dict(name=row['native_name'],
              birth_date=row['birth_date'], position=row['position'],
              startup_order=row['before']) for row in orders}
    calls = []
    monkeypatch.setattr(layer, 'roster_rows', lambda eq, club: ('index', b'raw', rows))
    monkeypatch.setattr(layer.facts, 'native_facts', lambda jug, id: native[id])
    def writer(jug, eq, **kwargs):
        calls.append((jug, eq, kwargs))
        return b'patched'
    monkeypatch.setattr(layer, 'patch_owned_mode1_complete_orders', writer)
    return plan, native, rows, calls


@pytest.mark.parametrize('preimage', ['before', 'factory_before', 'after'])
def test_order_accepts_only_explicit_source_factory_or_target_preimages(monkeypatch, preimage):
    plan, native, rows, calls = order_fixture(monkeypatch)
    for row in plan['orders']:
        native[row['carrier_id']]['startup_order'] = row[preimage]
    assert layer.order(b'jug', b'eq', plan) == b'patched'
    assert len(calls) == 1
    assert calls[0][2]['club_record_id'] == 223
    assert [(r.before, r.after) for r in calls[0][2]['replacements']] == [
        (row[preimage], row['after']) for row in plan['orders']]


def test_order_rejects_unbound_observed_startup_before_calling_native_writer(monkeypatch):
    plan, native, rows, calls = order_fixture(monkeypatch)
    native[16]['startup_order'] = 200
    with pytest.raises(ValueError, match='outside source/factory/target'):
        layer.order(b'jug', b'eq', plan)
    assert calls == []


@pytest.mark.parametrize('preimage', ['factory_before', 'after'])
def test_bounded_publisher_requires_exact_source_order(monkeypatch, preimage):
    plan, native, rows, calls = order_fixture(monkeypatch)
    native[1]['startup_order'] = plan['orders'][0][preimage]
    with pytest.raises(ValueError, match='exact baseline'):
        layer.order(b'jug', b'eq', plan, exact_before=True)
    assert calls == []


@pytest.mark.parametrize('problem', ['roster-id', 'roster-order', 'roster-flag',
    'duplicated-order', 'missing-order', 'duplicate-carrier', 'XI-mismatch'])
def test_order_rejects_roster_or_permutation_drift(monkeypatch, problem):
    plan, native, rows, calls = order_fixture(monkeypatch)
    if problem == 'roster-id': rows[-1] = (999, 0)
    if problem == 'roster-order': rows[0], rows[1] = rows[1], rows[0]
    if problem == 'roster-flag': rows[-1] = (16, 1)
    if problem == 'duplicated-order': plan['orders'][-1]['after'] = 1
    if problem == 'missing-order': plan['orders'].pop()
    if problem == 'duplicate-carrier': plan['orders'][-1]['carrier_id'] = 1
    if problem == 'XI-mismatch': plan['starting_xi'][-1] = 12
    # Do not share the plan's expected roster object with the native spy.
    plan['after_rows'] = [[id, 0] for id in range(1, 17)]
    with pytest.raises(ValueError):
        layer.order(b'jug', b'eq', plan)
    assert calls == []


@pytest.mark.parametrize('field,value', [('name', 'Wrong Person'),
    ('birth_date', '1981-01-01'), ('position', 'D')])
def test_order_rejects_native_identity_birthday_and_role_drift(monkeypatch, field, value):
    plan, native, rows, calls = order_fixture(monkeypatch)
    native[16][field] = value
    with pytest.raises(ValueError, match='identity/DOB/broad role'):
        layer.order(b'jug', b'eq', plan)
    assert calls == []


def test_order_does_not_suppress_native_ownership_rejection(monkeypatch):
    plan, native, rows, calls = order_fixture(monkeypatch)
    def strict_writer(*args, **kwargs):
        raise ValueError('full-XI players must have exclusive ownership')
    monkeypatch.setattr(layer, 'patch_owned_mode1_complete_orders', strict_writer)
    with pytest.raises(ValueError, match='exclusive ownership'):
        layer.order(b'jug', b'eq', plan)


def prune_fixture(monkeypatch):
    before = [(id, 0) for id in range(1, 17)] + [(99, 0)]
    after = before[:-1]
    plan = dict(schema_version=layer.SCHEMA, club_carrier_id=223,
                before_rows=[list(r) for r in before], after_rows=[list(r) for r in after],
                removed_player_ids=[99])
    calls = []
    monkeypatch.setattr(layer, 'roster_rows', lambda eq, club:
                        ('index', b'raw', before if eq == b'before' else after))
    def writer(raw, **kwargs):
        calls.append((raw, kwargs))
        return b'new-raw'
    monkeypatch.setattr(layer, 'prune_visible_mode1_roster_payload', writer)
    monkeypatch.setattr(compiler, '_rebuild_indexed', lambda eq, index, changes: b'after')
    monkeypatch.setattr(compiler, 'xor_decode', lambda raw: raw)
    monkeypatch.setattr(layer, 'preserve_other_records', lambda *args: None)
    monkeypatch.setattr(layer.ownership, 'native_owners', lambda eq:
                        {99: {223, 225}, 1: {223}} if eq == b'before'
                        else {99: {225}, 1: {223}})
    return plan, before, after, calls


def test_prune_uses_exact_preimage_and_is_noop_afterwards(monkeypatch):
    plan, before, after, calls = prune_fixture(monkeypatch)
    assert layer.prune(b'before', plan) == b'after'
    assert calls == [(b'raw', dict(expected_rows=before, removed_player_ids=[99]))]
    assert layer.prune(b'after', plan) == b'after'
    assert len(calls) == 1


@pytest.mark.parametrize('problem', ['empty', 'duplicate', 'outside', 'wrong-subset',
    'extra-row', 'schema', 'native-preimage'])
def test_prune_rejects_unapproved_subset_or_native_topology(monkeypatch, problem):
    plan, before, after, calls = prune_fixture(monkeypatch)
    if problem == 'empty': plan['removed_player_ids'] = []
    if problem == 'duplicate': plan['removed_player_ids'] = [99, 99]
    if problem == 'outside': plan['removed_player_ids'] = [100]
    if problem == 'wrong-subset': plan['after_rows'] = plan['before_rows']
    if problem == 'extra-row': plan['after_rows'].append([100, 0])
    if problem == 'schema': plan['schema_version'] = 'not-approved'
    if problem == 'native-preimage': before[-1] = (100, 0)
    with pytest.raises(ValueError):
        layer.prune(b'before', plan)
    assert calls == []


def test_prune_refuses_collateral_owner_loss(monkeypatch):
    plan, before, after, calls = prune_fixture(monkeypatch)
    monkeypatch.setattr(layer.ownership, 'native_owners', lambda eq:
                        {99: {223, 225}} if eq == b'before' else {})
    with pytest.raises(ValueError, match='another club ownership'):
        layer.prune(b'before', plan)


def test_prune_propagates_other_record_preservation_failure(monkeypatch):
    plan, before, after, calls = prune_fixture(monkeypatch)
    def reject(*args):
        raise ValueError('other EQ payload changed')
    monkeypatch.setattr(layer, 'preserve_other_records', reject)
    with pytest.raises(ValueError, match='other EQ'):
        layer.prune(b'before', plan)


def recipe_fixture():
    from scripts import season_mode1_sourced_keeper_slot_v1 as keeper
    old = keeper.PREFIX + '2006-07-223'
    club = dict(id='c223', carrier_id=223, name='Atalanta',
                roster_player_ids=['keep', 'shared', 'orphan'],
                shared_preserve_player_ids=['shared'],
                opening={'proof': {'artifact_id': old}})
    package = dict(clubs=[club, dict(id='c225', carrier_id=225,
                   roster_player_ids=['shared', 'other'])],
                   players=[dict(id=id, carrier_id=carrier, club_id=owner,
                                 policy='preserve-existing-mode1')
                            for id, carrier, owner in [('keep', 1, 'c223'),
                                ('shared', 2, 'c223'), ('orphan', 3, 'c223'),
                                ('other', 4, 'c225')]],
                   assets={'portraits': [dict(player_id=id, status='native-no-photo')
                                        for id in ['keep', 'shared', 'orphan', 'other']]},
                   artifacts=[dict(id=old, kind='season-input', relative_path='r49.json',
                                   sha256='a' * 64)],
                   sources=[dict(evidence_artifact_id=old)],
                   proofs=[dict(artifact_id=old)])
    plan = dict(schema_version=layer.SCHEMA, season='2006-07', club_id='c223',
                club_carrier_id=223, before_club=copy.deepcopy(club),
                removed_player_ids=[2, 3])
    return package, plan, old


def test_bind_retires_orphan_and_R49_but_keeps_surviving_shared_person(monkeypatch):
    package, plan, old = recipe_fixture()
    original = copy.deepcopy(package)
    validated = []
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: validated.append(p))
    result = layer.bind(package, plan)
    assert package == original
    assert len(validated) == 1
    assert result['clubs'][0]['roster_player_ids'] == ['keep']
    assert result['clubs'][0]['shared_preserve_player_ids'] == []
    assert result['clubs'][1] == original['clubs'][1]
    assert [p['id'] for p in result['players']] == ['keep', 'shared', 'other']
    shared = next(p for p in result['players'] if p['id'] == 'shared')
    expected = copy.deepcopy(original['players'][1]); expected['club_id'] = 'c225'
    assert shared == expected
    assert [p['player_id'] for p in result['assets']['portraits']] == ['keep', 'shared', 'other']
    historical = next(a for a in result['artifacts'] if a['id'] == 'retained-' + old)
    assert {k: v for k, v in historical.items() if k != 'id'} == {
        k: v for k, v in original['artifacts'][0].items() if k != 'id'}
    assert result['clubs'][0]['opening']['proof']['artifact_id'] == 'retained-' + old
    assert result['sources'][0]['evidence_artifact_id'] == 'retained-' + old
    assert result['proofs'][0]['artifact_id'] == 'retained-' + old
    assert not any(a['id'] == old for a in result['artifacts'])
    artifact = next(a for a in result['artifacts'] if a['id'].startswith(layer.PREFIX))
    assert artifact['sha256'] == layer.packages.sha256_bytes(layer.packages.canonical_json_bytes(plan))


def test_bind_refuses_changed_recipe_club_preimage(monkeypatch):
    package, plan, old = recipe_fixture()
    package['clubs'][0]['name'] = 'Wrong Club'
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError, match='preimage changed'):
        layer.bind(package, plan)


def test_source_review_reparses_explicit_release_not_current_preferred(tmp_path, monkeypatch):
    release = SimpleNamespace(season='2006-07', release_id='original',
                              package_path=tmp_path / 'package.json')
    release.package_path.write_bytes(b'original')
    review = dict(season=release.season, source_release_id=release.release_id,
                  source_package_sha256=layer.registry.sha256_file(release.package_path))
    review_path = tmp_path / 'review.json'; review_path.write_text(json.dumps(review))
    calls = []
    def prepare(*, release):
        calls.append(release)
        return copy.deepcopy(review)
    monkeypatch.setattr(layer.importlib, 'import_module', lambda name: SimpleNamespace(prepare=prepare))
    monkeypatch.setattr(layer.registry, 'load_preferred_release',
                        lambda season: pytest.fail('source replay must not load preferred'))
    assert layer.reviewed(release, review_path) == review
    assert calls == [release]
    monkeypatch.setattr(layer.importlib, 'import_module', lambda name:
                        SimpleNamespace(prepare=lambda **kwargs: dict(review, changed=True)))
    with pytest.raises(ValueError, match='independently reproduce'):
        layer.reviewed(release, review_path)


def test_verify_rejects_changed_review_or_derived_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(layer.registry, 'ROOT', tmp_path)
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    package = tmp_path / 'package.json'; package.write_bytes(b'package')
    for name in ['JUG98030.FDI', 'EQ98030.FDI']:
        (game / 'DBDAT' / name).write_bytes(name.encode())
    review_path = tmp_path / 'review.json'; review_path.write_bytes(b'original review')
    release = SimpleNamespace(season='2006-07', release_id='original',
                              package_path=package, game_path=game)
    plan = dict(schema_version=layer.SCHEMA, source_release_id='original',
                source_package_sha256=layer.registry.sha256_file(package),
                source_jug_sha256=layer.registry.sha256_file(game / 'DBDAT/JUG98030.FDI'),
                source_eq_sha256=layer.registry.sha256_file(game / 'DBDAT/EQ98030.FDI'),
                review_path='review.json', review_sha256=layer.registry.sha256_file(review_path))
    monkeypatch.setattr(layer, 'prepare', lambda rel, path: copy.deepcopy(plan))
    layer.verify(release, plan)
    monkeypatch.setattr(layer, 'prepare', lambda rel, path: dict(plan, forged=True))
    with pytest.raises(ValueError, match='derived plan changed'):
        layer.verify(release, plan)
    review_path.write_bytes(b'changed review')
    with pytest.raises(ValueError, match='source review'):
        layer.verify(release, plan)


@pytest.mark.parametrize('field', ['source_release_id', 'source_package_sha256',
                                 'source_jug_sha256', 'source_eq_sha256'])
def test_verify_rejects_unbound_immutable_source_before_source_reparse(tmp_path, monkeypatch, field):
    package = tmp_path / 'package'; package.write_bytes(b'package')
    game = tmp_path / 'game'; (game / 'DBDAT').mkdir(parents=True)
    for name in ['JUG98030.FDI', 'EQ98030.FDI']:
        (game / 'DBDAT' / name).write_bytes(name.encode())
    release = SimpleNamespace(release_id='original', package_path=package, game_path=game)
    plan = dict(schema_version=layer.SCHEMA, source_release_id='original',
                source_package_sha256=layer.registry.sha256_file(package),
                source_jug_sha256=layer.registry.sha256_file(game / 'DBDAT/JUG98030.FDI'),
                source_eq_sha256=layer.registry.sha256_file(game / 'DBDAT/EQ98030.FDI'))
    plan[field] = 'unbound'
    monkeypatch.setattr(layer, 'prepare', lambda *args: pytest.fail('must reject before source parse'))
    with pytest.raises(ValueError, match='baseline changed'):
        layer.verify(release, plan)


def layer_fixture(tmp_path, monkeypatch):
    source, plan, old = recipe_fixture()
    source['season'] = {'start_year': 2006, 'end_year': 2007}
    plan.update(source_release_id='original', after_rows=[[1, 0]],
                orders=[{'carrier_id': 1, 'player_id': 'keep'}])
    source_path = tmp_path / 'original-package.json'
    source_path.write_text(json.dumps(source))
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    package = layer.bind(source, plan)
    plan_path = tmp_path / layer.FILENAME
    plan_path.write_bytes(layer.packages.canonical_json_bytes(plan))
    monkeypatch.setattr(layer, 'verify', lambda release, expected_plan: None)
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda season, release:
                        SimpleNamespace(package_path=source_path))
    return source, package, plan, old, plan_path, tmp_path / 'package.json'


def test_layer_discovery_accepts_source_bound_recipe_and_ignores_retained_history(tmp_path, monkeypatch):
    source, package, plan, old, path, package_path = layer_fixture(tmp_path, monkeypatch)
    assert layer.layers(package, package_path) == [plan]


@pytest.mark.parametrize('problem', ['roster', 'active-R49', 'shared-declaration',
    'shared-owner', 'shared-policy', 'orphan-reintroduced', 'retained-owner',
    'retained-id', 'duplicate-layer', 'unsafe-path', 'artifact-hash', 'plan-season'])
def test_layer_discovery_rejects_proof_scope_or_artifact_drift(tmp_path, monkeypatch, problem):
    source, package, plan, old, path, package_path = layer_fixture(tmp_path, monkeypatch)
    target = package['clubs'][0]
    if problem == 'roster': target['roster_player_ids'] = ['other']
    if problem == 'active-R49': package['artifacts'].append(copy.deepcopy(source['artifacts'][0]))
    if problem == 'shared-declaration': target['shared_preserve_player_ids'] = ['keep']
    if problem == 'shared-owner': next(p for p in package['players'] if p['id'] == 'shared')['club_id'] = 'c223'
    if problem == 'shared-policy': next(p for p in package['players'] if p['id'] == 'shared')['policy'] = 'write-facts'
    if problem == 'orphan-reintroduced': package['players'].append(copy.deepcopy(source['players'][2]))
    if problem == 'retained-owner': next(p for p in package['players'] if p['id'] == 'keep')['club_id'] = 'c225'
    if problem == 'retained-id':
        next(p for p in package['players'] if p['id'] == 'keep')['id'] = 'renamed'
        target['roster_player_ids'] = ['renamed']
    artifact = next(a for a in package['artifacts'] if a['id'].startswith(layer.PREFIX))
    if problem == 'duplicate-layer':
        duplicate = copy.deepcopy(artifact); duplicate['id'] += '-duplicate'
        package['artifacts'].append(duplicate)
    if problem == 'unsafe-path': artifact['relative_path'] = '../escaped-plan.json'
    if problem == 'artifact-hash': path.write_bytes(b'changed')
    if problem == 'plan-season':
        plan['season'] = '2005-06'
        path.write_bytes(layer.packages.canonical_json_bytes(plan))
        artifact['sha256'] = layer.registry.sha256_file(path)
    with pytest.raises(ValueError):
        layer.layers(package, package_path)
