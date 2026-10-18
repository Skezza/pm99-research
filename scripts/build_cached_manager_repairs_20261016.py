"""Build real source-verified coach corrections on the completed role games.

Private candidates only: publication must await parent rollout and fresh
runner review. No ratings, player identities, tactics or artwork are rewritten.
"""
import argparse
import os
import shutil
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_registered_quality_release_v1 as builder
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_donor_role_safety_20261016 import ROOT as ROLE_ROOT, RELEASE as BASE
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/cached-manager-delivery-20261016-v1'
RELEASE='sourced-cached-managers-20261016-r109a'
REPLAY='replayed-cached-managers-20261016-r109b'


def build(season, *, batch_root=ROOT,release_id=RELEASE,replay_id=REPLAY,source_module=source,source_release_id=None):
    ROOT,RELEASE,REPLAY,source=batch_root,release_id,replay_id,source_module
    root=ROOT/season;root.mkdir(parents=True,exist_ok=True)
    if (root/'complete-SOURCE-replay.json').exists():
        print(dict(season=season,reused_completed_private_manager_build=True),flush=True);return
    if not (ROLE_ROOT/season/'complete-SOURCE-replay.json').exists():
        raise ValueError('parent role game is not complete; wait for the live own builder')
    if shutil.disk_usage(root).free<8.3*1024**3:
        raise ValueError('manager build refuses to threaten8GiB reserve')
    base_id=BASE if source_release_id is None else source_release_id
    base=registry.load_registered_release(season,base_id)
    path=root/'manager-plan.json'
    plan=source.prepare(base)
    if not plan['updates']:
        retained(root/'no-native-or-recipe-correction-needed.json',plan)
        print(dict(season=season,corrections=0,game_not_rebuilt=True),flush=True);return
    retained(path,plan)
    descriptor=dict(season=season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[])
    inert=root/'inert.json';retained(inert,descriptor)
    if not registry.locator_path(season,RELEASE).exists():
        publisher.publish(season,inert,release_id=RELEASE,source_release_id=base_id,manager_plan_path=path)
    actual=registry.load_registered_release(season,RELEASE)
    before=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    selected={r['carrier_id'] for r in plan['updates']}
    preserve_other_records(before,after,selected)
    holders,names=_manager_graph(eq_path=actual.game_path/'DBDAT/EQ98030.FDI',
        ent_path=actual.game_path/'DBDAT/ENT98030.FDI')
    changes=0
    for row in plan['updates']:
        if names[row['carrier_id']]!=row['native_after'] or [c['carrier_id'] for c in holders[row['carrier_id']]]!=[row['club_carrier_id']]:
            raise ValueError('independent actual coach identity/owner readback failed')
        changes+=row['native_before']!=row['native_after']
    old={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    new={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if any(old.get(k)!=new.get(k) for k in set(old)|set(new) if k!='DBDAT/ENT98030.FDI'):
        raise ValueError('manager correction changed another game file')
    expected=publisher.updated_package(pipeline.read_json_file(base.package_path),descriptor,manager_plan=plan)
    if expected!=pipeline.read_json_file(actual.package_path):
        raise ValueError('actual complete recipe differs from selected manager correction')
    retained(root/'native-byte-proof.json',dict(season=season,release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256,plan_sha256=registry.sha256_file(path),
        ENT_sha256=registry.sha256_file(actual.game_path/'DBDAT/ENT98030.FDI'),
        canonical_manager_corrections=len(plan['updates']),native_manager_name_changes=changes,
        all_unselected_ENT_records_identical=True,all_other_game_files_identical=True,
        complete_recipe_exact=True,original_source_reparsed=True,preferred_unchanged=True))
    if registry.locator_path(season,REPLAY).exists():
        raise ValueError('unreceipted manager SOURCE replay; inspect before retry')
    replay=builder._build_manager_reconstruction(actual,release_id=REPLAY)
    if not replay or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('complete manager SOURCE replay failed')
    retained(root/'complete-SOURCE-replay.json',replay)
    rebuilt=registry.load_registered_release(season,REPLAY)
    for a,b in ((actual.package_path,rebuilt.package_path),
        (actual.game_path/'DBDAT/ENT98030.FDI',rebuilt.game_path/'DBDAT/ENT98030.FDI')):
        if registry.sha256_file(a)!=registry.sha256_file(b):raise ValueError('own manager replay content differs')
        if a.stat().st_ino!=b.stat().st_ino:
            temporary=b.with_name(b.name+'.verified-link')
            if temporary.exists():raise ValueError('unreceipted manager sharing temporary')
            os.link(a,temporary);os.replace(temporary,b)
    print(dict(season=season,canonical_manager_corrections=len(plan['updates']),
        native_manager_name_changes=changes,complete_SOURCE_exact=True,preferred_unchanged=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='*',default=['2000-01'])
    args=parser.parse_args()
    for season in registry.supported_seasons() if args.seasons==['all'] else args.seasons:build(season)
