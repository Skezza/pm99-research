"""Deliver source/native/SOURCE/original-runner-verified position-only batches."""
import copy
from datetime import UTC, datetime

from app.fdi_indexed import IndexedFDIFile
from scripts import season_exact_primary_position_delta_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher, attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def binding(path):
    return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def run(root,season,release_id,replay_id,previous_path,output,tag,profiles,*,policy=None):
    source_policy = policy if policy is not None else source
    if output.exists():
        raise ValueError('completed position publication must not repeat')
    previous=pipeline.read_json_file(previous_path);old=previous['current_release_bindings']
    if bindings()!=old:
        raise ValueError('position publication defaults differ from previous checkpoint')
    actual=registry.load_registered_release(season,release_id)
    plan_path=root/'position-plan.json';plan=pipeline.read_json_file(plan_path)
    base=registry.load_registered_release(season,plan['release_id'])
    if registry.load_preferred_release(season).manifest_sha256!=base.manifest_sha256:
        raise ValueError('position parent advanced or is not yet delivered')
    source_policy.verify(base,plan)
    if not plan['updates'] or {r['carrier_id'] for r in plan['updates']}!={r[0] for r in profiles}:
        raise ValueError('every changed position requires its original final-game profile')
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source_policy.apply(before,eq,plan)!=(after,eq) or source_policy.apply(after,eq,plan)!=(after,eq):
        raise ValueError('complete position native bytes or idempotence differ')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed=set();native_rows=[]
    for row in plan['updates']:
        entry=entries[row['carrier_id']];payload=entry.decode_payload(after)
        native=source.roster.native_player(payload,row['carrier_id']);end=native['name_end']
        allowed.update(entry.payload_offset+end+offset for offset in (*range(2,8),11))
        if (native['position']!=row['primary_position']
                or native['roles']!=row['fine_roles']+[98]*(6-len(row['fine_roles']))):
            raise ValueError('independent stored broad/fine position differs from exact sources')
        native_rows.append(dict(carrier_id=row['carrier_id'],native=native))
    if len(before)!=len(after) or any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(before,after))):
        raise ValueError('position native correction changed an unrelated field')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left)!=set(right) or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('position edit changes another game file')
    if source_policy.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('position recipe changed beyond exact declared fields/artifact')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    rebuilt=registry.load_registered_release(season,replay_id)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('position whole SOURCE proof incomplete')
    for release in (actual,rebuilt):
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if rebuilt.package_path.read_bytes()!=actual.package_path.read_bytes():
        raise ValueError('position whole SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/tag
    transport=pipeline.read_json_file(root/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256']!=actual.manifest_sha256
            or summary['output_inventory_fingerprint']!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('position original startup not bound to corrected game')
    verify_digits(root,season,release_id,profiles)
    verify_profiles(root,season,release_id,profiles)
    for carrier,label,_,_ in profiles:
        observed=pipeline.read_json_file(root/(label+'-profile-visual-review.json'))
        row=next(r for r in plan['updates'] if r['carrier_id']==carrier)
        if (observed.get('observed_broad_position')!=row['primary_position']
                or observed.get('observed_primary_fine_role_code')!=row['fine_roles'][0]
                or observed.get('observed_primary_fine_role_label')!=source.roster.ROLE_LABELS[row['fine_roles'][0]]):
            raise ValueError('actual profile broad and first fine-role text not independently reviewed')
    backup=verify_original2015()
    if bindings()!=old:
        raise ValueError('another preferred game changed during position preflight')
    retained(root/'prepublication-proof.json',dict(rows=native_rows,source_native_whole_SOURCE_and_runtime=True,
        all_non_position_bytes_and_other_game_files_preserved=True,frozen_counts_unchanged=True))
    publisher.register_completed_delta(season,release_id)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    validation=registry.validate_preferred_release(season,level='playable')
    if not validation['valid']:
        raise ValueError('position default fails playable validation')
    retained(root/'preferred-playable-validation.json',validation)
    current=bindings()
    if [r for r in current if r['season']!=season]!=[r for r in old if r['season']!=season]:
        raise ValueError('position publication changed another preferred year')
    result=copy.deepcopy(previous)
    for finding in result['additional_confirmed_findings']:
        if season=='2021-22' and finding['id']=='shinnie-2021-broad-position-conflict' and 9718 in plan['targets']:
            finding.update(state='repaired-and-runtime-verified',correction_evidence=binding(root/'shinnie-profile-visual-review.json'))
        for carrier,label,_,_ in profiles:
            if finding['id']==f'country-source-position-{season}-{carrier}':
                finding.update(state='repaired-and-runtime-verified',
                    correction_evidence=binding(root/(label+'-profile-visual-review.json')))
    result['additional_confirmed_findings'].append(dict(id='exact-primary-position-'+release_id,season=season,
        state='delivered-source-native-SOURCE-and-runtime-verified',players_corrected=len(plan['updates']),
        source_plan=binding(plan_path),cross_club_cases_closed=0,
        no_global_position_or_opening_ownership_approval=True))
    names=['position-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'startup-transport.json','startup-visual-review.json','prepublication-proof.json',
        'final-attestation.json','preferred-playable-validation.json']
    names += [label+suffix for _,label,_,_ in profiles for suffix in ('-profile-transport.json',
        '-profile-visual-review.json','-native-runtime-proof.json','-original-digit-proof.json','-original-age-proof.json')]
    result['delivered_evidence'] += [backup]+[binding(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous_path),
        current_release_bindings=current,fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False)
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=binding(output),position_corrections=len(plan['updates']),
        all_other25_preferred_bindings_unchanged=True,original2015_backup_verified=True,
        frozen_counts_unchanged=True,global_historical_RC=False))
    print(dict(position_corrections_delivered=len(plan['updates']),cross_club_cases_closed=0),flush=True)
