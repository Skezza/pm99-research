"""Publish the exact Barnet game only after source/native/original-frame gates."""
import copy
from datetime import UTC, datetime
from pathlib import Path
import tempfile
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_paired_whole_club_reconstruction_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_frozen_fixture_reserve_v1 import next_count
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.publish_barnet2018_private_20261017 import ROOT, RELEASE, REPLAY, SEASON
from scripts.capture_barnet2018_runtime_20261017 import FOLDER, TAG, PROFILES

def run(*, root=ROOT, folder=FOLDER, season=SEASON, release_id=RELEASE, replay_id=REPLAY,
        tag=TAG, profiles=PROFILES, previous_version=109, next_version=110, proof_prefix='Barnet2018',
        target_club='Barnet', expected_source_ids=(159419,42026,45607,58647),require_hill=True,
        published_bench=5,positive_reserves=1,manager='John Still',ground='The Hive London',pending_country_proof=None):
    ROOT,FOLDER,SEASON,RELEASE,REPLAY,TAG,PROFILES=root,folder,season,release_id,replay_id,tag,profiles
    previous_path=ROOT/f'release-delivery-checklist-v{previous_version}.json'
    output=ROOT/f'release-delivery-checklist-v{next_version}.json'
    if output.exists():raise ValueError('completed publication must not repeat')
    previous=pipeline.read_json_file(previous_path)
    release=registry.load_registered_release(SEASON,RELEASE)
    rebuilt=registry.load_registered_release(SEASON,REPLAY)
    source.bound_receipt(release)
    replay=pipeline.read_json_file(FOLDER/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('whole SOURCE equality required')
    for item in (release,rebuilt):pipeline.assert_tree_matches_inventory(item.game_path,pipeline.read_json_file(release.inventory_path))
    if release.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('whole recipe differs')
    with tempfile.TemporaryDirectory(prefix='pm99-barnet-readback-') as folder:
        fresh=readback.verify(ROOT/(proof_prefix+'-complete-v1'),Path(folder)/'proof.json')
    saved=pipeline.read_json_file(ROOT/(proof_prefix+'-native-readback.json'))
    if pipeline.canonical_json_bytes(fresh)!=pipeline.canonical_json_bytes(saved) or len(fresh['players'])!=17:
        raise ValueError('fresh native17 readback differs')
    identity=pipeline.read_json_file(ROOT/(proof_prefix+'-identity-readback.json'))
    if (identity['candidate_receipt_sha256']!=registry.sha256_file(ROOT/(proof_prefix+'-complete-v1/candidate-receipt.json'))
            or identity['package_sha256']!=registry.sha256_file(release.package_path)
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared'] or not identity['unselected_recipe_players_identical']):
        raise ValueError('identity/preservation proof incomplete')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    visual=pipeline.read_json_file(FOLDER/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(FOLDER/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):
        raise ValueError('ordinary startup proof incomplete')
    profiles=[(c,l,'',t) for c,l,t in PROFILES]
    verify_profiles(FOLDER,SEASON,RELEASE,profiles);digits(FOLDER,SEASON,RELEASE,profiles)
    for carrier,label,_ in PROFILES:
        proof=pipeline.read_json_file(FOLDER/(label+'-native-runtime-proof.json'))
        checked=pipeline.read_json_file(FOLDER/(label+'-profile-visual-review.json'));check_visual(checked)
        profile_transport=pipeline.read_json_file(FOLDER/(label+'-profile-transport.json'))
        if (proof['carrier_id']!=carrier or proof['club']!=target_club or not proof['kit_pixels']['passed']
                or proof['release_id']!=RELEASE or proof['season']!=SEASON
                or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
                or proof['visual_review_sha256']!=registry.sha256_file(FOLDER/(label+'-profile-visual-review.json'))
                or proof['screenshot_sha256']!=checked['screenshot_sha256']
                or not proof['native_inputs_hash_verified'] or not proof['ten_visible_skills_verified']
                or profile_transport['exit_code']!=0 or profile_transport['release_manifest_sha256']!=release.manifest_sha256):
            raise ValueError('target actor runtime proof incomplete')
    cases=pipeline.read_json_file(FOLDER/'independent-frozen-case-proof.json')
    if (cases['manifest_sha256']!=release.manifest_sha256
            or cases['confirmed_frozen_cases_repaired']!=len(expected_source_ids)
            or {r['source_person_id'] for r in cases['dispositions']}!=set(expected_source_ids)
            or (require_hill and (not cases['Josh_Hill_case_still_open']
                or set(cases['remaining_Josh_Hill_carriers'])!={11233,11267}))):
        raise ValueError('exact source-proved frozen cases required; unrelated cases stay open')
    remaining=next_count(previous,cases['dispositions'])
    country_gap=None
    if pending_country_proof is not None:
        country_gap=pipeline.read_json_file(pending_country_proof)
        if (country_gap['manifest_sha256']!=release.manifest_sha256
                or country_gap['native_writes']!=0
                or country_gap['new_confirmed_country_omissions']!=len(country_gap['cases'])):
            raise ValueError('open country-gap evidence is not bound to this actual game')
        from scripts import season_soccerbase_secondary_facts_v2 as country_source
        players={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
        for row in country_gap['cases']:
            path=registry.ROOT/row['evidence']['path'];bio=row['original_profile']['identity']
            if registry.sha256_file(path)!=row['evidence']['sha256']:raise ValueError('open country original changed')
            if country_source.country(path.read_bytes(),person_id=bio['provider_player_id'],name=bio['name'],
                    birth_date=bio['birth_date'],url=bio['source_profile_url'])!=row['original_profile']:
                raise ValueError('open nationality original does not reproduce')
            if players[row['carrier_id']]['facts']['nationality']!='XXX' or row['delivered']:
                raise ValueError('do not silently accept a known wrong flag or claim delivery')
    expected={r['season']:r for r in previous['current_release_bindings']}
    def preserved():
        current=bindings()
        if {r['season'] for r in current}!=set(registry.supported_seasons()):raise ValueError('26 bindings required')
        for row in current:
            if row['season']!=SEASON and row!=expected[row['season']]:raise ValueError('unaffected release changed')
            if row['season']==SEASON:
                if row['release_id']==expected[SEASON]['release_id']:
                    if row!=expected[SEASON]:raise ValueError('parent target binding changed')
                elif (row['release_id'],row['manifest_sha256'])!=(RELEASE,release.manifest_sha256):
                    raise ValueError('unexpected target binding')
    preserved();backup=verify_original2015()
    publisher.register_completed_delta(SEASON,RELEASE)
    retained(FOLDER/'final-attestation.json',runtime.attest(season=SEASON,evidence_dir=evidence))
    valid=registry.validate_preferred_release(SEASON,level='playable')
    if not valid['valid']:raise ValueError('promoted release not playable')
    retained(FOLDER/'preferred-playable-validation.json',valid);preserved()
    result=copy.deepcopy(previous)
    result['cross_club_dispositions'].extend(dict(r,delivery=binding(FOLDER/'independent-frozen-case-proof.json')) for r in cases['dispositions'])
    result['remaining_cross_club_cases']=remaining
    result['additional_confirmed_findings'].append(dict(id=proof_prefix+'-complete-original-opening',season=SEASON,
        state='delivered-native-SOURCE-and-runner-verified',corrected_slots=17,original_XI=11,published_bench=published_bench,
        positive_dated_reserves=positive_reserves,dated_manager=manager,ground=ground,
        additional_frozen_cases_closed=len(expected_source_ids),
        **(dict(Josh_Hill_other_two_club_copies_still_open=True) if require_hill else {}),kit_exact_artwork_certified=False))
    if country_gap is not None:
        result['new_required_followups'].append(dict(id=proof_prefix+'-original-profile-country-omissions',season=SEASON,
            status='open-confirmed-source-composition-bug',confirmed_cases=len(country_gap['cases']),
            evidence=binding(pending_country_proof),cases=country_gap['cases'],
            scope='Known country rows omitted by legacy extractor; NOT unavailable facts or unsupported nationality exceptions. Narrow actual-game country fixes and reusable extraction fix required. Original cross-club denominator unchanged.'))
    names=['private-registration.json','complete-SOURCE-replay.json','independent-frozen-case-proof.json',
        'startup-transport.json','startup-visual-review.json','final-attestation.json','preferred-playable-validation.json']
    names += [label+suffix for _,label,_ in PROFILES for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json','-original-digit-proof.json','-original-age-proof.json')]
    result['delivered_evidence'] += [backup,binding(ROOT/(proof_prefix+'-native-readback.json')),binding(ROOT/(proof_prefix+'-identity-readback.json'))]
    result['delivered_evidence'] += [binding(FOLDER/name) for name in names]
    if pending_country_proof is not None:result['delivered_evidence'].append(binding(pending_country_proof))
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous_path),current_release_bindings=bindings(),
        fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Reconcile six independently sourced2017 cases; correct Jimmy Dunne2017 opening ownership. Continue remaining frozen cases and critical checklist; no global RC claim.')
    pipeline.write_canonical_json(output,result)
    retained(FOLDER/'final-delivery-summary.json',dict(utc=datetime.now(UTC).isoformat(),checklist=binding(output),
        corrected_slots=17,frozen_cross_club_cases_closed=len(expected_source_ids),remaining_cross_club_cases=remaining,
        all_other25_preferred_bindings_unchanged=True,original2015_backup_verified=True,global_historical_RC=False))
    print(dict(delivered=True,corrected_players=17,remaining_cross_club_cases=remaining),flush=True)

if __name__=='__main__':run()
