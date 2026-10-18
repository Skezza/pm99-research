import copy
import pytest
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts import prepare_duplicate_whole_club_native_v1 as native


def proposals():
    result=[]
    for tag,start in [('a',100),('b',200)]:
        rows=[{'player_id':f'{tag}-{i}','carrier_id':start+i} for i in range(1,19)]
        people=[{'source_person':{'source_player_id':start+1000+i},
            'source_player':{'name':f'Source {tag} {i}','birth_date':'1990-01-01'}} for i in range(1,19)]
        result.append({'schema_version':'pm99-whole-club-collision-diagnostic-only-v1',
            'collision_inspection_only':True,'approved_for_native_publication':False,
            'season':'2021-22','release_id':'baseline','package_sha256':'package','jug_sha256':'jug','eq_sha256':'eq',
            'before_club':{'id':tag,'carrier_id':start,'roster_player_ids':[r['player_id'] for r in rows]},
            'retained_duplicate_clubs':[{'id':tag+'-retained'}], 'new_club':'New '+tag,
            'original_opening':{'fixture':{'date':'2021-08-21'}},
            'allocation':rows,'allocation_gap':None,'desired_people':people,'outside_collisions':[]})
    result[0]['outside_collisions']=[{'source_player_id':1101,'other_player_id':'b-1','other_club_id':'b'}]
    return result


def test_complete_pair_covers_collision_without_authorising_publication():
    ps=proposals();before=copy.deepcopy(ps)
    proof=paired.validate_group(ps)
    assert proof['corrected_slots']==36 and len(proof['covered_other_club_copies'])==1
    assert proof['native_publication_authorised'] is False and ps==before


def test_explicit_complete_singleton_never_waives_outside_collisions():
    ps=proposals()[:1]
    ps[0]['outside_collisions']=[]
    document={'schema_version':paired.SINGLETON_SCHEMA}
    assert paired.source_guard(document,ps)['corrected_slots']==18
    with pytest.raises(ValueError,match='at least two'):
        paired.source_guard({'schema_version':paired.SCHEMA},ps)
    with pytest.raises(ValueError,match='one full club'):
        paired.source_guard(document,proposals())
    ps[0]['outside_collisions']=[{'other_club_id':'outside','other_player_id':'outside-1'}]
    with pytest.raises(ValueError,match='zero outside copies'):
        paired.source_guard(document,ps)


def test_conflicting_provider_birthdays_do_not_create_two_players_in_one_club():
    ps=proposals();first=ps[0]['desired_people'][0]
    ps[0]['desired_people'][1]['source_player']=dict(first['source_player'],birth_date='1990-02-01')
    with pytest.raises(ValueError,match='resolve provider identity/DOB conflict'):
        paired.validate_group(ps)


def test_old_candidate_with_recycled_child_biography_cannot_pass_current_guard():
    ps=proposals();ps[0]['desired_people'][0]['source_player']['birth_date']='2015-01-01'
    with pytest.raises(ValueError,match='child/future namesake'):
        paired.validate_group(ps)


@pytest.mark.parametrize('problem',['one','different-baseline','singleton-schema','missing','carrier',
    'same-person','same-identity','outside','unretired-slot','remove-last-real-club','same-target','empty'])
def test_pair_rejects_incomplete_dispositions_or_incoming_copies(problem):
    ps=proposals()
    if problem=='one':ps.pop()
    if problem=='different-baseline':ps[1]['eq_sha256']='other'
    if problem=='singleton-schema':ps[0]['schema_version']='pm99-duplicate-whole-club-disposition-source-plan-v1'
    if problem=='missing':ps[0]['before_club']['roster_player_ids'].append('missing')
    if problem=='carrier':ps[1]['allocation'][0]['carrier_id']=101
    if problem=='same-person':ps[1]['desired_people'][0]['source_person']=copy.deepcopy(ps[0]['desired_people'][0]['source_person'])
    if problem=='same-identity':ps[1]['desired_people'][0]['source_player']=copy.deepcopy(ps[0]['desired_people'][0]['source_player'])
    if problem=='outside':ps[0]['outside_collisions'][0]['other_club_id']='outside'
    if problem=='unretired-slot':ps[0]['outside_collisions'][0]['other_player_id']='not-in-retired-roster'
    if problem=='remove-last-real-club':ps[0]['retained_duplicate_clubs']=[{'id':'b'}]
    if problem=='same-target':ps[1]['new_club']=ps[0]['new_club']
    if problem=='empty':ps[0]['allocation']=[]
    with pytest.raises(ValueError):paired.validate_group(ps)


def test_diagnostic_singleton_cannot_enter_native_candidate_builder(tmp_path):
    import json
    proposal=tmp_path/'source.json';proposal.write_text(json.dumps(proposals()[0]))
    with pytest.raises(ValueError,match='explicit source-only proposal'):
        native.prepare(proposal,tmp_path/'manager.html',tmp_path/'candidate')
    assert not (tmp_path/'candidate').exists()
