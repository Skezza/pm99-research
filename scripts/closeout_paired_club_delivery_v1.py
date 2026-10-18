#!/usr/bin/env python3
"""Close one independently proved coupled delivery, not the whole duplicate queue."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def read(path):
    return json.loads(path.read_text())


def binding(path):
    return {'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)}


def identity_keys(audit):
    return {(section['season'], json.dumps(row['identity'], sort_keys=True))
        for section in audit['seasons'] for row in section['candidates']}


def closeout(args):
    if args.output.exists():
        raise ValueError('paired delivery closeout is immutable')
    receipt_path = args.candidate / 'candidate-receipt.json'
    receipt = read(receipt_path)
    season = receipt['season']
    release = registry.load_preferred_release(season)
    if (registry.sha256_file(release.package_path) != registry.sha256_file(args.candidate / 'season-package.json')
            or release.game_path.resolve() != (args.candidate / 'game').resolve()):
        raise ValueError('paired game is not the installed preferred release')
    native, identity = read(args.native_proof), read(args.identity_proof)
    digest = registry.sha256_file(receipt_path)
    if (native.get('candidate_receipt_sha256') != digest
            or identity.get('candidate_receipt_sha256') != digest
            or native.get('all_unselected_native_records_identical') is not True
            or identity.get('introduced_candidate_groups') != 0
            or identity.get('replacement_cross_club_candidates') != 0
            or identity.get('stale_portraits_cleared') is not True
            or identity.get('keeper_recipe_replay_idempotent') is not True):
        raise ValueError('paired independent proofs are incomplete')
    profiles = [read(path) for path in args.profile_proof]
    if len(profiles) != len(receipt['new_clubs']) or {p['club'] for p in profiles} != set(receipt['new_clubs']):
        raise ValueError('actual profile proof missing for a replacement club')
    for proof in profiles:
        if (proof['candidate_receipt_sha256'] != digest or not proof['native_inputs_hash_verified']
                or not proof['kit_pixels']['passed']
                or registry.sha256_file(ROOT / proof['screenshot']) != proof['screenshot_sha256']):
            raise ValueError('paired actual profile/kit proof is stale or failed')
    validation = read(args.release_validation)
    if len(validation) != 26 or not all(row['valid'] for row in validation):
        raise ValueError('full all-season release validation is incomplete')
    qa = read(args.quality_report)
    if qa['inputs']['package_sha256'] != registry.sha256_file(release.package_path):
        raise ValueError('quality report does not describe the installed recipe')
    for blocker in qa['blockers']:
        lines = blocker.get('details', {}).get('error', '').splitlines()
        if (blocker['code'] != 'package-validation-failed' or len(lines) < 2
                or any(not line.startswith('- strict validation rejects ambiguous same-person player candidates ')
                    for line in lines[1:])):
            raise ValueError('paired delivery has a new/non-duplicate quality blocker')
    before, after = read(args.before_audit), read(args.after_audit)
    if (before['snapshot'] != after['snapshot']
            or before.get('public_person_supplement') != after.get('public_person_supplement')):
        raise ValueError('identity comparison uses different source/join rules')
    old, new = identity_keys(before), identity_keys(after)
    if new - old:
        raise ValueError('paired delivery introduced cross-club identity candidates')
    for section in after['seasons']:
        current = registry.load_preferred_release(section['season'])
        if (current.release_id, registry.sha256_file(current.package_path)) != (
                section['release_id'], section['package_sha256']):
            raise ValueError('all-season identity audit is no longer current')
    ledger = read(args.cumulative_ledger)
    if ledger['prior_sha256'] != registry.sha256_file(args.prior_ledger):
        raise ValueError('cumulative correction ledger lost its predecessor')
    prior = read(args.prior_ledger)
    prior_slots = {(r['season'], r['carrier_id']) for r in prior['players']}
    current_slots = {(r['season'], r['carrier_id']) for r in ledger['players']}
    corrected = {(season, carrier) for carrier in identity['corrected_slots']}
    if current_slots != prior_slots | corrected:
        raise ValueError('distinct correction count is not the exact chained union')
    attestation = read(release.attestation_path)
    runtime = attestation['runtime_receipts'][0]
    screenshot = ROOT / runtime['lineup_screenshot']
    if registry.sha256_file(screenshot) != runtime['lineup_screenshot_sha256']:
        raise ValueError('fresh preferred-game lineup screenshot changed')
    result = {'schema_version': 'pm99-coupled-club-delivery-closeout-v1',
        'utc_time': datetime.now(timezone.utc).isoformat(),
        'source_session': '01a0592d-fcd5-7262-a637-743a8253d9b4', 'machine': 'joe-Vostro-3350',
        'season': season, 'release_id': release.release_id,
        'paired_delivery_complete': True, 'built': True, 'installed': True, 'verified': True,
        'duplicate_cleanup_complete': False, 'historical_quality_result': qa['result'],
        'changed_slots': len(corrected), 'additional_distinct_corrected_slots': len(corrected - prior_slots),
        'cumulative_corrected_slots': len(current_slots),
        'cross_club_candidates_before': len(old), 'cross_club_candidates_after': len(new),
        'removed_candidate_groups': len(old - new), 'introduced_candidate_groups': 0,
        'lineup_screenshot': runtime['lineup_screenshot'],
        'lineup_screenshot_sha256': runtime['lineup_screenshot_sha256'],
        'evidence': {name: binding(getattr(args, name)) for name in ('native_proof', 'identity_proof',
            'release_validation', 'quality_report', 'before_audit', 'after_audit', 'cumulative_ledger', 'prior_ledger')},
        'profile_proofs': [binding(path) for path in args.profile_proof],
        'scope_limits': ['no new portraits', 'declared replacement clubs only, not an all-season small-kit padding cascade',
            'native complete XI checked; profile screenshots do not prove full mode1 tactical deployment',
            'remaining identity groups are candidates, not all proven erroneous copies']}
    pipeline.write_canonical_json(args.output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'native-proof', 'identity-proof', 'release-validation', 'quality-report',
            'before-audit', 'after-audit', 'cumulative-ledger', 'prior-ledger', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile-proof', type=Path, action='append', required=True)
    result = closeout(parser.parse_args())
    print(json.dumps({k: result[k] for k in ('season', 'release_id', 'paired_delivery_complete',
        'duplicate_cleanup_complete', 'cumulative_corrected_slots', 'cross_club_candidates_after')}))
