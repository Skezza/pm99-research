"""Replay opening16 with explicit secondary-fact periods and dated coach.

No current player-feed positions/nationalities. Unknown weights remain logged;
Gerzon's already documented publisher birthday conflict remains visible.
"""
import copy
import json
import re
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import prepare_tachira_2015_source_allocation_v1 as source
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import ofk_2004_original_secondary_facts_v1 as secondary
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('verified source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-tachira2015-source-replay-') as temporary:
        proposal = source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    retained = source.ROOT.parent/'tachira-2015-fixed16-source-feasibility-v1.json'
    if pipeline.read_json_file(retained)!=proposal:
        raise ValueError('positive original16 allocation no longer reproduces')
    desired = copy.deepcopy(proposal['desired_people'])
    facts, bindings = {}, []
    for key, year in [('tachira-2014',2015),('tachira-2015',2016)]:
        _,raw,binding = source_rows(key)
        page = BeautifulSoup(raw,'html.parser')
        ids = {int(m[1]) for a in page.select('a[href*="/profil/spieler/"]') if (m:=re.search(r'/profil/spieler/(\d+)(?:/|$)',a.get('href','')))}
        selected = [r for r in desired if r['source_person']['source_player_id'] in ids and r['source_person']['source_player_id'] not in facts]
        facts.update(secondary.parse(raw,selected,expected_club_name='Deportivo Táchira',expected_calendar_year=year,
            country_codes={'Venezuela':'VEN','Colombia':'COL'},country_representation='native VENEZUELA/COLOMBIA for VEN/COL'))
        bindings.append(binding)
    _,raw,binding = source_rows('tachira-2015-marcos-original-full-profile')
    page = BeautifulSoup(raw,'html.parser')
    values = [p.get_text(' ',strip=True) for p in page.select('.info-table__content--bold')]
    canonical = page.select_one('link[rel="canonical"]')
    height = [re.fullmatch(r'(\d) ft (\d{1,2}) in',v) for v in values if re.fullmatch(r'(\d) ft (\d{1,2}) in',v)]
    if (canonical is None or canonical.get('href')!='https://www.transfermarkt.co.uk/marcos-sanchez/profil/spieler/146516'
            or 'Marcos Aníbal Sánchez Mullins' not in values or not any(v.startswith('23/12/1989 ') for v in values)
            or 'Panama' not in values or len(height)!=1):
        raise ValueError('original full Marcos biography/country/height missing')
    feet,inches = map(int,height[0].groups())
    facts[146516]=dict(source_player_id=146516,birth_date='1989-12-23',nationality='PAN',height_cm=round((feet*12+inches)*2.54),
        weight_kg=None,source_policy='original-full-biography-confirmed-identity',height_policy='rounded-original-imperial-display-not-exact-centimetre',
        weight_policy='unpublished-not-invented',country_representation='native PANAMA',
        limitation='Published current biography, not an opening-date passport or weigh-in. Dated first match independently publishes Panama flag.')
    bindings.append(binding)
    for row in desired:
        id = row['source_person']['source_player_id']
        if facts[id]['birth_date']!=row['source_person']['birth_date']:
            raise ValueError('secondary original birthday disagrees with confirmed person')
        row['source_player'].update({k:facts[id][k] for k in ('nationality','height_cm','weight_kg')})
        row['secondary_facts_status']=facts[id]
    by_id = {r['source_person']['source_player_id']:r for r in desired}
    for row in proposal['allocation']:
        row['replacement']=by_id[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version='pm99-private-original-tachira2015-verified-inputs-v1',
        source_title='Original2015 Táchira first league XI and used substitutes plus positively dated reserves',
        desired_people=desired,first_fixture=dict(date='2015-07-11'),
        secondary_fact_review=dict(policy='positive-dated-membership-with-explicit-calendar-secondary-facts',original_bindings=bindings,facts=facts,
            native_fallbacks=['unpublished weights'],nationality_limit='Published countries, not certified opening-date passports.'),
        dated_manager_ground=dict(date='2015-07-11',source_club_id=13297,manager='Daniel Farías',ground='Pueblo Nuevo',
            ground_basis='Original club press dated18July2015 explicitly publishes home ground for19July, not away opening venue.'),
        source_disagreements=[dict(person_id=75934,field='birth_date',used_original_publisher='1980-10-27',NFT_season_catalogue='1980-10-21',
            policy='Explicit conflict retained; publisher person/feed/calendar agree. Not a perfect-DOB certification.')])
    _,press_raw,press_binding=source_rows('tachira-2015-original-first-club-press-urllib')
    press=BeautifulSoup(press_raw,'html.parser').get_text(' ',strip=True)
    if (not press.startswith('El «Aurinegro» arrancó la temporada con victoria')
            or 'sábado, 11 de julio de 2015' not in press or 'Javier Joves / Prensa Deportivo Táchira' not in press
            or 'Suplentes sin jugar: José Contreras, Pablo Camacho, Juan Carlos Mora, Romeri Villamizar.' not in press
            or 'DT: Daniel Farías.' not in press or 'indumentaria alternativa de color verde' not in press):
        raise ValueError('independent original first club-press report/date/reserves/coach missing')
    proposal['original_bindings'].append(press_binding)
    proposal['opening_membership_corroboration']=dict(original=press_binding,
        reserves_actually_published_on_opening_bench=[308226,271263],unused_bench_missing_in_first_Foro_source_not_invented=True,
        first_fixture_away_strip='green, explicitly published; not the default home-kit source')
    proposal['source_disagreements'].append(dict(field='substitution_minutes',Foro=[78,87,89],club_press=[73,88,91],
        policy='Both originals confirm same XI and three substituted identities. Minutes conflict logged; native lineup/order does not depend on choosing a minute.'))
    proposal=json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output,proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Farias',display_name='Farias'),manager_person_id='manager-original-match-2015-daniel-farias',
        artifact_id='tachira-original-manager-ground-2015',relative_path='tachira-original-opening-2015.html')


if __name__=='__main__':
    result=prepare(source.ROOT.parent/'tachira-2015-verified-source-inputs-v2.json')
    print(dict(people=len(result['desired_people']),native_writes=0),flush=True)
