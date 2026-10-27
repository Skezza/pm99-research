import pytest
from scripts import season_dfb_profile_country_v1 as source

URL='https://datencenter.dfb.de/datencenter/personen/rein-van-duijnhoven/spieler'

def body():
    return f'''<link rel="canonical" href="{URL}"><table>
<tr><th>Name:</th><td>Rein van Duijnhoven</td></tr>
<tr><th>Geburtstag:</th><td>05.09.1967</td></tr>
<tr><th>Nation:</th><td>Niederlande</td></tr></table>'''.encode()

def parse(raw):
    return source.parse_country(raw,dict(provider=source.PROVIDER,url=URL),
        actor_name='Rein van Duijnhoven',birth_date='1967-09-05')

def test_explicit_canonical_same_identity_country():
    result=parse(body())
    assert result['nationality']=='NED'
    assert not result['target_season_ownership_claimed']

@pytest.mark.parametrize('before,after',[
    (b'1967',b'1968'), (b'Rein van Duijnhoven',b'Another Person'),
    (b'/rein-van-duijnhoven/',b'/someone-else/'),
    (b'Niederlande',b'Unknown Nation'), (b'Nation:',b'Geburtsort:'),
])
def test_false_or_incomplete_identity_and_country_refused(before,after):
    with pytest.raises(ValueError):parse(body().replace(before,after))

def test_ambiguous_country_refused():
    with pytest.raises(ValueError,match='duplicate'):
        parse(body().replace(b'</table>',b'<tr><th>Nation:</th><td>Deutschland</td></tr></table>'))
