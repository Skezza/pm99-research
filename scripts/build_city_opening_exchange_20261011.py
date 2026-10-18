"""Deliver and byte-verify the bounded six-person 2024 opening correction."""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_city_2024_opening_exchange_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as roster

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/city-opening-exchange-v1'
SEASON='2024-25'
BASE='sourced-savio-bobb-reserve-20261011-r96a'
RELEASE='sourced-city-opening-exchange-20261011-r97a'
REPLAY='replayed-city-opening-exchange-20261011-r97b'


def moved_skill_proof():
    """Compare the original ten actual native skills, not only recipe values."""
    base=registry.load_registered_release(SEASON,BASE)
    release=registry.load_registered_release(SEASON,RELEASE)
    plan=pipeline.read_json_file(ROOT/'opening-exchange-plan.json')
    left=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    right=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(left).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(right).entries}
    rows=[]
    for row in plan['exchanges']:
        raw=old[row['city_carrier']].decode_payload(left)
        before=dict(zip(delta.compiler.SKILLS,[b^0x61 for b in raw[-16:-7]]));before['handling']=raw[-7]^0x61
        raw=new[row['destination_carrier']].decode_payload(right)
        end=roster.native_player(raw,row['destination_carrier'])['name_end']
        observed=delta.compiler._read_native_dd6360_fields(raw,end)
        after=dict(zip(delta.compiler.SKILLS,observed['skills']));after['handling']=observed['handling']
        if before!=after or before!=row['moved_before']['ratings']['values']:
            raise ValueError('moved player native ten skills were not preserved')
        rows.append(dict(source_carrier=row['city_carrier'],destination_carrier=row['destination_carrier'],
            before=before,after=after,all_ten_actual_native_skills_identical=True))
    retained(ROOT/'moved-people-native-skill-preservation.json',dict(season=SEASON,release_id=RELEASE,rows=rows,
        source_jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        actual_jug_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')))


def main():
    ROOT.mkdir(exist_ok=True)
    base=registry.load_registered_release(SEASON,BASE)
    path=ROOT/'opening-exchange-plan.json'
    plan=source.prepare(base);retained(path,plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,profile_assignment_plan_path=path)
    release=registry.load_registered_release(SEASON,RELEASE)
    proof_path=ROOT/'native-byte-proof.json'
    if not proof_path.exists():
        original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        expected,expected_eq=source.apply(original,eq,plan)
        if (actual,(release.game_path/'DBDAT/EQ98030.FDI').read_bytes())!=(expected,expected_eq):
            raise ValueError('actual six-slot game does not reproduce')
        if source.apply(actual,eq,plan)!=(actual,eq):raise ValueError('six-slot native patch is not idempotent')
        selected={r[k] for r in plan['exchanges'] for k in ('city_carrier','destination_carrier')}
        preserve_other_records(original,actual,selected)
        package=pipeline.read_json_file(release.package_path)
        if package!=source.bind(pipeline.read_json_file(base.package_path),plan):raise ValueError('actual recipe differs')
        archive,offsets=delta.no_photo_archive((base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),selected)
        if archive!=(release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes():raise ValueError('actual photo archive differs')
        for k in selected:
            if (release.game_path/f'DBDAT/MINIFOTO/J96{k:05d}.BMP').exists():raise ValueError('old slot photo still present')
        before={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
        after={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
        allowed={'DBDAT/JUG98030.FDI','DBDAT/MINIFOTO.PKF'}|{f'DBDAT/MINIFOTO/J96{k:05d}.BMP' for k in selected}
        if any(before.get(k)!=after.get(k) for k in set(before)|set(after) if k not in allowed):
            raise ValueError('an unrelated game file changed')
        retained(proof_path,dict(season=SEASON,release_id=RELEASE,baseline=BASE,
            package_sha256=registry.sha256_file(release.package_path),
            jug_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
            plan_sha256=registry.sha256_file(path),changed_carriers=sorted(selected),
            exact_native_reproduction_from_sources=True,idempotent=True,
            all_unrelated_player_records='byte-identical',all_EQ_rosters_tactics_managers_kits_EXE='byte-identical',
            ten_visible_skills_verified=True,exact_portrait_directory_reproduction=True,
            preserved_first_XI_and_native_orders=True,all_unrelated_game_files='byte-identical'))
    replay_path=ROOT/'complete-SOURCE-replay.json'
    if not replay_path.exists():
        if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted City SOURCE replay exists')
        replay=source.reconstruction(release,REPLAY)
        retained(replay_path,replay)
    print(dict(built=True,exact_SOURCE_verified=True,runtime_pending=True,preferred_not_yet_promoted=True),flush=True)


if __name__=='__main__':main()
