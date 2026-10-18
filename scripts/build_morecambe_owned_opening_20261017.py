"""Build actual Morecambe fixed-person correction plus full SOURCE replay."""
import shutil
from datetime import date
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_morecambe_2000_owned_opening_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_public_fixture_batches_20261017 import share_verified

ROOT=source.registry.ROOT/'.local/consolidated-audit-20261009/morecambe-owned-opening-20261017'
SEASON='2000-01'
RELEASE='sourced-morecambe-owned-opening-20261017-r135a'
REPLAY='replayed-morecambe-owned-opening-20261017-r135b'


def native_proof(base,actual,plan):
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after_eq=(actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,after_eq):raise ValueError('actual native Morecambe delta differs')
    package=source.pipeline.read_json_file(actual.package_path)
    if source.bind(source.pipeline.read_json_file(base.package_path),plan)!=package:
        raise ValueError('actual Morecambe recipe differs from source decision')
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(after).entries}
    verified=[]
    for row in plan['assignment']['rows']:
        carrier=row['carrier_id'];payload=new[carrier].decode_payload(after)
        native=source.roster.native_player(payload,carrier);end=native['name_end']
        birthday=date(int.from_bytes(bytes(b^0x61 for b in payload[end+14:end+16]),'little'),
            payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
        if (birthday!=row['birth_date'] or native['position']!=row['primary_position']
                or native['roles'][0]!=row['fine_roles'][0]
                or read_initial_order(payload).order!=row['opening_order']):
            raise ValueError('actual native Morecambe DOB/broad/fine/opening order readback differs')
        if row['identity_changed']:
            if source.roster.normalise(native['name'])!='marksmith' or source.skills(after,carrier)!=row['new_person_ratings']:
                raise ValueError('actual new starting goalkeeper identity/skills differ')
        else:
            original=old[carrier].decode_payload(before)
            original_end=source.roster.native_player(original,carrier)['name_end']
            allowed={end,*range(end+2,end+8),end+11,*range(end+12,end+16)}
            if (end!=original_end or len(payload)!=len(original)
                    or any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(original,payload)))
                    or source.skills(before,carrier)!=source.skills(after,carrier)):
                raise ValueError('retained Morecambe name/skills/secondary facts/opaque bytes changed')
            verified.append(carrier)
    portraits,_=source.delta.no_photo_archive((base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),{11002})
    if portraits!=(actual.game_path/'DBDAT/MINIFOTO.PKF').read_bytes():raise ValueError('new keeper portrait clear differs')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/EQ98030.FDI','DBDAT/MINIFOTO.PKF','DBDAT/MINIFOTO/J9611002.BMP'}
    if any(left.get(k)!=right.get(k) for k in set(left)|set(right) if k not in allowed):
        raise ValueError('Morecambe correction changed an unrelated game file')
    return dict(season=SEASON,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        exact_source_native_and_recipe_verified=True,original_eleven_and_bench_and_reserves=18,
        missing_starting_keeper_added=11002,retained_people_and_ten_native_skills=verified,
        retained_names_secondary_facts_unknown_bytes_and_portraits_preserved=True,
        unrelated_clubs_managers_ground_kits_EXE_unchanged=True,portrait_cleared_only_new_identity=True,
        exact_match_fine_roles_or_opaque_tactics_approved=False,global_historical_RC=False)


def main():
    ROOT.mkdir(exist_ok=True)
    base=source.registry.load_preferred_release(SEASON)
    if base.release_id!=source.admission.BASE:raise ValueError('Morecambe baseline advanced; preserve intervening changes')
    path=ROOT/'opening-ownership-plan.json'
    if path.exists():raise ValueError('existing Morecambe native transaction requires inspection, not a rebuild')
    plan=source.prepare(base);retained(path,plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:raise ValueError('Morecambe build needs normal reserve')
    publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=source.registry.load_registered_release(SEASON,RELEASE)
    retained(ROOT/'native-byte-proof.json',native_proof(base,actual,plan))
    replay=source.reconstruction(actual,REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Morecambe SOURCE replay incomplete')
    share_verified(actual,source.registry.load_registered_release(SEASON,REPLAY),ROOT)
    retained(ROOT/'complete-SOURCE-replay.json',replay)
    print(dict(actual_Morecambe_squad_and_SOURCE_built=True,runtime_pending=True,preferred_changed=False),flush=True)


if __name__=='__main__':main()
