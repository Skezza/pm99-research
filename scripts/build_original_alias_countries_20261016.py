"""Finish new alias actors' sourced nationality with one byte per game."""
import argparse
import os
import shutil
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_original_alias_countries_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/original-alias-countries-delivery-v1'
RELEASE='sourced-original-alias-countries-20261016-r120a'
REPLAY='replayed-original-alias-countries-20261016-r120b'


def build(season):
    root=ROOT/season
    if (root/'complete-SOURCE-replay.json').exists():raise ValueError('completed country game must not repeat')
    if shutil.disk_usage(registry.ROOT).free<8.3*1024**3:raise ValueError('country-only build refuses to threaten8GiB reserve')
    base=registry.load_registered_release(season,source.SPECS[season]['base']);plan=source.prepare(base)
    root.mkdir(parents=True,exist_ok=True);path=root/source.FILENAME;retained(path,plan)
    descriptor=root/'inert.json';retained(descriptor,dict(season=season,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if not registry.locator_path(season,RELEASE).exists():
        publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=path)
    actual=registry.load_registered_release(season,RELEASE)
    old=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();new=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(old,eq,plan)!=(new,eq) or source.apply(new,eq,plan)!=(new,eq):raise ValueError('actual country delta reproduction/idempotence failed')
    diffs=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
    if len(old)!=len(new) or len(diffs)!=1:raise ValueError('country correction is not exactly one byte')
    prior={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    after={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(prior)!=set(after) or any(prior[k]!=after[k] for k in prior if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('country delta changed another game file')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('entire country recipe differs from exact field-only reproduction')
    retained(root/'native-byte-proof.json',dict(season=season,release_id=RELEASE,manifest_sha256=actual.manifest_sha256,
        source_plan_sha256=registry.sha256_file(path),native_byte_changes=1,allowed_offsets=diffs,idempotent=True,
        all_other_game_files_identical=True,all_other_facts_skills_roles_shirts_tactics_managers_and_artwork_identical=True,
        published_nationality=plan['updates'][0]['after'],country_inferred_from_birthplace=False,historical_caps_claimed=False))
    if registry.locator_path(season,REPLAY).exists():raise ValueError('unreceipted country SOURCE exists; inspect rather than rerun')
    replay=source.reconstruction(actual,REPLAY)
    retained(root/'complete-SOURCE-replay.json',dict(replay,manifest_sha256=actual.manifest_sha256,preferred_unchanged=True))
    rebuilt=registry.load_registered_release(season,REPLAY)
    for a,b in ((actual.package_path,rebuilt.package_path),(actual.game_path/'DBDAT/JUG98030.FDI',rebuilt.game_path/'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a)!=registry.sha256_file(b):raise ValueError('new country SOURCE bytes differ before content sharing')
        if a.stat().st_ino!=b.stat().st_ino:
            temporary=b.with_name(b.name+'.verified-link')
            if temporary.exists():raise ValueError('unreceipted sharing temporary')
            os.link(a,temporary);os.replace(temporary,b)
    print(dict(season=season,actual_country_byte_fixed=True,country=plan['updates'][0]['after'],full_SOURCE_exact=True,preferred_unchanged=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('seasons',nargs='*',default=list(source.SPECS))
    args=parser.parse_args()
    for season in args.seasons:build(season)
