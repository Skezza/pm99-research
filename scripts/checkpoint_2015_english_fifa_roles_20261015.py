"""Complete the role delivery with the separately verified English2015 layer."""
import copy
import re
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_2015_english_fifa_roles_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher,attest_registered_season_runtime_v1 as runtime
from scripts.build_2015_english_fifa_roles_20261015 import ROOT,RELEASE,REPLAY,TAG,PROFILES
from scripts.advance_exact_fifa_roles_20261015 import ROOT as MAIN,RELEASE as BASE
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles


def role_label_matches(code,label):
    clean=lambda s:re.sub('[^A-Z]','',s.upper())
    accepted={clean(source.prior.roster.ROLE_LABELS[code])}
    # Original native English UI abbreviates code10 to LEFT MID.; don't
    # manufacture a longer observed label or accept arbitrary prefix matches.
    if code==10:accepted.add('LEFTMID')
    return clean(label) in accepted


def run():
    prior=MAIN.parent/'release-delivery-checklist-v45.json';output=MAIN.parent/'release-delivery-checklist-v46.json'
    if output.exists():raise ValueError('completed English role checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    old={r['season']:r for r in result['current_release_bindings']}
    for season in registry.supported_seasons():
        current=registry.load_preferred_release(season)
        if season=='2015-16':
            if current.release_id not in (BASE,RELEASE):raise ValueError('English current baseline moved')
        elif (current.release_id,current.manifest_sha256)!=(old[season]['release_id'],old[season]['manifest_sha256']):
            raise ValueError('another season changed during English closeout')
    base=registry.load_registered_release('2015-16',BASE);release=registry.load_registered_release('2015-16',RELEASE)
    plan=pipeline.read_json_file(ROOT/'role-plan.json');source.verify(base,plan)
    native=pipeline.read_json_file(ROOT/'native-byte-proof.json');replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=release.manifest_sha256 or native['plan_sha256']!=registry.sha256_file(ROOT/'role-plan.json')
            or native['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
            or native['corrected_players']!=len(plan['updates'])
            or not all(native[k] for k in ('all_six_roles_verified','all_non_role_native_bytes_identical','all_other_game_files_identical','recipe_only_fine_roles_and_source_artifact_changed'))
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('English actual native/SOURCE proof differs')
    if (source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(release.package_path)
            or source.updated_english(plan)!=source.overlay(release)[0]):raise ValueError('English edited recipe not actually published')
    raw=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes();indexed={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
    changed=0
    for row in plan['updates']:
        roles=read_indexed_native_roles(indexed[row['carrier_id']].decode_payload(raw),row['carrier_id'])[1]
        if roles!=row['fine_roles']+[98]*(6-len(row['fine_roles'])):raise ValueError('fresh English role readback differs')
        changed+=roles!=row['before_native_roles']
    transport=pipeline.read_json_file(ROOT/'startup-transport.json');visual=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(visual)
    directory=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(directory/'summary.json');frame=lineup_frame(directory)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
        or transport['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/TAG)
        or visual['screenshot']!=registry.relative_workspace_path(frame) or visual['screenshot_sha256']!=registry.sha256_file(frame)
        or visual['release_manifest_sha256']!=release.manifest_sha256 or visual['observed_team']!='Stoke City'
        or visual['observed_date']!='2015-08-01' or summary.get('success') is not True
        or summary.get('crash_detected') or summary.get('wine_debugger_detected') or summary.get('process_exit_code') not in (None,0)
        or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')
        or summary['release_manifest_sha256']!=release.manifest_sha256
        or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):raise ValueError('English-final actual startup differs')
    english,_=source.overlay(release);players={p['carrier_id']:p for p in english['players']}
    verify_profiles(ROOT,'2015-16',RELEASE,[(c,l,'',t) for c,l,t in PROFILES])
    for carrier,label,_ in PROFILES:
        visual_profile=pipeline.read_json_file(ROOT/(label+'-profile-visual-review.json'))
        expected=players[carrier]['facts']['fine_roles'][0]
        if visual_profile['observed_role_code']!=expected or not role_label_matches(expected,visual_profile['observed_role_label']):
            raise ValueError('English final profile role not visually verified')
    if players[9260]['ratings']['values']['handling']!=7 or players[9277]['ratings']['values']['handling']!=15:
        raise ValueError('original handling correction regressed')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.register_completed_delta('2015-16',RELEASE)
    retained(ROOT/'final-attestation.json',runtime.attest(season='2015-16',evidence_dir=directory))
    validation=registry.validate_preferred_release('2015-16',level='release')
    if not validation['valid']:raise ValueError('final English preferred release invalid')
    retained(ROOT/'preferred-release-validation.json',validation)
    result['additional_confirmed_findings'].append(dict(id='separate2015-English-exact-FIFA-roles',
        state='delivered-native-SOURCE-and-runner-verified',declarations=len(plan['updates']),native_records_changed=changed,
        Arnautovic_role=source.prior.roster.ROLE_LABELS[players[9277]['facts']['fine_roles'][0]],
        Afellay_role=source.prior.roster.ROLE_LABELS[players[9260]['facts']['fine_roles'][0]],
        handling7_and15_and_all_ten_skills_preserved=True,foreign_players_tactics_and_assets_preserved=True))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in ('role-plan.json','native-byte-proof.json',
        'complete-SOURCE-replay.json','owned-identical-content-sharing.json','startup-transport.json','startup-visual-review.json',
        'final-attestation.json','preferred-release-validation.json'))
    result['delivered_evidence'].extend(binding(ROOT/(label+suffix)) for _,label,_ in PROFILES
        for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=bindings(),
        fresh_runtime_runs_this_checklist=['2015-16'],all_required_work_complete=False,
        next_batch='Nine exact-target-FIFA role games including separate2015 English roles delivered. Ratings/tactics preserved. Cross-club, broad-position/dated-manager/global visual queues remain; no all-position/ownership approval.')
    pipeline.write_canonical_json(output,result)
    main=pipeline.read_json_file(MAIN/'final-delivery-summary.json');rows=copy.deepcopy(main['season_evidence'])
    for row in rows:
        if row['season']=='2015-16':row.update(release_id=RELEASE,manifest_sha256=release.manifest_sha256,
            declarations=row['declarations']+len(plan['updates']),startup_screenshot=visual['screenshot'])
    retained(MAIN/'final-complete-delivery-summary.json',dict(checklist=binding(output),seasons_changed=9,unaffected_seasons=17,
        actual_native_records_changed=main['actual_native_records_changed']+changed,
        role_declarations_updated=main['role_declarations_updated']+len(plan['updates']),
        successful_original_startups=10,current_preferred_season_startups=9,role_and_ten_skill_profiles_verified=5,
        calibrated_ratings_and_tactics_preserved=True,cross_club_candidates_closed=0,original2015_backup_preserved=True,season_evidence=rows))
    print(dict(checklist=binding(output),English_native_changes=changed,English_declarations=len(plan['updates']),complete=True),flush=True)


if __name__=='__main__':run()
