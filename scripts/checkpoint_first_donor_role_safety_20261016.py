"""Deliver the actual first ownership/role/country game, not private trials."""
import copy
from datetime import UTC, datetime
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_donor_keeper_role_delta_v1 as source
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.build_donor_role_safety_20261016 import ROOT, RELEASE
from scripts.build_cross_club_reviewed_reserve_20261016 import RELEASE as PARENT
from scripts.capture_first_donor_role_safety_20261016 import TAG
from scripts.verify_cross_club_reserve_delivery_20261016 import verify as verify_ownership
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.register_verified_delta_chain_v1 import register_chain
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def run():
    season='2000-01';root=ROOT/season
    previous=ROOT.parent/'release-delivery-checklist-v46.json'
    output=ROOT.parent/'release-delivery-checklist-v47.json'
    if output.exists():
        raise ValueError('completed first donor-role checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(previous))
    original={r['season']:r for r in result['current_release_bindings']}
    ownership=verify_ownership()
    base=registry.load_registered_release(season,PARENT)
    release=registry.load_registered_release(season,RELEASE)
    plan=pipeline.read_json_file(root/'role-plan.json');source.verify(base,plan)
    left=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    right=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(left,eq,plan)!=(right,eq) or source.apply(right,eq,plan)!=(right,eq):
        raise ValueError('fresh native exact application or idempotence failed')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(release.package_path):
        raise ValueError('actual final recipe is not the exact composed repair')
    native=pipeline.read_json_file(root/'native-byte-proof.json')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=release.manifest_sha256
        or native['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
        or native['plan_sha256']!=registry.sha256_file(root/'role-plan.json')
        or native['corrected_players']!=len(plan['updates'])
        or not all(native[k] for k in ('all_six_roles_verified',
            'all_non_role_or_declared_country_native_bytes_identical','all_other_game_files_identical',
            'recipe_only_selected_roles_declared_countries_fallback_receipts_and_source_artifact_changed'))
        or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('native/full SOURCE proof does not bind this final game')
    a=pipeline.read_json_file(base.inventory_path);b=pipeline.read_json_file(release.inventory_path)
    if {r['path']:r['sha256'] for r in a['files'] if r['path']!='DBDAT/JUG98030.FDI'}!={
            r['path']:r['sha256'] for r in b['files'] if r['path']!='DBDAT/JUG98030.FDI'}:
        raise ValueError('role/country repair changed another game file')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(right).entries}
    countries=source.compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    actual_role_changes=actual_country_changes=0
    for row in plan['updates']:
        payload=entries[row['carrier_id']].decode_payload(right)
        end,roles=read_indexed_native_roles(payload,row['carrier_id'])
        expected=row['fine_roles']+[98]*(6-len(row['fine_roles'])) if row['fine_roles'] is not None else row['before_native_roles']
        if roles!=expected:raise ValueError('independent final native roles differ')
        actual_role_changes+=roles!=row['before_native_roles']
        if row['nationality'] is not None:
            if payload[end+8]^0x61!=source.compiler._country_code(row['nationality'],dict(countries)):
                raise ValueError('independent final native country differs')
            actual_country_changes+=(payload[end+8]^0x61)!=row['before_native_country_code']
    for label,role,country in (('wright_phillips',11,'ENGLAND'),('kanchelskis',6,'RUSSIA')):
        visual=pipeline.read_json_file(root/(label+'-profile-visual-review.json'));check_visual(visual)
        if visual['observed_role_code']!=role or visual['observed_nationality']!=country:
            raise ValueError('actual inspected final role/country still incorrect')
    verify_profiles(root,season,RELEASE,[(9171,'wright_phillips','','Wright'),(2774,'kanchelskis','','Kanchelskis')])
    transport=pipeline.read_json_file(root/'startup-transport.json')
    directory=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(directory/'summary.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    frame=lineup_frame(directory)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
        or visual['screenshot_sha256']!=registry.sha256_file(frame)
        or visual['release_manifest_sha256']!=release.manifest_sha256
        or visual['observed_date']!='2000-08-01' or visual['observed_team']!='Stoke City'
        or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
        or summary['release_manifest_sha256']!=release.manifest_sha256
        or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']
        or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')):
        raise ValueError('final original startup not bound/successful')
    for s in registry.supported_seasons():
        current=registry.load_preferred_release(s)
        if (current.release_id,current.manifest_sha256)!=(original[s]['release_id'],original[s]['manifest_sha256']):
            raise ValueError('another preferred baseline moved before checkpoint')
    composed=dict(season=season,release_id=RELEASE,manifest_sha256=release.manifest_sha256,
        frozen_case_id=ownership['case_id'],ownership_parent_proof=binding(
            ROOT.parent/'cross-club-reserves-20261016-v2/independent-native-case-proof.json'),
        native_role_records_changed=actual_role_changes,native_country_records_changed=actual_country_changes,
        exact_composed_recipe_and_native_verified=True,full_SOURCE_game_and_recipe_verified=True,
        actual_final_startup_and_two_profiles_verified=True,
        conservative_central_fallbacks_not_historical_specialism_certification=True)
    retained(root/'composed-delivery-proof.json',composed)
    promoted=register_chain(season,[PARENT,RELEASE])
    retained(root/'promotion.json',promoted)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=directory))
    validation=registry.validate_preferred_release(season,level='playable')
    if not validation['valid']:raise ValueError('final default game failed playable validation')
    retained(root/'preferred-playable-validation.json',validation)
    if result['remaining_cross_club_cases']!=2809:raise ValueError('frozen cross-club counter changed')
    result['remaining_cross_club_cases']=2808
    result.setdefault('cross_club_dispositions',[]).append(dict(case_id=ownership['case_id'],
        season=season,state='confirmed-fault-repaired-current-game',delivery=binding(root/'composed-delivery-proof.json'),
        retained='Andrei Kanchelskis at Rangers',replacement='Shaun Wright-Phillips at Manchester City'))
    result['additional_confirmed_findings'].append(dict(id='first-donor-GK-role-safety-and-known-country',
        state='delivered-native-SOURCE-and-runner-verified',season=season,
        actual_native_role_changes=actual_role_changes,actual_native_country_changes=actual_country_changes,
        source_bound_cross_club_cases_closed=1,not_global_historical_position_approval=True))
    # Reconcile a stale status, using the already-delivered all26 v3 proof.
    ratings=[r for r in result['additional_confirmed_findings'] if r['id']=='all26-source-bound-native-rating-calibration-v3']
    if len(ratings)!=1 or ratings[0]['state']!='repaired-and-runtime-verified' or ratings[0]['seasons']!=26:
        raise ValueError('cannot reconcile ratings without existing all26 delivery')
    next(r for r in result['work_items'] if r['id']=='ratings')['state']='delivered-native-SOURCE-and-runner-verified'
    names=('role-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','composed-delivery-proof.json',
        'startup-transport.json','startup-visual-review.json','promotion.json','final-attestation.json',
        'preferred-playable-validation.json','wright_phillips-profile-visual-review.json',
        'wright_phillips-native-runtime-proof.json','kanchelskis-profile-visual-review.json','kanchelskis-native-runtime-proof.json')
    result['delivered_evidence'].extend(binding(root/n) for n in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous),
        current_release_bindings=bindings(),fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch='Deliver remaining25 narrowly selected inherited-GK role corrections; preserve all ratings and unrelated bytes. Cross-club2808 and other historical review queues remain open.')
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=binding(output),**composed,
        cross_club_review_groups_remaining=2808,unchanged_preferred_seasons=25))
    print(dict(checklist=binding(output),delivered=True,roles=actual_role_changes,countries=actual_country_changes),flush=True)


if __name__=='__main__':run()
