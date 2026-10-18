"""Replay the positively sourced opening16; never pretend this fills fixed18.

The catalogue supplies explicit identity/DOB/broad-role links, NOT August
membership. Only actual first-match players and the two positively bracketed
signed arrivals qualify. Missing reserves stop publication, not source retention.
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

from scripts import jedinstvo_2005_original_opening_v1 as opening
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.prepare_ofk_2004_source_allocation_v1 import annual_roles
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_person_identity_v1 as biographies


def catalogue(raw):
    roles=annual_roles(raw,expected_year=2005,expected_club_name='Jedinstvo Bijelo Polje')
    page=BeautifulSoup(raw,'html.parser')
    result={}
    for row in page.select('table.items > tbody > tr'):
        links={a.get('href'):a.get_text(' ',strip=True) for a in row.select('a[href*="/profil/spieler/"]')}
        if not links:
            continue
        if len(links)!=1:
            raise ValueError('original identity row has multiple explicit people')
        href,name=next(iter(links.items()))
        id=int(re.search(r'/profil/spieler/(\d+)(?:/|$)',href)[1])
        cells=row.find_all('td',recursive=False)
        birth=re.fullmatch(r'(\d{2})/(\d{2})/(\d{4}) \(\d+\)',cells[2].get_text(' ',strip=True)) if len(cells)==10 else None
        if birth is None or id in result:
            raise ValueError('original identity DOB missing or duplicated')
        day,month,year=map(int,birth.groups())
        result[id]=dict(name=name,birth_date=dt.date(year,month,day).isoformat(),position=roles[id])
    return result


def join_opening(actual,identities,people):
    """Surname-only match labels must resolve uniquely, never by fuzzy initials."""
    if actual['season']!='2005-06' or actual['fixture_date']!='2005-08-06' or actual['club']!='Jedinstvo Bijelo Polje':
        raise ValueError('wrong opening club or date')
    matched=[]
    labels=actual['starting_xi']+[r['name'] for r in actual['used_substitutes']]
    if len(labels)!=14:
        raise ValueError('original XI11/used3 changed')
    for index,label in enumerate(labels):
        key=roster.normalise(label)
        choices=[(id,p) for id,p in identities.items()
            if roster.normalise(p['name'] if ' ' in label else p['name'].split()[-1])==key]
        if len(choices)!=1:
            raise ValueError('original match label has no unique explicit identity')
        id,person=choices[0]
        biography=people.get(id)
        if (biography is None or biography['birth_date']!=person['birth_date']
                or roster.normalise(biography['name'])!=roster.normalise(person['name'])):
            raise ValueError('original biography disagrees with explicit catalogue identity/DOB')
        matched.append(dict(source_player_id=id,published_match_name=label,
            canonical_published_name=person['name'],birth_date=person['birth_date'],position=person['position'],
            membership='starting-xi' if index<11 else 'used-opening-substitute',
            identity_basis='unique-exact-published-full-name-or-surname-and-explicit-publisher-ID-DOB'))
    if len({r['source_player_id'] for r in matched})!=14:
        raise ValueError('original first14 has a repeated identity')
    if matched[0]['position']!='G':
        raise ValueError('original opening keeper has contradictory broad role')
    return matched


def signed_arrival_report(raw):
    page=BeautifulSoup(raw,'html.parser')
    if page.title is None or not page.title.get_text(' ',strip=True).startswith('Borba, 11. 07. 2005., S. 12 —'):
        raise ValueError('signed-arrival report has the wrong original issue/date/page')
    press=re.sub(r'\s+',' ',page.get_text(' ',strip=True))
    if ('Ugovorne obaveze sa Jedinstvom' not in press or 'Mladen Kaluđerović iz Dečića, koji igra na poziciji štopera' not in press
            or 'Bojan Šljivančanin iz pljevaljskog Rudara' not in press
            or 'granitnu odbranu Jedinstva čine kolosi' not in press):
        raise ValueError('original signed-arrival report differs')


def prepare():
    _,raw,match_binding=source_rows('partizanopedia-2005-original-season')
    actual=opening.parse(raw)
    _,annual_raw,annual_binding=source_rows('jedinstvo-2005-original-annual')
    identities=catalogue(annual_raw)
    people_path=ROOT.parent/'jedinstvo-2005-original-person-identities-v1.json'
    document=pipeline.read_json_file(people_path)
    # Reparse the retained original response: a saved parsed identity is not
    # sufficient, even when it happens to agree with the annual catalogue.
    biographies.merge({},document)
    for binding in document['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT/binding['path'])!=binding['sha256']:
            raise ValueError('original biography input changed since acquisition')
    if any(b['gaps'] for b in document['batches']):
        raise ValueError('original biography acquisition has gaps')
    people={p['source_player_id']:p for b in document['batches'] for p in b['people']}
    matched=join_opening(actual,identities,people)
    history_path=ROOT.parent/'jedinstvo-2005-reserve-original-histories-v1.json'
    events,_=histories.merge({},pipeline.read_json_file(history_path))
    _,press_raw,press_binding=source_rows('jedinstvo-2005-original-borba-preseason')
    signed_arrival_report(press_raw)
    for id,name in [(36009,'Mladen Kaludjerovic'),(36068,'Bojan Sljivancanin')]:
        bracket=transfer.transfer_interval(events[id],actual['fixture_date'])
        if bracket.get('status')!='recorded-entry-and-exit-bracket-fixture' or bracket['source_owner_club_id']!=8357:
            raise ValueError('signed arrival has no positive opening ownership interval')
        person=people[id]
        if person['name']!=name or id==36068 and person['birth_date']!=identities[id]['birth_date']:
            raise ValueError('signed arrival biography identity changed')
        matched.append(dict(source_player_id=id,canonical_published_name=person['name'],birth_date=person['birth_date'],
            position='D',membership='positive-bracketed-and-original-signed-arrival',bracket=bracket,
            role_basis='original dated preseason defensive arrival report; not invented unused first-match bench'))
    if len(matched)!=16 or len({r['source_player_id'] for r in matched})!=16:
        raise ValueError('positive source16 incomplete or duplicated')
    return dict(season=actual['season'],original_match=actual,matched_people=matched,
        original_bindings=[match_binding,annual_binding,press_binding,
            dict(path=registry.relative_workspace_path(people_path),sha256=registry.sha256_file(people_path)),
            dict(path=registry.relative_workspace_path(history_path),sha256=registry.sha256_file(history_path))],
        positive_members=16,required_native_slots=18,remaining_positive_opening_members=2,
        native_writes=0,publication_authorised=False,
        limitations=['Annual broad roles are not a historically sourced formation or fine deployment.',
            'Videkanic transfer interval places him at Hajduk3140, not Jedinstvo8357, on opening day.',
            'Culafic/Zuric lack positive dated opening membership; annual appearance is insufficient.',
            'Original unused bench absent. Two more positive members required before fixed18 approval.'])


if __name__=='__main__':
    result=prepare()
    pipeline.write_canonical_json(ROOT.parent/'jedinstvo-2005-original16-identity-review-v1.json',result)
    print(dict(positive_members=result['positive_members'],remaining=result['remaining_positive_opening_members'],native_writes=0))
