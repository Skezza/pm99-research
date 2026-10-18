"""Publish the remaining25 only after exact native/SOURCE/original-runner QA."""
import copy
from datetime import UTC, datetime
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_donor_keeper_role_delta_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.build_donor_role_safety_20261016 import ROOT, RELEASE
from scripts.capture_donor_role_safety_20261016 import tag
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify(season):
    root=ROOT/season
    baseline=next(r for r in pipeline.read_json_file(ROOT/'baseline.json') if r['season']==season)
    base=registry.load_registered_release(season,baseline['release_id'])
    release=registry.load_registered_release(season,RELEASE)
    plan=pipeline.read_json_file(root/'role-plan.json');source.verify(base,plan)
    native=pipeline.read_json_file(root/'native-byte-proof.json')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=release.manifest_sha256
        or native['plan_sha256']!=registry.sha256_file(root/'role-plan.json')
        or native['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
        or native['corrected_players']!=len(plan['updates'])
        or not all(native[k] for k in ('all_six_roles_verified','all_other_game_files_identical',
            'all_non_role_or_declared_country_native_bytes_identical',
            'recipe_only_selected_roles_declared_countries_fallback_receipts_and_source_artifact_changed'))
        or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('native/full SOURCE proofs do not bind the final role game')
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq):
        raise ValueError('fresh exact native application/idempotence differs')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(release.package_path):
        raise ValueError('whole recipe differs from declared delta')
    old={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    new={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    if any(old.get(k)!=new.get(k) for k in set(old)|set(new) if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('an unrelated game file changed')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(after).entries}
    roles_changed=countries_changed=0
    for row in plan['updates']:
        raw=entries[row['carrier_id']].decode_payload(after)
        end,roles=read_indexed_native_roles(raw,row['carrier_id'])
        expected=row['fine_roles']+[98]*(6-len(row['fine_roles'])) if row['fine_roles'] is not None else row['before_native_roles']
        if roles!=expected:raise ValueError('independent role readback differs')
        roles_changed+=roles!=row['before_native_roles']
        countries_changed+=(raw[end+8]^0x61)!=row['before_native_country_code']
    # Only the first2000/01 plan is authorised to change a country in this batch.
    if countries_changed or any(row['nationality'] is not None for row in plan['updates']):
        raise ValueError('remaining25 must not silently extend the known-nationality scope')
    transport=pipeline.read_json_file(root/'startup-transport.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    directory=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(directory/'summary.json')
    frame=lineup_frame(directory)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
        or directory!=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)
        or visual['screenshot_sha256']!=registry.sha256_file(frame)
        or visual['release_manifest_sha256']!=release.manifest_sha256
        or visual['observed_date']!=season[:4]+'-08-01' or visual['observed_team']!='Stoke City'
        or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
        or summary.get('process_exit_code') not in (None,0)
        or summary['release_manifest_sha256']!=release.manifest_sha256
        or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']
        or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')):
        raise ValueError('original actual startup does not prove the final game')
    return dict(season=season,release_id=RELEASE,manifest_sha256=release.manifest_sha256,
        native_role_changes=roles_changed,native_country_changes=countries_changed,
        all_unselected_native_and_game_bytes_preserved=True,complete_SOURCE_game_and_recipe_identical=True,
        startup_screenshot=visual['screenshot'],startup_screenshot_sha256=visual['screenshot_sha256'])


def run():
    prior=ROOT.parent/'release-delivery-checklist-v47.json'
    output=ROOT.parent/'release-delivery-checklist-v48.json'
    if output.exists():raise ValueError('completed donor-role batch checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    originals={r['season']:r for r in result['current_release_bindings']}
    seasons=[s for s in registry.supported_seasons() if s!='2000-01']
    if len(seasons)!=25:raise ValueError('remaining batch must be exact25')
    # No catalog writes until every candidate passed independently.
    rows=[verify(season) for season in seasons]
    first=pipeline.read_json_file(ROOT/'2000-01/final-delivery-summary.json')
    if first['native_role_records_changed']+sum(r['native_role_changes'] for r in rows)!=16252:
        raise ValueError('frozen narrow role denominator differs')
    for s in registry.supported_seasons():
        current=registry.load_preferred_release(s)
        if current.release_id==originals[s]['release_id']:
            if current.manifest_sha256!=originals[s]['manifest_sha256']:
                raise ValueError('original preferred manifest changed')
        elif s not in seasons or current.release_id!=RELEASE:
            raise ValueError('another worker moved a batch preferred baseline')
    evidence=[]
    for row in rows:
        season=row['season'];root=ROOT/season
        retained(root/'prepublication-proof.json',row)
        publisher.register_completed_delta(season,RELEASE)
        if not (root/'final-attestation.json').exists():
            retained(root/'final-attestation.json',runtime.attest(season=season,
                evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)))
        validation=registry.validate_preferred_release(season,level='playable')
        if not validation['valid']:raise ValueError('new default role game not playable')
        retained(root/'preferred-playable-validation.json',validation)
        evidence.extend(binding(root/name) for name in ('role-plan.json','native-byte-proof.json',
            'complete-SOURCE-replay.json','prepublication-proof.json','startup-transport.json',
            'startup-visual-review.json','final-attestation.json','preferred-playable-validation.json'))
    result['additional_confirmed_findings'].append(dict(id='remaining25-inherited-GK-role-safety',
        state='delivered-native-SOURCE-and-runner-verified',seasons=25,
        actual_native_role_changes=sum(r['native_role_changes'] for r in rows),
        actual_native_country_changes=0,cross_club_cases_closed=0,
        conservative_editorial_roles_not_historical_specialism_proof=True))
    result['delivered_evidence'].extend(evidence)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=bindings(),fresh_runtime_runs_this_checklist=seasons,all_required_work_complete=False,
        next_batch='All26 inherited goalkeeper-donor role fixes delivered. Continue dated ownership/opening-squad, broader historical position, manager and visual QA; frozen cross-club2808 unchanged by remaining25 role-only work.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'all26-final-delivery-summary.json',dict(checklist=binding(output),
        all26_native_role_changes=16252,all26_known_native_country_changes=1,
        actual_new_startups=26,remaining25=rows,first_season_delivery=binding(ROOT/'2000-01/final-delivery-summary.json'),
        cross_club_review_groups_remaining=2808,global_historical_RC=False))
    print(dict(checklist=binding(output),all26_native_role_changes=16252,delivered=True),flush=True)


if __name__=='__main__':run()
