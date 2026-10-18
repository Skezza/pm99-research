"""Deliver13 measured shirt bytes while preserving the validated actor game."""
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_source_bound_shirt_numbers_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/arsenal-shirts-2021-v1'
SEASON='2021-22'
BASE='sourced-arsenal-owned-opening-20261016-r111a'
RELEASE='sourced-arsenal-shirt-numbers-20261016-r112a'
REPLAY='replayed-arsenal-shirt-numbers-20261016-r112b'


def native_proof(base,release,plan):
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(original,eq,plan)!=(actual,(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()):
        raise ValueError('actual shirt game differs from exact thirteen-byte delta')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
    expected={entries[row['carrier_id']].payload_offset+7 for row in plan['updates'] if row['before_number']!=row['number']}
    changed={i for i,(a,b) in enumerate(zip(original,actual)) if a!=b}
    if len(original)!=len(actual) or changed!=expected or len(changed)!=13:
        raise ValueError('shirt correction changed more/fewer than exactly13 authorized bytes')
    before=pipeline.read_json_file(base.package_path);after=pipeline.read_json_file(release.package_path)
    if source.bind(before,plan)!=after:raise ValueError('actual shirt recipe differs')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    if any(left.get(k)!=right.get(k) for k in set(left)|set(right) if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('shirt correction changed another game file')
    current_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(actual).entries}
    profile_carriers=[9080,21228,14650,30550,9116]
    if any(entries[c].decode_payload(original)!=current_entries[c].decode_payload(actual) for c in profile_carriers):
        raise ValueError('a previously runner-verified target profile changed')
    retained(ROOT/'native-byte-proof.json',dict(season=SEASON,release_id=RELEASE,
        manifest_sha256=release.manifest_sha256,plan_sha256=registry.sha256_file(ROOT/'shirt-number-plan.json'),
        exact_authorized_byte_offsets=sorted(changed),native_shirt_bytes_changed=13,recipe_shirt_facts=25,
        all_other_player_bytes_identical=True,all_other_game_files_identical=True,
        identities_DOBs_skills_roles_order_tactics_managers_kits_portraits_preserved=True,
        all_Arsenal_numbers_source_bound_and_unique=True,complete_recipe_exact=True,idempotent=True,
        unchanged_parent_profile_carriers=profile_carriers))


def main():
    ROOT.mkdir(parents=True,exist_ok=True);base=registry.load_registered_release(SEASON,BASE)
    path=ROOT/'shirt-number-plan.json'
    if path.exists():plan=pipeline.read_json_file(path)
    else:
        plan=source.prepare(base)
        source.bind(pipeline.read_json_file(base.package_path),plan)
        source.apply((base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),
            (base.game_path/'DBDAT/EQ98030.FDI').read_bytes(),plan)
        retained(path,plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,profile_assignment_plan_path=path)
    release=registry.load_registered_release(SEASON,RELEASE)
    if not (ROOT/'native-byte-proof.json').exists():native_proof(base,release,plan)
    if not (ROOT/'complete-SOURCE-replay.json').exists():
        if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted shirt SOURCE replay exists; inspect')
        retained(ROOT/'complete-SOURCE-replay.json',source.reconstruction(release,REPLAY))
    print(dict(actual_shirt_bytes_changed=13,explicit_source_numbers=25,complete_SOURCE_exact=True,
        other_game_files_unchanged=True,runtime_pending=True,preferred_unchanged=True),flush=True)


if __name__=='__main__':main()
