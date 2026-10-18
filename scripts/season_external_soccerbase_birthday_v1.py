"""Explicit secondary biography for a dated player's unpublished birthday.

Do not weaken ordinary full-name/DOB matching or overwrite a known original
date. Require the same original numerical profile, a positive original club
career interval, a dated match appearance and the external publisher's literal
full name/role/club-season. A single published secondary fact is not consensus.
"""
import copy
from datetime import datetime,date
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as biographies
from scripts import season_original_soccerbase_reserves_v1 as careers
from scripts import season_historical_roster_audit_v1 as roster

POLICY='original-numeric-Soccerbase-missing-DOB-and-literal-StatsCrew-secondary-biography-v1'


def raw_source(binding):
    path=registry.ROOT/binding['path'];receipt=registry.ROOT/binding['source_receipt_path']
    if (registry.sha256_file(path)!=binding['sha256']
            or registry.sha256_file(receipt)!=binding['source_receipt_sha256']
            or pipeline.read_json_file(receipt)!=dict(url=binding['url'],sha256=binding['sha256'])):
        raise ValueError('secondary biography original URL/body/receipt changed')
    return path.read_bytes()


def statscrew(raw,name,club,role,interval):
    page=BeautifulSoup(raw,'lxml')
    headings=[h.get_text(' ',strip=True) for h in page.select('h1')]
    if headings not in ([name],[name,'World Football']):raise ValueError('one exact external player biography required')
    # Only the person's paragraph containing Born, not script/advert metadata.
    paragraphs=[p for p in page.find_all('p') if any('Born:' in str(t) for t in p.find_all(string=True,recursive=False))]
    if len(paragraphs)!=1:raise ValueError('one original external birthday paragraph required')
    text=paragraphs[0].get_text(' ',strip=True)
    match=re.findall(r'\bBorn:\s+([A-Z][a-z]+ \d{1,2}, \d{4})\b',text)
    label={'G':'G - Goalkeeper','D':'D - Defender','M':'M - Midfielder','F':'F - Forward'}[role]
    if len(match)!=1 or not text.startswith(name+' Born:') or 'Position: '+label not in text:
        raise ValueError('external full-name/date/role does not identify the dated actor')
    career=[]
    for table in page.select('table'):
        first=table.find('tr')
        headers=[c.get_text(' ',strip=True) for c in first.find_all(['th','td'])] if first else []
        if headers!=['Year','Country','Level','League','Team']:continue
        for tr in table.find_all('tr')[1:]:
            cells=[c.get_text(' ',strip=True) for c in tr.find_all('td',recursive=False)]
            if len(cells)!=5:continue
            season=re.fullmatch(r'(\d{4})-(\d{2})',cells[0])
            if season is None:continue
            year=int(season[1])
            if (int(season[2])!=(year+1)%100 or not date.fromisoformat(interval['from_date']).year<=year<date.fromisoformat(interval['to_date']).year):
                continue
            if roster.normalise(cells[4]) not in {roster.normalise(club),roster.normalise(club+' FC'),roster.normalise(club+' Football Club')}:
                continue
            career.append(dict(season=cells[0],club=cells[4]))
    if len(career)!=1:raise ValueError('external biography lacks one club-season inside the original playing spell')
    return dict(birth_date=datetime.strptime(match[0],'%B %d, %Y').date().isoformat(),external_club_season=career[0])


def resolve(review,bio,actual):
    if (review.get('secondary_birthday_policy')!=POLICY or bio.get('birth_date') is not None
            or review.get('published_birth_date') is not None or review['name']!=bio['name']
            or review['source_provider_person_id']!=bio['source_player_id']
            or review['canonical_source_player_id']!=bio['source_player_id']):
        raise ValueError('external secondary route cannot override known dates or another original person')
    rows=[p for group in ('starting_xi','published_bench') for p in actual['original_match'][group]
        if p['source_player_id']==bio['source_player_id']]
    if len(rows)!=1 or rows[0]['position'] not in ('G','D','M','F'):
        raise ValueError('secondary birthday requires the original dated numerical actor/role')
    profile=review['original_profile'];raw=raw_source(profile)
    if profile['url']!=bio['source_profile_url']:raise ValueError('secondary birthday original profile URL differs')
    parsed=biographies.profile(raw,rows[0],profile['url'],allow_missing_birth_date=True)
    if parsed!=bio:raise ValueError('original unpublished full biography no longer independently reproduces')
    team=actual['original_match']['provider_club_id']
    if not re.fullmatch(r'soccerbase:\d+',team):raise ValueError('original numerical club missing')
    interval=careers.career_interval(raw,int(team.split(':')[1]),actual['fixture']['date'])
    external=review['external_biography'];url=urlparse(external['url'])
    if (url.scheme!='https' or url.netloc!='www.statscrew.com'
            or not re.fullmatch(r'/worldfootball/stats/p-[a-z0-9]+',url.path) or url.query or url.fragment):
        raise ValueError('unsupported secondary original biography URL')
    found=statscrew(raw_source(external),bio['name'],actual['club'],rows[0]['position'],interval)
    if found['birth_date']!=review['canonical_birth_date']:
        raise ValueError('secondary birthday differs from its literal original publication')
    born=date.fromisoformat(found['birth_date']);day=date.fromisoformat(actual['fixture']['date'])
    if not 12 <= (day-born).days/365.2425 <= 50:raise ValueError('secondary birthday outside plausible playing age')
    person=copy.deepcopy(bio)
    person.update(birth_date=found['birth_date'],source_provider='soccerbase',identity_policy=POLICY,
        secondary_birth_date_original=external,birthday_confidence='single-original-secondary-publication-not-consensus',
        competing_date_lead=copy.deepcopy(review.get('competing_date_lead')))
    return person
