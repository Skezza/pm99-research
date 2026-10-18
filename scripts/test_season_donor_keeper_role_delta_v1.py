import copy
import pytest
from scripts import season_donor_keeper_role_delta_v1 as source


def page():
    return '''<h1>Andrei Kanchelskis</h1><table class="infobox"><span class="bday">1969-01-23</span>
<tr><th class="infobox-header">International career</th></tr>
<tr><th>1989–1991</th><td>Soviet Union</td></tr><tr><th>1992–1998</th><td>Russia</td></tr>
<tr><th class="infobox-header">Managerial career</th></tr><tr><th>2010–2020</th><td>France</td></tr></table>
<p>Kanchelskis usually played as a right-winger throughout his career, where he was known for his work-rate.</p>'''


def test_known_country_is_from_dated_representation_not_manager_club_or_birthplace():
    result=source.known_biography(page())
    assert result['nationality']=='RUS' and result['role_by_existing_broad_position']=={'M':6,'F':11}
    assert result['exact_target_match_role_claimed'] is False
    assert source.known_biography(page()+'<table class="infobox">External videos</table>')==result


@pytest.mark.parametrize('old,new',[('Andrei Kanchelskis','Another Person'),('1969-01-23','1969-01-24'),
    ('1992–1998','2001–2008'),('>Russia<','>France<'),('right-winger throughout his career','goalkeeper throughout his career')])
def test_wrong_person_date_country_and_role_witness_refuse(old,new):
    with pytest.raises(ValueError):source.known_biography(page().replace(old,new))


def test_second_person_biography_and_later_other_international_country_refuse():
    with pytest.raises(ValueError):source.known_biography(page()+'<table class="infobox"><span class="bday">1969-01-23</span></table>')
    extra='<tr><th>1999–2000</th><td>France</td></tr>'
    with pytest.raises(ValueError):source.known_biography(page().replace('<tr><th class="infobox-header">Managerial career',extra+'<tr><th class="infobox-header">Managerial career'))


@pytest.mark.parametrize('roles,country',[([6],'RUS'),([9],None),(None,'RUS')])
def test_recipe_changes_only_selected_roles_country_and_matching_fallbacks(monkeypatch,roles,country):
    monkeypatch.setattr(source.packages,'validate_package',lambda p:None)
    p=dict(carrier_id=2774,name='Andrei Kanchelskis',facts=dict(primary_position='M',
        birth_date='1969-01-23',fine_roles={'policy':'preserve-existing-mode1'},nationality={'policy':'preserve-existing-mode1'}),
        ratings=dict(values=dict(handling=8,quality=67)),fact_fallbacks=[dict(field='nationality'),dict(field='height_cm')])
    package=dict(players=[p,dict(carrier_id=2,untouched=True)],artifacts=[],proofs=[])
    before=copy.deepcopy(package)
    plan=dict(transaction_id='test',updates=[dict(carrier_id=2774,before_player_sha256=source.digest(p),fine_roles=roles,nationality=country)])
    after=source.bind(package,plan)
    assert package==before and after['players'][1]==before['players'][1]
    assert after['players'][0]['ratings']==p['ratings']
    assert after['players'][0]['facts']['birth_date']=='1969-01-23'
    assert after['players'][0]['facts']['primary_position']=='M'
    assert after['players'][0]['facts']['fine_roles']==(roles if roles is not None else p['facts']['fine_roles'])
    assert after['players'][0]['facts']['nationality']==(country if country is not None else p['facts']['nationality'])
    after['players'][0]['facts']=copy.deepcopy(p['facts'])
    after['players'][0]['fact_fallbacks']=copy.deepcopy(p['fact_fallbacks'])
    assert after['players']==before['players']
    bad=copy.deepcopy(package);bad['players'][0]['ratings']['values']['quality']=99
    with pytest.raises(ValueError,match='preimage'):source.bind(bad,plan)


def test_factory_cannot_silently_drop_the_bounded_role_country_layer():
    with pytest.raises(ValueError):source.reject_factory_recipe(dict(artifacts=[dict(id=source.PREFIX+'test')]))
