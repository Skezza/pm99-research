#!/usr/bin/env python3
"""Deliver one natively verified batch; preserve unresolved historical failures.

Serial catalog promotion, bounded runner lanes, exact unchanged QA reuse,
fixed-reader identity comparisons, cumulative ledger and full release closeout.
Never infer batch size from a progress message or reuse another game's proof.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import closeout_duplicate_ownership_batch_v1 as batch
from scripts import season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import capture_registered_season_runtime_v1 as runtime
from scripts import audit_published_player_identities_v1 as identities
from scripts import audit_cumulative_duplicate_repairs_v1 as ledger
from scripts import season_pipeline_v2 as pipeline


def verify_batch_size(plans, proof):
    changed = {season: plan for season, plan in plans.items() if plan['updates']}
    rows = {r['season']: r for r in proof['seasons']}
    if (set(rows) != set(changed) or len(rows) != len(proof['seasons'])
            or proof['players'] != sum(len(p['updates']) for p in changed.values())
            or any(rows[s]['players'] != len(p['updates']) for s, p in changed.items())):
        raise ValueError('native proof must cover the exact planned slots and seasons')
    return sorted(changed)


def identity_difference(before, after):
    if before['policy'] != after['policy'] or before.get('public_person_supplement') != after.get('public_person_supplement'):
        raise ValueError('before and after identity matching rules differ')
    def keys(doc):
        return {(s['season'], tuple(c['identity'])) for s in doc['seasons'] for c in s['candidates']}
    removed, introduced = keys(before) - keys(after), keys(after) - keys(before)
    if introduced:
        raise ValueError('new cross-club identity groups introduced')
    return {'before': before['cross_club_candidate_groups'], 'after': after['cross_club_candidate_groups'],
            'removed': len(removed), 'introduced': len(introduced), 'reader': after['policy']}


def deliver(root, plan_root, release_id, label, prior_label, person_path, enriched_before=None):
    proof_path = root / f'native-verification-{label}-final.json'
    proof = json.loads(proof_path.read_text())
    if proof['release_id'] != release_id or not (root / f'closeout-{prior_label}-final/summary.json').exists():
        raise ValueError('exact batch proof and frozen prior closeout required')
    plans = {s: json.loads((plan_root / s / 'ownership-plan.json').read_text())
             for s in registry.supported_seasons()}
    changed = verify_batch_size(plans, proof)
    for row in proof['seasons']:
        path = plan_root / row['season'] / 'ownership-plan.json'
        if registry.sha256_file(path) != row['ownership_plan_sha256']:
            raise ValueError('planned native correction changed since verification')
    for season in changed:
        publisher.register_completed_delta(season, release_id)
        print(json.dumps({'promoted': season, 'release_id': release_id}), flush=True)
    os.environ.update(PM99_RUNNER_WORKER_LANE_COUNT='3', PM99_RUNNER_HOST_LOCK_CONCURRENCY='3',
                      PM99_RUNNER_WORKER_DISPLAY_BASE='90')
    options = SimpleNamespace(expect_release_id=release_id, execute=True, attest=True,
                              worker='tiny-m73', run_tag=None, compact_evidence=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(runtime.capture_one, season=s, args=options): s for s in changed}
        for f in as_completed(futures):
            print(json.dumps({'runtime_season': futures[f], 'result': f.result()}), flush=True)
    qa = root / f'registered-qa-{label}-final'
    batch.resume_quality(root / f'registered-qa-{prior_label}-final', qa, 2)
    audit = root / f'current-source-name-dob-candidates-{label}-final.json'
    batch.audit_current_identities(audit, root / f'current-source-name-dob-candidates-{prior_label}-final.json')
    for enriched in (False, True):
        suffix = '-enriched' if enriched else ''
        output = root / f'published-identities-after-{label}{suffix}.json'
        identities.run(output, person_supplement=person_path if enriched else None)
        previous = (enriched_before if enriched and enriched_before is not None
                    else root / f'published-identities-after-{prior_label}{suffix}.json')
        difference = identity_difference(json.loads(previous.read_text()), json.loads(output.read_text()))
        pipeline.write_canonical_json(root / f'published-identity-difference-{label}{suffix}.json', difference)
        print(json.dumps({'identity_difference': difference}), flush=True)
    cumulative = ledger.run(root / f'repair-and-portrait-ledger-{prior_label}.json', [plan_root],
                            root / f'repair-and-portrait-ledger-{label}.json')
    print(json.dumps({'cumulative_corrected_slots': cumulative['corrected_slot_count']}), flush=True)
    return batch.closeout(plan_root, root / f'closeout-{label}-final', qa,
                         native_readback=proof_path, native_reproduction=proof_path, identity_audit=audit)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--prior-label', required=True)
    parser.add_argument('--person-input', type=Path, required=True)
    parser.add_argument('--enriched-before', type=Path,
        help='Frozen prior-release audit using the exact same public person input, if that input advanced.')
    args = parser.parse_args()
    deliver(args.root, args.plan_root, args.release_id, args.label, args.prior_label, args.person_input,
            args.enriched_before)
