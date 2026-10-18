"""Promote exactly13 shirt bytes after fresh ordinary and Arsenal screenshots."""
import copy
from datetime import UTC,datetime
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_source_bound_shirt_numbers_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_arsenal_shirt_numbers_20261016 import ROOT,SEASON,BASE,RELEASE
from scripts.capture_arsenal_shirt_numbers_20261016 import TAG
from scripts.build_arsenal_owned_opening_20261016 import ROOT as PARENT_ROOT
from scripts.capture_arsenal_owned_opening_20261016 import PROFILES
from scripts.review_rating_frames_20261011 import lineup_frame


def inherit_profile_and_tactics_proofs(base,release):
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    current=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(current).entries}
    left=pipeline.read_json_file(base.package_path);right=pipeline.read_json_file(release.package_path)
    a=next(c for c in left['clubs'] if c['carrier_id']==309)
    b=next(c for c in right['clubs'] if c['carrier_id']==309)
    if a!=b or (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()!=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes():
        raise ValueError('shirt delta changed the proven roster/phase coordinate inputs')
    records=[]
    for carrier,label,_ in PROFILES:
        if old[carrier].decode_payload(original)!=new[carrier].decode_payload(current):
            raise ValueError('cannot inherit a changed native profile')
        review=pipeline.read_json_file(PARENT_ROOT/(label+'-profile-visual-review.json'));check_visual(review)
        proof=pipeline.read_json_file(PARENT_ROOT/(label+'-native-runtime-proof.json'))
        if (proof['screenshot_sha256']!=review['screenshot_sha256'] or not proof['native_inputs_hash_verified']
            or not proof['ten_visible_skills_verified'] or not proof['kit_pixels']['passed']
            or proof['compiler_receipt_sha256']!=registry.sha256_file(base.compiler_receipt_path)):
            raise ValueError('parent original profile evidence incomplete')
        records.append(dict(carrier_id=carrier,unchanged_native_record_sha256=source.digest(new[carrier].decode_payload(current)),
            original_visual_review=binding(PARENT_ROOT/(label+'-profile-visual-review.json')),
            original_runtime_proof=binding(PARENT_ROOT/(label+'-native-runtime-proof.json'))))
    for name in ('ENT98030.FDI','MINIFOTO.PKF','RIDIESC.PKF','MINIESC.PKF','NANOESC.PKF'):
        if registry.sha256_file(base.game_path/'DBDAT'/name)!=registry.sha256_file(release.game_path/'DBDAT'/name):
            raise ValueError('shirt delta changed profile/asset inputs')
    phase=pipeline.read_json_file(PARENT_ROOT/'actual-Arsenal-tactics-runtime-proof.json')
    if not phase['success'] or phase['exact_game_EQ_sha256']!=registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'):
        raise ValueError('parent complete phase proof cannot be inherited')
    # Exact13-header-byte proof below guarantees every role/order/name and
    # offset remains identical, not merely these five representative records.
    result=dict(method='parent-runner-proof-plus-identical-native-profile-and-asset-inputs',
        parent_release_id=BASE,child_release_id=RELEASE,profiles=records,
        not_new_child_profile_captures=True,parent_all880_phase_values_proof=binding(PARENT_ROOT/'actual-Arsenal-tactics-runtime-proof.json'),
        phase_coordinates_and_all_player_startup_controls_unchanged=True)
    retained(ROOT/'inherited-profile-and-phase-proof.json',result)
    return result


def run():
    prior=ROOT.parent/'release-delivery-checklist-v50.json';output=ROOT.parent/'release-delivery-checklist-v51.json'
    if output.exists():raise ValueError('completed shirt publication must not repeat')
    previous=pipeline.read_json_file(prior);result=copy.deepcopy(previous)
    base=registry.load_registered_release(SEASON,BASE);release=registry.load_registered_release(SEASON,RELEASE)
    plan=pipeline.read_json_file(ROOT/'shirt-number-plan.json');source.verify(base,plan)
    native=pipeline.read_json_file(ROOT/'native-byte-proof.json');replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=release.manifest_sha256 or native['native_shirt_bytes_changed']!=13
        or len(native['exact_authorized_byte_offsets'])!=13 or native['recipe_shirt_facts']!=25
        or native['plan_sha256']!=registry.sha256_file(ROOT/'shirt-number-plan.json')
        or not all(native[k] for k in ('all_other_player_bytes_identical','all_other_game_files_identical',
            'identities_DOBs_skills_roles_order_tactics_managers_kits_portraits_preserved',
            'all_Arsenal_numbers_source_bound_and_unique','complete_recipe_exact','idempotent'))
        or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('actual shirt native/full SOURCE proof incomplete')
    actual=pipeline.read_json_file(release.package_path)
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=actual:raise ValueError('actual shirt recipe changed')
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(original,eq,plan)!=((release.game_path/'DBDAT/JUG98030.FDI').read_bytes(),eq):
        raise ValueError('actual thirteen-byte native readback differs')
    expected={str(row['carrier_id']):row['number'] for row in plan['updates']}
    players_by_id={p['id']:p for p in actual['players']}
    arsenal=next(c for c in actual['clubs'] if c['carrier_id']==309)
    expected_visible=[players_by_id[pid]['carrier_id'] for pid in arsenal['roster_player_ids'][:20]]
    for target,team in (('stoke','Stoke City'),('Arsenal','Arsenal')):
        review=pipeline.read_json_file(ROOT/(target+'-startup-visual-review.json'));check_visual(review)
        receipt=pipeline.read_json_file(ROOT/(target+'-startup-transport.json'))
        run=registry.ROOT/'.local/runlogs/pm99_runner'/(TAG+'_'+target.lower())
        summary=pipeline.read_json_file(run/'summary.json')
        if (review['observed_team']!=team or review['observed_date']!='2021-08-01'
            or review['release_manifest_sha256']!=release.manifest_sha256 or receipt['exit_code']!=0
            or receipt['release_manifest_sha256']!=release.manifest_sha256
            or receipt['evidence']!=registry.relative_workspace_path(run)
            or review['screenshot']!=registry.relative_workspace_path(lineup_frame(run))
            or summary.get('success') is not True or summary.get('crash_detected')
            or summary.get('release_manifest_sha256')!=release.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=release.locator['game_inventory_fingerprint']
            or not summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{}).get('matched')):
            raise ValueError('fresh child exact game/club startup not proved')
        if target=='Arsenal':
            observed=review['observed_visible_numbers']
            if ([r['carrier_id'] for r in observed]!=expected_visible
                or len(set(expected_visible))!=20
                or any(expected.get(str(r['carrier_id']))!=r['number'] for r in observed)):
                raise ValueError('twenty genuinely visible sourced shirt numbers not reviewed')
    inherit_profile_and_tactics_proofs(base,release)
    old={r['season']:r for r in previous['current_release_bindings']}
    def current_bindings():
        current=bindings()
        for row in current:
            if row['season']!=SEASON and row!=old[row['season']]:raise ValueError('another season changed during shirt delta')
            if row['season']==SEASON:
                if row['release_id']==BASE and row!=old[SEASON]:raise ValueError('shirt parent binding changed')
                if row['release_id'] not in (BASE,RELEASE):raise ValueError('shirt baseline superseded')
                if row['release_id']==RELEASE and row['manifest_sha256']!=release.manifest_sha256:raise ValueError('shirt candidate manifest differs')
        return current
    current_bindings()
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.register_completed_delta(SEASON,RELEASE)
    if not (ROOT/'final-attestation.json').exists():retained(ROOT/'final-attestation.json',runtime.attest(season=SEASON,
        evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/(TAG+'_stoke')))
    validation=registry.validate_preferred_release(SEASON,level='playable')
    if not validation['valid']:raise ValueError('shirt child failed playable validation')
    retained(ROOT/'preferred-playable-validation.json',validation)
    issue=next(r for r in result['additional_confirmed_findings'] if r['id']=='Arsenal2021-source-backed-shirt-number-conflicts')
    if issue['state']!='confirmed-native-defect-repair-pending' or issue['native_shirt_numbers_to_correct']!=13:
        raise ValueError('shirt issue counter cannot be reset/reclosed')
    issue.update(state='delivered-native-SOURCE-and-runner-verified',delivery=binding(ROOT/'native-byte-proof.json'),
        changed_native_bytes=13,explicit_recipe_numbers=25,original_visible_numbers_reviewed=20)
    names=['shirt-number-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'stoke-startup-transport.json','stoke-startup-visual-review.json','Arsenal-startup-transport.json',
        'Arsenal-startup-visual-review.json','inherited-profile-and-phase-proof.json',
        'final-attestation.json','preferred-playable-validation.json']
    result['delivered_evidence'].extend(binding(ROOT/name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=current_bindings(),
        fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Arsenal source25/eleven duplicate closures/13 shirt-byte fixes delivered. Continue2797 frozen cross-club candidates, broader opening/positions, deferred and legacy2015 managers, and kit/portrait/facts QA. Genoa orange-kit design candidate still needs source comparison.')
    retained(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(checklist=binding(output),changed_native_bytes=13,
        recipe_numbers=25,original_visible_numbers=20,other25_preferred_unchanged=True,
        all_other_game_files_and_player_bytes_unchanged=True,remaining_cross_club_cases_unchanged=2797,
        global_historical_RC=False))
    print(dict(checklist=binding(output),thirteen_shirt_bytes_delivered=True,other25_unchanged=True),flush=True)


if __name__=='__main__':run()
