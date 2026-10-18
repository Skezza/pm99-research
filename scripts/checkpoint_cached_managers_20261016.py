"""Publish source-replayed coach games only after the parent role rollout.

All25 candidates must pass before any catalogue update. Legacy2015 stays on
its exact parent and remains a separate source task, never an implicit waiver.
"""
import copy
from datetime import UTC,datetime
from app.fdi_indexed import IndexedFDIFile
from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.build_cached_manager_repairs_20261016 import ROOT,RELEASE,BASE
from scripts.capture_cached_manager_repairs_20261016 import tag
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def profile_name_changes(before,after):
    """Graph/display and surname fields are distinct on full ENT profiles."""
    return before.display_name!=after.display_name,before.surname!=after.surname


def check_progress_counts(native,canonical_updates,display_changes):
    if (native['canonical_manager_corrections']!=canonical_updates
        or native['native_manager_name_changes']!=display_changes):
        raise ValueError('manager progress counts differ from fresh actual readback')


def verify(season, *, evidence_root=None, release_id=None, source_module=None, run_tag=None, source_release_id=None):
    root=ROOT/season if evidence_root is None else evidence_root
    release_id=RELEASE if release_id is None else release_id
    source_module=source if source_module is None else source_module
    run_tag=tag(season) if run_tag is None else run_tag
    base=registry.load_registered_release(season,BASE if source_release_id is None else source_release_id)
    actual=registry.load_registered_release(season,release_id)
    plan=pipeline.read_json_file(root/'manager-plan.json')
    if any(r['first_fixture_date'][:4]!=season[:4] for r in plan['updates']):
        raise ValueError('manager source fixture is outside the actual requested game year')
    if source_module.prepare(base)!=plan:raise ValueError('current manager plan no longer independently reparses')
    native=pipeline.read_json_file(root/'native-byte-proof.json')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=actual.manifest_sha256
        or native['plan_sha256']!=registry.sha256_file(root/'manager-plan.json')
        or native['ENT_sha256']!=registry.sha256_file(actual.game_path/'DBDAT/ENT98030.FDI')
        or not all(native[k] for k in ('all_unselected_ENT_records_identical',
            'all_other_game_files_identical','complete_recipe_exact','original_source_reparsed'))
        or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('manager native/full SOURCE proof does not bind actual candidate')
    descriptor=pipeline.read_json_file(root/'inert.json')
    if publisher.updated_package(pipeline.read_json_file(base.package_path),descriptor,manager_plan=plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('entire actual manager recipe differs from declared delta')
    before=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    selected={r['carrier_id'] for r in plan['updates']}
    if len(selected)!=len(plan['updates']):raise ValueError('repeated manager native target')
    preserve_other_records(before,after,selected)
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(after).entries}
    holders,names=_manager_graph(eq_path=actual.game_path/'DBDAT/EQ98030.FDI',
        ent_path=actual.game_path/'DBDAT/ENT98030.FDI')
    actual_records_changed=visible_short_names_changed=native_display_names_changed=0
    for row in plan['updates']:
        carrier=row['carrier_id'];a=old[carrier];b=new[carrier]
        pa=parse_indexed_ent_manager_profile(before[a.payload_offset:a.payload_offset+a.payload_length],record_id=carrier)
        pb=parse_indexed_ent_manager_profile(after[b.payload_offset:b.payload_offset+b.payload_length],record_id=carrier)
        raw_a=a.decode_payload(before);raw_b=b.decode_payload(after)
        if ((pb.surname,pb.display_name)!=(row['native_after'],row['native_after'])
            or pa.display_name!=row['native_before']
            or pa.format!=pb.format or raw_a[2:7]!=raw_b[2:7]
            or (raw_a[pa.profile_text_offset:] if pa.profile_text_offset is not None else b'')!=
               (raw_b[pb.profile_text_offset:] if pb.profile_text_offset is not None else b'')
            or names[carrier]!=row['native_after']
            or [c['carrier_id'] for c in holders[carrier]]!=[row['club_carrier_id']]):
            raise ValueError('selected actual coach name/owner/opaque profile preservation failed')
        actual_records_changed+=raw_a!=raw_b
        display_changed,surname_changed=profile_name_changes(pa,pb)
        native_display_names_changed+=display_changed
        visible_short_names_changed+=surname_changed
    check_progress_counts(native,len(plan['updates']),native_display_names_changed)
    old_files={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    new_files={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if any(old_files.get(k)!=new_files.get(k) for k in set(old_files)|set(new_files) if k!='DBDAT/ENT98030.FDI'):
        raise ValueError('manager candidate changed another game file')
    pipeline.assert_tree_matches_inventory(actual.game_path,pipeline.read_json_file(actual.inventory_path))
    transport=pipeline.read_json_file(root/'startup-transport.json')
    review=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(review)
    directory=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(directory/'summary.json')
    frame=lineup_frame(directory)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
        or directory!=registry.ROOT/'.local/runlogs/pm99_runner'/run_tag
        or review['screenshot_sha256']!=registry.sha256_file(frame)
        or review['release_manifest_sha256']!=actual.manifest_sha256
        or review['observed_date']!=season[:4]+'-08-01' or review['observed_team']!='Stoke City'
        or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
        or summary.get('process_exit_code') not in (None,0)
        or summary['release_manifest_sha256']!=actual.manifest_sha256
        or summary['output_inventory_fingerprint']!=actual.locator['game_inventory_fingerprint']
        or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')):
        raise ValueError('final original manager-game startup not approved/bound')
    return dict(season=season,release_id=release_id,manifest_sha256=actual.manifest_sha256,
        canonical_manager_updates=len(plan['updates']),actual_ENT_records_changed=actual_records_changed,
        actual_visible_short_names_changed=visible_short_names_changed,
        actual_native_display_names_changed=native_display_names_changed,
        source_plan=binding(root/'manager-plan.json'),startup_screenshot=review['screenshot'],
        startup_screenshot_sha256=review['screenshot_sha256'],
        all_player_ratings_tactics_ownership_and_artwork_preserved=True,
        all_unselected_ENT_records_and_selected_opaque_profile_bytes_identical=True,
        complete_SOURCE_game_and_recipe_identical=True,
        not_a_visual_inspection_of_every_coach_menu=True)


def run():
    prior=ROOT.parent/'release-delivery-checklist-v48.json'
    output=ROOT.parent/'release-delivery-checklist-v49.json'
    if output.exists():raise ValueError('completed manager checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    originals={r['season']:r for r in result['current_release_bindings']}
    seasons=[s for s in registry.supported_seasons() if s!='2015-16']
    if len(seasons)!=25:raise ValueError('manager publication must remain exact25 plus separate legacy2015')
    rows=[verify(s) for s in seasons]
    if sum(r['canonical_manager_updates'] for r in rows)!=495:
        raise ValueError('frozen495 source-qualified manager proposals changed')
    for s in registry.supported_seasons():
        current=registry.load_preferred_release(s)
        expected=originals[s]
        if current.release_id==expected['release_id']:
            if current.manifest_sha256!=expected['manifest_sha256']:
                raise ValueError('parent preferred manifest changed')
        elif s not in seasons or current.release_id!=RELEASE:
            raise ValueError('unexpected preferred transition during manager batch')
    evidence=[]
    for row in rows:
        season=row['season'];root=ROOT/season
        retained(root/'prepublication-proof.json',row)
        publisher.register_completed_delta(season,RELEASE)
        if not (root/'final-attestation.json').exists():
            retained(root/'final-attestation.json',runtime.attest(season=season,
                evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)))
        validation=registry.validate_preferred_release(season,level='playable')
        if not validation['valid']:raise ValueError('manager default failed playable validation')
        retained(root/'preferred-playable-validation.json',validation)
        evidence.extend(binding(root/name) for name in ('manager-plan.json','native-byte-proof.json',
            'complete-SOURCE-replay.json','prepublication-proof.json','startup-transport.json',
            'startup-visual-review.json','final-attestation.json','preferred-playable-validation.json'))
    result['additional_confirmed_findings'].append(dict(id='cached-original-target-season-manager-corrections',
        state='delivered-native-SOURCE-and-runner-verified',seasons=25,canonical_updates=495,
        actual_ENT_records_changed=sum(r['actual_ENT_records_changed'] for r in rows),
        actual_visible_short_names_changed=sum(r['actual_visible_short_names_changed'] for r in rows),
        legacy2015_separate_source_review_remaining=True,global_manager_approval=False,
        cross_club_cases_closed=0,all_player_ratings_tactics_ownership_and_artwork_preserved=True))
    result['delivered_evidence'].extend(evidence)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=bindings(),
        fresh_runtime_runs_this_checklist=seasons,all_required_work_complete=False,
        next_batch='Known source-qualified coach corrections delivered across25; legacy2015 and288 source/identity/display ambiguities remain. Continue Arsenal2021 coupled ownership/opening-squad and broader checklist; frozen cross-club2808 unchanged by manager work.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(checklist=binding(output),seasons=25,canonical_updates=495,
        actual_ENT_records_changed=sum(r['actual_ENT_records_changed'] for r in rows),
        actual_visible_short_names_changed=sum(r['actual_visible_short_names_changed'] for r in rows),
        legacy2015_preferred_unchanged=True,season_evidence=rows,global_historical_RC=False))
    print(dict(checklist=binding(output),canonical_manager_updates=495,delivered=True),flush=True)


if __name__=='__main__':run()
