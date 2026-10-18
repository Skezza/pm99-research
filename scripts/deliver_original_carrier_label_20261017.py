"""Publish a name-only club repair without certifying its unresolved squad."""
import argparse
import copy
from datetime import UTC, datetime

from scripts import build_original_carrier_label_20261017 as build
from scripts.capture_original_carrier_label_20261017 import TAG, PROFILE
from scripts.verify_original_carrier_label_20261017 import verify
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def bind(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def main(previous_version):
    folder = build.ROOT/build.SEASON
    previous_path = build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output = build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():
        raise ValueError('completed club-name publication must not repeat')
    previous = pipeline.read_json_file(previous_path); initial = bindings()
    if initial != previous['current_release_bindings']:
        raise ValueError('club label defaults differ from explicit previous checkpoint')
    plan = pipeline.read_json_file(folder/'club-plan.json')
    base = registry.load_preferred_release(build.SEASON)
    if base.release_id != plan['release_id']:
        raise ValueError('club label parent advanced; preserve intervening changes')
    actual = registry.load_registered_release(build.SEASON, build.RELEASE)
    retained(folder/'independent-prepublication-native-proof.json', verify(base, actual, plan))
    rebuilt = registry.load_registered_release(build.SEASON, build.REPLAY)
    proof = pipeline.read_json_file(folder/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
        raise ValueError('club label full SOURCE proof incomplete')
    for release in (actual, rebuilt):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes() != rebuilt.package_path.read_bytes():
        raise ValueError('club label SOURCE recipe differs')
    evidence = registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport = pipeline.read_json_file(folder/'startup-transport.json')
    summary = pipeline.read_json_file(evidence/'summary.json')
    visual = pipeline.read_json_file(folder/'startup-visual-review.json'); check_visual(visual)
    if (transport['exit_code'] != 0 or transport['release_manifest_sha256'] != actual.manifest_sha256
            or transport['evidence'] != registry.relative_workspace_path(evidence)
            or visual['observed_team'] != 'Stoke City' or visual['observed_date'] != '2000-08-01'
            or visual['screenshot_sha256'] != registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256'] != actual.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected')
            or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256') != actual.manifest_sha256
            or summary.get('output_inventory_fingerprint') != actual.locator['game_inventory_fingerprint']):
        raise ValueError('restored club game lacks exact original successful startup')
    profiles = [(PROFILE['carrier_id'], PROFILE['label'], PROFILE['search'], PROFILE['token'])]
    digits(folder, build.SEASON, build.RELEASE, profiles)
    verify_profiles(folder, build.SEASON, build.RELEASE, profiles)
    reviewed = pipeline.read_json_file(folder/(PROFILE['label']+'-profile-visual-review.json'))
    if reviewed['observed_club'] != 'Morecambe':
        raise ValueError('actual original profile does not display restored Morecambe name')
    original_backup = verify_original2015()
    if bindings() != initial:
        raise ValueError('another preferred game changed during club-label preflight')
    publisher.register_completed_delta(build.SEASON, build.RELEASE)
    retained(folder/'final-attestation.json', runtime.attest(season=build.SEASON, evidence_dir=evidence))
    validation = registry.validate_preferred_release(build.SEASON, level='playable')
    if not validation['valid']:
        raise ValueError('restored club default failed playable gate')
    retained(folder/'preferred-playable-validation.json', validation)
    current = bindings()
    if [r for r in current if r['season'] != build.SEASON] != [r for r in initial if r['season'] != build.SEASON]:
        raise ValueError('club label publication changed another season')
    result = copy.deepcopy(previous)
    for finding in result['additional_confirmed_findings']:
        if finding['id'] == 'Morecambe2000-existing-roster-under-Barrow-native3312':
            finding.update(state='partially-repaired-label-runtime-verified-opening-squad-still-open',
                label_corrected='Morecambe', correct_target_slot_identity_not_yet_adjudicated=False,
                label_evidence=bind(folder/(PROFILE['label']+'-profile-visual-review.json')))
    result['additional_confirmed_findings'].append(dict(
        id='Morecambe2000-original-carrier-club-label-restored', season=build.SEASON,
        state='delivered-source-native-SOURCE-and-runner-verified', native_club_labels_changed=1,
        player_or_coach_or_ground_or_asset_changes=0, missing_starting_keeper_and_secondary_facts_still_open=True,
        cross_club_cases_closed=0, source_plan=bind(folder/'club-plan.json')))
    names = ['club-plan.json', 'native-byte-proof.json', 'complete-SOURCE-replay.json',
        'startup-transport.json', 'startup-visual-review.json', 'independent-prepublication-native-proof.json',
        'final-attestation.json', 'preferred-playable-validation.json']
    names += [PROFILE['label']+suffix for suffix in ('-profile-transport.json', '-profile-visual-review.json',
        '-original-digit-proof.json', '-original-age-proof.json', '-native-runtime-proof.json')]
    result['delivered_evidence'] += [original_backup] + [bind(folder/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=bind(previous_path),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=[build.SEASON],
        all_required_work_complete=False,
        next_batch='Finish Morecambe2000 opening GK/positive capacity squad and sourced missing DOBs at its restored original3312 identity. Continue frozen2789 cross-club cases and full remaining checklist; no new roster clone.')
    pipeline.write_canonical_json(output, result)
    retained(folder/'final-delivery-summary.json', dict(checklist=bind(output), native_club_label_fixes=1,
        all_other25_preferred_bindings_unchanged=True, player_and_coach_and_asset_bytes_unchanged=True,
        original2015_backup_verified=True, cross_club_cases_closed=0, global_historical_RC=False))
    print(dict(club_label_fixed_in_actual_game=True, opening_squad_still_open=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-version', type=int, required=True)
    main(parser.parse_args().previous_version)
