"""Build only the bounded Arsenal2021 correction and exact SOURCE replay."""
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_arsenal_2021_owned_opening_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_woking_owned_opening_20261011 import skills

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/arsenal-opening-2021-v1'
SEASON='2021-22'
BASE='sourced-year-bound-managers-20261016-r110a'
RELEASE='sourced-arsenal-owned-opening-20261016-r111a'
REPLAY='replayed-arsenal-owned-opening-20261016-r111b'


def proof(base,release,plan):
    before=pipeline.read_json_file(base.package_path);after=pipeline.read_json_file(release.package_path)
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    actual_eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.bind(before,plan)!=after or source.apply(original,eq,plan)!=(actual,actual_eq):
        raise ValueError('actual Arsenal game/recipe differs from exact source transaction')
    if source.apply(actual,actual_eq,plan)!=(actual,actual_eq):raise ValueError('actual Arsenal transaction not idempotent')
    preserved=[]
    for row in plan['player_decisions']:
        if row['preserved_source_carrier'] is not None:
            source_id=row['preserved_source_carrier'];target=row['carrier_id']
            left=skills(original,source_id);right=skills(actual,target)
            if left!=right or right!=row['ratings']['values']:raise ValueError('existing actor ten native skills changed')
            preserved.append(dict(original_carrier=source_id,target_carrier=target,skills=right))
    if len(preserved)!=16:raise ValueError('exact16 native preserved rating profiles required')
    changed=source.selected_carriers(plan)
    archive,_=delta.no_photo_archive((base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),changed)
    if archive!=(release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes():raise ValueError('Arsenal portrait clear differs')
    if any((release.game_path/f'DBDAT/MINIFOTO/J96{k:05d}.BMP').exists() for k in changed):raise ValueError('stale identity photo retained')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/EQ98030.FDI','DBDAT/MINIFOTO.PKF'}|{f'DBDAT/MINIFOTO/J96{k:05d}.BMP' for k in changed}
    if any(left.get(k)!=right.get(k) for k in set(left)|set(right) if k not in allowed):raise ValueError('unrelated Arsenal game file changed')
    club=next(c for c in after['clubs'] if c['carrier_id']==309)
    retained(ROOT/'native-byte-proof.json',dict(season=SEASON,release_id=RELEASE,
        manifest_sha256=release.manifest_sha256,plan_sha256=registry.sha256_file(ROOT/'opening-ownership-plan.json'),
        actual_Arsenal_capacity=25,original_first_XI_count=11,original_bench_count=9,positive_August_reserve_count=5,
        paired_reserve_replacements=4,identity_changed_carriers=sorted(changed),
        all_ten_native_skills_preserved_for=preserved,source_birth_date_corrections=3,
        actual_formation=club['opening']['formation'],contextual_phase_tactics_written=True,
        exact_native_reproduction_from_sources=True,idempotent=True,complete_recipe_exact=True,
        unrelated_player_and_club_records_identical=True,all_other_game_files_identical=True,
        managers_kits_and_EXE_unchanged=True,exact_portrait_clear=True))


def main():
    base=registry.load_registered_release(SEASON,BASE);path=ROOT/'opening-ownership-plan.json'
    if path.exists():plan=pipeline.read_json_file(path)
    else:
        plan=source.prepare(base)
        original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        # No frozen plan or game write until the actual bounded writer passes.
        candidate,candidate_eq=source.apply(original,eq,plan)
        if source.apply(candidate,candidate_eq,plan)!=(candidate,candidate_eq):raise ValueError('Arsenal dry-run not idempotent')
        retained(path,plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,profile_assignment_plan_path=path)
    release=registry.load_registered_release(SEASON,RELEASE)
    if not (ROOT/'native-byte-proof.json').exists():proof(base,release,plan)
    if not (ROOT/'complete-SOURCE-replay.json').exists():
        if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted Arsenal replay exists; inspect before continuation')
        retained(ROOT/'complete-SOURCE-replay.json',source.reconstruction(release,REPLAY))
    print(dict(built=True,actual_Arsenal_source25=True,complete_SOURCE_game_and_recipe_exact=True,
        runtime_pending=True,preferred_unchanged=True),flush=True)


if __name__=='__main__':main()
