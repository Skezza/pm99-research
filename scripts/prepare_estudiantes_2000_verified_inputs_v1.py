"""Replay the period cup16 with explicit secondary defaults, never namesakes."""
import copy
import json
import tempfile
from pathlib import Path
from scripts import prepare_estudiantes_2000_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline

SCHEMA='pm99-private-original-estudiantes2000-verified-inputs-v1'
POLICY='original-August-cup-XI-and-published-bench-fixed16-with-unresolved-Gomez-v1'


def prepare(output,baseline_release_id=None):
    if output.exists():raise ValueError('verified source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-estudiantes-original-') as temporary:
        proposal=source.prepare(Path(temporary)/'allocation.json',baseline_release_id)
    facts={}
    for row in proposal['desired_people']:
        role=row['source_player']['position'];id=row['source_person']['source_player_id']
        height={'G':185,'D':180,'M':178,'F':180}[role];weight={'G':80,'D':76,'M':74,'F':76}[role]
        row['source_player'].update(nationality='XXX',height_cm=height,weight_kg=weight)
        fact=dict(nationality='unpublished-in-original-match-explicit-XXX',
            height=dict(value=height,historically_sourced=False,basis='deterministic-role-default'),
            weight=dict(value=weight,historically_sourced=False,basis='deterministic-role-default'),
            birth_date='original-independent-biography' if row['source_person']['birth_date'] else 'unknown-preserve-native-date-not-a-person-fact')
        facts[str(id)]=fact;row['secondary_facts_status']=copy.deepcopy(fact)
    persons={r['source_person']['source_player_id']:r for r in proposal['desired_people']}
    for row in proposal['allocation']:row['replacement']=persons[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,policy=POLICY,
        source_title='Original CONMEBOL August2,2000 Estudiantes cup XI and published bench; unresolved Javier Gomez identity explicit',
        source_fallback=proposal['original_opening']['approved_lineup_fallback'],
        secondary_fact_review=dict(policy='explicit-unpublished-nationality-physical-and-Gomez-date-fallback-v1',facts=facts),
        dated_manager_ground=dict(date='2000-08-02',source_club_id=14555,
            manager=proposal['original_opening']['manager'],ground=proposal['original_opening']['ground']))
    proposal=json.loads(pipeline.canonical_json_bytes(proposal));pipeline.write_canonical_json(output,proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'],report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname="D'Accorso",display_name="D'Accorso"),
        manager_person_id='manager-original-august2000-antonio-daccorso',
        artifact_id='estudiantes-original-manager-ground-2000',relative_path='estudiantes-original-opening-2000.pdf',
        media_type='application/pdf')
