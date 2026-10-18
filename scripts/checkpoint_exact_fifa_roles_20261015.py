"""Promote only the nine SOURCE/native/original-runner-verified role deltas."""
import copy
import re
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_exact_fifa_role_delta_v2 as source
from scripts import publish_historical_role_delta_v1 as publisher, attest_registered_season_runtime_v1 as runtime
from scripts.advance_exact_fifa_roles_20261015 import ROOT, SEASONS, RELEASE, PROFILES, tag
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles


def run():
    prior=ROOT.parent/'release-delivery-checklist-v44.json'
    output=ROOT.parent/'release-delivery-checklist-v45.json'
    if output.exists():raise ValueError('completed role checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    baseline={r['season']:r for r in pipeline.read_json_file(ROOT/'baseline.json')}
    original={r['season']:r for r in result['current_release_bindings']}
    if set(baseline)!=set(SEASONS) or len(SEASONS)!=9:raise ValueError('role scope must remain exact nine seasons')
    for season in registry.supported_seasons():
        actual=registry.load_preferred_release(season)
        if season in baseline:
            if actual.release_id not in (baseline[season]['release_id'],RELEASE):
                raise ValueError('another worker moved role baseline')
        elif actual.release_id!=original[season]['release_id'] or actual.manifest_sha256!=original[season]['manifest_sha256']:
            raise ValueError('an unaffected preferred season changed')
    evidence=[];rows=[];declarations=0;native_changes=0;protected=0
    for season in SEASONS:
        root=ROOT/season;base=registry.load_registered_release(season,baseline[season]['release_id'])
        release=registry.load_registered_release(season,RELEASE)
        plan=pipeline.read_json_file(root/'role-plan.json');source.verify(base,plan)
        native=pipeline.read_json_file(root/'native-byte-proof.json')
        replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
        if (native['manifest_sha256']!=release.manifest_sha256 or native['plan_sha256']!=registry.sha256_file(root/'role-plan.json')
            or native['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
            or native['corrected_players']!=len(plan['updates'])
            or not all(native[k] for k in ('all_six_roles_verified','all_non_role_native_bytes_identical','all_other_game_files_identical','recipe_only_fine_roles_and_source_artifact_changed'))
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
            raise ValueError('role byte/SOURCE proof not exact')
        raw=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        indexed={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
        for update in plan['updates']:
            native_roles=read_indexed_native_roles(indexed[update['carrier_id']].decode_payload(raw),update['carrier_id'])[1]
            expected=update['fine_roles']+[98]*(6-len(update['fine_roles']))
            if native_roles!=expected:raise ValueError('fresh actual six-role readback differs')
            if (5 in update['before_native_roles'] and 4 not in update['before_native_roles']
                    and 'CB' in {p.strip() for p in update['source']['player_positions'].split(',')}
                    and 4 in update['fine_roles']):raise ValueError('right-only centre-back side was discarded')
            native_changes+=native_roles!=update['before_native_roles']
        transport=pipeline.read_json_file(root/'startup-transport.json')
        visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
        directory=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(directory/'summary.json')
        frame=lineup_frame(directory)
        if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/tag(season))
            or visual['screenshot']!=registry.relative_workspace_path(frame) or visual['screenshot_sha256']!=registry.sha256_file(frame)
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('process_exit_code') not in (None,0)
            or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')
            or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):
            raise ValueError('role startup is not the exact successful game/club/date/frame')
        declarations+=len(plan['updates']);protected+=plan['native_CB_side_preferences_preserved']
        broader=pipeline.read_json_file(root/'broader-position-review-candidates.json')
        if (broader['baseline']!=base.release_id or broader['package_sha256']!=registry.sha256_file(base.package_path)
                or broader['count']!=plan['skipped'].get('primary-class-needs-separate-source-review',0)
                or broader['count']!=len(broader['players']) or broader['native_writes']!=0):
            raise ValueError('separate broad-position review queue differs from pinned inputs')
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
        evidence.extend(binding(root/name) for name in ('role-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
            'owned-identical-content-sharing.json','broader-position-review-candidates.json',
            'startup-transport.json','startup-visual-review.json'))
        rows.append(dict(season=season,release_id=RELEASE,manifest_sha256=release.manifest_sha256,
            declarations=len(plan['updates']),startup_screenshot=visual['screenshot']))
    for season,carrier,label,token in PROFILES:
        root=ROOT/season
        verify_profiles(root,season,RELEASE,[(carrier,label,'',token)])
        visual=pipeline.read_json_file(root/(label+'-profile-visual-review.json'))
        release=registry.load_registered_release(season,RELEASE)
        package=pipeline.read_json_file(release.package_path)
        person=next(p for p in package['players'] if p['carrier_id']==carrier)
        expected=person['facts']['fine_roles'][0]
        clean=lambda s:re.sub('[^A-Z]','',s.upper())
        if visual['observed_role_code']!=expected or clean(visual['observed_role_label'])!=clean(source.prior.roster.ROLE_LABELS[expected]):
            raise ValueError('original actual player role label not visually approved')
        evidence.extend(binding(root/(label+suffix)) for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    for season in SEASONS:
        publisher.register_completed_delta(season,RELEASE)
        retained(ROOT/season/'final-attestation.json',runtime.attest(season=season,
            evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)))
        validation=registry.validate_preferred_release(season,level='release')
        if not validation['valid']:raise ValueError('new default role game failed validation')
        retained(ROOT/season/'preferred-release-validation.json',validation)
        evidence.extend(binding(ROOT/season/name) for name in ('final-attestation.json','preferred-release-validation.json'))
    result['additional_confirmed_findings'].append(dict(id='nine-exact-target-FIFA-role-deltas-v2',
        state='delivered-native-SOURCE-and-runner-verified',seasons=9,role_declarations_updated=declarations,
        actual_native_records_changed=native_changes,right_only_CB_mappings_protected=protected,
        skills_ownership_tactics_managers_assets_preserved=True,cross_club_cases_closed=0,
        not_global_historical_position_or_opening_squad_approval=True))
    result['delivered_evidence'].extend(evidence)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=bindings(),
        fresh_runtime_runs_this_checklist=list(SEASONS),all_required_work_complete=False,
        next_batch='Nine exact-edition fine-role deltas delivered without changing ratings/tactics/ownership. Continue dated cross-club/whole-club and broad-position reviews; no duplicate candidate is cleared by a fine-role change.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(checklist=binding(output),seasons_changed=9,
        unaffected_seasons=17,role_declarations_updated=declarations,actual_native_records_changed=native_changes,
        right_only_CB_mappings_protected=protected,original_startups_verified=9,ten_skill_role_profiles_verified=len(PROFILES),
        calibrated_ratings_and_tactics_preserved=True,cross_club_candidates_closed=0,season_evidence=rows))
    print(dict(checklist=binding(output),seasons=9,role_declarations=declarations,native_changes=native_changes),flush=True)


if __name__=='__main__':run()
