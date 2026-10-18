import copy
import pytest
from scripts import season_exact_fifa_role_delta_v1 as roles


def player(name='Erik Pieters', born='1988-08-07', primary='D'):
    return dict(name=name, source_name=name, carrier_id=9254,
        facts=dict(birth_date=born, primary_position=primary, fine_roles=[4]),
        ratings=dict(values=dict(handling=8, quality=74)))


def row(**changes):
    return dict(player_id='178023', dob='1988-08-07', long_name='Erik Pieters',
        short_name='E. Pieters', player_positions='LB, CB', fifa_update_date='2014-09-18') | changes


def test_exact_target_and_birthday_required():
    index={(15,'1988-08-07'):[row()]}
    assert roles.match(player(),'2014-15',index)==row()
    assert roles.match(player(),'2015-16',index) is None
    assert roles.match(player(born='1988-08-08'),'2014-15',index) is None
    assert roles.match(player(),'2000-01',index) is None
    assert roles.match(player(),'2024-25',index) is None


def test_no_surname_or_initial_only_identity():
    for name in ('Pieters','E. Pieters'):
        assert roles.match(player(name),'2014-15',{(15,'1988-08-07'):[row()]}) is None


def test_explicit_published_comma_reverses_family_given_not_arbitrary_words():
    p=player('Ben-Haim, Tal',born='1982-03-31')
    r=row(dob='1982-03-31',long_name='Tal Ben Haim',short_name='T. Ben Haim')
    assert roles.match(p,'2015-16',{(16,'1982-03-31'):[r]})==r


def test_distinct_people_and_contradictory_source_updates_refuse():
    key=(15,'1988-08-07')
    assert roles.match(player(),'2014-15',{key:[row(),row(player_id='other')]}) is None
    assert roles.match(player(),'2014-15',{key:[row(),row(player_positions='RW')]}) is None


def test_earliest_consistent_snapshot_not_last_csv_row():
    first=row();later=row(fifa_update_date='2015-04-01')
    assert roles.match(player(),'2014-15',{(15,'1988-08-07'):[later,first]})==first


@pytest.mark.parametrize('position,code,expected',[('D',2,True),('D',12,False),
    ('M',14,True),('F',13,True),('G',0,True),('G',4,False),('F',0,False)])
def test_primary_class_not_silently_changed(position,code,expected):
    assert roles.compatible(position,code)==expected


def test_unknown_broad_position_is_not_inferred():
    assert not roles.compatible({'policy':'preserve-existing-mode1'}, 4)


def test_only_recipe_fine_roles_change(monkeypatch):
    monkeypatch.setattr(roles.packages,'validate_package',lambda p:None)
    p=player();original=dict(players=[p],artifacts=[],proofs=[])
    plan=dict(transaction_id='test',updates=[dict(carrier_id=9254,
        before_player_sha256=roles.digest(p),fine_roles=[2,4])])
    before=copy.deepcopy(original);updated=roles.bind(original,plan)
    assert original==before
    assert updated['players'][0]['facts']['fine_roles']==[2,4]
    for artifact in updated['artifacts']:
        assert roles.packages.ID_RE.fullmatch(artifact['id'])
    for proof in updated['proofs']:
        assert roles.packages.ID_RE.fullmatch(proof['id'])
    updated['players'][0]['facts']['fine_roles']=[4]
    assert updated['players']==before['players']
    bad=copy.deepcopy(original);bad['players'][0]['ratings']['values']['quality']=99
    with pytest.raises(ValueError):roles.bind(bad,plan)


def test_factory_does_not_drop_role_layer():
    with pytest.raises(ValueError):roles.reject_factory_recipe(dict(artifacts=[dict(id=roles.PREFIX+'test')]))


@pytest.mark.parametrize('old,new,expected',[
    ([5,98,98,98,98,98],[4],[5]),
    ([1,5,98,98,98,98],[1,4],[1,5]),
    ([4,98,98,98,98,98],[4],[4]),
    ([4,98,98,98,98,98],[2],[2]),
    ([5,4,98,98,98,98],[4],[4]),
])
def test_generic_cb_never_overwrites_existing_right_centre_preference(old,new,expected):
    from scripts import season_exact_fifa_role_delta_v2 as v2
    assert v2.preserve_cb_side(dict(before_native_roles=old,fine_roles=new,
        source=dict(player_positions='RB, CB' if new[0]==1 else 'CB' if new[0]==4 else 'LB')))==expected
