"""Promote only the proved Eastleigh game, never source preparation alone."""
import copy
from datetime import UTC,datetime
from pathlib import Path
import tempfile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_paired_whole_club_reconstruction_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.publish_eastleigh_private_20261017 import ROOT,RELEASE,REPLAY,SEASON
from scripts.capture_eastleigh_runtime_20261017 import FOLDER,TAG,PROFILES


def validate_case_count(previous,cases,manifest_sha):
    closed={r['case_id'] for r in previous['cross_club_dispositions']}
    rows=cases['dispositions'];ids={r['case_id'] for r in rows}
    if (previous['remaining_cross_club_cases']!=2797 or len(rows)!=1 or len(ids)!=1
            or ids&closed or cases['confirmed_frozen_cases_repaired']!=1
            or cases['manifest_sha256']!=manifest_sha or rows[0]['source_person_id']!=223790
            or rows[0]['retained_native_carrier']!=9574 or rows[0]['replaced_native_carrier']!=11157
            or not cases['Tom_Aldred_other_two_club_copies_still_open']):
        raise ValueError('exact frozen one-case count/owner proof changed or already counted')


def check_bindings(previous,release):
    expected={r['season']:r for r in previous['current_release_bindings']}
    current=bindings()
    if set(expected)!=set(registry.supported_seasons()) or {r['season'] for r in current}!=set(expected):
        raise ValueError('all26 bindings required before publication')
    for row in current:
        old=expected[row['season']]
        if row['season']!=SEASON:
            if row!=old:raise ValueError('another season changed; preserve intervening repairs')
        elif row['release_id']==old['release_id']:
            if row!=old:raise ValueError('current parent game binding changed')
        elif (row['release_id'],row['manifest_sha256'])!=(RELEASE,release.manifest_sha256):
            raise ValueError('unexpected new current game')


def validate_native_readback(actual,saved):
    # JSON serialises native XI tuples as arrays. Compare canonical documents,
    # not Python container types; every actual value still has to be identical.
    if pipeline.canonical_json_bytes(actual)!=pipeline.canonical_json_bytes(saved) or len(actual['players'])!=17:
        raise ValueError('fresh independent native readback differs')


def run():
    output=ROOT/'release-delivery-checklist-v57.json'
    if output.exists():raise ValueError('completed publication must not repeat')
    previous=pipeline.read_json_file(ROOT/'release-delivery-checklist-v56.json')
    release=registry.load_registered_release(SEASON,RELEASE)
    reconstructed=registry.load_registered_release(SEASON,REPLAY)
    source.bound_receipt(release)
    replay=pipeline.read_json_file(FOLDER/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('whole source proof incomplete')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    pipeline.assert_tree_matches_inventory(reconstructed.game_path,pipeline.read_json_file(release.inventory_path))
    if release.package_path.read_bytes()!=reconstructed.package_path.read_bytes():raise ValueError('SOURCE whole recipe differs')
    # Re-read actual native facts rather than merely trusting earlier booleans.
    with tempfile.TemporaryDirectory(prefix='pm99-eastleigh-readback-') as folder:
        actual=readback.verify(ROOT/'Eastleigh2014-complete-v1',Path(folder)/'proof.json')
    validate_native_readback(actual,pipeline.read_json_file(ROOT/'Eastleigh2014-native-readback.json'))
    identity=pipeline.read_json_file(ROOT/'Eastleigh2014-identity-readback.json')
    if (identity['candidate_receipt_sha256']!=registry.sha256_file(ROOT/'Eastleigh2014-complete-v1/candidate-receipt.json')
            or identity['package_sha256']!=registry.sha256_file(release.package_path)
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared'] or not identity['unselected_recipe_players_identical']):
        raise ValueError('final game identity/preservation proof differs')
    visual=pipeline.read_json_file(FOLDER/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(FOLDER/'startup-transport.json')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    summary=pipeline.read_json_file(evidence/'summary.json')
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!='2014-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):
        raise ValueError('ordinary original startup proof incomplete')
    verify_profiles(FOLDER,SEASON,RELEASE,[(c,l,'',t) for c,l,t in PROFILES])
    for carrier,label,_ in PROFILES:
        proof=pipeline.read_json_file(FOLDER/(label+'-native-runtime-proof.json'))
        reviewed=pipeline.read_json_file(FOLDER/(label+'-profile-visual-review.json'));check_visual(reviewed)
        profile_transport=pipeline.read_json_file(FOLDER/(label+'-profile-transport.json'))
        if (proof['carrier_id']!=carrier or proof['club']!='Eastleigh' or not proof['kit_pixels']['passed']
                or proof['release_id']!=RELEASE or proof['season']!=SEASON
                or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
                or proof['visual_review_sha256']!=registry.sha256_file(FOLDER/(label+'-profile-visual-review.json'))
                or proof['screenshot_sha256']!=reviewed['screenshot_sha256']
                or not proof['native_inputs_hash_verified'] or not proof['ten_visible_skills_verified']
                or profile_transport['exit_code']!=0 or profile_transport['release_manifest_sha256']!=release.manifest_sha256):
            raise ValueError('actual target actor/kit proof incomplete')
    cases=pipeline.read_json_file(FOLDER/'independent-frozen-case-proof.json')
    validate_case_count(previous,cases,release.manifest_sha256)
    check_bindings(previous,release);backup=verify_original2015()
    publisher.register_completed_delta(SEASON,RELEASE)
    retained(FOLDER/'final-attestation.json',runtime.attest(season=SEASON,evidence_dir=evidence))
    valid=registry.validate_preferred_release(SEASON,level='playable')
    if not valid['valid']:raise ValueError('promoted game is not playable')
    retained(FOLDER/'preferred-playable-validation.json',valid)
    check_bindings(previous,release)
    result=copy.deepcopy(previous)
    result['cross_club_dispositions'].extend(dict(r,delivery=binding(FOLDER/'independent-frozen-case-proof.json')) for r in cases['dispositions'])
    result['remaining_cross_club_cases']=2796
    result['additional_confirmed_findings'].append(dict(id='Eastleigh2014-complete-original-opening',season=SEASON,
        state='delivered-native-SOURCE-and-runner-verified',corrected_slots=17,original_XI=11,published_bench=5,
        positive_dated_reserves=1,dated_manager='Richard Hill',ground='Silverlake Stadium',
        additional_frozen_cases_closed=1,Tom_Aldred_remaining_pair_open=True,
        kit_exact_sponsor_piping_and_shorts_not_certified=True,mode1_tactical_deployment_not_historically_certified=True,
        Noice_birthday_single_original_secondary_not_consensus=True))
    names=['private-registration.json','complete-SOURCE-replay.json','independent-frozen-case-proof.json',
        'startup-transport.json','startup-visual-review.json','final-attestation.json','preferred-playable-validation.json']
    names += [label+suffix for _,label,_ in PROFILES for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup,binding(ROOT/'Eastleigh2014-native-readback.json'),binding(ROOT/'Eastleigh2014-identity-readback.json')]
    result['delivered_evidence'] += [binding(FOLDER/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(ROOT/'release-delivery-checklist-v56.json'),
        current_release_bindings=bindings(),fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Continue frozen2796 cross-club/opening-squad cases; Aldred remaining two-club pair not closed. Broader managers, roles, facts and global present-image/kit QA remain open.')
    pipeline.write_canonical_json(output,result)
    retained(FOLDER/'final-delivery-summary.json',dict(utc=datetime.now(UTC).isoformat(),checklist=binding(output),
        corrected_slots=17,frozen_cross_club_cases_closed=1,remaining_cross_club_cases=2796,
        all_other25_preferred_bindings_unchanged=True,original2015_backup_verified=True,global_historical_RC=False))
    print(dict(delivered=True,corrected_players=17,remaining_cross_club_cases=2796),flush=True)


if __name__=='__main__':run()
