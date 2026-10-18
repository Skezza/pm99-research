"""Deliverable two-byte native corrections, independently checked and replayed."""
import argparse
import shutil
from app.fdi_indexed import IndexedFDIFile
from scripts import season_preetz_period_profile_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_public_fixture_batches_20261017 import share_verified

ROOT=source.registry.ROOT/'.local/consolidated-audit-20261009/preetz-period-profile-20261017'
RELEASE='sourced-preetz-period-profile-20261017-r138a'
REPLAY='replayed-preetz-period-profile-20261017-r138b'


def verify_native(base,actual,plan):
    source.verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq):
        raise ValueError('Preetz actual two-byte delta/idempotence differs')
    entry=next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id==plan['carrier_id'])
    payload=entry.decode_payload(after);native=source.roster.native_player(payload,plan['carrier_id'])
    if native['position']!='F' or native['roles']!=[12,98,98,98,98,98] or payload[native['name_end']+8]^0x61!=plan['native_country_code']:
        raise ValueError('Preetz actual country or profile role wrong')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if left.keys()!=right.keys() or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('Preetz correction changed another game file')
    if source.bind(source.pipeline.read_json_file(base.package_path),plan)!=source.pipeline.read_json_file(actual.package_path):
        raise ValueError('Preetz actual recipe changed beyond source-bound nationality/roles/provenance')
    return dict(season=base.season,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        native_byte_changes=2,native_country='GERMANY',native_roles=native['roles'],
        all_dates_ten_skills_names_other_roles_broad_position_rosters_tactics_managers_assets_EXE_preserved=True,
        global_historical_RC=False)


def main(season):
    folder=ROOT/season
    if (folder/'profile-plan.json').exists() or source.registry.locator_path(season,RELEASE).exists():
        raise ValueError('existing Preetz transaction must be inspected, not regenerated')
    base=source.registry.load_preferred_release(season);plan=source.prepare(base)
    folder.mkdir(parents=True,exist_ok=True);path=folder/'profile-plan.json';retained(path,plan)
    descriptor=folder/'inert.json'
    retained(descriptor,dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:raise ValueError('Preetz build requires unchanged normal disk reserve')
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=source.registry.load_registered_release(season,RELEASE)
    retained(folder/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=source.reconstruction(actual,REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Preetz complete SOURCE replay failed')
    share_verified(actual,source.registry.load_registered_release(season,REPLAY),folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    print(dict(season=season,Preetz_Germany_striker_built=True,native_byte_changes=2,SOURCE_identical=True,preferred_changed=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=source.TARGETS,required=True)
    main(parser.parse_args().season)
