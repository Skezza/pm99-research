"""Replay original opening ownership; separate period facts from defaults."""
import copy
import json
import re
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup

from scripts import prepare_monagas_2002_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA = 'pm99-private-original-monagas2002-verified-inputs-v1'
POLICY = source.POLICY


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('verified opening evidence is immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-monagas-original-') as temporary:
        proposal = source.prepare(Path(temporary) / 'allocation.json', baseline_release_id)
    _, raw, binding = source_rows('monagas-2002-original-linked-identity-catalogue')
    page = BeautifulSoup(raw, 'html.parser')
    facts = {}
    for row in page.select('table.items > tbody > tr'):
        links = {a['href'] for a in row.select('a[href*="/profil/spieler/"]')}
        if not links:
            continue
        if len(links) != 1:
            raise ValueError('ambiguous original secondary-fact person row')
        id = int(re.search(r'/profil/spieler/(\d+)', next(iter(links)))[1])
        flags = [i.get('title') for i in row.select('img.flaggenrahmen')]
        countries = {'Venezuela': 'VEN', 'Paraguay': 'PAR', 'Uruguay': 'URU', 'Argentina': 'ARG'}
        if not flags or flags[0] not in countries:
            raise ValueError('unreviewed original primary nationality flag')
        height = re.search(r'\b([12]),(\d{2})m\b', row.get_text(' ', strip=True))
        facts[id] = dict(nationality=countries[flags[0]], published_flags=flags,
            height_cm=int(height[1]) * 100 + int(height[2]) if height else None)
    review = {}
    for actor in proposal['desired_people']:
        id = actor['source_person']['source_player_id']
        role = actor['source_player']['position']
        published = facts[id]
        height = published['height_cm'] or {'G': 185, 'D': 180, 'M': 178, 'F': 180}[role]
        weight = {'G': 80, 'D': 76, 'M': 74, 'F': 76}[role]
        actor['source_player'].update(nationality=published['nationality'], height_cm=height, weight_kg=weight)
        review[str(id)] = dict(nationality=dict(source='original-labelled-period-identity-row-primary-flag',
            flags=published['published_flags'], historical_passport_transition_not_independently_dated=True),
            height=dict(value=height, historically_sourced=published['height_cm'] is not None,
                basis='published-original-person-row' if published['height_cm'] else 'deterministic-role-default'),
            weight=dict(value=weight, historically_sourced=False, basis='deterministic-role-default'),
            birth_date='original-independent-biography' if actor['source_person']['birth_date'] else 'explicit-unpublished-preserve-native-not-person-date')
        actor['secondary_facts_status'] = copy.deepcopy(review[str(id)])
    by_id = {a['source_person']['source_player_id']: a for a in proposal['desired_people']}
    for row in proposal['allocation']:
        row['replacement'] = by_id[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version=SCHEMA,
        source_title='Original Monagas August2002 cup XI, used substitutes and two original unused substitutes, missing secondary dates explicitly declared',
        secondary_fact_review=dict(policy='original-period-primary-flags-published-heights-and-explicit-unknown-DOB-defaults-v1',
            original_binding=binding, facts=review),
        dated_manager_ground=dict(date='2002-08-28', source_club_id=14596,
            manager='Eduardo Borrero', ground='Estadio Alexander Bottini',
            ground_source=dict(date='2002-09-06', limitation='Original September6 return-leg home ground, not an independently verified August home match.')))
    proposal = json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output, proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'], report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Borrero', display_name='Borrero'),
        manager_person_id='manager-original-august2002-eduardo-borrero',
        artifact_id='monagas-original-manager-ground-2002', relative_path='monagas-original-opening-2002.html')
