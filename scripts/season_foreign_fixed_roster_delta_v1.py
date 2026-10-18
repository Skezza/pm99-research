"""Exact known-good reconstruction for a source-backed foreign roster delta.

First adapter: OFK2004, replacing the obsolete18-player Becej carrier. Replays
original XI, dated reserves, biography and annual facts before native APIs are
called. Does not edit a preferred release or silently discard a recipe edit.
"""
import copy
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_ofk_2004_private_native_v1 as native
from scripts import prepare_ofk_2004_private_kits_v1 as kits
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_kit_render_bindings_v1 as render
from scripts import cascade_compact_kit_v6 as cascade
from scripts.prepare_paired_club_assets_v1 import pixel_payload
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts.season_visual_patch_v1 import source_inventory
from app.bitmap_pixel_rows import bitmap_pixel_ranges

MODE = 'known-good-baseline-original-foreign-fixed-roster-delta'
SCHEMA = 'pm99-source-bound-foreign-fixed-roster-delta-v1'
PREFIX = 'original-foreign-fixed-roster-'
FILENAME = 'foreign-fixed-roster.json'
COUPLED_ADAPTER = 'OFK2015-original-XI-and-positive-Celta-opening-fixed-carrier-exchange'
TACHIRA_ADAPTER = 'Tachira2014-original-club-press-first-XI-and-published-bench'
TACHIRA_2015_ADAPTER = 'Tachira2015-original-first-XI-used-subs-and-positive-opening-reserves'
JEDINSTVO_2005_ADAPTER = 'Jedinstvo2005-original-first-XI-used-subs-and-positive-opening-reserves'
BORAC_2003_ADAPTER = 'Borac2003-original-first-XI-used-subs-and-positive-opening-reserves'
ITALCHACAO_2001_ADAPTER = 'Italchacao2001-approved-August-cup-XI-and-friendly-additions'
HAJDUK_2002_ADAPTER = 'Hajduk2002-original-XI-positive-reserves-and-approved-surname-actor'
MONAGAS_2003_ADAPTER = 'Monagas2003-original-August-cup-XI-adjoining-opening-actors-and-explicit-secondary-gaps'
MONAGAS_2002_ADAPTER = 'Monagas2002-original-August-cup-XI-used-and-unused-bench-and-explicit-secondary-gaps'
SARTID_2000_ADAPTER = 'Sartid2000-original-August-round2-XI-used-subs-and-positive-reserves'
ESTUDIANTES_2000_ADAPTER = 'Estudiantes2000-original-August-cup-XI-and-published-bench-with-unresolved-Gomez'
MLADOST_2001_ADAPTER = 'Mladost2001-original-August-round2-XI-positive-reserves-and-surname-actors'


def kit_source_artifact(season, catalogue, *, carrier=None):
    """Bind the kit proof to its actual period, not the first adapter's year."""
    if season not in ('2004-05', '2015-16', '2014-15', '2005-06', '2003-04', '2001-02', '2002-03', '2000-01'):
        raise ValueError('unsupported foreign kit source period')
    if carrier is not None and (carrier,season) not in ((2953,'2015-16'),(2953,'2003-04'),(2953,'2002-03'),(2953,'2000-01'),(706,'2001-02')):
        raise ValueError('unsupported explicit foreign kit carrier/period')
    if (carrier,season)==(706,'2001-02'):
        return dict(id='mladost-explicit-factory-seed-kit-2001',kind='season-input',
            relative_path='mladost-factory-seed-kit-source-2001.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if (carrier,season)==(2953,'2000-01'):
        return dict(id='estudiantes-reviewed-editorial-kit-2000',kind='season-input',
            relative_path='estudiantes-editorial-kit-source-2000.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if season=='2000-01':
        return dict(id='sartid-reviewed-editorial-kit-2000',kind='season-input',
            relative_path='sartid-editorial-kit-source-2000.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if (carrier,season)==(2953,'2002-03'):
        return dict(id='monagas-reviewed-period-kit-2002',kind='season-input',
            relative_path='monagas-period-kit-source-2002.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if (carrier,season)==(2953,'2003-04'):
        return dict(id='monagas-reviewed-period-kit-2003',kind='season-input',
            relative_path='monagas-period-kit-source-2003.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if season == '2001-02':
        return dict(id='italchacao-reviewed-period-kit-2001',kind='season-input',
            relative_path='italchacao-period-kit-source-2001.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if season == '2002-03':
        return dict(id='hajduk-reviewed-period-kit-2002',kind='season-input',
            relative_path='hajduk-period-kit-source-2002.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue)+b'\n').hexdigest())
    if season == '2003-04':
        return dict(id='borac-reviewed-period-kit-2003', kind='season-input',
            relative_path='borac-period-kit-source-2003.json',
            sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue) + b'\n').hexdigest())
    prefix = 'jedinstvo' if season=='2005-06' else ('tachira' if season == '2014-15' or carrier==2953 else 'ofk')
    return dict(id=prefix + '-reviewed-period-kit-' + season[:4], kind='season-input',
        relative_path='jedinstvo-period-kit-source-2005.json' if season=='2005-06' else ('tachira-period-kit-source-2015.json' if carrier==2953 else 'ofk-period-kit-source.json'),
        sha256=hashlib.sha256(pipeline.canonical_json_bytes(catalogue) + b'\n').hexdigest())


def reject_factory_recipe(package):
    if any(a.get('id', '').startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('foreign fixed-roster recipe requires its exact source-bound delta reconstruction; factory compilation would discard it')


def descriptor(proposal_path):
    proposal = pipeline.read_json_file(proposal_path)
    if proposal.get('schema_version')=='pm99-private-original-mladost2001-verified-inputs-v1':
        from scripts import prepare_mladost_2001_verified_inputs_v1 as inputs
        from scripts import prepare_mladost_2001_seed_kits_v1 as seed_kits
        from scripts import season_original_fixture_display_v1 as fixture_display
        actors=[r['source_person'] for r in proposal['desired_people'] if r['source_person']['birth_date'] is None]
        if len(actors)!=8:raise ValueError('Mladost requires eight explicit unresolved surname actors')
        for actor in actors:fixture_display.verify_actor(actor)
        if (proposal['season']!='2001-02' or proposal['policy']!=inputs.POLICY
                or len(proposal['desired_people'])!=18 or proposal['outside_identity_owners']
                or proposal['original_opening']['first_league_xi'] is not False
                or proposal['original_opening']['fixture_date']!='2001-08-26'):
            raise ValueError('Mladost period capacity/policy/ownership differs')
        return dict(schema_version=SCHEMA,policy=inputs.POLICY,season='2001-02',source_adapter=MLADOST_2001_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='serbia',source_club_id=904,native_club_carrier_id=706,fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(seed_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version')=='pm99-private-original-estudiantes2000-verified-inputs-v1':
        from scripts import prepare_estudiantes_2000_verified_inputs_v1 as inputs
        from scripts import prepare_estudiantes_2000_period_kits_v1 as period_kits
        from scripts import season_original_fixture_display_v1 as fixture_display
        actors=[r['source_person'] for r in proposal['desired_people'] if r['source_person']['birth_date'] is None]
        if len(actors)!=1:raise ValueError('Estudiantes requires one explicit unresolved period Gomez actor')
        fixture_display.verify_actor(actors[0])
        if (proposal['season']!='2000-01' or proposal['policy']!=inputs.POLICY
                or len(proposal['desired_people'])!=16 or proposal['outside_identity_owners']
                or proposal['source_fallback']!=proposal['original_opening']['approved_lineup_fallback']):
            raise ValueError('Estudiantes original capacity/policy/ownership differs')
        return dict(schema_version=SCHEMA,policy=inputs.POLICY,season='2000-01',
            source_adapter=ESTUDIANTES_2000_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='venezuela',source_club_id=14555,native_club_carrier_id=2953,fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version')=='pm99-private-original-sartid2000-verified-inputs-v1':
        from scripts import prepare_sartid_2000_verified_inputs_v1 as inputs
        from scripts import prepare_sartid_2000_period_kits_v1 as period_kits
        if (proposal['season']!='2000-01' or proposal['policy']!=inputs.POLICY
                or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']
                or len(proposal['desired_people'])!=18
                or proposal['original_opening']['first_league_xi'] is not False
                or proposal['original_opening']['fixture_date']!='2000-08-19'):
            raise ValueError('unsupported Sartid period/policy/ownership/declared round2 fixture')
        return dict(schema_version=SCHEMA,policy=inputs.POLICY,season='2000-01',
            source_adapter=SARTID_2000_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='serbia',source_club_id=3544,native_club_carrier_id=706,fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-monagas2002-verified-inputs-v1':
        from scripts import prepare_monagas_2002_verified_inputs_v1 as monagas_inputs
        from scripts import prepare_monagas_2002_period_kits_v1 as period_kits
        if (proposal['season']!='2002-03' or proposal['policy']!=monagas_inputs.POLICY
                or proposal['outside_identity_owners'] or len(proposal['desired_people'])!=16):
            raise ValueError('Monagas original opening policy/capacity/ownership differs')
        return dict(schema_version=SCHEMA,policy=proposal['policy'],season='2002-03',
            source_adapter=MONAGAS_2002_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='venezuela',source_club_id=14596,native_club_carrier_id=2953,fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-monagas2003-verified-inputs-v1':
        from scripts import prepare_monagas_2003_verified_inputs_v1 as monagas_inputs
        from scripts import prepare_monagas_2003_period_kits_v1 as period_kits
        if (proposal['season']!='2003-04' or proposal['policy']!=monagas_inputs.POLICY
                or proposal['outside_identity_owners'] or len(proposal['desired_people'])!=16):
            raise ValueError('Monagas original opening policy/capacity/ownership differs')
        return dict(schema_version=SCHEMA,policy=proposal['policy'],season='2003-04',
            source_adapter=MONAGAS_2003_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='venezuela',source_club_id=14596,native_club_carrier_id=2953,fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-hajduk2002-verified-inputs-v1':
        from scripts import prepare_hajduk_2002_verified_inputs_v1 as hajduk_inputs
        from scripts import prepare_hajduk_2002_period_kits_v1 as period_kits
        from scripts import season_original_fixture_display_v1 as fixture_display
        actors=[r['source_person'] for r in proposal['desired_people'] if r['source_person']['birth_date'] is None]
        if len(actors)!=1:raise ValueError('Hajduk requires exactly one explicitly reviewed surname actor')
        fixture_display.verify_actor(actors[0])
        if (proposal['season']!='2002-03' or proposal['policy']!=hajduk_inputs.POLICY
                or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']):
            raise ValueError('unsupported original Hajduk period/policy/ownership')
        return dict(schema_version=SCHEMA,policy=hajduk_inputs.POLICY,season='2002-03',
            source_adapter=HAJDUK_2002_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='serbia',source_club_id=3140,native_club_carrier_id=706,fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-italchacao2001-verified-inputs-v1':
        from scripts import prepare_italchacao_2001_source_allocation_v1 as ital_source
        from scripts import prepare_italchacao_2001_period_kits_v1 as period_kits
        from scripts import season_august_source_fallback_v1 as fallback
        expected_fallback = fallback.lineup(season='2001-02',fixture_date='2001-08-08',
            competition='cup',source_binding=proposal['original_bindings'][0],missing_league_xi=True)
        if (proposal['season'] != '2001-02' or proposal['policy'] != ital_source.POLICY
                or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']
                or proposal.get('source_fallback') != expected_fallback):
            raise ValueError('unsupported original Italchacao period/policy/ownership/fallback')
        return dict(schema_version=SCHEMA,policy=ital_source.POLICY,season='2001-02',
            source_adapter=ITALCHACAO_2001_ADAPTER,baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='venezuela',source_club_id=21800,native_club_carrier_id=2953,fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-borac2003-verified-inputs-v1':
        from scripts import prepare_borac_2003_period_kits_v1 as period_kits
        from scripts.prepare_borac_2003_source_allocation_v1 import POLICY
        if proposal['season'] != '2003-04' or proposal['policy'] != POLICY or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']:
            raise ValueError('unsupported original Borac source period/policy/ownership')
        return dict(schema_version=SCHEMA, policy=POLICY, season='2003-04', source_adapter=BORAC_2003_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path), sha256=registry.sha256_file(proposal_path)),
            country='serbia', source_club_id=2209, native_club_carrier_id=706, fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'], kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version')=='pm99-private-original-jedinstvo2005-verified-inputs-v1':
        from scripts import prepare_jedinstvo_2005_period_kits_v1 as period_kits
        from scripts.prepare_jedinstvo_2005_source_allocation_v1 import POLICY
        if proposal['season']!='2005-06' or proposal['policy']!=POLICY or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']:
            raise ValueError('unsupported original Jedinstvo source period/policy/ownership')
        return dict(schema_version=SCHEMA,policy=POLICY,season='2005-06',source_adapter=JEDINSTVO_2005_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='serbia',source_club_id=8357,native_club_carrier_id=706,fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version')=='pm99-private-original-tachira2015-verified-inputs-v1':
        from scripts import prepare_tachira_2015_period_kits_v1 as period_kits
        if (proposal['season']!='2015-16' or proposal['policy']!='original-dated-match-XI-used-subs-plus-bracketed-reserves-fixed-capacity-v1'
                or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']):
            raise ValueError('unsupported original2015 Táchira period/policy/ownership')
        return dict(schema_version=SCHEMA,policy=proposal['policy'],season='2015-16',source_adapter=TACHIRA_2015_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='venezuela',source_club_id=13297,native_club_carrier_id=2953,fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('schema_version') == 'pm99-private-original-tachira2014-verified-inputs-v1':
        from scripts import prepare_tachira_2014_period_kits_v1 as period_kits
        if (proposal['season'] != '2014-15' or proposal['policy'] != 'original-dated-club-press-XI-plus-published-bench-fixed-capacity-v1'
                or not proposal.get('secondary_fact_review') or proposal['outside_identity_owners']):
            raise ValueError('unsupported original Táchira source period/policy/ownership')
        return dict(schema_version=SCHEMA, policy=proposal['policy'], season='2014-15', source_adapter=TACHIRA_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path), sha256=registry.sha256_file(proposal_path)),
            country='venezuela', source_club_id=13297, native_club_carrier_id=2953, fixed_slots=16,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'], kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    if proposal.get('policy') != source.POLICY or proposal.get('season') not in ('2004-05','2015-16') or not proposal.get('secondary_fact_review'):
        raise ValueError('unsupported original foreign source adapter/policy')
    if proposal['season']=='2015-16':
        from scripts import prepare_ofk_2015_period_kits_v1 as period_kits
        if proposal.get('schema_version')!='pm99-private-original-ofk2015-celta-coupled-inputs-v1':
            raise ValueError('coupled foreign source proposal schema differs')
        return dict(schema_version=SCHEMA,policy=source.POLICY,season='2015-16',source_adapter=COUPLED_ADAPTER,
            baseline_release_id=proposal['baseline_release_id'],
            original_proposal=dict(path=registry.relative_workspace_path(proposal_path),sha256=registry.sha256_file(proposal_path)),
            country='serbia',source_club_id=53,native_club_carrier_id=706,fixed_slots=18,
            secondary_fact_policy=proposal['secondary_fact_review']['policy'],
            kit_source_catalogue=copy.deepcopy(period_kits.catalogue()),
            carrier_exchange=copy.deepcopy(proposal['coupled_native_carrier_exchange']),
            opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')
    return dict(schema_version=SCHEMA, policy=source.POLICY, season='2004-05',
        source_adapter='OFK2004-original-first-XI-plus-strict-dated-reserves',
        baseline_release_id=proposal['baseline_release_id'],
        original_proposal=dict(path=registry.relative_workspace_path(proposal_path), sha256=registry.sha256_file(proposal_path)),
        country='serbia', source_club_id=53, native_club_carrier_id=706,
        fixed_slots=18, secondary_fact_policy=proposal['secondary_fact_review']['policy'],
        kit_source_catalogue=copy.deepcopy(kits.catalogue()),
        opaque_foreign_tactics_policy='preserve-existing-mode1-not-historically-certified')


def verify_plan(plan):
    if plan.get('schema_version') != SCHEMA or plan.get('source_adapter') not in ('OFK2004-original-first-XI-plus-strict-dated-reserves',COUPLED_ADAPTER,TACHIRA_ADAPTER,TACHIRA_2015_ADAPTER,JEDINSTVO_2005_ADAPTER,BORAC_2003_ADAPTER,ITALCHACAO_2001_ADAPTER,HAJDUK_2002_ADAPTER,MONAGAS_2003_ADAPTER,MONAGAS_2002_ADAPTER,SARTID_2000_ADAPTER,ESTUDIANTES_2000_ADAPTER,MLADOST_2001_ADAPTER):
        raise ValueError('unsupported foreign fixed-roster delta descriptor')
    binding = plan['original_proposal']
    path = registry.ROOT / binding['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != binding['sha256'] or descriptor(path) != plan:
        raise ValueError('foreign original source descriptor changed')
    proposal = pipeline.read_json_file(path)
    with tempfile.TemporaryDirectory(prefix='pm99-foreign-original-replay-') as temporary:
        if plan['source_adapter'] == MLADOST_2001_ADAPTER:
            from scripts import prepare_mladost_2001_verified_inputs_v1 as inputs
            replay=inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == ESTUDIANTES_2000_ADAPTER:
            from scripts import prepare_estudiantes_2000_verified_inputs_v1 as inputs
            replay=inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == SARTID_2000_ADAPTER:
            from scripts import prepare_sartid_2000_verified_inputs_v1 as inputs
            replay=inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == MONAGAS_2002_ADAPTER:
            from scripts import prepare_monagas_2002_verified_inputs_v1 as monagas_inputs
            replay=monagas_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == MONAGAS_2003_ADAPTER:
            from scripts import prepare_monagas_2003_verified_inputs_v1 as monagas_inputs
            replay=monagas_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == HAJDUK_2002_ADAPTER:
            from scripts import prepare_hajduk_2002_verified_inputs_v1 as hajduk_inputs
            replay=hajduk_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == ITALCHACAO_2001_ADAPTER:
            from scripts import prepare_italchacao_2001_verified_inputs_v1 as ital_inputs
            replay=ital_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == BORAC_2003_ADAPTER:
            from scripts import prepare_borac_2003_verified_inputs_v1 as borac_inputs
            replay = borac_inputs.prepare(Path(temporary) / 'source.json', baseline_release_id=plan['baseline_release_id'],
                fallback_defaults=plan['secondary_fact_policy'] in (borac_inputs.EDITORIAL_POLICY, borac_inputs.STABLE_SKILLS_POLICY),
                preserve_skills=plan['secondary_fact_policy'] == borac_inputs.STABLE_SKILLS_POLICY)
        elif plan['source_adapter']==JEDINSTVO_2005_ADAPTER:
            from scripts import prepare_jedinstvo_2005_verified_inputs_v1 as jedinstvo_inputs
            replay=jedinstvo_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter']==TACHIRA_2015_ADAPTER:
            from scripts import prepare_tachira_2015_verified_inputs_v1 as tachira_inputs
            replay=tachira_inputs.prepare(Path(temporary)/'source.json',baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter'] == TACHIRA_ADAPTER:
            from scripts import prepare_tachira_2014_verified_inputs_v1 as tachira_inputs
            replay = tachira_inputs.prepare(Path(temporary)/'source.json', baseline_release_id=plan['baseline_release_id'])
        elif plan['source_adapter']==COUPLED_ADAPTER:
            from scripts import prepare_ofk_2015_verified_inputs_v1 as coupled_inputs
            replay=coupled_inputs.prepare(Path(temporary)/'proposal.json')
        else:
            replay = source.prepare(Path(temporary) / 'proposal.json', secondary_facts=True,
                baseline_release_id=plan['baseline_release_id'])
        if replay != proposal: raise ValueError('foreign source allocation does not reproduce from originals')
    baseline = registry.load_registered_release(plan['season'], plan['baseline_release_id'])
    if registry.sha256_file(baseline.package_path) != proposal['baseline_package']['sha256']:
        raise ValueError('foreign exact baseline recipe changed')
    return baseline, proposal


def compose(plan, render_dir):
    baseline, proposal = verify_plan(plan)
    if plan['source_adapter'] == MLADOST_2001_ADAPTER:
        from scripts import prepare_mladost_2001_verified_inputs_v1 as inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=inputs.native_dated(proposal))
    elif plan['source_adapter'] == ESTUDIANTES_2000_ADAPTER:
        from scripts import prepare_estudiantes_2000_verified_inputs_v1 as inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=inputs.native_dated(proposal))
    elif plan['source_adapter'] == SARTID_2000_ADAPTER:
        from scripts import prepare_sartid_2000_verified_inputs_v1 as inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=inputs.native_dated(proposal))
    elif plan['source_adapter'] == MONAGAS_2002_ADAPTER:
        from scripts import prepare_monagas_2002_verified_inputs_v1 as monagas_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=monagas_inputs.native_dated(proposal))
    elif plan['source_adapter'] == MONAGAS_2003_ADAPTER:
        from scripts import prepare_monagas_2003_verified_inputs_v1 as monagas_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=monagas_inputs.native_dated(proposal))
    elif plan['source_adapter'] == HAJDUK_2002_ADAPTER:
        from scripts import prepare_hajduk_2002_verified_inputs_v1 as hajduk_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=hajduk_inputs.native_dated(proposal))
    elif plan['source_adapter'] == ITALCHACAO_2001_ADAPTER:
        from scripts import prepare_italchacao_2001_verified_inputs_v1 as ital_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=ital_inputs.native_dated(proposal))
    elif plan['source_adapter'] == BORAC_2003_ADAPTER:
        from scripts import prepare_borac_2003_verified_inputs_v1 as borac_inputs
        result, composition, before, files, detail = native.compile_files(baseline, proposal,
            pipeline.read_json_file(baseline.package_path), original_dated=borac_inputs.native_dated(proposal))
    elif plan['source_adapter']==JEDINSTVO_2005_ADAPTER:
        from scripts import prepare_jedinstvo_2005_verified_inputs_v1 as jedinstvo_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=jedinstvo_inputs.native_dated(proposal))
    elif plan['source_adapter']==TACHIRA_2015_ADAPTER:
        from scripts import prepare_tachira_2015_verified_inputs_v1 as tachira_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path),original_dated=tachira_inputs.native_dated(proposal))
    elif plan['source_adapter'] == TACHIRA_ADAPTER:
        from scripts import prepare_tachira_2014_verified_inputs_v1 as tachira_inputs
        result,composition,before,files,detail=native.compile_files(baseline,proposal,
            pipeline.read_json_file(baseline.package_path), original_dated=tachira_inputs.native_dated(proposal))
    elif plan['source_adapter']==COUPLED_ADAPTER:
        from scripts import prepare_coupled_foreign_native_v1 as coupled_native
        result,composition,before,files,detail=coupled_native.compile_files(baseline,proposal)
    else:
        result, composition, before, files, detail = native.compile_files(baseline, proposal,
            pipeline.read_json_file(baseline.package_path))
    catalogue = plan['kit_source_catalogue']
    if plan['source_adapter']==MLADOST_2001_ADAPTER:
        from scripts import prepare_mladost_2001_seed_kits_v1 as seed_kits
        bindings,rendered=seed_kits.render_seed(catalogue,render_dir)
    else:
        bindings, rendered = render.render_catalogue(catalogue, dbdat=cascade.BASE,
            output_dir=render_dir, pattern_cache_dir=cascade.CACHE, allow_network=False)
    if rendered['coverage']['bound_club_count'] != 1: raise ValueError('foreign kit has a source/render gap')
    artifact_paths = {}
    changes = []
    for archive in render.ARCHIVES:
        raw = (baseline.game_path / 'DBDAT' / archive).read_bytes()
        record = render._record_index(baseline.game_path / 'DBDAT' / archive)[plan['native_club_carrier_id']]
        artifact = next(a for a in bindings['clubs'][0]['artifacts'] if a['id'].endswith('-' + archive[:-4].lower()))
        path = render_dir / artifact['relative_path']
        if registry.sha256_file(path) != artifact['sha256']: raise ValueError('foreign render differs from its binding')
        payload = pixel_payload(record, path.read_bytes())
        patched = bytearray(raw)
        patched[record.bitmap_offset:record.bitmap_offset + record.bitmap_length] = payload
        intervals = [(record.bitmap_offset + lo, record.bitmap_offset + hi)
            for lo, hi in bitmap_pixel_ranges(record)]
        if len(raw) != len(patched) or any(not any(lo <= i < hi for lo, hi in intervals)
                for i, (a, b) in enumerate(zip(raw, patched)) if a != b):
            raise ValueError('foreign kit changed another club, palette, wrapper or padding')
        files[archive] = bytes(patched)
        before[archive] = raw
        artifact_paths[artifact['relative_path']] = path
        changes.append(dict(archive=archive, carrier_id=plan['native_club_carrier_id'], only_pixel_lane_changed=True,
            before_sha256=hashlib.sha256(raw).hexdigest(), after_sha256=hashlib.sha256(bytes(patched)).hexdigest()))
    artifacts = copy.deepcopy(bindings['clubs'][0]['artifacts'])
    new_tachira=plan['source_adapter']==TACHIRA_2015_ADAPTER
    source_artifact = kit_source_artifact(plan['season'], catalogue,
        carrier=706 if plan['source_adapter']==MLADOST_2001_ADAPTER else (2953 if new_tachira or plan['source_adapter'] in (MONAGAS_2003_ADAPTER,MONAGAS_2002_ADAPTER,ESTUDIANTES_2000_ADAPTER) else None))
    plan_artifact = next_source_plan_artifact(result, plan, baseline.package_path.parent, artifact_paths)
    target = next(k for k in result['assets']['kits'] if k['club_id'] == 'club-' + str(plan['native_club_carrier_id']))
    target.update(policy='write', artifact_ids=[a['id'] for a in artifacts],
        proof=dict(artifact_id=source_artifact['id'], grade='source-receipt' if plan['source_adapter']==MLADOST_2001_ADAPTER else 'reviewed-editorial'))
    result['artifacts'] += artifacts + [source_artifact, plan_artifact]
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return baseline, result, composition, before, files, detail, artifact_paths, bindings, rendered, changes


def next_source_plan_artifact(recipe, plan, baseline_dir, paths):
    """Stack a club repair without overwriting an earlier club's source proof.

    Existing first repairs and the delivered 2015 second repair retain their
    exact IDs/bytes. Later repairs get distinct IDs while inherited proof IDs
    remain untouched. This changes metadata paths, not any unrelated native DB.
    """
    inherited = [a for a in recipe['artifacts'] if a.get('relative_path') == FILENAME]
    if inherited or plan['source_adapter'] == TACHIRA_2015_ADAPTER:
        preserve_inherited_plan(recipe, baseline_dir, paths)
    ids = {a['id'] for a in recipe['artifacts']}
    new_id = PREFIX + plan['season'] + ('-club-2953' if plan['source_adapter'] == TACHIRA_2015_ADAPTER else '')
    digest = hashlib.sha256(pipeline.canonical_json_bytes(plan) + b'\n').hexdigest()
    if new_id in ids:
        new_id += '-club-' + str(plan['native_club_carrier_id']) + '-' + digest[:12]
    if new_id in ids:
        raise ValueError('foreign source-plan identity collision; no prior proof overwritten')
    return dict(id=new_id, kind='season-input', relative_path=FILENAME, sha256=digest)


def preserve_inherited_plan(recipe, baseline_dir, paths):
    inherited=[a for a in recipe['artifacts'] if a.get('relative_path')==FILENAME]
    if len(inherited)!=1 or not inherited[0]['id'].startswith(PREFIX):
        raise ValueError('chained foreign delta lacks one explicit inherited source plan')
    artifact=inherited[0]
    original=baseline_dir/FILENAME
    verify_recipe_artifact(original,artifact['sha256'])
    relative='inherited-foreign-fixed-roster-'+artifact['sha256'][:12]+'.json'
    if any(a.get('relative_path')==relative for a in recipe['artifacts']) or relative in paths:
        raise ValueError('inherited foreign source path collision')
    artifact['relative_path']=relative
    paths[relative]=original


def materialise(plan, output):
    if output.exists(): raise ValueError('foreign exact-replay workspace is immutable')
    output.mkdir(parents=True)
    baseline, recipe, composition, before, files, detail, paths, bindings, rendered, changes = compose(plan, output / 'renders')
    if shutil.disk_usage(baseline.game_path).free < 8 * 1024**3 + sum(len(b) for b in files.values()):
        raise ValueError('foreign replay crosses8GiB local reserve')
    shutil.copytree(baseline.game_path, output / 'game', copy_function=os.link)
    for name, payload in files.items(): atomic_bytes(output / 'game/DBDAT' / name, payload)
    corrected=detail.get('corrected_native_carriers',detail['ordered_native_carriers'])
    for id in corrected:
        path = output / 'game/DBDAT/MINIFOTO' / f'J96{id:05d}.BMP'
        if path.exists(): path.unlink()  # Private hardlink only, not the known-good baseline.
    compositions=composition if isinstance(composition,list) else [composition]
    new_tachira=plan['source_adapter']==TACHIRA_2015_ADAPTER
    kit_relative=kit_source_artifact(plan['season'],plan['kit_source_catalogue'],
        carrier=706 if plan['source_adapter']==MLADOST_2001_ADAPTER else (2953 if new_tachira or plan['source_adapter'] in (MONAGAS_2003_ADAPTER,MONAGAS_2002_ADAPTER,ESTUDIANTES_2000_ADAPTER) else None))['relative_path']
    generated = {FILENAME: plan, kit_relative: plan['kit_source_catalogue'],
        **{native.delta.plan_filename(c):c for c in compositions}}
    if plan['source_adapter'] == MLADOST_2001_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['mladost-original-opening-2001.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == ESTUDIANTES_2000_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['estudiantes-original-opening-2000.pdf']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == SARTID_2000_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['sartid-original-opening-2000.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == MONAGAS_2002_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['monagas-original-opening-2002.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == MONAGAS_2003_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['monagas-original-opening-2003.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == HAJDUK_2002_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['hajduk-original-manager-2002.html']=registry.ROOT/original_input['original_bindings'][2]['path']
    elif plan['source_adapter'] == ITALCHACAO_2001_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['italchacao-original-opening-2001.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == BORAC_2003_ADAPTER:
        original_input = pipeline.read_json_file(registry.ROOT / plan['original_proposal']['path'])
        paths['borac-original-manager-2003.html'] = registry.ROOT / original_input['original_bindings'][2]['path']
    elif plan['source_adapter']==JEDINSTVO_2005_ADAPTER:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['jedinstvo-original-opening-2005.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif new_tachira:
        original_input=pipeline.read_json_file(registry.ROOT/plan['original_proposal']['path'])
        paths['tachira-original-opening-2015.html']=registry.ROOT/original_input['original_bindings'][0]['path']
    elif plan['source_adapter'] == TACHIRA_ADAPTER:
        original_input = pipeline.read_json_file(registry.ROOT / plan['original_proposal']['path'])
        paths['tachira-original-opening.html'] = registry.ROOT / original_input['original_bindings'][0]['path']
    elif plan['source_adapter']==COUPLED_ADAPTER:
        paths['ofk-original-opening-2015.html']=source.ROOT/'ofk-first-fixture-2015-2598829.html'
    else:
        paths['ofk-original-opening.html'] = source.ROOT / 'ofk-first-fixture-2004-3142214.html'
    for artifact in recipe['artifacts']:
        relative = artifact.get('relative_path')
        if not relative: continue
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('unsafe foreign recipe artifact')
        target = output / rel
        if relative in generated: pipeline.write_canonical_json(target, generated[relative])
        else:
            original = paths.get(relative, baseline.package_path.parent / rel)
            verify_recipe_artifact(original, artifact['sha256'])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(original, target)
        verify_recipe_artifact(target, artifact['sha256'])
    pipeline.write_canonical_json(output / 'season-package.json', recipe)
    pipeline.write_canonical_json(output / 'render-bindings.json', bindings)
    pipeline.write_canonical_json(output / 'render-receipt.json', rendered)
    pipeline.write_canonical_json(output / f"kit-source-{plan['native_club_carrier_id']}.json", dict(
        catalogue_row=plan['kit_source_catalogue']['rows'][0], render_row=rendered['rows'][0]))
    inventory = pipeline.build_tree_inventory(output / 'game')
    pipeline.write_canonical_json(output / 'inventory.json', inventory)
    for name, payload in before.items():
        if (baseline.game_path / 'DBDAT' / name).read_bytes() != payload:
            raise ValueError('foreign known-good baseline changed during replay')
    receipt = dict(schema_version=SCHEMA, season=plan['season'], baseline_release_id=baseline.release_id,
        plan_sha256=registry.sha256_file(output / FILENAME),
        source_proposal_sha256=plan['original_proposal']['sha256'],
        source_plan=plan['original_proposal'], ordered_native_carriers=detail['ordered_native_carriers'],
        corrected_native_carriers=corrected,detail=detail,
        before_hashes={name:registry.sha256_file(baseline.game_path/'DBDAT'/name) for name in files},
        native_hashes={name: registry.sha256_file(output / 'game/DBDAT' / name) for name in files},
        recipe_sha256=registry.sha256_file(output / 'season-package.json'),
        paired_asset_stage={'grounds': [{'carrier_id':plan['native_club_carrier_id'], 'club':plan['kit_source_catalogue']['rows'][0]['club_name'], **detail['dated_manager_ground']}]},
        kit_changes=changes, game_inventory_fingerprint=inventory['files_fingerprint'],
        registered=False, publication_authorised=False, runtime_verified=False,
        native_XI_scope=f"{plan['fixed_slots']} unique sourced people; full original XI membership/order/broad roles. Opaque mode1 deployment not certified.")
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    atomic_bytes(output / 'README.sources.txt', (
        plan['season']+' '+plan['kit_source_catalogue']['rows'][0]['club_name']+' source-backed replacement. Research sources credited:\n'
        'Transfermarkt: original first domestic fixture, annual squads, stable biographies and dated transfer histories.\n'
        'OFK Beograd official club (2004); HotSport original2015 match photograph: period kit design evidence.\n'
        'RC Celta official club: dated2015 preseason membership and2014 international-team witnesses. Wikipedia: declared Cancarevic nationality chronology inference.\n'
        + ('Prensa Deportivo Táchira / LaVinotinto: original10August2014 match and photograph. Dubraska Roa: original8August2014 club presentation. Fichajes and National Football Teams: declared season role/biography comparisons.\n' if plan['source_adapter']==TACHIRA_ADAPTER else '') +
        ('ForoVinotinto / Armando García: original11July2015 first fixture and explicitly linked biographies. Prensa Deportivo Táchira / Café Deportivo: original18July2015 membership/home-ground corroboration and May2015 home-kit photographs; exact first-match away kit was green, not the home default. Earlier OFK/Celta source proofs above remain inherited, not replaced.\n' if new_tachira else '') +
        'Source photographs are retained as local research evidence, not inserted into the game.\n'
        'Kit sponsors/logos/fine panels simplified. Native Yugoslavia represents SRB/MNE.\n'
        'Unavailable secondary facts retained as explicitly logged native fallbacks, not proven source values.\n'
        'Source membership/biographies are not approval of opaque foreign tactics or every fine-role deployment.\n'
        + ('Partizanopedia: original6August2005 Jedinstvo XI/used substitutes and Sava Kovacevic. Borba / Pretraziva archive: original11July2005 signed arrivals and centimetre heights; original8August2005 opening-match colour photograph. Transfermarkt: original27August2005 home ground and independent entry/exit intervals.\n'
           'Jedinstvo V1 kit default uses the observed opening-match blue/white strip; home/away classification remains unconfirmed.\n' if plan['source_adapter']==JEDINSTVO_2005_ADAPTER else '')
        + ('Borac2003-specific sources: Marko Stojanovic / Fudbalske Lige Srbije i Crne Gore (dekisa.tripod.com), preserved by Internet Archive: opening match and full catalogue. Partizanopedia: independent9August2003 first date and13 match participants. UEFA23September2003: Radovan Guduric opening-manager chronology. Transfermarkt: independent literal birthdays and positive entry/exit intervals, NOT the first fixture provider. Crno-bela Nostalgija: retained opening-match colour report/photo and22February2004 home-ground record.\n'
           'Borac red V1 default is the observed opening strip, not certified home/away or exact sponsor/panel artwork. Gradski stadion is the compact target-season February home-ground name, not a first-home or opening-day stadium certification. Heights/weights and opening shirt numbers remain declared secondary gaps; any explicit role-based physical defaults are estimates, not historical facts, and prevent unknown native sentinels from randomising on startup.\n' if plan['source_adapter']==BORAC_2003_ADAPTER else '')
        + ('Deportivo ItalChacao official2000/2001 site / Manuel De Oliveira: original8August2001 cup XI and12August friendly, dated Raul Cavallieri, club ground and May2001 strip artwork/photo. Cup/friendly fallback explicitly approved; first league XI remains unavailable. VenezuelaFutbol2020 interview and original Wikipedia biography resolve Bidoglio birthday while retaining contrary period value.\n' if plan['source_adapter']==ITALCHACAO_2001_ADAPTER else '')
        + ('Marko Stojanovic / Fudbalske Lige Srbije i Crne Gore, Internet Archive: original10August2002 Hajduk XI. Partizanopedia: independent first date, conflicting lineup retained. UEFA1September2002: Miloljub Ostojic June appointment/September departure. Transfermarkt original biographies and positive reserve intervals: identity only, not current nationality/role import. Crno-bela Nostalgija: dated26February2003 Gradski stadion home fixture; linked monochrome ticket is NOT kit colour evidence. Colours of Football / Mikhail Sipovich: original period-labelled Hajduk Kula home2002/03 kit illustration. Original artwork is local design evidence, not redistributed. Trajkovic published surname retained: first name/DOB unknown, native date explicit unsourced fallback.\n' if plan['source_adapter']==HAJDUK_2002_ADAPTER else '')
        + ('Eliezer Sebastian Perez Perez / RSSSF: original5August2003 Monagas cup XI and31July opening actors; compilation credits El Nacional, El Universal and Meridiano. Transfermarkt original calendar2003 identity links/biographies: four missing birthdays explicitly logged, native dates are not player facts. LaVinotinto.com originalJuly2003 screenshot preserved in Universidad Rafael Belloso Chacin thesis0075242 annex: broad blue/maroon strip reference, illustrative photo date/home classification/exact artwork unconfirmed. Original images local research only, not redistributed.\n' if plan['source_adapter']==MONAGAS_2003_ADAPTER else '')
        + ('Partizanopedia: original19August2000 Sartid round2 XI, used substitutes and Slobodan Dogandzic. Transfermarkt: original linked person identities/birthdays and positive entry-exit reserve histories, not current roles/nationality import. FK Smederevo1924: official retrospective ground identity, exact2000 naming unconfirmed. Colours of Football / Mikhail Sipovich: original2002/03 Sartid illustration, explicitly adjoining-year editorial colour fallback NOT target2000/01 artwork. Nationalities XXX/physical defaults are logged; original surnames may be used for display.\n' if plan['source_adapter']==SARTID_2000_ADAPTER else '')
        + ('CONMEBOL magazine66, original period publication archived by SPFCpedia: August2,2000 Estudiantes cup XI and published bench, Antonio DAccorso and Guillermo Soto Rosa. Scanned original page60/printed52 explicitly visually transcribed and hash-bound, not an automatic text scrape. Transfermarkt original linked biographies supply15 birthdays, not present-day nationalities/roles. Period Javier Gomez has unresolved cross-provider identity and birthday; modern Jesus Gomez103260 NOT imported. Wikipedia contributors: traditional red/white stripes and blue shorts, explicitly editorial colour fallback NOT verified target2000 artwork.\n' if plan['source_adapter']==ESTUDIANTES_2000_ADAPTER else '')
        + ('Partizanopedia: original August26,2001 Mladost Apatin round2 XI, used substitutes and Dragi Bogic. Transfermarkt original linked biographies and positively dated reserve histories; eight unresolved fixture surnames retain unknown first names/birthdays. Crno-bela Nostalgija: target-fixture historical ground transcription. Factory carrier706 kit is explicitly a seed fallback, NOT verified Mladost target2001 colours. No current successor-club kit imported.\n' if plan['source_adapter']==MLADOST_2001_ADAPTER else '')
    ).encode())
    return receipt


def publish(candidate, native_proof, identity_proof, release_id):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id): raise ValueError('unsafe foreign release ID')
    plan = pipeline.read_json_file(candidate / FILENAME)
    baseline, proposal = verify_plan(plan)
    receipt_path = candidate / 'candidate-receipt.json'
    receipt = pipeline.read_json_file(receipt_path)
    proof = pipeline.read_json_file(native_proof)
    coupled=plan['source_adapter']==COUPLED_ADAPTER
    if coupled:
        if (not proof.get('source_bound_complete_game')
                or proof['candidate_receipt_sha256']!=registry.sha256_file(receipt_path)
                or proof['package_sha256']!=registry.sha256_file(candidate/'season-package.json')
                or proof['native_hashes']!=receipt['native_hashes']
                or not proof['original_sources_replayed'] or not proof['all19_native_identities_and_skills_read_back']
                or not proof['all_unselected_native_records_identical'] or len(proof['players'])!=19):
            raise ValueError('coupled publication lacks current independent19-player native proof')
    elif (not proof.get('source_bound_complete_game')
            or proof['source_candidate_receipt_sha256'] != registry.sha256_file(receipt_path)
            or proof['package_sha256'] != registry.sha256_file(candidate / 'season-package.json')
            or proof['native_hashes'] != receipt['native_hashes']
            or not proof['source_allocation_replayed'] or not proof['source_people_unique']
            or not proof['unrelated_native_records_byte_identical']
            or len(proof['players']) != plan['fixed_slots']):
        raise ValueError('foreign publication lacks current independent native proof')
    if plan['source_adapter'] in (TACHIRA_ADAPTER,TACHIRA_2015_ADAPTER,JEDINSTVO_2005_ADAPTER,BORAC_2003_ADAPTER,ITALCHACAO_2001_ADAPTER,HAJDUK_2002_ADAPTER,MONAGAS_2003_ADAPTER,MONAGAS_2002_ADAPTER,SARTID_2000_ADAPTER,ESTUDIANTES_2000_ADAPTER,MLADOST_2001_ADAPTER) and not proof.get('all_selected_native_ownership_exclusive'):
        raise ValueError('foreign publication lacks actual all-club native ownership proof')
    if (receipt['plan_sha256'] != registry.sha256_file(candidate / FILENAME)
            or receipt['source_proposal_sha256'] != plan['original_proposal']['sha256']
            or receipt['recipe_sha256'] != proof['package_sha256']):
        raise ValueError('foreign publication source/recipe receipt changed')
    identity = pipeline.read_json_file(identity_proof)
    if (identity['package_sha256'] != registry.sha256_file(candidate / 'season-package.json')
            or identity['candidate_receipt_sha256'] != registry.sha256_file(receipt_path)
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared']):
        raise ValueError('foreign publication lacks current independent identity/portrait proof')
    before, drift = source_inventory(baseline)
    after = pipeline.build_tree_inventory(candidate / 'game')
    if after['files_fingerprint'] != receipt['game_inventory_fingerprint']:
        raise ValueError('foreign complete game inventory changed since composition')
    difference = pipeline.inventory_difference(before, after)
    removed = {f'DBDAT/MINIFOTO/J96{id:05d}.BMP' for id in receipt.get('corrected_native_carriers',receipt['ordered_native_carriers'])}
    allowed = {'DBDAT/' + n for n in receipt['native_hashes']}
    if difference['only_right'] or set(difference['only_left']) - removed or any(r['path'] not in allowed for r in difference['changed']):
        raise ValueError('foreign delta changed an unrelated game file')
    if any(registry.sha256_file(candidate / 'game/DBDAT' / name) != sha for name, sha in receipt['native_hashes'].items()):
        raise ValueError('foreign proved output changed')
    destination = registry.locator_path(plan['season'], release_id).parent
    if destination.exists(): raise ValueError('foreign release metadata is immutable')
    outputs = [dict(path='DBDAT/' + name, sha256=sha, size=(candidate / 'game/DBDAT' / name).stat().st_size)
        for name, sha in sorted(receipt['native_hashes'].items())]
    compiler = dict(schema=SCHEMA, season=plan['season'], compilation_mode=MODE,
        season_package_sha256=registry.canonical_document_sha256(candidate / 'season-package.json'),
        source_season_package_sha256=registry.canonical_document_sha256(baseline.package_path),
        source_compiler_receipt_sha256=registry.sha256_file(baseline.compiler_receipt_path),
        source_build_chain_sha256=registry.sha256_file(baseline.build_chain_path),
        source_game_inventory_fingerprint=before['files_fingerprint'], foreign_plan_sha256=registry.sha256_file(candidate / FILENAME),
        candidate_receipt_sha256=registry.sha256_file(receipt_path), outputs=outputs, difference=difference,
        independent_native_proof_sha256=registry.sha256_file(native_proof),
        independent_identity_proof_sha256=registry.sha256_file(identity_proof),
        players_written=19 if coupled else plan['fixed_slots'], clubs_written=2 if coupled else 1, managers_written=1,
        existing_runtime_config_difference=drift, historical_verification_complete=False)
    destination.mkdir(parents=True)
    compiler_path = destination / 'foreign-delta-compiler.json'
    pipeline.write_canonical_json(compiler_path, compiler)
    from scripts.publish_paired_whole_club_delta_v1 import attach_pair_kit_receipts
    application, complete = attach_pair_kit_receipts(baseline, candidate, destination, receipt, native_proof, identity_proof, difference)
    output_paths = {r['path'] for r in outputs}
    chain = dict(schema_version='pm99-season-build-chain-v1', season=plan['season'],
        package_canonical_sha256=compiler['season_package_sha256'], stages=[
            dict(id='database', receipt_sha256=registry.sha256_file(compiler_path), outputs={r['path']:r['sha256'] for r in outputs}),
            dict(id='inherited-known-good-files', source_build_chain_sha256=compiler['source_build_chain_sha256'],
                outputs={r['path']:r['sha256'] for r in after['files'] if r['path'] not in output_paths})])
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(baseline.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(candidate / 'season-package.json', document_id='season-package')
    manifest['output'] = dict(file_count=after['file_count'], total_bytes=after['total_bytes'], inventory_fingerprint=after['files_fingerprint'])
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=id, path=path, role='input') for id, path in [
        ('foreign-source-receipt',receipt_path), ('foreign-original-source-plan',candidate / FILENAME),
        ('foreign-native-proof',native_proof), ('foreign-identity-proof',identity_proof),
        ('foreign-delta-compiler',compiler_path), ('foreign-kit-application',application),
        ('foreign-complete-kit-receipt',complete), ('previous-recipe',baseline.package_path),
        ('previous-build-chain',baseline.build_chain_path), ('previous-compiler-receipt',baseline.compiler_receipt_path),
        ('build-chain',chain_path)]]
    ids = {a['id'] for a in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in ids] + artifacts, key=lambda a:a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='foreign-fixed-roster-' + release_id,
        implementation_path=Path(__file__), input_fingerprints={'previous-release':baseline.manifest_sha256},
        parameters={'corrected_slots':plan['fixed_slots'], 'country':plan['country'], 'source_club_id':plan['source_club_id'], 'historical_verification_complete':False}, external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s:s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    manifest_path, inventory_path = metadata / 'season-manifest.json', metadata / 'output.inventory.json'
    pipeline.write_canonical_json(manifest_path,manifest)
    pipeline.write_canonical_json(inventory_path,after)
    locator = copy.deepcopy(baseline.locator)
    for key in ('qa_report_path','qa_report_sha256','historical_role_plan_path','historical_role_delta_path','ownership_plan_path','ownership_delta_path'):
        locator.pop(key,None)
    locator.update(release_id=release_id, game_path=registry.relative_workspace_path(candidate / 'game'),
        package_path=registry.relative_workspace_path(candidate / 'season-package.json'),
        package_canonical_sha256=compiler['season_package_sha256'], compiler_receipt_path=registry.relative_workspace_path(compiler_path),
        build_chain_path=registry.relative_workspace_path(chain_path), inventory_path=registry.relative_workspace_path(inventory_path),
        release_manifest_path=registry.relative_workspace_path(manifest_path), game_inventory_fingerprint=after['files_fingerprint'],
        attestation_path=None, runtime_evidence_path=None, technical_status='playable-unverified', qa_status='not-recorded',
        foreign_fixed_roster_plan_path=registry.relative_workspace_path(candidate / FILENAME),
        foreign_fixed_roster_candidate_receipt_path=registry.relative_workspace_path(receipt_path),
        foreign_fixed_roster_candidate_receipt_sha256=registry.sha256_file(receipt_path),
        kit_patch_application_path=registry.relative_workspace_path(application))
    locator['required_file_hashes'] = {name:registry.sha256_file(candidate / 'game' / name) for name in registry.REQUIRED_GAME_FILES}
    visual = {name:sha for name,sha in locator.get('required_visual_file_hashes',{}).items() if name not in removed}
    visual.update({r['path']:r['sha256'] for r in outputs if not r['path'].endswith('.FDI')})
    locator['required_visual_file_hashes'] = visual
    locator['required_visual_absent_paths'] = sorted(set(locator.get('required_visual_absent_paths',[])) | removed)
    pipeline.write_canonical_json(destination / 'locator.json',locator)
    pipeline.assert_tree_matches_inventory(baseline.game_path,before)
    return dict(season=plan['season'], release_id=release_id, release_manifest_sha256=registry.sha256_file(manifest_path), registered=False)


def reconstruction(previous, release_id):
    if previous.compiler_receipt_path is None: return None
    compiler = pipeline.read_json_file(previous.compiler_receipt_path)
    if compiler.get('compilation_mode') != MODE: return None
    plan_path = previous.package_path.parent / FILENAME
    if (registry.sha256_file(plan_path) != compiler['foreign_plan_sha256']
            or registry.canonical_document_sha256(previous.package_path) != compiler['season_package_sha256']):
        raise ValueError('edited foreign recipe cannot use exact reconstruction; no edits discarded')
    original_receipt = previous.package_path.parent / 'candidate-receipt.json'
    if registry.sha256_file(original_receipt) != compiler['candidate_receipt_sha256']:
        raise ValueError('foreign reconstruction receipt changed')
    pipeline.assert_tree_matches_inventory(previous.game_path, pipeline.read_json_file(previous.inventory_path))
    plan = pipeline.read_json_file(plan_path)
    output = registry.ROOT / '.local/foreign-fixed-roster-deltas-v1' / previous.season / release_id
    materialise(plan, output)
    pipeline.assert_tree_matches_inventory(output / 'game', pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(output / 'season-package.json') != pipeline.read_json_file(previous.package_path):
        raise ValueError('foreign full recipe replay differs; no edits discarded')
    from scripts import verify_ofk_2004_private_native_v1 as native_readback
    from scripts import verify_ofk_2004_private_identity_v1 as identity_readback
    proposal_path = registry.ROOT / plan['original_proposal']['path']
    native_path, identity_path = output / 'independent-native.json', output / 'independent-identity.json'
    if plan['source_adapter']==COUPLED_ADAPTER:
        from scripts import verify_coupled_foreign_native_v1 as coupled_readback
        coupled_readback.verify(output,native_path,source_bound_game=True)
        identity_path=native_path  # Same complete-game proof independently reads identity/ownership too.
    else:
        native_readback.verify(output, native_path, proposal_path=proposal_path, source_bound_game=True)
        identity_readback.verify(output, identity_path, proposal_path)
    result = publish(output, native_path, identity_path, release_id)
    result.update(complete_game_inventory_identical=True, complete_recipe_identical=True,
        workspace=registry.relative_workspace_path(output))
    return result
