"""Country corrections must not resize carriers or silently alter other data."""
import copy
from pathlib import Path
import pytest
from scripts import season_authored_country_delta_v1 as d


@pytest.fixture
def recipes(monkeypatch):
    monkeypatch.setattr(d, 'club_group', lambda c: c['country'])
    monkeypatch.setattr(d.packages, 'validate_package', lambda p: None)
    before = dict(package_id='parent', sources=[dict(id='original')], proofs=[], artifacts=[],
        season='2000-01', clubs=[dict(id='c1', carrier_id=1, country='test',
            manager_id='m1', roster_player_ids=['p1'], name='Old'),
            dict(id='c2', carrier_id=2, country='other', manager_id='m2',
            roster_player_ids=['p2'], name='Other')],
        players=[dict(id='p1', carrier_id=11, club_id='c1', carrier_family='dd6360'),
            dict(id='p2', carrier_id=12, club_id='c2', carrier_family='dd6360')],
        managers=[dict(id='m1', carrier_id=21), dict(id='m2', carrier_id=22)],
        assets=dict(kits=[], portraits=[dict(player_id='p1', status='unresolved'),
            dict(player_id='p2', status='unresolved')]))
    after=copy.deepcopy(before)
    after['package_id']='child'
    after['clubs'][0]['name']='Correct'
    after['sources'].append(dict(id='new-original'))
    return before,after,dict(country='test', club_carrier_ids=[1])


def test_selected_country_and_append_only_sources(recipes):
    before,after,request=recipes
    assert d.verify_recipe_mask(before,after,request)==({1},{'p1'},{'m1'})


@pytest.mark.parametrize('mutation', [
    lambda p:p['clubs'][1].update(name='Unrelated'),
    lambda p:p['clubs'][0]['roster_player_ids'].append('p2'),
    lambda p:p['players'][0].update(club_id='c2'),
    lambda p:p['players'][0].update(carrier_id=999),
    lambda p:p['players'][1].update(name='Unrelated'),
    lambda p:p['managers'][1].update(name='Unrelated'),
    lambda p:p['sources'][0].update(title='Changed evidence'),
    lambda p:p['assets']['kits'].append(dict(id='new-kit')),
    lambda p:p['assets']['portraits'][1].update(status='native-no-photo'),
    lambda p:p.update(season='2001-02'),
])
def test_closed_scope_rejects_unrelated_mutations(recipes,mutation):
    before,after,request=recipes
    mutation(after)
    with pytest.raises(ValueError):
        d.verify_recipe_mask(before,after,request)


def test_country_graph_must_be_complete(recipes):
    before,after,request=recipes
    request['club_carrier_ids']=[]
    with pytest.raises(ValueError,match='exactly'):
        d.verify_recipe_mask(before,after,request)


def test_country_carrier_exchange_preserves_sizes_and_explicit_owners(recipes):
    before,after,request=recipes
    before['clubs'][1]['country']=after['clubs'][1]['country']='test'
    request['club_carrier_ids']=[1,2]
    after['clubs'][0]['roster_player_ids']=['p2']
    after['clubs'][1]['roster_player_ids']=['p1']
    after['players'][0]['club_id']='c2'
    after['players'][1]['club_id']='c1'
    assert d.verify_recipe_mask(before,after,request)==({1,2},{'p1','p2'},{'m1','m2'})
    after['players'][1]['club_id']='c2'
    with pytest.raises(ValueError,match='owner'):
        d.verify_recipe_mask(before,after,request)


def test_explicit_club_selection_keeps_other_same_country_clubs_closed(recipes):
    before,after,request=recipes
    before['clubs'][1]['country']=after['clubs'][1]['country']='test'
    with pytest.raises(ValueError,match='exactly'):
        d.verify_recipe_mask(before,after,request)
    request['selection_kind']='clubs'
    assert d.verify_recipe_mask(before,after,request)==({1},{'p1'},{'m1'})
    after['players'][1]['name']='Unrelated player'
    with pytest.raises(ValueError,match='unselected'):
        d.verify_recipe_mask(before,after,request)


@pytest.mark.parametrize('selected', [[],[1,1],[1,2],[99]])
def test_club_selection_refuses_empty_repeated_cross_country_or_unknown_clubs(recipes,selected):
    before,after,request=recipes
    request.update(selection_kind='clubs',club_carrier_ids=selected)
    with pytest.raises(ValueError,match='unique existing clubs'):
        d.verify_recipe_mask(before,after,request)


def test_club_slice_cannot_modify_a_manager_owned_outside_the_slice(recipes):
    before,after,request=recipes
    request['selection_kind']='clubs'
    before['clubs'][1]['manager_id']=after['clubs'][1]['manager_id']='m1'
    with pytest.raises(ValueError,match='shared with an unselected club'):
        d.verify_recipe_mask(before,after,request)


@pytest.mark.parametrize('mutation', [
    lambda p:p['clubs'][1].update(name='Unselected same-country club'),
    lambda p:p['managers'][1].update(name='Unselected same-country coach'),
    lambda p:p['assets']['portraits'][1].update(status='native-no-photo'),
    lambda p:p['clubs'][0]['roster_player_ids'].append('p2'),
])
def test_club_slice_does_not_weaken_closed_graph_or_asset_guards(recipes,mutation):
    before,after,request=recipes
    before['clubs'][1]['country']=after['clubs'][1]['country']='test'
    request['selection_kind']='clubs'
    mutation(after)
    with pytest.raises(ValueError):
        d.verify_recipe_mask(before,after,request)


def test_player_only_selection_keeps_every_club_and_owner_closed(recipes):
    before,after,request=recipes
    after['clubs']=copy.deepcopy(before['clubs'])
    request.update(selection_kind='players-only',club_carrier_ids=[],player_ids=['p1'])
    after['players'][0]['name']='Correct identity'
    assert d.verify_recipe_mask(before,after,request)==(set(),{'p1'},set())
    after['players'][0]['club_id']='c2'
    with pytest.raises(ValueError,match='owner'):
        d.verify_recipe_mask(before,after,request)


@pytest.mark.parametrize('mutation',[
    lambda p:p['clubs'][0].update(name='Changed club'),
    lambda p:p['managers'][0].update(name='Changed manager'),
    lambda p:p['players'][1].update(name='Unselected identity'),
])
def test_player_only_scope_cannot_expand_to_clubs_or_other_people(recipes,mutation):
    before,after,request=recipes
    after['clubs']=copy.deepcopy(before['clubs'])
    request.update(selection_kind='players-only',club_carrier_ids=[],player_ids=['p1'])
    mutation(after)
    with pytest.raises(ValueError):
        d.verify_recipe_mask(before,after,request)


def test_explicit_opening_selection_does_not_authorise_other_club_edits(recipes):
    before,after,request=recipes
    after['clubs']=copy.deepcopy(before['clubs'])
    request.update(selection_kind='players-and-openings',club_carrier_ids=[1],player_ids=['p1'])
    after['clubs'][0]['opening']={'starting_xi_player_ids':['p1']}
    assert d.verify_recipe_mask(before,after,request)==({1},{'p1'},set())
    after['clubs'][0]['name']='Unrelated metadata'
    with pytest.raises(ValueError,match='metadata'):
        d.verify_recipe_mask(before,after,request)


def test_factory_compilation_cannot_drop_country_layer():
    with pytest.raises(ValueError,match='SOURCE'):
        d.reject_factory_recipe(dict(artifacts=[dict(id=d.PREFIX+'abc')]))


@pytest.fixture(scope='module')
def native_country():
    from scripts import season_release_registry_v1 as r, season_pipeline_v2 as p
    source=r.ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/calendar-2017-irish-august-v1/country-recipe-r329-v6/native-plan.json'
    if not source.exists():
        pytest.skip('retained country corpus unavailable')
    plan=p.read_json_file(source)
    base=r.load_registered_release(plan['season'],plan['release_id'])
    child=r.load_registered_release(plan['season'],'sourced-irish-2017-country-correction-20261026-r329a')
    return base,child,plan,d._outputs(plan)


def test_actual_country_publication_replays_from_immutable_parent(native_country):
    base,child,plan,out=native_country
    assert (len(out['selected_players']),len(out['selected_clubs']),len(out['selected_managers']))==(230,12,12)
    for key,name in [('jug','JUG98030.FDI'),('eq','EQ98030.FDI'),('ent','ENT98030.FDI')]:
        assert (child.game_path/'DBDAT'/name).read_bytes()==out[key]
    assert d.bind(d.p.read_json_file(base.package_path),plan)==d.p.read_json_file(child.package_path)


def test_native_country_rejects_mixed_preimages_and_unrelated_assets(native_country):
    base,child,plan,out=native_country
    parent_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    with pytest.raises(ValueError,match='complete parent'):
        d.apply(parent_jug,out['eq'],plan)
    with pytest.raises(ValueError,match='ENT preimage'):
        d.apply_ent(b'unrelated archive',plan)
    with pytest.raises(ValueError,match='portrait archive'):
        d.apply_minifoto(b'unrelated archive',plan)


@pytest.fixture(scope='module')
def native_counterparts():
    from scripts import season_release_registry_v1 as r, season_pipeline_v2 as p
    path=r.ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/calendar-2017-irish-august-v1/counterpart-owner-evidence-v1/counterpart-recipe-r330-v2/native-plan.json'
    if not path.exists():
        pytest.skip('retained counterpart corpus unavailable')
    plan=p.read_json_file(path)
    child=r.load_registered_release('2017-18','sourced-irish-2017-counterpart-corrections-20261026-r330a')
    return child,plan,d._outputs(plan)


def test_mixed_layout_corrections_replay_the_published_native_game(native_counterparts):
    child,plan,out=native_counterparts
    assert out['selected_players']==[9676,18068,27024,29914]
    assert out['selected_clubs']==[1261]
    assert out['selected_managers']==[]
    for key,name in [('jug','JUG98030.FDI'),('eq','EQ98030.FDI'),('ent','ENT98030.FDI')]:
        assert (child.game_path/'DBDAT'/name).read_bytes()==out[key]


def test_native_starting_copy_is_removed_from_the_source_opening_xi(native_counterparts):
    from app.fdi_indexed import IndexedFDIFile
    from app.player_initial_order import read_initial_order
    child,plan,out=native_counterparts
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(out['jug']).entries}
    assert read_initial_order(entries[29914].decode_payload(out['jug'])).order==15
    club=next(c for c in out['package']['clubs'] if c['carrier_id']==1261)
    assert len(club['opening']['starting_xi_player_ids'])==11
    assert 'player-29914' not in club['opening']['starting_xi_player_ids']
    assert 'player-29914' in club['opening']['substitute_player_ids']


def test_english_mode0_identity_and_bench_delta_preserves_native_scope():
    """Exercise the real mixed identity/order boundary, including compact records."""
    from app.fdi_indexed import IndexedFDIFile
    from app.player_initial_order import read_initial_order
    source = d.r.ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/english-2023-winter-ownership-v1/recipe-r398-v2/native-plan.json'
    if not source.exists():
        pytest.skip('retained English opening-ownership corpus unavailable')
    plan = d.p.read_json_file(source)
    base = d.r.load_registered_release(plan['season'], plan['release_id'])
    output = d._outputs(plan)
    raw = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    before = {e.record_id: e.decode_payload(raw) for e in IndexedFDIFile.from_bytes(raw).entries}
    after = {e.record_id: e.decode_payload(output['jug']) for e in IndexedFDIFile.from_bytes(output['jug']).entries}
    assert len(output['selected_players']) == 12
    assert output['selected_clubs'] == [322, 351, 355, 378]
    assert before.keys() == after.keys()
    order_only = []
    for cid, payload in before.items():
        if cid in output['selected_players'] or payload == after[cid]:
            continue
        field = read_initial_order(payload)
        expected = bytearray(payload)
        expected[field.offset] = after[cid][field.offset]
        assert bytes(expected) == after[cid]
        order_only.append(cid)
    assert order_only
    for key, name in [('eq', 'EQ98030.FDI'), ('ent', 'ENT98030.FDI')]:
        assert output[key] == (base.game_path / 'DBDAT' / name).read_bytes()
