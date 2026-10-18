"""Replay the original fixed18; declare unknown surname actor facts honestly."""
import copy
import json
import re
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import prepare_hajduk_2002_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA = 'pm99-private-original-hajduk2002-verified-inputs-v1'
POLICY = 'original-first-XI-plus-positive-reserves-and-approved-published-surname-fixed18-v1'


def prepare(output, baseline_release_id=None):
    if output.exists():raise ValueError('verified source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-hajduk-original-') as temporary:
        proposal=source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    _,raw,binding=source_rows('hajduk-2002-original-opening-photographs-retrospective')
    page=BeautifulSoup(raw,'html.parser')
    sections=[h for h in page.select('h3') if h.get_text(' ',strip=True)=='Hajduk (K) – Partizan 0-1']
    if (len(sections)!=1 or re.sub(r'\s+',' ',sections[0].find_next('p').get_text(' ',strip=True))!=
            '18. kolo, 26.02.2003, Kula, Gradski stadion, 7.000 gledalaca, strelac: Lazović 43’'):
        raise ValueError('dated target-season home ground missing or changed')
    facts={}
    for row in proposal['desired_people']:
        role=row['source_player']['position'];id=row['source_person']['source_player_id']
        # Do not import present-day nationalities from the identity API. The
        # original XI has no nationality/physical columns; explicit XXX is
        # preferable to certifying a guessed passport from the club's country.
        height={'G':185,'D':180,'M':178,'F':180}[role]
        weight={'G':80,'D':76,'M':74,'F':76}[role]
        row['source_player'].update(nationality='XXX',height_cm=height,weight_kg=weight)
        fact=dict(nationality='unpublished-in-opening-sources-explicit-XXX',
            height=dict(value=height,historically_sourced=False,basis='deterministic-role-based-fallback'),
            weight=dict(value=weight,historically_sourced=False,basis='deterministic-role-based-fallback'),
            birth_date='original-independent-biography' if row['source_person']['birth_date'] else 'unknown-preserve-native-field-not-a-person-fact',
            first_name='original-independent-biography' if row['source_person']['birth_date'] else 'unknown-retain-published-surname')
        facts[str(id)]=fact;row['secondary_facts_status']=copy.deepcopy(fact)
    people={r['source_person']['source_player_id']:r for r in proposal['desired_people']}
    for row in proposal['allocation']:row['replacement']=people[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,policy=POLICY,
        source_title='Original10August2002 Hajduk Kula XI and positive reserves; one approved published surname-only identity',
        secondary_fact_review=dict(policy='explicit-unpublished-country-physical-and-surname-actor-date-fallbacks-v1',facts=facts,
            native_fallbacks=['Unknown nationalities explicitly XXX; no nationality inferred from team location.',
                'Height/weight are declared deterministic estimates, not historical measurements.',
                'Trajkovic first name and DOB unavailable: original surname, native date preserved and visibly flagged.',
                'No inherited player portraits or certified opening shirt numbers.']),
        dated_manager_ground=dict(date='2002-08-10',source_club_id=3140,
            manager=proposal['original_opening']['manager'],ground='Gradski stadion',
            ground_source=dict(date='2003-02-26',original=binding,
                limitation='Dated same-season home fixture, not a first-home/August ground certificate.')))
    proposal['original_bindings'].append(binding)
    proposal=json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output,proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][2],
        manager_native_names=dict(surname='Ostojic',display_name='Ostojic'),
        manager_person_id='manager-original-june-september2002-miloljub-ostojic',
        artifact_id='hajduk-original-manager-ground-2002',relative_path='hajduk-original-manager-2002.html')


if __name__=='__main__':
    result=prepare(source.ROOT/'hajduk-2002-verified-source-inputs-v1.json')
    print(dict(people=len(result['desired_people']),native_writes=0),flush=True)
