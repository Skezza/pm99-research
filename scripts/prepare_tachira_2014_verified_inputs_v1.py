"""Replay positive16; retain role/DOB disagreements and source secondary facts."""
import copy
import json
import re
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import prepare_tachira_2014_source_allocation_v1 as source
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import ofk_2004_original_secondary_facts_v1 as secondary
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('verified source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-tachira-original-replay-') as temporary:
        proposal = source.prepare(Path(temporary) / 'allocation.json', baseline_release_id)
    retained = source.ROOT.parent / 'tachira-2014-fixed16-source-feasibility-v1.json'
    if pipeline.read_json_file(retained) != proposal:
        raise ValueError('positive original source allocation no longer reproduces')
    _, annual, annual_binding = source_rows('tachira-2014')
    desired = proposal['desired_people']
    catalogued = [r for r in desired if r['source_person']['source_player_id'] != 76530]
    facts = secondary.parse(annual, catalogued, expected_club_name='Deportivo Táchira',
        expected_calendar_year=2015, country_codes={'Venezuela':'VEN','Colombia':'COL'},
        country_representation='native VENEZUELA/COLUMBIA for published VEN/COL')
    _, profile, profile_binding = source_rows('tancredi-original-profile')
    page = BeautifulSoup(profile, 'html.parser')
    values = [p.get_text(' ', strip=True) for p in page.select('.info-table__content--bold')]
    match = next((re.fullmatch(r'(\d) ft (\d{1,2}) in', v) for v in values if re.fullmatch(r'(\d) ft (\d{1,2}) in', v)), None)
    if 'Uruguay' not in values or match is None or 'José Luis Tancredi Malatez' not in values:
        raise ValueError('original full Tancredi country/height missing')
    height = round((int(match[1]) * 12 + int(match[2])) * 2.54)
    facts[76530] = dict(source_player_id=76530, birth_date='1983-02-14', nationality='URU',
        height_cm=height, weight_kg=None, source_policy='original-full-biography-confirmed-identity',
        height_policy='rounded-original-imperial-display-not-exact-centimetre', weight_policy='unpublished-not-invented',
        country_representation='native URUGUAY', limitation='Original current publication, not a dated passport or weigh-in.')
    desired = copy.deepcopy(desired)
    for row in desired:
        id = row['source_person']['source_player_id']
        if facts[id]['birth_date'] != row['source_person']['birth_date']:
            raise ValueError('secondary original biography disagrees with confirmed source person')
        row['source_player'].update({k:facts[id][k] for k in ('nationality','height_cm','weight_kg')})
        row['secondary_facts_status'] = facts[id]
    by_id = {r['source_person']['source_player_id']:r for r in desired}
    for row in proposal['allocation']:
        row['replacement'] = by_id[row['replacement']['source_person']['source_player_id']]
    proposal.update(schema_version='pm99-private-original-tachira2014-verified-inputs-v1',
        source_title='Original2014 Táchira club press opening XI and published match bench',
        desired_people=desired, first_fixture=dict(date='2014-08-10'),
        secondary_fact_review=dict(policy='positive-dated-membership-with-explicit-calendar-secondary-facts',
            original_bindings=[annual_binding, profile_binding], facts=facts,
            native_fallbacks=['unpublished weights'],
            nationality_limit='Published country flags/profile; not certified opening-date passports.'),
        dated_manager_ground=dict(date='2014-08-10', source_club_id=13297, manager='Daniel Farías', ground='Pueblo Nuevo'),
        source_disagreements=[dict(person_id=75934, field='birth_date',
            used_original_publisher='1980-10-27', NFT_season_catalogue='1980-10-21',
            policy='Retain explicit conflict; original confirmed person and annual agree. Not a perfect-DOB certification.')])
    proposal = json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output, proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'], report_binding=proposal['original_bindings'][0],
        manager_native_names=dict(surname='Farias', display_name='Farias'),
        manager_person_id='manager-original-club-press-2014-daniel-farias',
        artifact_id='tachira-original-manager-ground-2014', relative_path='tachira-original-opening.html')


if __name__ == '__main__':
    result = prepare(source.ROOT.parent / 'tachira-2014-verified-source-inputs-v1.json')
    print(dict(people=len(result['desired_people']), native_writes=0), flush=True)
