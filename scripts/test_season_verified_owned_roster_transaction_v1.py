from types import SimpleNamespace
import pytest
from scripts import season_verified_owned_roster_transaction_v1 as transaction


@pytest.mark.parametrize('fault',['schema','season','parent','empty'])
def test_wrong_or_empty_request_is_not_admitted(monkeypatch,fault):
    request=dict(schema=transaction.INPUT_SCHEMA,season='2017-18',release_id='parent',groups=[{}])
    if fault=='schema':request['schema']='arbitrary'
    elif fault=='season':request['season']='2018-19'
    elif fault=='parent':request['release_id']='other'
    elif fault=='empty':request['groups']=[]
    monkeypatch.setattr(transaction.pipeline,'read_json_file',lambda _:request)
    with pytest.raises(ValueError,match='exact parent'):
        transaction.prepare(SimpleNamespace(season='2017-18',release_id='parent'),'unused')


def test_owned_roster_cannot_be_factory_rebuilt():
    with pytest.raises(ValueError,match='source reconstruction'):
        transaction.reject_factory_recipe(dict(artifacts=[dict(id=transaction.PREFIX+'example')]))
    transaction.reject_factory_recipe(dict(artifacts=[]))


def test_changed_request_hash_is_rejected_before_native_write():
    path=transaction.registry.ROOT/'.local/consolidated-audit-20261009/Barrow2017-owned-roster-delivery-v1/source-owned-roster-0af29910882af17f04e700c0.json'
    if not path.exists():pytest.skip('local retained original-source transaction unavailable')
    plan=transaction.pipeline.read_json_file(path)
    plan['source_input']['sha256']='0'*64
    with pytest.raises(ValueError,match='does not reproduce'):
        transaction.verify(SimpleNamespace(),plan)


def test_effective_overlay_cannot_escape_global_identity_guard(monkeypatch):
    monkeypatch.setattr(transaction.layers,'package_layers',lambda _:[('main',{},None),('english',{},None)])
    with pytest.raises(ValueError,match='overlays'):transaction.main_package(SimpleNamespace())


def test_main_only_source_is_admitted(monkeypatch):
    package={'players':[]}
    monkeypatch.setattr(transaction.layers,'package_layers',lambda _:[('main',package,None)])
    assert transaction.main_package(SimpleNamespace()) is package


def test_correct_selected_partial_people_cannot_be_swapped():
    current=[dict(name='First Player',facts=dict(birth_date='1990-01-01')),
             dict(name='Other Player',facts=dict(birth_date='1991-01-01'))]
    incoming=[dict(source_player=dict(name='Other Player',birth_date='1991-01-01'))]
    with pytest.raises(ValueError,match='existing correct'):transaction.refuse_correct_people(current,incoming)
