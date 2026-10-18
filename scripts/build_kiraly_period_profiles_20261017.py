"""Build only explicit faulty Kiraly seasons, with complete SOURCE replay."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import shutil
from scripts import season_kiraly_period_profile_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=source.registry.ROOT/'.local/consolidated-audit-20261009/kiraly-period-profiles-20261017'
RELEASE='sourced-kiraly-period-profiles-20261017-r141a'
REPLAY='replayed-kiraly-period-profiles-20261017-r141b'


def verify_native(base,actual,plan):
    source.verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq):
        raise ValueError('actual Kiraly country/keeper bytes or idempotence differ')
    entry=next(e for e in source.IndexedFDIFile.from_bytes(after).entries if e.record_id==plan['carrier_id'])
    payload=entry.decode_payload(after);native=source.roster.native_player(payload,plan['carrier_id'])
    if native['position']!='G' or native['roles']!=[0,98,98,98,98,98] or payload[native['name_end']+8]^0x61!=plan['native_country_code']:
        raise ValueError('actual Kiraly native readback is not Hungary/GK')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if left.keys()!=right.keys() or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('Kiraly correction changed another game file')
    if source.bind(source.pipeline.read_json_file(base.package_path),plan)!=source.pipeline.read_json_file(actual.package_path):
        raise ValueError('Kiraly actual recipe changed outside country/keeper declaration/provenance')
    return dict(season=base.season,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        native_byte_changes=plan['expected_native_byte_changes'],carrier_id=plan['carrier_id'],native_country='HUNGARY',
        native_roles=native['roles'],native_family=native['family'],
        all_other_people_dates_names_skills_broad_positions_orders_rosters_tactics_managers_assets_EXE_preserved=True,
        historical_opening_owner_or_squad_approved=False,global_historical_RC=False)


def build_one(season,resume_pre_native=False,source_release=None):
    folder=ROOT/season;path=folder/'profile-plan.json';descriptor=folder/'inert.json'
    if source.registry.locator_path(season,RELEASE).exists():raise ValueError('existing Kiraly game needs inspection, not regeneration')
    base=(source.registry.load_registered_release(season,source_release) if source_release
          else source.registry.load_preferred_release(season))
    if source_release:
        source.pipeline.assert_tree_matches_inventory(base.game_path,source.pipeline.read_json_file(base.inventory_path))
    if resume_pre_native:
        workspace=source.registry.ROOT/'.local/historical-role-deltas-v1'/season/RELEASE
        if workspace.exists() or not path.is_file() or not descriptor.is_file() or not (folder/'pre-native-disk-stop.json').is_file():
            raise ValueError('only exact saved pre-native disk stop can resume')
        stop=source.pipeline.read_json_file(folder/'pre-native-disk-stop.json')
        if stop.get('native_build_started') is not False or stop.get('source_plan_sha256')!=source.registry.sha256_file(path):
            raise ValueError('saved pre-native country stop does not bind exact source plan')
        plan=source.pipeline.read_json_file(path);source.verify(base,plan)
    else:
        if path.exists():raise ValueError('saved country plan requires inspection before explicit pre-native resume')
        plan=source.prepare(base);folder.mkdir(parents=True,exist_ok=True);retained(path,plan)
        retained(descriptor,dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],
            jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    expected=dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
    if source.pipeline.read_json_file(descriptor)!=expected:raise ValueError('Kiraly descriptor differs from verified parent')
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:
        retained(folder/'pre-native-disk-stop.json',dict(source_plan_sha256=source.registry.sha256_file(path),native_build_started=False))
        raise ValueError('Kiraly source retained; normal preflight reserve requires space before native writes')
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=source.registry.load_registered_release(season,RELEASE)
    retained(folder/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=source.reconstruction(actual,REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Kiraly complete SOURCE replay failed')
    share_verified(actual,source.registry.load_registered_release(season,REPLAY),folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    result=dict(season=season,native_Hungary_and_keeper_built=True,native_bytes_changed=plan['expected_native_byte_changes'],
        SOURCE_identical=True,preferred_changed=False,runtime_pending=True)
    retained(folder/'build-summary.json',result);print(result,flush=True);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seasons',nargs='+',choices=source.TARGETS,required=True)
    parser.add_argument('--workers',type=int,choices=[1,2],default=2);parser.add_argument('--resume-pre-native',action='store_true')
    parser.add_argument('--source-release',help='Explicit immutable registered parent for one season; publication still requires this parent to become the validated default first.')
    args=parser.parse_args()
    if len(args.seasons)!=len(set(args.seasons)):parser.error('unique explicit seasons required')
    if args.source_release and len(args.seasons)!=1:parser.error('explicit source parent requires one season')
    failed=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(build_one,season,args.resume_pre_native,args.source_release):season for season in args.seasons}
        for job in as_completed(jobs):
            try:job.result()
            except Exception as exc:
                failed.append(jobs[job]);print(dict(season=jobs[job],build_stopped_inspect_partial_state=True,error=repr(exc)),flush=True)
    if failed:raise SystemExit(1)
