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
