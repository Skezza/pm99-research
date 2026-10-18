#!/usr/bin/env python3
"""Overlap independent in-memory checks with unpromoted season builds.

Every changed season must have a completed component, the same frozen checker
versions, the exact current plan hash and exact compiled native bytes. Aggregate
only after all 26 plans exist; a component alone never closes an entire batch.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import closeout_duplicate_ownership_batch_v1 as batch
from scripts import deliver_compiled_duplicate_batch_v1 as delivery
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def component(season, plan_root, release_id, output):
    return batch.verify_native_batch(plan_root, release_id, output, seasons=[season])


def combine(plans, components, release_id):
    changed = {s for s, p in plans.items() if p['updates']}
    if set(components) != changed:
        raise ValueError('native components do not cover the exact changed seasons')
    rows, first = [], None
    for season in sorted(components):
        proof = components[season]
        if (proof['release_id'] != release_id or len(proof['seasons']) != 1
                or proof['seasons'][0]['season'] != season
                or proof['verification_scope'] != 'selected-season-components'):
            raise ValueError('native component belongs to another season or scope')
        hashes = {k: v for k, v in proof.items() if k.endswith('_sha256')}
        if first is None:
            first = copy.deepcopy(proof)
        elif hashes != {k: v for k, v in first.items() if k.endswith('_sha256')}:
            raise ValueError('native component checker versions differ')
        rows.extend(proof['seasons'])
    if first is None:
        raise ValueError('empty batch does not need native publication')
    first.update(seasons=rows, players=sum(p['players'] for p in components.values()),
                 verification_scope='all-supported-seasons')
    delivery.verify_batch_size(plans, first)
    return first


def run(plan_root, release_id, output, jobs):
    if output.exists():
        raise ValueError('native batch proof already exists; never overwrite')
    pending, active, components, paths = set(registry.supported_seasons()), {}, {}, {}
    component_root = output.parent / (output.stem + '-components')
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        while pending or active:
            for season in sorted(pending):
                if len(active) >= jobs:
                    break
                plan_path = plan_root / season / 'ownership-plan.json'
                if not plan_path.is_file():
                    continue
                try:
                    plan = json.loads(plan_path.read_text())
                except json.JSONDecodeError:
                    # An orchestration writer may have only just created the
                    # path; incomplete JSON is not a completed immutable plan.
                    continue
                if not plan['updates']:
                    pending.remove(season)
                    continue
                if not registry.locator_path(season, release_id).is_file():
                    continue
                target = component_root / season / 'native.json'
                if target.exists():
                    proof = json.loads(target.read_text())
                    paths[season], components[season] = target, proof
                    pending.remove(season)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                active[pool.submit(component, season, plan_root, release_id, target)] = (season, target)
                pending.remove(season)
            done, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED) if active else (set(), set())
            for future in done:
                season, target = active.pop(future)
                proof = future.result()
                components[season], paths[season] = proof, target
                print(json.dumps({'native_verified': season, 'players': proof['players']}), flush=True)
            if not active:
                time.sleep(5)
    plans = {s: json.loads((plan_root / s / 'ownership-plan.json').read_text())
             for s in registry.supported_seasons()}
    result = combine(plans, components, release_id)
    for row in result['seasons']:
        release = registry.load_registered_release(row['season'], release_id)
        if (registry.sha256_file(plan_root / row['season'] / 'ownership-plan.json') != row['ownership_plan_sha256']
                or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != row['jug_sha256']):
            raise ValueError('component plan or compiled database changed before aggregation')
    for proof in components.values():
        for key, value in proof.items():
            if key.endswith('_path') and key.removesuffix('_path') + '_sha256' in proof:
                if registry.sha256_file(ROOT / value) != proof[key.removesuffix('_path') + '_sha256']:
                    raise ValueError('frozen component checker changed')
    result['component_proofs'] = [{'season': s, 'path': registry.relative_workspace_path(paths[s]),
        'sha256': registry.sha256_file(paths[s])} for s in sorted(paths)]
    pipeline.write_canonical_json(output, result)
    print(json.dumps({'native_batch_verified': release_id, 'players': result['players'],
                      'seasons': len(result['seasons'])}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2, 3), default=2,
                        help='bounded native-check lanes; three permitted on the 8-core worker')
    args = parser.parse_args()
    run(args.plan_root, args.release_id, args.output, args.jobs)
