import pytest
from scripts import season_period_squad_carrier_label_v2 as source


@pytest.mark.parametrize('native,full',[('Röber','Jürgen Röber'),('Jürgen Röber','Jürgen Röber'),('van Gaal','Louis van Gaal')])
def test_only_literal_native_published_surname_or_fullname_can_be_retained(native,full):
    source.coach_alias(native,full)


@pytest.mark.parametrize('native,full',[('J. R.','Jürgen Röber'),('Röber','Another Coach'),('',''),('Röber','Röbert')])
def test_manager_alias_not_initial_expansion_or_arbitrary_fuzzy_match(native,full):
    with pytest.raises(ValueError):source.coach_alias(native,full)


def stadium():
    return b'<h1>Olympiastadion</h1><p>Hertha BSC seit 1963, 1986 und 1988</p>'


def review():
    return dict(kind='official-Hertha-Olympiastadion-continuity-v1',original=dict(url='https://www.herthabsc.com/de/club/olympiastadion'))


def test_dated_ground_witness_not_a_claim_about_current_capacity_or_opening_xi():
    proof=source.ground(stadium(),review(),'Hertha Berlin','Olympiastadion',2000)
    assert proof['exact_target_season_capacity_not_approved'] is True


@pytest.mark.parametrize('year',[1962,1986,1987,1988])
def test_ground_explicit_historical_exceptions_not_ignored(year):
    with pytest.raises(ValueError):source.ground(stadium(),review(),'Hertha Berlin','Olympiastadion',year)


@pytest.mark.parametrize('bad',['other-club','other-ground','other-original','other-body'])
def test_ground_url_identity_and_literal_anchors_are_required(bad):
    data=stadium();r=review();club='Hertha Berlin';name='Olympiastadion'
    if bad=='other-club':club='1. FC Koln'
    if bad=='other-ground':name='Müngersdorfer Stadion'
    if bad=='other-original':r['original']['url']='https://example.com/stadium'
    if bad=='other-body':data=data.replace(b'1963',b'2003')
    with pytest.raises(ValueError):source.ground(data,r,club,name,2000)


@pytest.mark.parametrize('label,group,accepted',[('2000/01','germany',True),('2000/2001','germany',True),
    ('2000/02','germany',False),('2001/02','germany',False),('2000','germany',False),
    ('2000','finland',True),('2001','finland',False),('2000/01','finland',False)])
def test_literal_period_check_does_not_accept_calendar_ending_year_surrogates(tmp_path,label,group,accepted):
    path=tmp_path/'squad.txt';path.write_text('= Club Name - League '+label+'\n')
    if accepted:assert source.dated_annual_title(path,'2000-01',group)==label
    else:
        with pytest.raises(ValueError):source.dated_annual_title(path,'2000-01',group)
