"""Promote the one-byte source-backed country repair after actual runner proof.

No duplicate or birthday counters change. The still-wrong broad position is
an explicit required follow-up, not concealed by factual country approval.
"""
import argparse
import copy
from datetime import UTC, datetime

from scripts import build_shinnie_country_20261017 as build
from scripts.capture_shinnie_country_20261017 import TAG
from scripts import season_original_secondary_facts_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.verify_original_secondary_fact_delta_v1 import verify
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def main(previous_version):
    folder = build.ROOT / 'country-delivery'
    audit_root = build.ROOT.parent
    previous_path = audit_root / f'release-delivery-checklist-v{previous_version}.json'
    output = audit_root / f'release-delivery-checklist-v{previous_version + 1}.json'
    if output.exists():
        raise ValueError('completed country publication must not repeat')
    previous = pipeline.read_json_file(previous_path)
    old = previous['current_release_bindings']
    if bindings() != old:
        raise ValueError('current defaults differ from explicit previous checklist')
    base = registry.load_registered_release(build.SEASON, build.BASE)
    actual = registry.load_registered_release(build.SEASON, build.RELEASE)
    if registry.load_preferred_release(build.SEASON).manifest_sha256 != base.manifest_sha256:
        raise ValueError('country parent advanced; preserve intervening fixes')
    plan_path = folder / 'country-plan.json'
    plan = pipeline.read_json_file(plan_path)
    source.verify(base, plan)
    if (len(plan['updates']) != 1 or plan['targets'] != {'9718': ['nationality']}
            or plan['updates'][0]['nationality'] != 'SCO' or plan['unresolved']):
        raise ValueError('country publication changed its exact source scope')
    proof_path = folder / 'final-independent-proof.json'
    proof = verify(build.SEASON, build.RELEASE, plan_path, proof_path)
    if (proof['native_bytes_changed'] != 1 or not proof['all_other_native_bytes_identical']
            or not proof['all_other_game_files_identical'] or not proof['all_other_recipe_facts_identical']):
        raise ValueError('country correction changes more than one authorised native byte')
    replay = pipeline.read_json_file(folder / 'complete-SOURCE-replay.json')
    rebuilt = registry.load_registered_release(build.SEASON, build.REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('country whole SOURCE proof incomplete')
    for release in (actual, rebuilt):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes() != rebuilt.package_path.read_bytes():
        raise ValueError('whole country SOURCE recipe differs')
    evidence = registry.ROOT / '.local/runlogs/pm99_runner' / TAG
    visual = pipeline.read_json_file(folder / 'startup-visual-review.json')
    check_visual(visual)
    summary = pipeline.read_json_file(evidence / 'summary.json')
    transport = pipeline.read_json_file(folder / 'startup-transport.json')
    if (visual['observed_team'] != 'Stoke City' or visual['observed_date'] != '2021-08-01'
            or visual['release_manifest_sha256'] != actual.manifest_sha256
            or visual['screenshot_sha256'] != registry.sha256_file(lineup_frame(evidence))
            or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != actual.manifest_sha256
            or transport['evidence'] != registry.relative_workspace_path(evidence)
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256'] != actual.manifest_sha256
            or summary['output_inventory_fingerprint'] != actual.locator['game_inventory_fingerprint']):
        raise ValueError('country startup original evidence is not the actual corrected game')
    profiles = [(9718, 'shinnie', 'Graeme Shinnie', 'Shinnie')]
    visual = pipeline.read_json_file(folder / 'shinnie-profile-visual-review.json')
    check_visual(visual, name='Graeme Shinnie', club='Derby County', age=30, nationality='SCOTLAND')
    verify_digits(folder, build.SEASON, build.RELEASE, profiles)
    verify_profiles(folder, build.SEASON, build.RELEASE, profiles)
    backup = verify_original2015()
    if bindings() != old:
        raise ValueError('another preferred game changed during country preflight')
    retained(folder / 'prepublication-proof.json', dict(source_country='SCO',
        independently_verified_native_bytes=1, whole_SOURCE=True, original_startup_and_profile_verified=True,
        frozen_counts_unchanged=True, primary_position_conflict_still_open=True))
    publisher.register_completed_delta(build.SEASON, build.RELEASE)
    retained(folder / 'final-attestation.json', runtime.attest(season=build.SEASON, evidence_dir=evidence))
    validation = registry.validate_preferred_release(build.SEASON, level='playable')
    if not validation['valid']:
        raise ValueError('corrected country default failed playable validation')
    retained(folder / 'preferred-playable-validation.json', validation)
    current = bindings()
    if [r for r in current if r['season'] != build.SEASON] != [r for r in old if r['season'] != build.SEASON]:
        raise ValueError('country publication changed another preferred season')
    result = copy.deepcopy(previous)
    result['additional_confirmed_findings'].extend([
        dict(id='shinnie-2021-native-nationality-eng', season=build.SEASON,
            state='repaired-and-runtime-verified', carrier_id=9718, corrected_observed='SCOTLAND',
            source_plan=binding(plan_path), correction_evidence=binding(folder / 'shinnie-profile-visual-review.json')),
        dict(id='shinnie-2021-broad-position-conflict', season=build.SEASON, carrier_id=9718,
            state='open-source-confirmed-position-conflict', observed='D', source_annual='M',
            source_native_readback=binding(build.ROOT / 'all26-source-native-readback.json'),
            country_repair_does_not_approve_roles=True)])
    names = ['country-plan.json', 'native-byte-proof.json', 'final-independent-proof.json',
        'complete-SOURCE-replay.json', 'startup-transport.json', 'startup-visual-review.json',
        'shinnie-profile-transport.json', 'shinnie-profile-visual-review.json',
        'shinnie-original-digit-proof.json', 'shinnie-original-age-proof.json', 'shinnie-native-runtime-proof.json',
        'prepublication-proof.json', 'final-attestation.json', 'preferred-playable-validation.json']
    result['delivered_evidence'] += [backup] + [binding(folder / name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(previous_path),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=[build.SEASON],
        all_required_work_complete=False)
    if result['remaining_cross_club_cases'] != previous['remaining_cross_club_cases']:
        raise ValueError('country correction must not close an ownership case')
    pipeline.write_canonical_json(output, result)
    retained(folder / 'final-delivery-summary.json', dict(checklist=binding(output),
        country_delivered=True, all_other25_preferred_bindings_unchanged=True,
        original2015_backup_verified=True, primary_position_fix_pending=True,
        cross_club_cases_closed=0, global_historical_RC=False))
    print(dict(country_delivered=True, primary_position_fix_pending=True, cross_club_cases_closed=0), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-checklist-version', type=int, required=True)
    main(parser.parse_args().previous_checklist_version)
