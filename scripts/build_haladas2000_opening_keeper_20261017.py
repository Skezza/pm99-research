"""Build the source-positive keeper correction, not a wholesale Haladas rewrite."""
import shutil
import argparse
from scripts import season_haladas2000_opening_keeper_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=source.admission.ROOT
RELEASE='sourced-haladas2000-opening-keeper-20261017-r139a'
REPLAY='replayed-haladas2000-opening-keeper-20261017-r139b'
BASE='sourced-preetz-period-profile-20261017-r138a'


def verify_native(base,actual,plan):
    source.verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq):
        raise ValueError('actual Haladas opening keeper/idempotence differs')
    archive=(base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes();expected,offsets=source.delta.no_photo_archive(archive,{8507})
    if (actual.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()!=expected:raise ValueError('selected keeper old portrait not cleared exactly')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/MINIFOTO.PKF'}
    removed=set(left)-set(right)
    if set(right)-set(left) or removed-{'DBDAT/MINIFOTO/J9608507.BMP'} or any(left[k]!=right[k] for k in left.keys()&right.keys() if k not in allowed):
        raise ValueError('Haladas keeper changed an unrelated file/portrait/asset')
    if source.bind(source.pipeline.read_json_file(base.package_path),plan)!=source.pipeline.read_json_file(actual.package_path):
        raise ValueError('actual Haladas recipe differs from exact selected source actor')
    return dict(season=base.season,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        corrected_actor=source.admission.native.native_facts(after,8507),retained_actor=source.admission.native.native_facts(after,2211),
        retained_Kiraly_and_all_unrelated_players_exact=True,all_clubs_orders_tactics_managers_kits_EXE_exact=True,
        old_displaced_portrait_cleared=True,removed_loose_paths=sorted(removed),
        selected_portrait_directory_offsets={str(carrier):values for carrier,values in offsets.items()},
        frozen_case_id=plan['source_decision']['frozen_case_id'],
        full_Haladas_or_Hertha_squad_approved=False,global_historical_RC=False)


def main(resume_before_native=False):
    path=ROOT/'keeper-plan.json'
    if source.registry.locator_path('2000-01',RELEASE).exists():
        raise ValueError('existing Haladas game build must be inspected, not regenerated')
    base=source.registry.load_preferred_release('2000-01')
    if base.release_id!=BASE:raise ValueError('Haladas parent advanced; preserve intervening fixes')
    descriptor=ROOT/'inert.json'
    if resume_before_native:
        workspace=source.registry.ROOT/'.local/historical-role-deltas-v1'/base.season/RELEASE
        if workspace.exists() or not path.is_file() or not descriptor.is_file():
            raise ValueError('only the exact pre-native disk stop may resume; existing workspace requires inspection')
        plan=source.pipeline.read_json_file(path);source.verify(base,plan)
        expected=dict(season=base.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
            jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
        if source.pipeline.read_json_file(descriptor)!=expected:raise ValueError('pre-native descriptor differs')
    else:
        if path.exists():raise ValueError('saved pre-native plan needs explicit --resume-before-native')
        plan=source.prepare(base);retained(path,plan)
        retained(descriptor,dict(season=base.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
            jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:raise ValueError('Haladas requires unchanged normal disk reserve')
    publisher.publish(base.season,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=source.registry.load_registered_release(base.season,RELEASE)
    retained(ROOT/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=source.reconstruction(actual,REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Haladas whole SOURCE proof incomplete')
    share_verified(actual,source.registry.load_registered_release(base.season,REPLAY),ROOT)
    retained(ROOT/'complete-SOURCE-replay.json',replay)
    print(dict(actual_positive_Haladas_opening_keeper_built=True,SOURCE_identical=True,preferred_changed=False,runtime_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--resume-before-native',action='store_true')
    main(parser.parse_args().resume_before_native)
