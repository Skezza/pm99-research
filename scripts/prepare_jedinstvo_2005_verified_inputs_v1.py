"""Positive opening18, period secondary facts and dated coach/home ground.

Source proposal only: no game writes or release promotion. Kit/source replay,
independent native readback and actual runtime still required for delivery.
"""
import copy
import json
import re
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import prepare_jedinstvo_2005_source_allocation_v1 as source
from scripts import ofk_2004_original_secondary_facts_v1 as secondary
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry


def home_ground(raw):
    page=BeautifulSoup(raw,'html.parser')
    club=page.select('.sb-team.sb-heim a.sb-vereinslink')
    date=page.select('a[href$="/datum/2005-08-27"]')
    grounds=page.select('a[href="/stadion/stadion/verein/8357/saison_id/2005"]')
    if (len(club)!=1 or club[0].get('href')!='/jedinstvo-bijelo-polje/startseite/verein/8357/saison_id/2005'
            or len(date)!=1 or len(grounds)!=1 or grounds[0].get_text(' ',strip=True)!='Gradski stadion'):
        raise ValueError('original dated target home-ground evidence missing or changed')
    return dict(date='2005-08-27',ground='Gradski stadion',source_club_id=8357,source_match_id=2927765,
        limitation='First played home league fixture, not the away opening venue; delayed Red Star fixture not treated as first home.')


def prepare(output,baseline_release_id=None):
    if output.exists():
        raise ValueError('verified foreign source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-jedinstvo2005-replay-') as temporary:
        proposal=source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    retained=source.ROOT.parent/'jedinstvo-2005-fixed18-source-feasibility-v1.json'
    if pipeline.read_json_file(retained)!=proposal:
        raise ValueError('original positive fixed18 allocation no longer reproduces')
    desired=copy.deepcopy(proposal['desired_people'])
    facts,bindings={},[]
    for year in (2005,2006):
        _,raw,binding=source_rows(f'jedinstvo-{year}-original-annual')
        page=BeautifulSoup(raw,'html.parser')
        ids={int(m[1]) for a in page.select('table.items a[href*="/profil/spieler/"]')
            if (m:=re.search(r'/profil/spieler/(\d+)(?:/|$)',a.get('href','')))}
        selected=[r for r in desired if r['source_person']['source_player_id'] in ids and r['source_person']['source_player_id'] not in facts]
        facts.update(secondary.parse(raw,selected,expected_year=year,expected_club_name='Jedinstvo Bijelo Polje',
            country_codes={'Serbia':'SRB','Montenegro':'MNE'},country_representation='native YUGOSLAVIA for pre-independence Serbian/Montenegrin representation'))
        bindings.append(binding)
    _,press_raw,press_binding=source_rows('jedinstvo-2005-original-borba-preseason')
    from scripts.prepare_jedinstvo_2005_identity_review_v1 import signed_arrival_report
    signed_arrival_report(press_raw)
    press=re.sub(r'\s+',' ',BeautifulSoup(press_raw,'html.parser').get_text(' ',strip=True))
    if ('197 centimetara' not in press or 'visok 191 centimetar' not in press or 'visoki su po 192 centimetra' not in press):
        raise ValueError('original dated signed-player centimetre heights missing')
    height_conflicts=[]
    for id,height in ((27230,197),(36050,191),(36068,192)):
        fact=facts[id]
        height_conflicts.append(dict(source_player_id=id,annual_rounded_height_cm=fact['height_cm'],dated_published_height_cm=height,
            policy='Dated original11July2005 published centimetres take precedence over rounded later annual imperial display.'))
        fact.update(height_cm=height,height_policy='dated-original11July2005-centimetre-display',dated_height_original=press_binding)
    for row in desired:
        fact=facts[row['source_person']['source_player_id']]
        if fact['birth_date']!=row['source_person']['birth_date']:
            raise ValueError('original secondary facts have a different literal birthday')
        row['source_player'].update({k:fact[k] for k in ('nationality','height_cm','weight_kg')})
        row['secondary_facts_status']=fact
    assigned={r['source_person']['source_player_id']:r for r in desired}
    for row in proposal['allocation']:
        row['replacement']=assigned[row['replacement']['source_person']['source_player_id']]
    _,home_raw,home_binding=source_rows('jedinstvo-2005-original-first-home-match2927765')
    ground=home_ground(home_raw)
    if proposal['original_opening']['manager']!='Sava Kovačević':
        raise ValueError('original opening coach differs')
    proposal.update(schema_version='pm99-private-original-jedinstvo2005-verified-inputs-v1',
        desired_people=desired,source_title='Original2005 Jedinstvo openingXI and used substitutes plus positive dated reserves',
        dated_manager_ground=dict(date='2005-08-06',source_club_id=8357,manager='Sava Kovačević',ground=ground['ground'],
            ground_source=ground,ground_original=home_binding),
        secondary_fact_review=dict(policy='positive-dated-membership-original-annual-and-original-preseason-centimetres',
            facts=facts,original_bindings=bindings+[press_binding],
            native_fallbacks=['Unpublished weights and shirt numbers; no inherited portraits.'],
            nationality_limit='Published annual country labels, not certified opening-day passports; native country representation explicitly declared.'),
        source_disagreements=height_conflicts)
    proposal['original_bindings'].append(home_binding)
    proposal=json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output,proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Kovacevic',display_name='Kovacevic'),
        manager_person_id='manager-original-match-2005-sava-kovacevic',artifact_id='jedinstvo-original-manager-ground-2005',
        relative_path='jedinstvo-original-opening-2005.html')


if __name__=='__main__':
    result=prepare(source.ROOT.parent/'jedinstvo-2005-verified-source-inputs-v1.json')
    print(dict(people=len(result['desired_people']),outside_owners=len(result['outside_identity_owners']),native_writes=0))
