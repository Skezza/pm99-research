"""One positively proved reserve-alias repair; no general fuzzy alias join."""
import html
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import original_namesake_birthday_witness_v1 as witness
from scripts import season_wikipedia_career_identity_v1 as wiki

POLICY='original-Savio-Savinho-primary-alias-and-Bobb-August-friendly-reserve-2024-v1'
SOURCES={
    'savio-alias-primary-opening-Chelsea2024':'https://www.chelseafc.com/en/news/article/match-report-chelsea-0-2-man-city-18082024',
    'oscar-bobb-primary-August3-2024-friendly':'https://www.chelseafc.com/en/news/article/match-report-manchester-city-4-2-chelsea',
    'oscar-bobb-original-wikipedia':'https://en.wikipedia.org/wiki/Oscar_Bobb',
    'six-dates-original-man-city-2024-squad':witness.KEYS['six-dates-original-man-city-2024-squad'],
    'six-dates-original-Savio-Savinho-primary-alias':'https://www.premierleague.com/en/news/4051917',
}


def original(key,proofs):
    path,raw,binding=source_rows(key)
    receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
    if receipt['url']!=SOURCES[key]:raise ValueError('alias reserve original URL differs')
    proofs.append(dict(binding,url=receipt['url'],source_receipt_path=registry.relative_workspace_path(path.with_suffix('.source.json')),
        source_receipt_sha256=registry.sha256_file(path.with_suffix('.source.json'))))
    return raw


def report(raw,*,opening):
    page=BeautifulSoup(raw,'html.parser')
    title=('Match report: Chelsea 0-2 Man City' if opening else 'Match Report: Manchester City 4-2 Chelsea')
    date='2024-08-18' if opening else '2024-08-03'
    dates=set(re.findall(r'"content_publish_date"\s*:\s*"(\d{4}-\d{2}-\d{2})T',html.unescape(raw.decode())))
    if page.title is None or page.title.get_text(' ',strip=True)!=title+' | News | Official Site | Chelsea Football Club' or dates!={date}:
        raise ValueError('primary alias reserve match title/date differs')
    paragraphs=[p.get_text(' ',strip=True) for p in page.find_all('p')]
    if opening:
        expected='Man City : Ederson, Lewis, Akanji, Dias, Gvardiol, Kovacic, De Bruyne (C), Bernardo, Doku, Savinho (Foden 46), Haaland'
        if len([p for p in paragraphs if p.startswith(expected+' Unused substitutes')])!=1:
            raise ValueError('primary first-league XI does not positively name Savinho')
    else:
        expected="Manchester City starting XI: Ortega, Lewis, Phillips, Gvardiol, Wilson-Esbrand, Kovacic, O'Reilly, Bobb, McAtee, Grealish, Haaland"
        if paragraphs.count(expected)!=1 or not any('there was a goal for Oscar Bobb' in p for p in paragraphs):
            raise ValueError('primary August friendly does not positively identify Oscar Bobb')
    return date


def evidence():
    proofs=[]
    raw=original('six-dates-original-man-city-2024-squad',proofs)
    identity=witness.parse('six-dates-original-man-city-2024-squad',raw)
    original('six-dates-original-Savio-Savinho-primary-alias',proofs)
    if identity['birth_date']!='2004-04-10' or identity['period_person_source_id']!=743591:
        raise ValueError('primary alias person/DOB differs')
    opening=report(original('savio-alias-primary-opening-Chelsea2024',proofs),opening=True)
    friendly=report(original('oscar-bobb-primary-August3-2024-friendly',proofs),opening=False)
    raw=original('oscar-bobb-original-wikipedia',proofs)
    person,owner=wiki.read(raw,'Oscar_Bobb',SOURCES['oscar-bobb-original-wikipedia'],
        '2024-08-01','Manchester City','england',expected_name='Oscar Bobb')
    if person['birth_date']!='2003-07-12':raise ValueError('Bobb identity birthday differs')
    person['provider_player_id']='Oscar_Bobb'
    owner['positive_August_friendly']=dict(date=friendly,club='Manchester City',name='Oscar Bobb',exact_starting_appearance=True)
    duplicate=dict(name='Savinho',birth_date=identity['birth_date'],source_player_id=743591,
        provider_player_id=743591,source_provider='original-primary-alias',source_profile_url=SOURCES['six-dates-original-Savio-Savinho-primary-alias'],
        published_name_variants=['Savinho','Sávio'],identity_policy=POLICY)
    duplicate_owner=dict(policy=POLICY,fixture_date=opening,club='Manchester City',positive_first_league_XI=True,
        exact_August1_transfer_bracket_claimed=False)
    return duplicate,duplicate_owner,person,owner,proofs


def validate_pair(release,displaced,retained,names,birthdays,club,provider_id,duplicate_provider_id):
    from scripts.season_number_label_names_v2 import undecorated,literal_name
    if (release.season!='2024-25' or (displaced,retained)!=(9246,9232)
            or club['carrier_id']!=313 or club['name']!='Manchester City'
            or [literal_name(undecorated(n)) for n in names]!=['savinho','sávio']
            or birthdays!=['2004-04-10','2004-04-10']
            or provider_id!='Oscar_Bobb' or duplicate_provider_id!=743591):
        raise ValueError('positive alias reserve policy is outside its exact reviewed pair')
