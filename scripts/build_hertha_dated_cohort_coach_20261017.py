"""Build coupled club/coach fixes without rewriting any player or assets."""
import argparse
import shutil
from scripts import season_period_cohort_coach_v3 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_registered_quality_release_v1 as reconstruction
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=source.admission.ROOT
RELEASE='sourced-hertha-dated-cohort-coach-20261017-r142a'
REPLAY='replayed-hertha-dated-cohort-coach-20261017-r142b'


def verify_native(base,actual,plan):
    source.verify(base,plan)
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes();after_eq=(actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    expected,changes=source.prior.labels.rewrite_club_labels(eq,plan['updates'])
    if expected!=after_eq or len(changes)!=1:raise ValueError('coupled native club labels differ')
    before_index={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(eq).entries}
    after_index={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(after_eq).entries}
    if before_index.keys()!=after_index.keys():raise ValueError('club directory IDs changed')
    for carrier,entry in after_index.items():
        before=before_index[carrier].decode_payload(eq);after=entry.decode_payload(after_eq)
        if carrier==421:
            if source.prior.labels.prefix_parts(before)[2]!=source.prior.labels.prefix_parts(after)[2]:
                raise ValueError('club names changed ground/manager link/roster/tactics/unknown tail')
        elif before!=after:raise ValueError('another native club changed')
    ent=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes();after_ent=(actual.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    old={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(ent).entries}
    new={e.record_id:e for e in source.prior.IndexedFDIFile.from_bytes(after_ent).entries}
    if old.keys()!=new.keys():raise ValueError('manager directory IDs changed')
    for carrier,entry in new.items():
        before=old[carrier].decode_payload(ent)
        expected=publisher._patch_ent_name(before,carrier,'Stevens') if carrier==1313 else before
        if entry.decode_payload(after_ent)!=expected:raise ValueError('manager bytes differ outside exact selected name')
    holders,names=source.prior.old._manager_graph(eq_path=actual.game_path/'DBDAT/EQ98030.FDI',ent_path=actual.game_path/'DBDAT/ENT98030.FDI')
    if names[1313]!='Stevens' or [c['carrier_id'] for c in holders[1313]]!=[421]:raise ValueError('actual sourced coach owner/name differs')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if left.keys()!=right.keys() or any(left[k]!=right[k] for k in left if k not in ('DBDAT/EQ98030.FDI','DBDAT/ENT98030.FDI')):
        raise ValueError('coupled name correction changed players/assets/EXE/another file')
    inert=source.pipeline.read_json_file(ROOT/base.season/'inert.json')
    expected=publisher.updated_package(source.pipeline.read_json_file(base.package_path),inert,
        manager_plan=plan['manager_plan'],club_plan=plan)
    if expected!=source.pipeline.read_json_file(actual.package_path):raise ValueError('coupled recipe differs outside declared identities/provenance')
    return dict(season=base.season,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        club_carrier_id=421,native_club='Hertha Berlin',manager_carrier_id=1313,native_manager='Stevens',
        sourced_manager_identity='Huub Stevens',represented_raw_and_native_cohort=25,
        all_players_skills_dates_positions_orders_tactics_ground_kits_photos_EXE_preserved=True,
        full_opening_XI_or_kit_design_approved=False,global_historical_RC=False)


def main(season):
    folder=ROOT/season;folder.mkdir(parents=True,exist_ok=True)
    path=folder/'club-plan.json'
    if path.exists() or source.registry.locator_path(season,RELEASE).exists():
        raise ValueError('existing coupled build must be inspected, not regenerated')
    base=source.registry.load_preferred_release(season)
    if base.release_id!='sourced-kiraly-period-profiles-20261017-r141a':
        raise ValueError('source parent must retain the delivered Kiraly correction')
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:
        raise ValueError('normal pre-native reserve requires space; no game write attempted')
    plan=source.prepare(base);retained(path,plan)
    retained(folder/'manager-plan.json',plan['manager_plan'])
    retained(folder/'inert.json',dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    publisher.publish(season,folder/'inert.json',release_id=RELEASE,source_release_id=base.release_id,
        club_plan_path=path,manager_plan_path=folder/'manager-plan.json')
    actual=source.registry.load_registered_release(season,RELEASE)
    retained(folder/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=reconstruction._build_manager_reconstruction(actual,release_id=REPLAY)
    if not replay or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('coupled complete SOURCE replay failed')
    share_verified(actual,source.registry.load_registered_release(season,REPLAY),folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    retained(folder/'build-summary.json',dict(coupled_club_and_manager_game_and_SOURCE_built=True,
        preferred_changed=False,all_player_and_asset_bytes_preserved=True,runtime_pending=True))
    print(dict(season=season,actual_coupled_club_and_coach_built=True,SOURCE_exact=True,preferred_changed=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=['2002-03','2003-04'],required=True)
    main(parser.parse_args().season)
