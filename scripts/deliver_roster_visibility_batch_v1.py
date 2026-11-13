#!/usr/bin/env python3
"""Deliver exact two-byte visibility deltas; reuse, never rebuild completed work."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import json_storage_io_v1 as storage_io
from scripts import season_roster_visibility_v1 as visibility
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import capture_registered_season_runtime_v1 as runtime
from scripts import audit_registered_roster_visibility_v1 as inventory

RELEASE = 'authored-roster-visibility-20261006-r40a'
FACTORY = ROOT/'.local/season-pipeline-v2/pm99-base-clean/DBDAT/EQ98030.FDI'
PILOT = ROOT/'.local/runlogs/pm99_runner/prove_2007_08_stoke_roster_flags_20261006t1501z/screens/022_line_up_inspect.png'


def write_once(path, document):
    path.parent.mkdir(parents=True,exist_ok=True)
    if storage_io.exists(path):
        if json.loads(storage_io.read_text(path)) != document: raise ValueError('immutable batch input changed: '+str(path))
    else: pipeline.write_canonical_json(path,document)


def build_one(season, root):
    locator = registry.locator_path(season, RELEASE)
    if storage_io.exists(locator):
        built = registry.load_registered_release(season,RELEASE)
        layer = json.loads(storage_io.read_text(built.package_path.parent / 'roster-visibility.json'))
        source = registry.load_registered_release(season,layer['source_release_id'])
    else:
        source = registry.load_preferred_release(season)
        layer = visibility.prepare(source,factory_path=FACTORY,pilot_path=PILOT)
        write_once(root/season/'roster-visibility.json',layer)
        if not layer['clubs']:
            return {'season':season,'unchanged':True,'source_release_id':source.release_id,'changed_flags':0}
        role = {'season':season,'release_id':source.release_id,
            'package_sha256':registry.sha256_file(source.package_path),
            'jug_sha256':registry.sha256_file(source.game_path/'DBDAT/JUG98030.FDI'),
            'updates':[], 'unresolved':[]}
        write_once(root/season/'role-plan.json',role)
        print(json.dumps({'season':season,'stage':'compiling-two-byte-visibility-delta'}),flush=True)
        publisher.publish(season,root/season/'role-plan.json',release_id=RELEASE,
            visibility_plan_path=root/season/'roster-visibility.json')
        built = registry.load_registered_release(season,RELEASE)
    # Reproduce independently from the exact immutable original, not the
    # publisher's claimed byte count. Recheck every original recipe binding.
    visibility.verify_bound(source,layer)
    before = storage_io.read_bytes(source.game_path / 'DBDAT/EQ98030.FDI')
    expected, changes = visibility.apply(before,layer,exact_before=True)
    if expected != storage_io.read_bytes(built.game_path / 'DBDAT/EQ98030.FDI'):
        raise ValueError('visibility delta differs from independently reproduced bytes')
    pipeline.assert_tree_matches_inventory(source.game_path,json.loads(storage_io.read_text(source.inventory_path)))
    pipeline.assert_tree_matches_inventory(built.game_path,json.loads(storage_io.read_text(built.inventory_path)))
    difference = pipeline.inventory_difference(json.loads(storage_io.read_text(source.inventory_path)),
        json.loads(storage_io.read_text(built.inventory_path)))
    if difference['only_left'] or difference['only_right'] or [r['path'] for r in difference['changed']] != ['DBDAT/EQ98030.FDI']:
        raise ValueError('visibility delta changed players, assets, executable or other files')
    if json.loads(storage_io.read_text(built.package_path)) != visibility.bind(json.loads(storage_io.read_text(source.package_path)),layer):
        raise ValueError('visibility recipe changed beyond exact policy binding')
    proof = {'season':season,'source_release_id':source.release_id,'release_id':RELEASE,
        'changed_flags':len(changes),'intended_starters':sum(p['declared_starter'] for c in layer['clubs'] for p in c['players']),
        'changes':changes,'difference':difference,'original_eq_sha256':layer['eq_sha256'],
        'eq_sha256':registry.sha256_file(built.game_path/'DBDAT/EQ98030.FDI'),
        'recipe_sha256':registry.sha256_file(built.package_path),'source_preserved':True,
        'historical_verification_complete':False}
    write_once(root/season/'native-proof.json',proof)
    print(json.dumps({'season':season,'stage':'independently-verified','changed_flags':len(changes)}),flush=True)
    return proof


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    if storage_io.exists(root / 'closeout.json'): raise ValueError('closed batch must not be repeated')
    os.environ.update(PM99_RUNNER_WORKER_LANE_COUNT='3',PM99_RUNNER_HOST_LOCK_CONCURRENCY='3',
        PM99_RUNNER_WORKER_DISPLAY_BASE='90')
    options = SimpleNamespace(expect_release_id=RELEASE,execute=True,attest=True,worker='tiny-m73',
        run_tag=None,compact_evidence=True)
    seasons = registry.supported_seasons()
    seasons.sort(key=lambda s:(s!='2007-08',s))
    native, runtime_rows = [], []
    with ThreadPoolExecutor(max_workers=2) as builds, ThreadPoolExecutor(max_workers=3) as captures:
        pending = {builds.submit(build_one,s,root):s for s in seasons}
        runtimes = {}
        for task in as_completed(pending):
            proof = task.result(); native.append(proof)
            if not proof.get('unchanged'):
                # Only the main thread updates the shared preferred catalogue.
                publisher.register_completed_delta(proof['season'],RELEASE)
                runtimes[captures.submit(runtime.capture_one,season=proof['season'],args=options)] = proof['season']
        for task in as_completed(runtimes):
            result = task.result();runtime_rows.append({'season':runtimes[task],'result':result})
            print(json.dumps({'stage':'fresh-runtime-complete','season':runtimes[task]}),flush=True)
    after_path = root/'after-visibility-audit.json'
    after = json.loads(storage_io.read_text(after_path)) if storage_io.exists(after_path) else inventory.audit(after_path)
    if after['nonzero_flag_rows']:
        raise ValueError('authored English exclusions remain; cannot close visibility batch')
    validations = [registry.validate_preferred_release(s,level='release') for s in registry.supported_seasons()]
    write_once(root/'full-release-validation.json',validations)
    if not all(v['valid'] for v in validations): raise ValueError('release validation failed')
    result = {'schema_version':'pm99-roster-visibility-batch-closeout-v1',
        'release_id':RELEASE,'changed_seasons':len(runtime_rows),'changed_flags':sum(p['changed_flags'] for p in native),
        'intended_starters_restored':sum(p.get('intended_starters',0) for p in native),
        'fresh_runtime_captures':len(runtime_rows),'release_validation_passed':len(validations),
        'native_proofs':sorted(native,key=lambda p:p['season']),'runtime':sorted(runtime_rows,key=lambda p:p['season']),
        'remaining_authored_exclusions':0,'duplicate_cleanup_complete':False,
        'historical_verification_complete':False,
        'runtime_scope':'fresh Stoke startup/lineup on every changed game, plus earlier two-byte affected-club causal control; not every club rendered'}
    write_once(root/'closeout.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('native_proofs','runtime')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    run(p.parse_args().root)
