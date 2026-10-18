"""Replay opening18 and dated manager; declare unavailable secondary facts."""
import json
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import prepare_borac_2003_source_allocation_v1 as source
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

EDITORIAL_POLICY = 'original-archived-facts-and-explicit-deterministic-unpublished-secondary-defaults-v1'
STABLE_SKILLS_POLICY = 'original-archived-facts-and-explicit-unpublished-physical-defaults-frozen-skills-v2'
UNPUBLISHED_DEFAULTS = {'G': (185, 80), 'D': (180, 76), 'M': (178, 74), 'F': (180, 76)}


def apply_unpublished_physical_defaults(proposal):
    rows = proposal['desired_people']
    if any(row['source_player'].get(key) is not None for row in rows for key in ('height_cm', 'weight_kg')):
        raise ValueError('editorial defaults cannot overwrite a published physical fact')
    if any(row['source_player']['position'] not in UNPUBLISHED_DEFAULTS for row in rows):
        raise ValueError('editorial physical defaults require a supported broad role')
    defaults = []
    for row in rows:
        height, weight = UNPUBLISHED_DEFAULTS[row['source_player']['position']]
        row['source_player'].update(height_cm=height, weight_kg=weight)
        row['secondary_facts_status'].update(height='explicit deterministic unsourced role-based fallback',
            weight='explicit deterministic unsourced role-based fallback')
        defaults.append(dict(source_player_id=row['source_person']['source_player_id'],
            height_cm=height, weight_kg=weight, historically_sourced=False,
            basis='Fixed declared role-based V1 fallback; avoid native loader randomising unknown sentinels.'))
    assigned = {r['source_person']['source_player_id']: r for r in rows}
    for row in proposal['allocation']:
        row['replacement'] = assigned[row['replacement']['source_person']['source_player_id']]
    return defaults


def prepare(output, baseline_release_id=None, *, fallback_defaults=False, preserve_skills=False):
    if preserve_skills and not fallback_defaults:
        raise ValueError('stable physical defaults require explicit fallback defaults')
    if output.exists():
        raise ValueError('verified foreign source inputs are immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-borac2003-source-') as temporary:
        proposal = source.prepare(Path(temporary) / 'allocation.json', baseline_release_id)
    retained = source.ROOT.parent / 'borac-2003-fixed18-source-feasibility-v1.json'
    if pipeline.read_json_file(retained) != proposal:
        raise ValueError('original positive fixed18 allocation no longer reproduces')
    _, raw, binding = source_rows('borac-2003-original-opening-photographs-retrospective')
    page = BeautifulSoup(raw, 'html.parser')
    headers = [h for h in page.select('h3') if h.get_text(' ', strip=True) == 'Borac (ČA) - Partizan 0-1']
    expected = "16. kolo, 22.02.2004, Čačak, Gradski stadion kraj Morave, 4.500 gledalaca, strelac: Boja 68'"
    paragraph = headers[0].find_next('p') if len(headers) == 1 else None
    if paragraph is None or paragraph.get_text(' ', strip=True) != expected:
        raise ValueError('target-season home-ground record missing or changed')
    proposal.update(schema_version='pm99-private-original-borac2003-verified-inputs-v1',
        source_title='Original2003 Borac openingXI and used substitutes plus five positive dated reserves',
        dated_manager_ground=dict(date='2003-08-09', source_club_id=2209,
            manager='Radovan Gudurić', ground='Gradski stadion',
            ground_source=dict(date='2004-02-22', published_name='Gradski stadion kraj Morave',
                native_name_policy='Compact facility name; target-season February home fixture, not claimed first home or August proof.'),
            ground_original=binding),
        secondary_fact_review=dict(policy='original-archived-birthday-country-and-declared-unpublished-fallbacks-v1',
            original_bindings=[proposal['original_bindings'][0]],
            native_fallbacks=['Heights and weights unpublished in original catalogue; preserved seed-slot values, NOT source facts.',
                'Later catalogue shirt numbers are not certified as opening numbers.', 'No inherited portraits.'],
            nationality_limit='Original catalogue Scg mapped to native YUGOSLAVIA; no later Serbian/Montenegrin citizenship claim.'),
        source_disagreements=[dict(name='Bozo Milic', selected=False,
            archive_birthday='1981-10-10', biography_birthday='1981-11-10',
            policy='Conflicting secondary identity excluded; not silently corrected or selected.')])
    proposal['original_bindings'].append(binding)
    if fallback_defaults:
        defaults = apply_unpublished_physical_defaults(proposal)
        proposal['secondary_fact_review'].update(policy=EDITORIAL_POLICY,
            unpublished_native_defaults=defaults,
            native_fallbacks=['Explicit unsourced role-based height/weight defaults, not historical claims.',
                'Later catalogue shirt numbers are not certified as opening numbers.', 'No inherited portraits.'],
            native_loader_reason='Height byte below150 randomly becomes170..179cm; weight below20 randomly becomes75..84kg at startup. Observed original executable4aff35..4aff72; defaults disable only that unknown-field behaviour.')
        if preserve_skills:
            proposal['secondary_fact_review'].update(policy=STABLE_SKILLS_POLICY,
                rating_height_policy='Unpublished height remains None for rating generation; physical defaults must not change any of the ten skills.')
    proposal = json.loads(pipeline.canonical_json_bytes(proposal))
    pipeline.write_canonical_json(output, proposal)
    return proposal


def native_dated(proposal):
    return dict(dated=proposal['dated_manager_ground'], report_binding=proposal['original_bindings'][2],
        manager_native_names=dict(surname='Guduric', display_name='Guduric'),
        manager_person_id='manager-original-chronology-2003-radovan-guduric',
        artifact_id='borac-original-manager-ground-2003', relative_path='borac-original-manager-2003.html')
