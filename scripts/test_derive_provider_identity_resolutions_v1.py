import copy
from scripts import derive_provider_identity_resolutions_v1 as derive


def fixture(original='2007-02-03',annual='1991-12-10',known=((139402,'1991-12-10'),)):
    actual={'fixture':{'date':'2014-08-09'},'identity_bridges':{'starting_xi':[],
        'published_bench':[{'soccerbase_person':{'source_player_id':'soccerbase:53261',
            'name':'Harry Crawford','birth_date':original}}]}}
    yearly={'players':[{'name':'Harry Crawford','birth_date':annual}]}
    people={}
    for id,birthday in known:
        people.setdefault(('harrycrawford',birthday),{})[id]={'source_player_id':id,'name':'Harry Crawford',
            'birth_date':birthday,'source_profile_url':f'https://www.transfermarkt.co.uk/person/profil/spieler/{id}'}
    return actual,yearly,people


def test_two_sources_resolve_recycled_child_biography_without_modifying_originals():
    args=fixture(known=((139402,'1991-12-10'),(1289687,'2007-02-03')));before=copy.deepcopy(args)
    report,gaps=derive.derive('2014-15','Dartford',*args)
    assert not gaps and len(report['resolutions'])==1
    assert report['resolutions'][0]['canonical_source_player_id']==139402
    assert report['resolutions'][0]['published_birth_date']=='2007-02-03'
    assert args==before


def test_independent_original_agreement_can_reject_a_wrong_annual_birthday():
    args=fixture(original='1991-12-10',annual='1991-10-12')
    report,gaps=derive.derive('2014-15','Club',*args)
    assert not gaps
    r=report['resolutions'][0]
    assert r['canonical_birth_date']=='1991-12-10'
    assert r['annual_fact_policy']=='discard-conflicting-annual-biography'
    assert r['rejected_annual_birth_date']=='1991-10-12'


def test_two_plausible_namesakes_are_not_outvoted_or_automatically_merged():
    args=fixture(original='1990-01-01',known=((139402,'1991-12-10'),(123,'1990-01-01')))
    report,gaps=derive.derive('2014-15','Club',*args)
    assert not report['resolutions']
    assert gaps[0]['reason']=='both-birthdays-identify-plausible-independent-publisher-namesakes'


def test_annual_name_alone_without_independent_confirmed_person_does_not_authorise_DOB():
    report,gaps=derive.derive('2014-15','Club',*fixture(known=()))
    assert not report['resolutions'] and gaps


def test_same_namespace_biography_is_not_an_independent_publisher_vote():
    args=fixture(known=(('soccerbase:53261','1991-12-10'),))
    report,gaps=derive.derive('2014-15','Club',*args)
    assert not report['resolutions'] and gaps


def test_multiple_annual_people_with_same_name_are_not_collapsed():
    actual,annual,people=fixture();annual['players'].append(dict(annual['players'][0],birth_date='1990-01-01'))
    report,gaps=derive.derive('2014-15','Club',actual,annual,people)
    assert not report['resolutions'] and gaps[0]['reason']=='annual-same-name-identity-ambiguous'


def test_missing_original_birthday_requires_annual_and_independent_publisher_agreement():
    report,gaps=derive.derive('2014-15','Dartford',*fixture(original=None))
    assert not gaps
    assert report['allow_explicitly_reviewed_missing_provider_birth_date'] is True
    assert report['resolutions'][0]['published_birth_date'] is None
    assert report['resolutions'][0]['canonical_birth_date']=='1991-12-10'
    report,gaps=derive.derive('2014-15','Dartford',*fixture(original=None,known=()))
    assert gaps and not report['resolutions']
    assert not report.get('allow_explicitly_reviewed_missing_provider_birth_date')


def test_missing_birthday_without_a_target_annual_identity_is_logged_not_accepted():
    actual,annual,people=fixture(original=None)
    annual['players'][0]['name']='Another Player'
    report,gaps=derive.derive('2014-15','Dartford',actual,annual,people)
    assert not report['resolutions']
    assert gaps[0]['reason']=='missing-provider-DOB-and-no-unique-full-name-target-annual-biography'


def test_optional_unknown_bench_exclusion_is_explicit_and_does_not_authorise_a_birthday():
    actual,annual,people=fixture(original=None)
    annual['players'][0]['name']='Another Player'
    before=copy.deepcopy((actual,annual,people))
    report,gaps=derive.derive('2014-15','Club',actual,annual,people,
        exclude_unpublished_bench_birth_dates=True)
    assert not gaps and not report['resolutions']
    assert report['optional_bench_exclusions']==[{
        'source_provider_person_id':'soccerbase:53261','name':'Harry Crawford',
        'published_birth_date':None,
        'reason':'optional-published-bench-DOB-unpublished-and-no-target-annual-biography'}]
    assert not report.get('allow_explicitly_reviewed_missing_provider_birth_date')
    assert (actual,annual,people)==before


def test_opt_in_optional_exclusions_never_hide_an_unidentified_starter():
    actual,annual,people=fixture(original=None)
    actual['identity_bridges']['starting_xi']=actual['identity_bridges']['published_bench']
    actual['identity_bridges']['published_bench']=[]
    annual['players']=[]
    report,gaps=derive.derive('2014-15','Club',actual,annual,people,
        exclude_unpublished_bench_birth_dates=True)
    assert gaps and report['optional_bench_exclusions']==[]


def test_known_two_source_missing_bench_date_still_gets_proper_identity_resolution():
    report,gaps=derive.derive('2014-15','Club',*fixture(original=None),
        exclude_unpublished_bench_birth_dates=True)
    assert not gaps and report['optional_bench_exclusions']==[]
    assert report['resolutions'][0]['canonical_birth_date']=='1991-12-10'


def test_new_optional_bench_route_cannot_outvote_conflicting_historical_annual_with_copied_catalogues():
    report,gaps=derive.derive('2014-15','Club',
        *fixture(original='1991-12-10',annual='1991-10-12'),
        exclude_unpublished_bench_birth_dates=True)
    assert not report['resolutions']
    assert gaps[0]['reason']=='period-annual-DOB-conflict-needs-positive-historical-identity-witness'
