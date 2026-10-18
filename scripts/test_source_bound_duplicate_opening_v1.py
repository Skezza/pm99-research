import copy
from types import SimpleNamespace

import pytest

from scripts import season_source_bound_duplicate_opening_v1 as layer


def recipe():
    keep = dict(id='keep', carrier_id=10, facts={'fine_roles': [0], 'birth_date': '1972-11-28'},
                ratings={'handling': 7})
    bad = dict(id='bad', carrier_id=11)
    club = dict(id='club', carrier_id=1005, roster_player_ids=['keep', 'bad'],
                shared_preserve_player_ids=['bad'])
    package = dict(clubs=[club, {'id': 'other', 'roster_player_ids': ['other']}],
        players=[keep, bad, {'id': 'other'}], artifacts=[{'id': 'existing'}],
        portraits=[{'player_id': 'bad'}, {'player_id': 'keep'}])
    plan = dict(schema=layer.SCHEMA, season='2001-02', before_club=copy.deepcopy(club),
        package_canonical_sha256=layer.digest(layer.packages.canonical_json_bytes(package)),
        review=dict(club_id='club', retained_player=copy.deepcopy(keep), removed_player=copy.deepcopy(bad)),
        primary_role_changes=[dict(player_id='keep', recipe_fine_roles_before=[0],
                                   recipe_fine_roles_after=[4])])
    return package, plan


def test_bind_keeps_birthday_ratings_and_unrelated_recipe(monkeypatch):
    package, plan = recipe()
    original = copy.deepcopy(package)
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    result = layer.bind(package, plan)
    assert package == original
    assert result['clubs'][0]['roster_player_ids'] == ['keep']
    assert result['clubs'][0]['shared_preserve_player_ids'] == []
    assert result['players'][0]['facts'] == {'fine_roles': [4], 'birth_date': '1972-11-28'}
    assert result['players'][0]['ratings'] == original['players'][0]['ratings']
    assert result['clubs'][1] == original['clubs'][1]
    assert result['portraits'] == [{'player_id': 'keep'}]
    assert result['artifacts'][0] == original['artifacts'][0]


@pytest.mark.parametrize('problem', ['recipe-edit', 'shared-removed', 'wrong-person',
                                    'changed-role', 'wrong-club', 'declared-starter', 'duplicate-layer'])
def test_bind_rejects_unapproved_preimages(monkeypatch, problem):
    package, plan = recipe()
    if problem == 'recipe-edit': package['unrelated'] = 'edit'
    if problem == 'shared-removed': package['clubs'][1]['roster_player_ids'].append('bad')
    if problem == 'wrong-person': package['players'][1]['carrier_id'] = 99
    if problem == 'changed-role': package['players'][0]['facts']['fine_roles'] = [9]
    if problem == 'wrong-club': package['clubs'][0]['carrier_id'] = 99
    if problem == 'declared-starter': package['clubs'][0]['starting_xi_player_ids'] = ['bad']
    if problem == 'duplicate-layer': package['artifacts'].append({'id': layer.PREFIX+'2001-02-1005'})
    if problem != 'recipe-edit':
        plan['package_canonical_sha256'] = layer.digest(layer.packages.canonical_json_bytes(package))
    if problem in ('declared-starter',): plan['before_club'] = copy.deepcopy(package['clubs'][0])
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError): layer.bind(package, plan)


def test_apply_refuses_whole_native_preimage_before_any_writer(monkeypatch):
    monkeypatch.setattr(layer.source.native, 'roster_rows', lambda *a: pytest.fail('no writer/read should run'))
    with pytest.raises(ValueError, match='whole source'):
        layer._apply_before(b'jug', b'eq', {'review': {}, 'jug_sha256': 'wrong', 'eq_sha256': 'wrong'})


def test_apply_requires_exact_complete_before_or_after_not_partial(tmp_path, monkeypatch):
    game = tmp_path / 'game/DBDAT'; game.mkdir(parents=True)
    (game/'JUG98030.FDI').write_bytes(b'old jug')
    (game/'EQ98030.FDI').write_bytes(b'old eq')
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: SimpleNamespace(game_path=game.parent))
    monkeypatch.setattr(layer, '_apply_before', lambda *a: (b'new jug', b'new eq'))
    plan = dict(schema=layer.SCHEMA, season='2001-02', release_id='baseline',
                review={'removed_is_current_native_starter': True})
    assert layer.apply(b'old jug', b'old eq', plan) == (b'new jug', b'new eq')
    assert layer.apply(b'new jug', b'new eq', plan) == (b'new jug', b'new eq')
    for jug, eq in [(b'new jug', b'old eq'), (b'old jug', b'new eq'), (b'edited jug', b'new eq')]:
        with pytest.raises(ValueError, match='partially applied'): layer.apply(jug, eq, plan)
    plan['review']['removed_is_current_native_starter'] = False
    with pytest.raises(ValueError, match='unapproved'): layer.apply(b'old jug', b'old eq', plan)


def test_verify_rederives_original_evidence_not_receipt_hash(monkeypatch):
    expected = dict(schema=layer.SCHEMA, case={}, profile_root='cache', profile_receipt={'path': 'receipt'})
    monkeypatch.setattr(layer, 'prepare', lambda *a: copy.deepcopy(expected))
    layer.verify('baseline', expected)
    changed = dict(expected, orders=[{'after': 1}])
    with pytest.raises(ValueError, match='does not reproduce'): layer.verify('baseline', changed)


def test_reserve_replay_dispatches_starter_schema_before_reserve_guards(tmp_path, monkeypatch):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path = tmp_path / 'plan.json'; path.write_text('{"schema":"' + layer.SCHEMA + '"}')
    previous = SimpleNamespace(package_path=tmp_path/'package', locator={'sourced_profile_assignment_plan_path': str(path)})
    monkeypatch.setattr(reserve.pipeline, 'read_json_file', lambda p: {'schema': layer.SCHEMA} if p==path else {})
    monkeypatch.setattr(layer, 'reconstruction', lambda p, id: {'starter_schema_replayed': True})
    assert reserve.reconstruction(previous, 'replay') == {'starter_schema_replayed': True}


def test_factory_rejects_starter_layer_before_native_io(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler, '_load_native_package', lambda p: ({'artifacts': [{'id': layer.PREFIX+'2001-02-1005'}]}, 'hash'))
    monkeypatch.setattr(compiler, '_ensure_clean_database_inputs', lambda **k: pytest.fail('must reject before native IO'))
    with pytest.raises(compiler.SeasonCompilerError, match='must not drop'):
        compiler.compile_package_to_tree(package_path='recipe', base_tree='base', materialisation_tree='output')


def test_wingers_stay_dated_midfield_broad_not_invented_forward():
    assert layer.ROLE_MAP['Left Winger'] == ('M', 13)
    assert layer.ROLE_MAP['Right-Back'] == ('D', 1)
    assert layer.ROLE_MAP['Attacking Midfield'] == ('M', 9)


def opening_shape():
    xi = [dict(carrier_id=n, source_player_id=str(n), profile={}, native_before={}) for n in range(1, 12)]
    xi[1].update(profile={'published_profile_position': 'Centre-Back'}, native_before={'position': 'D'})
    ids = list(range(1, 12)) + list(range(13, 19))
    orders = [dict(carrier_id=id, startup_order=n, after=n) for n, id in enumerate(ids, 1)]
    return dict(review=dict(removed_player={'carrier_id': 12}, retained_player={'carrier_id': 2},
        first_fixture={'starting_xi': {str(n): 'Name' for n in range(1, 12)}},
        native_roster_before=[[n, 0] for n in range(1, 19)],
        duplicate_input_assignment_proved=True, removed_is_current_native_starter=True),
        starting_xi=xi, orders=orders, primary_role_changes=[dict(carrier_id=2, before=0, after=4,
            native_roles_before=[0, 98, 98, 98, 98, 98],
            native_roles_after=[4, 98, 98, 98, 98, 98], recipe_fine_roles_after=[4])])


@pytest.mark.parametrize('problem', ['duplicate-xi', 'different-match-id', 'xi-order',
    'missing-roster-member', 'order-gap', 'reserves-reordered', 'duplicate-link-absent',
    'hidden-roster-flag', 'role-wrong-target', 'unapproved-secondary-edit',
    'role-wrong-broad', 'role-nonstarter', 'role-repeated'])
def test_opening_shape_rejects_unsourced_order_or_role_changes(problem):
    plan = opening_shape()
    layer.validate_opening_shape(plan)
    if problem == 'duplicate-xi': plan['starting_xi'][0]['carrier_id'] = 2
    if problem == 'different-match-id': plan['starting_xi'][0]['source_player_id'] = '999'
    if problem == 'xi-order': plan['orders'][0], plan['orders'][1] = plan['orders'][1], plan['orders'][0]
    if problem == 'missing-roster-member': plan['orders'].pop()
    if problem == 'order-gap': plan['orders'][-1]['after'] = 99
    if problem == 'reserves-reordered':
        plan['orders'][-1]['startup_order'], plan['orders'][-2]['startup_order'] = (
            plan['orders'][-2]['startup_order'], plan['orders'][-1]['startup_order'])
    if problem == 'duplicate-link-absent': plan['review']['native_roster_before'][11][0] = 99
    if problem == 'hidden-roster-flag': plan['review']['native_roster_before'][0][1] = 1
    if problem == 'role-wrong-target': plan['primary_role_changes'][0]['after'] = 0
    if problem == 'unapproved-secondary-edit': plan['primary_role_changes'][0]['native_roles_after'][2] = 8
    if problem == 'role-wrong-broad': plan['starting_xi'][1]['native_before']['position'] = 'G'
    if problem == 'role-nonstarter': plan['primary_role_changes'][0]['carrier_id'] = 18
    if problem == 'role-repeated': plan['primary_role_changes'].append(copy.deepcopy(plan['primary_role_changes'][0]))
    with pytest.raises(ValueError): layer.validate_opening_shape(plan)


def test_only_a_promoted_duplicate_secondary_role_can_be_cleared():
    plan = opening_shape()
    plan['primary_role_changes'][0]['native_roles_before'][1] = 4
    layer.validate_opening_shape(plan)
    plan['primary_role_changes'][0]['native_roles_before'][1] = 5
    with pytest.raises(ValueError): layer.validate_opening_shape(plan)


def shared_recipe():
    from scripts import review_factory_fallthrough_duplicate_v1 as factory
    package, plan = recipe()
    other = package['clubs'][1]
    other.update(carrier_id=1006, shared_preserve_player_ids=['bad'])
    other['roster_player_ids'].append('bad')
    bad = package['players'][1]
    bad.update(club_id='club', policy='preserve-existing-mode1', facts={'birth_date': {'policy': 'preserve-existing-mode1'}})
    plan['review'].update(schema=factory.SCHEMA, removed_player=copy.deepcopy(bad),
        shared_removed_membership=dict(player=copy.deepcopy(bad), native_owners_before=[1005, 1006],
            surviving_club_id='other', surviving_club_before=copy.deepcopy(other)))
    plan['package_canonical_sha256'] = layer.digest(layer.packages.canonical_json_bytes(package))
    return package, plan


def test_shared_retirement_keeps_global_person_portrait_other_roster_and_only_rebinds_owner(monkeypatch):
    package, plan = shared_recipe()
    original = copy.deepcopy(package)
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    result = layer.bind(package, plan)
    assert package == original
    assert result['clubs'][0]['roster_player_ids'] == ['keep']
    assert result['clubs'][1]['roster_player_ids'] == original['clubs'][1]['roster_player_ids']
    assert result['clubs'][1]['shared_preserve_player_ids'] == []
    bad = next(p for p in result['players'] if p['id'] == 'bad')
    assert bad == dict(original['players'][1], club_id='other')
    assert result['portraits'] == original['portraits']


@pytest.mark.parametrize('problem', ['untyped', 'changed-person', 'changed-survivor',
    'hidden-third-owner', 'duplicate-retirement', 'declared-shared-starter'])
def test_shared_retirement_rejects_unsourced_recipe_changes(monkeypatch, problem):
    package, plan = shared_recipe()
    if problem == 'untyped': plan['review']['schema'] = 'name-only-unapproved'
    if problem == 'changed-person': package['players'][1]['facts']['birth_date'] = '1990-01-01'
    if problem == 'changed-survivor': package['clubs'][1]['carrier_id'] = 999
    if problem == 'hidden-third-owner':
        package['clubs'].append(dict(id='third', carrier_id=1007, roster_player_ids=['bad']))
    if problem == 'duplicate-retirement':
        plan['review']['additional_shared_membership_retirements'] = [copy.deepcopy(plan['review']['shared_removed_membership'])]
    if problem == 'declared-shared-starter':
        package['clubs'][0]['starting_xi_player_ids'] = ['bad']
        plan['before_club'] = copy.deepcopy(package['clubs'][0])
    plan['package_canonical_sha256'] = layer.digest(layer.packages.canonical_json_bytes(package))
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError): layer.bind(package, plan)


def test_only_typed_original_bench_identity_can_remain_reserve():
    from scripts import review_factory_fallthrough_duplicate_v1 as factory
    plan = opening_shape()
    plan['review'].update(schema=factory.SCHEMA, retained_player={'carrier_id': 13},
        retained_source_player_id='19123', retained_positive_fixture_surface='published-bench')
    plan['review']['first_fixture']['substitutes'] = {'19123': 'Arturo Di Napoli'}
    layer.validate_opening_shape(plan)
    for key, value in [('schema', 'unapproved'), ('retained_source_player_id', '999'),
                       ('retained_positive_fixture_surface', 'starting-XI')]:
        changed = copy.deepcopy(plan); changed['review'][key] = value
        with pytest.raises(ValueError): layer.validate_opening_shape(changed)


def test_additional_shared_link_not_written_in_source_XI_or_order_list():
    from scripts import review_factory_fallthrough_duplicate_v1 as factory
    plan = opening_shape()
    plan['review'].update(schema=factory.SCHEMA,
        additional_shared_membership_retirements=[{'player': {'carrier_id': 18}}])
    plan['orders'].pop()
    layer.validate_opening_shape(plan)
    plan['review']['additional_shared_membership_retirements'][0]['player']['carrier_id'] = 2
    with pytest.raises(ValueError): layer.validate_opening_shape(plan)


@pytest.mark.parametrize('problem', [None, 'different-id', 'different-native', 'different-DOB', 'different-family'])
def test_omitted_middle_name_is_not_a_general_fuzzy_match(problem):
    profile = dict(source_player_id='16907', published_full_name='Fabian Natale Valtolina',
                   published_birth_date='1971-06-10')
    row = dict(opening_source_player_id='16907', facts={'name': 'Fabian Valtolina', 'birth_date': '1971-06-10'})
    person = dict(carrier_id=4392, source_name='Fabian Valtolina', facts={'birth_date': '1971-06-10'})
    actual = {'birth_date': '1971-06-10'}
    if problem == 'different-id': profile['source_player_id'] = '999'
    if problem == 'different-native': person['carrier_id'] = 999
    if problem == 'different-DOB': actual['birth_date'] = '1971-06-11'
    if problem == 'different-family': row['facts']['name'] = 'Fabian Bianchi'
    if problem:
        with pytest.raises(ValueError): layer.original_profile_identity(profile, row, person, actual)
    else:
        assert layer.original_profile_identity(profile, row, person, actual)['policy'].startswith('explicit-original-numeric')


def test_second_opening_layer_has_its_own_filename():
    assert layer.filename({}) == layer.FILENAME
    assert layer.filename({'layer_suffix': 'abc123'}) == 'sourced-duplicate-opening-abc123.json'
