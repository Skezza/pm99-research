"""Original August squad with explicit surname/DOB and secondary fallbacks."""
import copy
import json
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import prepare_mladost_2001_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA='pm99-private-original-mladost2001-verified-inputs-v1'
POLICY='original-August-round2-XI-used-subs-positive-reserves-fixed18-with-unresolved-surnames-v1'


def prepare(output,baseline_release_id=None):
    if output.exists():raise ValueError('verified Mladost inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-mladost-original-') as temporary:
        proposal=source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    path,raw,binding=source_rows('mladost-original-August2001-ground-retrospective')
    if pipeline.read_json_file(path.with_suffix('.source.json'))['url']!='https://crnobelanostalgija.com/2023/01/prvenstvo-2001-02.html':
        raise ValueError('Mladost historical ground source differs')
    text=BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
    if 'Mladost (A) - Partizan 1-3 2. kolo, 26.8.2001, Apatin, Stadion Mladosti, 7.000 gledalaca' not in text:
        raise ValueError('target-date Mladost ground text missing')
    facts={}
    for row in proposal['desired_people']:
        role=row['source_player']['position'];id=row['source_person']['source_player_id']
        height={'G':185,'D':180,'M':178,'F':180}[role];weight={'G':80,'D':76,'M':74,'F':76}[role]
        row['source_player'].update(nationality='XXX',height_cm=height,weight_kg=weight)
        fact=dict(nationality='unpublished-in-selected-opening-sources-explicit-XXX',
            height=dict(value=height,historically_sourced=False,basis='deterministic-role-default'),
            weight=dict(value=weight,historically_sourced=False,basis='deterministic-role-default'),
            birth_date='original-independent-biography' if row['source_person']['birth_date'] else 'unknown-preserve-native-date-not-a-person-fact')
        facts[str(id)]=fact;row['secondary_facts_status']=copy.deepcopy(fact)
    persons={r['source_person']['source_player_id']:r for r in proposal['desired_people']}
    for row in proposal['allocation']:row['replacement']=persons[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,policy=POLICY,
        source_title='Original August26,2001 Mladost round2 XI, used substitutes and four positively dated reserves; eight surname actors explicit',
        secondary_fact_review=dict(policy='explicit-unpublished-nationality-physical-and-surname-date-fallback-v1',facts=facts),
        dated_manager_ground=dict(date='2001-08-26',source_club_id=904,
            manager=proposal['original_opening']['manager'],ground='Stadion Mladosti',
            ground_source=dict(original=binding,limitation='Target-fixture ground transcribed by a retrospective archive; original scanned newspaper page not separately text-decoded.')))
    proposal['original_bindings'].append(binding)
    proposal=json.loads(pipeline.canonical_json_bytes(proposal));pipeline.write_canonical_json(output,proposal);return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Bogic',display_name='Bogic'),
        manager_person_id='manager-original-august2001-dragi-bogic',
        artifact_id='mladost-original-manager-ground-2001',relative_path='mladost-original-opening-2001.html')
