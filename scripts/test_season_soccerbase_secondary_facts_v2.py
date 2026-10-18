import pytest
from scripts.season_soccerbase_secondary_facts_v2 import country

RAW='<h1>Tunji Moses</h1><table><tr><td>Born</td><td>12 Sep, 1983</td></tr><tr><td>Nationality</td><td>England</td></tr></table>'
URL='https://www.soccerbase.com/players/player.sd?player_id=66030'

def check(raw=RAW,**kwargs):
    args=dict(person_id=66030,name='Tunji Moses',birth_date='1983-09-12',url=URL);args.update(kwargs)
    return country(raw,**args)

def test_country_does_not_depend_on_unrelated_date_signed_section():
    assert 'Date Signed' not in RAW
    result=check()
    assert result['nationality']=='ENG' and result['published_country']=='England'
    assert result['target_season_ownership_claimed'] is False

@pytest.mark.parametrize('fault',['name','DOB','URL','missing','duplicate','unmapped'])
def test_unknown_ambiguous_or_different_identity_is_not_assigned_a_default(fault):
    with pytest.raises(ValueError):
        if fault=='name':check(name='Another Moses')
        elif fault=='DOB':check(birth_date='1984-09-12')
        elif fault=='URL':check(person_id=66031)
        elif fault=='missing':check(RAW.replace('<tr><td>Nationality</td><td>England</td></tr>',''))
        elif fault=='duplicate':check(RAW.replace('</table>','<tr><td>Nationality</td><td>Scotland</td></tr></table>'))
        elif fault=='unmapped':check(RAW.replace('England','Unknown Republic'))
