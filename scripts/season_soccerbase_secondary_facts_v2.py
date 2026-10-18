"""Read explicit biography rows without requiring unrelated Date Signed text.

Identity is exact numeric URL/full name/DOB. Country is a biographical source
claim, not proof of target-season ownership or international eligibility.
Leave the older capture parser and its frozen source records untouched.
"""
from bs4 import BeautifulSoup
from scripts import season_soccerbase_original_opening_v1 as original
from scripts.capture_soccerbase_august_squads_v1 import NATIONALITY

POLICY='original-numeric-full-identity-explicit-biography-country-row-v2'

def country(raw,*,person_id,name,birth_date,url,nationality_codes=None):
    identity=original.profile(raw,dict(provider_player_id=person_id,
        source_player_id='soccerbase:'+str(person_id)),url)
    if (identity['name'],identity['birth_date'])!=(name,birth_date):
        raise ValueError('country source does not identify the exact original actor')
    values=[]
    for row in BeautifulSoup(raw,'lxml').select('tr'):
        cells=row.find_all(['th','td'],recursive=False)
        if len(cells)==2 and cells[0].get_text(' ',strip=True)=='Nationality':
            values.append(cells[1].get_text(' ',strip=True))
    mapping=NATIONALITY if nationality_codes is None else nationality_codes
    if len(values)!=1 or values[0] not in mapping:
        raise ValueError('one explicit mapped country row required; never default to England')
    code=mapping[values[0]]
    if not code:raise ValueError('original country label has no supported source mapping')
    return dict(identity=identity,published_country=values[0],nationality=code,policy=POLICY,
        target_season_ownership_claimed=False,international_eligibility_claimed=False)
