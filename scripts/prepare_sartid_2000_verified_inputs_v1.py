"""Original August Sartid squad with explicit secondary-fact defaults."""
import copy
import json
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import prepare_sartid_2000_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA='pm99-private-original-sartid2000-verified-inputs-v1'
POLICY='original-August-round2-XI-used-subs-and-positive-reserves-fixed18-v1'


def prepare(output,baseline_release_id=None):
    if output.exists(): raise ValueError('verified Sartid source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-sartid-original-') as temporary:
        proposal=source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    _,raw,binding=source_rows('sartid-original-official-ground-history')
    text=BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
    if 'Gradski Stadion Smederevo' not in text or 'ranije stadion FK Sartid' not in text:
        raise ValueError('official historical ground identity missing or changed')
    facts={}
    for row in proposal['desired_people']:
        role=row['source_player']['position'];id=row['source_person']['source_player_id']
        height={'G':185,'D':180,'M':178,'F':180}[role]
        weight={'G':80,'D':76,'M':74,'F':76}[role]
        row['source_player'].update(nationality='XXX',height_cm=height,weight_kg=weight)
        fact=dict(nationality='unpublished-in-selected-opening-sources-explicit-XXX',
            height=dict(value=height,historically_sourced=False,basis='deterministic-role-default'),
            weight=dict(value=weight,historically_sourced=False,basis='deterministic-role-default'),
            birth_date='original-independent-biography',first_name='original-independent-biography')
        facts[str(id)]=fact;row['secondary_facts_status']=copy.deepcopy(fact)
    persons={r['source_person']['source_player_id']:r for r in proposal['desired_people']}
    for row in proposal['allocation']:row['replacement']=persons[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,policy=POLICY,
        source_title='Original August19,2000 Sartid round2 XI and used substitutes plus four positively dated reserves',
        secondary_fact_review=dict(policy='explicit-unpublished-nationality-and-deterministic-physical-fallbacks-v1',facts=facts),
        dated_manager_ground=dict(date='2000-08-19',source_club_id=3544,
            manager=proposal['original_opening']['manager'],ground='Gradski stadion',
            ground_source=dict(original=binding,limitation='Official club retrospective identifies the ground; exact August2000 naming is not independently certified.')))
    proposal['original_bindings'].append(binding)
    proposal=json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output,proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Dogandzic',display_name='Dogandzic'),
        manager_person_id='manager-original-august2000-slobodan-dogandzic',
        artifact_id='sartid-original-manager-ground-2000',relative_path='sartid-original-opening-2000.html')
