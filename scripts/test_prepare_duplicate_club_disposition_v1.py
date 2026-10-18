import copy
import itertools
import random
import pytest
import datetime as dt
from scripts import prepare_duplicate_club_disposition_v1 as plan


@pytest.mark.parametrize('year,month,day,expected',[
    (1900,1,1,False),(1960,1,1,True),(1986,8,26,True),(1986,8,27,False),
    (1956,8,26,True),(1955,8,26,False),(2004,1,1,False),(1975,0,0,False)])
def test_unknown_source_date_retains_only_plausible_compact_seed_date(monkeypatch,year,month,day,expected):
    monkeypatch.setattr(plan.roster,'native_player',lambda raw,carrier:{'name_end':8})
    raw=bytearray(30);raw[2:5]=bytes.fromhex('dd6360')
    raw[20]=day^0x61;raw[21]=month^0x61
    raw[22:24]=bytes(b^0x61 for b in year.to_bytes(2,'little'))
    assert plan.plausible_unknown_birthday_slot(bytes(raw),7,dt.date(2001,8,26)) is expected


def test_unknown_date_guard_never_guesses_an_extended_record_offset():
    assert not plan.plausible_unknown_birthday_slot(bytes.fromhex('0000dd6361')+bytes(30),7,dt.date(2001,8,26))


def test_club_aliases_are_explicit_and_symmetric_not_substring_matches():
    assert plan.club_keys('Boreham W') & plan.club_keys('Boreham Wood')
    assert plan.club_keys('Dag & Red') & plan.club_keys('Dagenham & Redbridge')
    assert plan.club_keys('Fylde') & plan.club_keys('AFC Fylde')
    assert not plan.club_keys('Fylde') & plan.club_keys('AFC Fylde Women')
    assert not plan.club_keys('Wrexham') & plan.club_keys('Wrexham AFC Women')
    assert not plan.club_keys('Barrow') & plan.club_keys('Barrowford')


def test_cached_alias_sets_are_independent_and_alias_changes_are_not_hidden(monkeypatch):
    first=plan.club_keys('Boreham W');first.add('not-an-original-alias')
    assert 'not-an-original-alias' not in plan.club_keys('Boreham W')
    monkeypatch.setitem(plan.soccerbase.CLUB_ALIASES,'Test Published Short',('Test Published Full',))
    assert plan.club_keys('Test Published Short') & plan.club_keys('Test Published Full')


def test_assignment_matches_exhaustive_minimum_including_missing_edges():
    rng = random.Random(9917)
    for n in range(1,6):
        for _ in range(15):
            costs = [[None if rng.randrange(5)==0 else rng.randrange(100) for _ in range(n)] for _ in range(n)]
            eligible = [(sum(costs[i][j] for i,j in enumerate(choice)),choice)
                for choice in itertools.permutations(range(n))
                if all(costs[i][j] is not None for i,j in enumerate(choice))]
            if not eligible:
                with pytest.raises(ValueError): plan.minimum_assignment(costs)
            else:
                selected = plan.minimum_assignment(costs)
                assert sum(costs[i][j] for i,j in enumerate(selected)) == min(eligible)[0]
                assert len(set(selected)) == n
                assert selected == plan.minimum_assignment(costs)


@pytest.mark.parametrize('costs',[[],[[1,2]],[[None]],[[1,None],[1,None]]])
def test_invalid_or_impossible_capacity_never_gets_approximate_assignment(costs):
    with pytest.raises(ValueError): plan.minimum_assignment(costs)


def test_reserve_pool_selects_fitting_alternative_but_never_drops_an_unfittable_starter():
    costs=[[1,None,None,None],[None,None,5,3]]
    assert plan.minimum_reserve_pool_assignment(costs,[True,False,False,False])==[0,3]
    with pytest.raises(ValueError):
        plan.minimum_reserve_pool_assignment(costs,[True,True,False,False])


def test_oversupplied_published_bench_is_not_truncated_before_opted_in_fitting():
    desired=[{'membership':'starting_xi','id':i} for i in range(11)]
    desired += [{'membership':'published_bench','id':i} for i in range(11,18)]
    before=copy.deepcopy(desired)
    pool, needed=plan.opening_pool_for_capacity(desired,16,fit_verified_reserve_pool=True)
    assert pool==desired and len(pool)==18 and needed==0
    assert plan.opening_pool_for_capacity(desired,16)==(desired[:16],0)
    assert desired==before and pool is not desired


def test_opening_pool_preserves_shortage_and_never_waives_missing_starters():
    desired=[{'membership':'starting_xi','id':i} for i in range(11)]
    assert plan.opening_pool_for_capacity(desired,16,fit_verified_reserve_pool=True)==(desired,5)
    with pytest.raises(ValueError,match='eleven original starters'):
        plan.opening_pool_for_capacity(desired[:-1],16,fit_verified_reserve_pool=True)
    with pytest.raises(ValueError,match='exact first XI'):
        plan.opening_pool_for_capacity(desired,10,fit_verified_reserve_pool=True)


def test_reserve_pool_matches_exhaustive_minimum_with_mandatory_columns():
    rng=random.Random(20261011)
    for n,m in ((1,3),(2,4),(3,5)):
        for _ in range(12):
            mandatory=[i<n-1 for i in range(m)]
            costs=[[None if rng.randrange(4)==0 else rng.randrange(20) for _ in range(m)] for _ in range(n)]
            valid=[sum(costs[i][j] for i,j in enumerate(choice))
                for choice in itertools.permutations(range(m),n)
                if all(costs[i][j] is not None for i,j in enumerate(choice))
                and all(not required or j in choice for j,required in enumerate(mandatory))]
            if not valid:
                with pytest.raises(ValueError):plan.minimum_reserve_pool_assignment(costs,mandatory)
            else:
                choice=plan.minimum_reserve_pool_assignment(costs,mandatory)
                assert len(set(choice))==n
                assert sum(costs[i][j] for i,j in enumerate(choice))==min(valid)
                assert choice==plan.minimum_reserve_pool_assignment(costs,mandatory)


@pytest.mark.parametrize('costs,mandatory',[([],[]),([[1]],[True,False]),([[1],[2]],[False]),([[1,None]],[True,True])])
def test_reserve_pool_invalid_shapes_and_overfull_mandatory_sets_refused(costs,mandatory):
    with pytest.raises(ValueError):plan.minimum_reserve_pool_assignment(costs,mandatory)


def fixture():
    rows=[]; raw=[]; annual=[]
    for i in range(12):
        bio={'source_player_id':f'soccerbase:{i+1}', 'source_profile_url':f'https://www.soccerbase.com/players/player.sd?player_id={i+1}',
             'name':f'Real Player {i}', 'birth_date':f'1990-01-{i+1:02d}'}
        rows.append({'soccerbase_person':bio,'transfermarkt_person':None,
            'dated_match_position':'G' if i==0 else 'D','published_match_name':f'Player {i}'})
        raw.append({'url':bio['source_profile_url'],'path':f'original/{i}.html','sha256':'a'*64})
        annual.append({'name':bio['name'],'birth_date':bio['birth_date'],'position':'D','nationality':'ENG','height_cm':180})
    actual={'identity_bridges':{'starting_xi':rows[:11],'published_bench':rows[11:]},'raw_sources':raw}
    return actual,{'players':annual}


def test_matchday_people_keep_provider_namespace_and_exact_dated_role():
    actual,annual=fixture();before=copy.deepcopy((actual,annual))
    result=plan.matchday_people(actual,annual)
    assert len(result)==12 and result[0]['source_player']['position']=='G'
    assert result[0]['source_player']['nationality']=='ENG'
    assert result[0]['source_person']['source_player_id']=='soccerbase:1'
    assert result[0]['source_person']['source_provider']=='soccerbase'
    assert result[-1]['membership']=='published_bench'
    assert (actual,annual)==before


def test_opt_in_optional_unpublished_bench_dob_does_not_block_complete_xi():
    actual,annual=fixture()
    actual['identity_bridges']['published_bench'][0]['soccerbase_person']['birth_date']=None
    annual['players'].pop()
    before=copy.deepcopy((actual,annual))
    with pytest.raises(ValueError,match='missing provider DOB'):
        plan.matchday_people(actual,annual)
    result=plan.matchday_people(actual,annual,exclude_unpublished_bench_birth_dates=True)
    assert len(result)==11 and all(p['membership']=='starting_xi' for p in result)
    assert (actual,annual)==before


def test_optional_bench_policy_never_excludes_missing_starter_identity():
    actual,annual=fixture()
    actual['identity_bridges']['starting_xi'][1]['soccerbase_person']['birth_date']=None
    annual['players'].pop(1)
    with pytest.raises(ValueError,match='missing provider DOB'):
        plan.matchday_people(actual,annual,exclude_unpublished_bench_birth_dates=True)


def test_optional_bench_policy_never_waives_known_conflicting_dates():
    actual,annual=fixture();annual['players'][-1]['birth_date']='1989-12-10'
    with pytest.raises(ValueError,match='annual same-name biography'):
        plan.matchday_people(actual,annual,exclude_unpublished_bench_birth_dates=True)


def test_optional_bench_exclusion_is_not_a_single_player_or_unrecorded_source_waiver(tmp_path):
    with pytest.raises(ValueError,match='complete source transaction and explicit identity review'):
        plan.prepare('2002-03',3313,'Barnet',tmp_path/'p',tmp_path/'h',tmp_path/'e',tmp_path/'out',
            inspect_collisions=True,exclude_unpublished_bench_birth_dates=True)
    with pytest.raises(ValueError,match='complete source transaction and explicit identity review'):
        plan.prepare('2002-03',3313,'Barnet',tmp_path/'p',tmp_path/'h',tmp_path/'e',tmp_path/'out',
            identity_review_path=tmp_path/'review',exclude_unpublished_bench_birth_dates=True)


def test_explicit_provider_DOB_review_requires_annual_and_independent_person_agreement():
    actual,annual=fixture();original=actual['identity_bridges']['published_bench'][0]['soccerbase_person']
    published=original['birth_date'];canonical='1990-12-01'
    annual['players'][-1]['birth_date']=canonical
    person={'source_player_id':123,'name':original['name'],'birth_date':canonical}
    people={(plan.roster.normalise(person['name']),canonical):{123:person}}
    correction={'name':original['name'],'published_birth_date':published,
        'canonical_birth_date':canonical,'canonical_source_player_id':123}
    resolutions={original['source_player_id']:correction};before=copy.deepcopy((actual,annual))
    corrected=plan.matchday_people(actual,annual,identity_resolutions=resolutions,people=people)[-1]
    assert corrected['source_player']['birth_date']==canonical
    assert corrected['source_person']['source_player_id']==123
    assert corrected['source_display_aliases']['published_birth_date']==published
    assert corrected['source_identity_resolution']==correction
    assert (actual,annual)==before
    with pytest.raises(ValueError,match='independent publisher'):
        plan.matchday_people(actual,annual,identity_resolutions=resolutions,people={})
    with pytest.raises(ValueError,match='annual source agreement'):
        plan.matchday_people(actual,{'players':[]},identity_resolutions=resolutions,people=people)
    resolutions[original['source_player_id']]=dict(correction,published_birth_date='1900-01-01')
    with pytest.raises(ValueError,match='original full biography'):
        plan.matchday_people(actual,annual,identity_resolutions=resolutions,people=people)


@pytest.mark.parametrize('problem',['missing-starter','keeper','unknown-starting-role','double-annual'])
def test_incomplete_or_ambiguous_opening_roster_is_refused(problem):
    actual,annual=fixture()
    if problem=='missing-starter':actual['identity_bridges']['starting_xi'].pop()
    if problem=='keeper':actual['identity_bridges']['starting_xi'][1]['dated_match_position']='G'
    if problem=='unknown-starting-role':
        actual['identity_bridges']['starting_xi'][1]['dated_match_position']=None
        annual['players'][1]['position']=None
    if problem=='double-annual':annual['players'].append(copy.deepcopy(annual['players'][0]))
    with pytest.raises(ValueError):plan.matchday_people(actual,annual)


def test_missing_bench_role_is_not_invented_and_missing_secondary_facts_are_explicit():
    actual,annual=fixture();actual['identity_bridges']['published_bench'][0]['dated_match_position']=None
    result=plan.matchday_people(actual,{'players':[]})
    assert len(result)==11
    assert all(p['source_player']['nationality'] is None for p in result)


def test_missing_original_badge_can_use_identity_matched_target_season_basic_position():
    actual,annual=fixture();actual['identity_bridges']['starting_xi'][1]['dated_match_position']=None
    before=copy.deepcopy((actual,annual));result=plan.matchday_people(actual,annual)
    assert result[1]['source_player']['position']=='D'
    assert result[1]['source_role_basis']['exact_match_deployment_claimed'] is False
    assert result[1]['source_role_basis']['original_match_role'] is None
    assert (actual,annual)==before
    annual['players'][1]['name']='Different Full Name'
    with pytest.raises(ValueError,match='unsourced role'):plan.matchday_people(actual,annual)


def test_wrong_namesake_birthday_is_not_treated_as_missing_annual_facts():
    actual,annual=fixture()
    annual['players'][-1]['birth_date']='1989-12-10'
    with pytest.raises(ValueError,match='annual same-name biography'):
        plan.matchday_people(actual,annual)


def test_retaining_original_DOB_requires_explicit_rejected_annual_row_and_independent_identity():
    actual,annual=fixture();original=actual['identity_bridges']['published_bench'][0]['soccerbase_person']
    rejected='1989-12-10';annual['players'][-1]['birth_date']=rejected
    person={'source_player_id':123,'name':original['name'],'birth_date':original['birth_date']}
    people={(plan.roster.normalise(person['name']),person['birth_date']):{123:person}}
    review={'name':original['name'],'published_birth_date':original['birth_date'],
        'canonical_birth_date':original['birth_date'],'canonical_source_player_id':123,
        'annual_fact_policy':'discard-conflicting-annual-biography','rejected_annual_birth_date':rejected}
    resolutions={original['source_player_id']:review}
    result=plan.matchday_people(actual,annual,identity_resolutions=resolutions,people=people)[-1]
    assert result['source_player']['birth_date']==original['birth_date']
    assert result['source_player']['nationality'] is None
    assert result['source_identity_resolution']==review
    resolutions[original['source_player_id']]=dict(review,rejected_annual_birth_date='1980-01-01')
    with pytest.raises(ValueError,match='annual source agreement'):
        plan.matchday_people(actual,annual,identity_resolutions=resolutions,people=people)


@pytest.mark.parametrize('born,refused',[('2007-02-03',True),('2015-01-01',True),
    ('2002-08-10',True),('2002-08-09',False),('1999-07-13',False)])
def test_opening_age_guard_rejects_children_not_authentic_teenagers(born,refused):
    people=[{'source_player':{'name':'Real Fixture Person','birth_date':born}}]
    if refused:
        with pytest.raises(ValueError,match='child/future namesake'):
            plan.validate_opening_birth_dates(people,'2014-08-09')
    else:
        plan.validate_opening_birth_dates(people,'2014-08-09')


def test_annual_reserve_requires_positive_matching_ownership_bracket():
    person={'source_player_id':42,'name':'Reserve Player','birth_date':'1990-01-02'}
    people={('reserveplayer','1990-01-02'):{42:person}}
    annual={'players':[dict(person,position='D')]};raw={'status':'raw-source-reparsed'}
    def edge(day,before,after):return {'date':day,'from_club_id':before,'to_club_id':after,'from_club':str(before),'to_club':str(after)}
    events={42:[edge('2020-07-01',1,2),edge('2022-07-01',2,3)]}
    assert len(plan.reserve_people(annual,raw,people,events,2,'2021-08-21',[]))==1
    assert not plan.reserve_people(annual,raw,people,events,1,'2021-08-21',[])
    assert not plan.reserve_people(annual,raw,people,{},2,'2021-08-21',[])
    assert not plan.reserve_people(annual,raw,people,{42:events[42][:1]},2,'2021-08-21',[])
    assert not plan.reserve_people(annual,raw,people,events,2,'2020-07-01',[])
    selected=[{'source_player':{'name':'Reserve Player','birth_date':'1990-02-01'}}]
    assert not plan.reserve_people(annual,raw,people,events,2,'2021-08-21',selected)


def matchday_identity_fixture():
    actual,annual=fixture()
    actual.update(source_capture={'source_path':'soccerbase/team/42/august'},
        fixture={'date':'2014-08-09'},original_match={
            'provider_club_id':'soccerbase:42','date':'2014-08-09',
            'fixture_date_published_on_original_schedule':True,
            **{group:[{'source_player_id':r['soccerbase_person']['source_player_id']} for r in rows]
                for group,rows in actual['identity_bridges'].items()}})
    return actual,plan.matchday_people(actual,annual)


def test_complete_original_matchday_can_establish_its_own_provider_identity_without_TM_mapping():
    actual,desired=matchday_identity_fixture();before=copy.deepcopy((actual,desired))
    witness=plan.original_matchday_club_witness(actual,desired)
    assert witness['source_club_id']=='soccerbase:42'
    assert not witness['cross_provider_club_identity_claimed']
    assert not witness['annual_reserve_ownership_authorised']
    assert len(witness['selected_original_starting_xi'])==11
    assert (actual,desired)==before


@pytest.mark.parametrize('problem',['wrong-provider','date','date-not-original','missing-starter','invented-bench','annual-reserve','repeated-place'])
def test_matchday_only_route_never_waives_source_or_full_roster_evidence(problem):
    actual,desired=matchday_identity_fixture()
    if problem=='wrong-provider':actual['original_match']['provider_club_id']='soccerbase:43'
    if problem=='date':actual['original_match']['date']='2014-08-10'
    if problem=='date-not-original':actual['original_match']['fixture_date_published_on_original_schedule']=False
    if problem=='missing-starter':desired.pop(0)
    if problem=='invented-bench':desired[-1]['source_display_aliases']['source_provider_person_id']='soccerbase:999'
    if problem=='annual-reserve':desired[-1]['membership']='positive-annual-and-dated-opening-reserve'
    if problem=='repeated-place':desired.append(copy.deepcopy(desired[-1]))
    with pytest.raises(ValueError):plan.original_matchday_club_witness(actual,desired)


def test_cached_native_allocation_matches_existing_fitter_without_reindexing(monkeypatch):
    from scripts.test_season_duplicate_ownership_delta_v1 import fixture as native_fixture
    from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload
    from scripts import season_duplicate_ownership_delta_v1 as delta
    package,proposal=native_fixture('dd6361')
    slots=[copy.deepcopy(package['players'][1])]
    second=copy.deepcopy(slots[0]);second.update(id='slot-three',carrier_id=3);slots.append(second)
    desired=[copy.deepcopy(proposal['updates'][0]['replacement'])]
    extra=copy.deepcopy(desired[0]);extra['source_person']['source_player_id']=101
    extra['source_player'].update(name='Another King',position='G');desired.append(extra)
    original=_indexed_fdi([(2,'',_dd6361_player_payload(2)),(3,'',_dd6361_player_payload(3))])
    reader=plan.IndexedFDIFile;calls=[]
    class CachedReader:
        @staticmethod
        def from_bytes(data):
            calls.append(data)
            return reader.from_bytes(data)
    monkeypatch.setattr(plan,'IndexedFDIFile',CachedReader)
    result=plan.allocate(original,slots,desired,{})
    assert len(calls)==1
    assert len(result)==2 and {r['replacement']['source_player']['position'] for r in result}=={'G','D'}
    mismatched={p['source_person']['source_player_id']:{'birth_date':'1900-01-01'} for p in desired}
    assert plan.allocate(original,slots,desired,{},published_families=mismatched)==result
    matching_but_invalid={desired[0]['source_person']['source_player_id']:
        {'birth_date':desired[0]['source_person']['birth_date'],'policy':'unproven'}}
    with pytest.raises(ValueError,match='different confirmed person'):
        plan.allocate(original,slots,desired,{},published_families=matching_but_invalid)
    for row in result:
        view={'players':[{'id':row['player_id'],'name':row['replacement']['source_player']['name'],
                         'source_name':row['replacement']['source_player']['name']}]}
        assert delta.fit_display_names(original,view,{'updates':[row]})[0]==row['display']


@pytest.mark.parametrize('full,label,expected',[
    ('Reece Hall-Johnson','R Hall-Johnson','Hall-Johnson'),
    ('Dawid Szczepaniak','D Szczepaniak','Szczepaniak'),
    ('Paolo di Giacomo','P di Giacomo','P. di Giacomo'),
])
def test_replayed_match_full_family_never_drops_particles_or_hyphens(full,label,expected):
    replacement={'source_person':{'source_player_id':'soccerbase:42','birth_date':'1990-01-01','name':full},
        'source_display_aliases':{'policy':plan.soccerbase.POLICY,'source_person_id':'soccerbase:42',
        'source_provider_person_id':'soccerbase:42','birth_date':'1990-01-01',
        'names':[{'field':'dated-match-label','name':label}]}}
    assert plan.match_family_names(replacement)==[(expected,'entire-family-from-replayed-biography-and-match-label')]


@pytest.mark.parametrize('label',['S Hall-Johnson','R Johnson','Hall-Johnson','R Hall'])
def test_match_family_requires_exact_original_initial_and_whole_remainder(label):
    replacement={'source_person':{'source_player_id':'soccerbase:42','birth_date':'1990-01-01','name':'Reece Hall-Johnson'},
        'source_display_aliases':{'policy':plan.soccerbase.POLICY,'source_person_id':'soccerbase:42',
        'source_provider_person_id':'soccerbase:42','birth_date':'1990-01-01',
        'names':[{'field':'dated-match-label','name':label}]}}
    assert plan.match_family_names(replacement)==[]


@pytest.mark.parametrize('order,membership,role,expected',[
    (1,'starting_xi','G',True),(1,'starting_xi','F',False),(1,'published_bench','G',False),
    (2,'starting_xi','D',True),(11,'starting_xi','F',True),(2,'starting_xi','G',False),
    (11,'published_bench','F',False),(12,'starting_xi','D',False),
    (18,'published_bench','G',True),(0,'positive-annual-and-dated-opening-reserve','D',True),
])
def test_whole_club_startup_assignment_never_puts_an_outfielder_in_goal_or_bench_person_in_XI(order,membership,role,expected):
    assert plan.opening_edge(order,{'membership':membership,'source_player':{'position':role}}) is expected


def exchange_allocation(keeper_order=7):
    return [{'carrier_id':100+n,'display':{'display_name':f'Player {n}'},
        'native_startup_order_before':n,'replacement':{'membership':'starting_xi' if n<=11 else 'published_bench',
        'source_player':{'position':'G' if n==keeper_order else 'D'}}} for n in range(1,19)]


def test_keeper_exchange_changes_exactly_two_existing_starter_orders():
    allocation=exchange_allocation();before=copy.deepcopy(allocation)
    assert plan.keeper_exchange(allocation)==[
        {'carrier_id':101,'expected_name':'Player 1','before':1,'after':7},
        {'carrier_id':107,'expected_name':'Player 7','before':7,'after':1}]
    assert allocation==before
    assert plan.keeper_exchange(exchange_allocation(1))==[]


@pytest.mark.parametrize('problem',['reserve','two-keepers','missing-XI','repeated-order','unknown-outfielder'])
def test_keeper_exchange_refuses_missing_source_or_unproved_actual_XI(problem):
    allocation=exchange_allocation()
    if problem=='reserve':allocation=exchange_allocation(18)
    if problem=='two-keepers':allocation[2]['replacement']['source_player']['position']='G'
    if problem=='missing-XI':allocation[10]['replacement']['membership']='published_bench'
    if problem=='repeated-order':allocation[10]['native_startup_order_before']=10
    if problem=='unknown-outfielder':allocation[0]['replacement']['source_player']['position']=None
    with pytest.raises(ValueError):plan.keeper_exchange(allocation)


def test_optional_exchange_never_relaxes_the_XI_bench_boundary():
    for role in 'GDMF':
        assert plan.opening_edge(7,{'membership':'starting_xi','source_player':{'position':role}},
            allow_keeper_order_exchange=True)
        assert not plan.opening_edge(12,{'membership':'starting_xi','source_player':{'position':role}},
            allow_keeper_order_exchange=True)
        assert not plan.opening_edge(7,{'membership':'published_bench','source_player':{'position':role}},
            allow_keeper_order_exchange=True)
