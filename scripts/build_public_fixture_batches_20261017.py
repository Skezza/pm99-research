"""Replay five discovered original fixture repairs and build affected games.

Two independent build workers, no preferred catalogue writes. A refused source
is retained as a gap instead of weakening the admission or blocking other years.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import UTC,datetime
import os
import shutil
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v2 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/public-fixture-batch-20261017-v2'
DISCOVERY=ROOT.parent/'frozen-fixture-next-batches-v2/reconciled-discovery.json'
RELEASE='sourced-public-original-fixture-reserves-20261017-r124a'
REPLAY='replayed-public-original-fixture-reserves-20261017-r124b'


def share_verified(actual,rebuilt,folder):
    rows=[]
    for a,b in ((actual.package_path,rebuilt.package_path),
            *((actual.game_path/'DBDAT'/name,rebuilt.game_path/'DBDAT'/name) for name in ('JUG98030.FDI','MINIFOTO.PKF'))):
        digest=registry.sha256_file(a)
        if registry.sha256_file(b)!=digest:raise ValueError('SOURCE sharing refuses any changed bytes')
        was_shared=a.stat().st_ino==b.stat().st_ino
        if not was_shared:
            temporary=b.with_name(b.name+'.verified-source-link')
            if temporary.exists():raise ValueError('unreceipted sharing temporary must be inspected')
            os.link(a,temporary);os.replace(temporary,b)
        rows.append(dict(source=registry.relative_workspace_path(a),retained_replay_path=registry.relative_workspace_path(b),
            sha256=digest,bytes=a.stat().st_size,already_shared=was_shared,all_bytes_and_paths_preserved=True))
    retained(folder/'verified-SOURCE-content-sharing.json',dict(rows=rows,
        policy='Exact whole SOURCE inventory/recipe verified first. All original/replay paths retained. Future file updates must use atomic replacement, never in-place writes to immutable hardlinks.'))


def build_one(row):
    season=row['season'];folder=ROOT/season
    if (folder/'complete-SOURCE-replay.json').exists():
        return dict(season=season,status='complete-SOURCE-replay-already-exists-inspect-before-resume')
    base=registry.load_registered_release(season,row['release_id'])
    if (base.release_id,base.manifest_sha256,registry.sha256_file(base.package_path))!=(
            row['release_id'],row['manifest_sha256'],row['package_sha256']):
        raise ValueError('discovered baseline advanced; do not overwrite intervening corrections')
    folder.mkdir(parents=True,exist_ok=True)
    input_path=folder/'opening-fixture-input.json';plan_path=folder/'ownership-plan.json'
    if registry.locator_path(season,RELEASE).exists():raise ValueError('partial existing game needs inspection, not regeneration')
    decisions=[{k:r[k] for k in ('source_person_id','displaced_carrier','retained_carrier','replacement_name','replacement_source_person_id')}
        for r in row['candidates']]
    retained(input_path,dict(schema=source.INPUT_SCHEMA,season=season,cases=decisions))
    try:
        plan=source.prepare(base,input_path)
    except (ValueError,KeyError,pipeline.PipelineError) as exc:
        result=dict(season=season,status='original-source-admission-refused-not-built',error=str(exc),
            source_discovery_approved=False,native_writes=0)
        retained(folder/'source-gap.json',result);print(result,flush=True);return result
    if {p['case_id'] for p in plan['bindings']['positive_pairs']}!={c['frozen_case_id'] for c in row['candidates']}:
        raise ValueError('source admission resolved another frozen cohort')
    retained(plan_path,plan)
    descriptor=folder/'inert.json';retained(descriptor,dict(season=season,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free<8.15*1024**3:raise ValueError('batch paused before crossing unchanged8GiB reserve')
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,ownership_plan_path=plan_path)
    print(dict(season=season,actual_private_game_built=True,source_repaired_slots=len(plan['updates'])),flush=True)
    proof=folder/'native-byte-proof.json';verify_native_batch(ROOT,RELEASE,proof,seasons=[season])
    actual=registry.load_registered_release(season,RELEASE)
    result=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(season,REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('whole SOURCE recipe differs')
    share_verified(actual,rebuilt,folder)
    retained(folder/'complete-SOURCE-replay.json',dict(result,actual_release_id=RELEASE,replay_release_id=REPLAY,
        source_release_id=base.release_id,manifest_sha256=actual.manifest_sha256,
        native_proof_sha256=registry.sha256_file(proof),source_plan_sha256=registry.sha256_file(plan_path)))
    result=dict(season=season,status='actual-private-native-and-whole-SOURCE-complete',players=len(plan['updates']),
        cases=[p['case_id'] for p in plan['bindings']['positive_pairs']],preferred_changed=False,runtime_pending=True)
    retained(folder/'build-summary.json',result);print(result,flush=True);return result


def main():
    if ROOT.exists():raise ValueError('batch workspace exists; inspect running/completed jobs before resuming')
    ROOT.mkdir(parents=True)
    discovery=pipeline.read_json_file(DISCOVERY);rows=[r for r in discovery['seasons'] if r['candidates']]
    retained(ROOT/'batch-input.json',dict(discovery=source.binding(DISCOVERY),seasons=rows,preferred_writes=0))
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(build_one,row):row['season'] for row in rows}
        for future in as_completed(jobs):
            season=jobs[future]
            try:result=future.result()
            except Exception as exc:
                result=dict(season=season,status='build-stopped-inspect-partial-state',error=type(exc).__name__+': '+str(exc),rerun_automatically=False)
                retained(ROOT/season/'build-failure.json',result);print(result,flush=True)
            results.append(result)
    retained(ROOT/'batch-summary.json',dict(utc=datetime.now(UTC).isoformat(),rows=sorted(results,key=lambda r:r['season']),
        preferred_changed=False,regenerated_unaffected_seasons=0,global_historical_RC=False,
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',machine='joe-Vostro-3350'))


if __name__=='__main__':main()
