import pytest
from scripts.prepare_jedinstvo_2005_source_allocation_v1 import native_membership
from scripts.prepare_jedinstvo_2005_verified_inputs_v1 import home_ground


def test_original_starter_label_maps_to_native_starting_xi():
    assert native_membership('starting-xi')=='starting_xi'


@pytest.mark.parametrize('value',['used-opening-substitute','positive-bracketed-and-original-signed-arrival','positive-original-dated-opening-reserve'])
def test_positive_reserves_stay_reserves(value):
    assert native_membership(value)==value


@pytest.mark.parametrize('value',['annual-appearance','starting_xi','current-player','unknown',''])
def test_unknown_membership_is_not_silently_a_bench_member(value):
    with pytest.raises(ValueError):native_membership(value)


def fixture():
    return ('<div class="sb-team sb-heim"><a class="sb-vereinslink" href="/jedinstvo-bijelo-polje/startseite/verein/8357/saison_id/2005">Jedinstvo</a></div>'
        '<a href="/aktuell/waspassiertheute/aktuell/new/datum/2005-08-27">Date</a>'
        '<a href="/stadion/stadion/verein/8357/saison_id/2005">Gradski stadion</a>').encode()


def test_original_target_home_ground_has_its_own_date():
    assert home_ground(fixture())['date']=='2005-08-27'


@pytest.mark.parametrize('old,new',[
    ('8357','3140'),('saison_id/2005','saison_id/2006'),
    ('2005-08-27','2005-08-06'),('Gradski stadion','Partizan stadium'),('sb-heim','sb-gast')])
def test_other_club_year_date_ground_or_away_venue_rejected(old,new):
    with pytest.raises(ValueError):home_ground(fixture().decode().replace(old,new).encode())
