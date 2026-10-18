import copy
from scripts.season_cached_manager_repairs_v2_20261016 import filtered


def package(*names):
    return dict(managers=[dict(id=str(i),name=n,person_id='old-'+str(i)) for i,n in enumerate(names)])


def update(id,after,day='2019-08-01'):
    return dict(manager_id=str(id),after=after,first_fixture_date=day,club_id='club-'+str(id),
        club='club-'+str(id),before='old')


def plan(*rows):
    return dict(season='2019-20',updates=list(rows),unresolved=[],implementation_inputs=[],
        summary=dict(corrections=len(rows),mismatches_requiring_further_review=0))


def test_wrong_year_rejected_for_brazil_or_any_other_country():
    original=plan(update(0,'Eduardo Coudet','2020-08-08'))
    result,deferred=filtered(package('Luxemburgo','Eduardo Coudet'),original)
    assert result['updates']==[] and len(deferred)==1
    assert 'outside actual game start year' in deferred[0]['reason']
    assert original['updates'][0]['first_fixture_date']=='2020-08-08'


def test_preserved_owner_collision_is_not_fixed_by_inventing_person_ids():
    result,deferred=filtered(package('old','Eduardo Coudet'),plan(update(0,'Eduardo Coudet')))
    assert result['updates']==[] and 'assigned elsewhere' in deferred[0]['reason']


def test_deferred_move_propagates_back_through_proposed_owner_chain():
    result,deferred=filtered(package('A','B','C','D'),plan(update(0,'B'),update(1,'C'),update(2,'D')))
    assert result['updates']==[] and len(deferred)==3


def test_positive_source_bound_swap_and_unrelated_correction_can_proceed():
    original=plan(update(0,'B'),update(1,'A'),update(2,'D'))
    result,deferred=filtered(package('A','B','C'),original)
    assert result is original and deferred==[]


def test_valid_exact_private_plan_is_preserved_not_regenerated():
    original=plan(update(0,'C'));before=copy.deepcopy(original)
    result,deferred=filtered(package('A','B'),original)
    assert result is original and result==before and deferred==[]
