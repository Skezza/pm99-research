import pytest
from scripts import season_shtanyuk_2002_coupled_alias_v1 as subject


def inputs():
    actors={10542:dict(id='keep',club_id='stoke',source_name='Sergey Shtanyuk',name='Sergey Shtanyuk'),
        10580:dict(id='copy',club_id='stoke',source_name='Siarhei Shtaniuk',name='Siarhei Shtaniuk'),
        7972:dict(id='foreign',club_id='shinnik',source_name='Sergey Shtanyuk',name='Shtanyuk')}
    clubs={348:dict(id='stoke',roster_player_ids=['keep','copy']),757:dict(id='shinnik',roster_player_ids=['foreign'])}
    facts={10542:dict(name='Sergey SHTANYUK',birth_date='1973-08-13',position='D',startup_order=2),
        10580:dict(name='Siarhei SHTANIUK',birth_date='1972-01-11',position='D',startup_order=13),
        7972:dict(name='Shtanyuk',birth_date='1900-01-01',position='D',startup_order=8)}
    return [actors,clubs,facts,{10542:{348},10580:{348},7972:{757}},set(range(10))|{10542},set(range(10))|{7972}]


def test_all_three_owners_and_one_explicit_native_starter_accounted_for():
    subject.guard(*inputs())


@pytest.mark.parametrize('change',['wrong_owner','shared_owner','changed_DOB','wrong_namesake',
    'wrong_native_name','changed_foreign_order','unexpected_Stoke_starter','foreign_not_starter'])
def test_no_arbitrary_same_name_merge_or_bench_waiver(change):
    args=inputs()
    if change=='wrong_owner':args[0][7972]['club_id']='different'
    elif change=='shared_owner':args[3][7972].add(758)
    elif change=='changed_DOB':args[2][7972]['birth_date']='1973-08-13'
    elif change=='wrong_namesake':args[0][10580]['source_name']='Another Shtaniuk'
    elif change=='wrong_native_name':args[2][7972]['name']='Different'
    elif change=='changed_foreign_order':args[2][7972]['startup_order']=12
    elif change=='unexpected_Stoke_starter':args[4].remove(0);args[4].add(10580)
    else:args[5].remove(7972);args[5].add(10)
    with pytest.raises(ValueError):subject.guard(*args)
