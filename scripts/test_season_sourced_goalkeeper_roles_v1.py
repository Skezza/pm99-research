import copy
import json
from types import SimpleNamespace
import pytest
from scripts import season_sourced_goalkeeper_roles_v1 as module


def fixture():
    return {'players': [{'name': 'Real Goalkeeper', 'birth_date': '1980-02-03', 'position': 'G'}]}


def test_literal_G_full_identity_and_DOB_authorize_goalkeeper_role_not_a_side_guess():
    capture = fixture()
    before = copy.deepcopy(capture)
    assert module.original_keeper(capture, 'Real GOALKEEPER', '1980-02-03') == capture['players'][0]
    assert capture == before


@pytest.mark.parametrize('problem', ['initial', 'different-person', 'wrong-DOB', 'missing-DOB', 'outfielder', 'duplicate'])
def test_uncertain_identity_or_nonkeeper_is_not_authorized(problem):
    capture, name, birthday = fixture(), 'Real Goalkeeper', '1980-02-03'
    if problem == 'initial': name = 'R. Goalkeeper'
    if problem == 'different-person': name = 'Other Goalkeeper'
    if problem == 'wrong-DOB': birthday = '1981-02-03'
    if problem == 'missing-DOB': capture['players'][0]['birth_date'] = None
    if problem == 'outfielder': capture['players'][0]['position'] = 'M'
    if problem == 'duplicate': capture['players'].append(dict(capture['players'][0]))
    assert module.original_keeper(capture, name, birthday) is None


def test_case_accents_do_not_expand_a_shortened_name():
    capture = fixture(); capture['players'][0]['name'] = 'José Keeper'
    assert module.original_keeper(capture, 'José KEEPER', '1980-02-03') is not None
    assert module.original_keeper(capture, 'J. Keeper', '1980-02-03') is None


def consistency_fixture():
    return ({'name': 'Declared Keeper', 'facts': {'primary_position': 'G',
             'fine_roles': {'policy': 'preserve-existing-mode1'},
             'birth_date': {'policy': 'preserve-existing-mode1'}}},
            {'name': 'Declared KEEPER', 'position': 'G'})


def test_declared_keeper_consistency_does_not_require_or_invent_secondary_facts():
    player, native = consistency_fixture()
    original = copy.deepcopy(player)
    assert module.declared_keeper_target(player, native)
    assert player == original


@pytest.mark.parametrize('problem', [
    'whole-person-fallback', 'recipe-outfielder', 'native-outfielder',
    'different-native-person', 'explicit-outfield-roles', 'explicit-keeper-roles',
])
def test_declared_keeper_consistency_does_not_override_other_declarations(problem):
    player, native = consistency_fixture()
    if problem == 'whole-person-fallback': player['policy'] = 'preserve-existing-mode1'
    if problem == 'recipe-outfielder': player['facts']['primary_position'] = 'M'
    if problem == 'native-outfielder': native['position'] = 'M'
    if problem == 'different-native-person': native['name'] = 'Other Keeper'
    if problem == 'explicit-outfield-roles': player['facts']['fine_roles'] = [12]
    if problem == 'explicit-keeper-roles': player['facts']['fine_roles'] = [0]
    assert not module.declared_keeper_target(player, native)


def test_consistency_plan_reproduces_and_writes_only_the_native_role_window(tmp_path):
    from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
    from scripts.test_season_package_compiler_v2 import _dd6361_player_payload, _indexed_fdi
    payload = bytearray(_dd6361_player_payload(1, role=14))
    end, _ = read_indexed_native_roles(payload, 1)
    payload[end + 11] = 0 ^ 0x61  # Existing native broad G, not a position rewrite.
    native = module.audit.native_player(payload, 1)
    player, _ = consistency_fixture()
    player.update(id='player-1', carrier_id=1, name=native['name'])
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    jug = game / 'DBDAT/JUG98030.FDI'
    jug.write_bytes(_indexed_fdi([(1, 'fixture', bytes(payload))]))
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'players': [player]}))
    release = SimpleNamespace(season='2009-10', release_id='parent',
                              game_path=game, package_path=package)
    original = jug.read_bytes()
    plan = module.prepare_position_consistency(release)
    assert len(plan['updates']) == 1 and plan['updates'][0]['fine_roles'] == [0]
    assert plan['proof_grade'] == 'reviewed-editorial'
    assert plan['updates'][0]['birth_date'] == {'policy': 'preserve-existing-mode1'}
    module.verify(release, plan)
    legacy = copy.deepcopy(plan)
    legacy.pop('proof_grade')
    module.verify(release, legacy)
    patched, changes = rewrite_indexed_native_roles(original, {1: [0]})
    changed = {i for i, (a, b) in enumerate(zip(original, patched)) if a != b}
    assert changed and changed <= set(changes[0]['allowed_offsets'])
    assert jug.read_bytes() == original
    plan['updates'][0]['fine_roles'] = [12]
    with pytest.raises(ValueError, match='does not reproduce'):
        module.verify(release, plan)
    plan['updates'][0]['fine_roles'] = [0]
    plan['proof_grade'] = 'source-receipt'
    with pytest.raises(ValueError, match='does not reproduce'):
        module.verify(release, plan)


@pytest.mark.parametrize('policy', [module.POLICY, module.CONSISTENCY_POLICY])
@pytest.mark.parametrize('problem', ['empty', 'unresolved', 'mixed-manager', 'register'])
def test_keeper_source_replay_cannot_expand_or_publish_an_unresolved_plan(tmp_path, monkeypatch, policy, problem):
    from scripts import publish_historical_role_delta_v1 as publisher
    monkeypatch.setattr(publisher.registry, 'load_registered_release', lambda *args: object())
    plan = {'policy': policy, 'updates': [{'sentinel': True}], 'unresolved': []}
    options = {'source_release_id': 'parent'}
    if problem == 'empty': plan['updates'] = []
    if problem == 'unresolved': plan['unresolved'] = [{'case': 'unresolved'}]
    if problem == 'mixed-manager': options['manager_plan_path'] = tmp_path / 'manager.json'
    if problem == 'register': options['register'] = True
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='nonempty resolved role-only'):
        publisher.publish('2009-10', path, release_id='candidate', **options)
