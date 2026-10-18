"""Build one sourced country byte, preserving the delivered opening repair."""
import shutil
from app.fdi_indexed import IndexedFDIFile
from scripts import season_takano_period_country_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_morecambe_owned_opening_20261017 import RELEASE as BASE

ROOT=source.registry.ROOT/'.local/consolidated-audit-20261009/takano-period-country-20261017'
SEASON='2000-01'
RELEASE='sourced-takano-period-country-20261017-r136a'
REPLAY='replayed-takano-period-country-20261017-r136b'


def verify_native(base,actual,plan):
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq):
        raise ValueError('actual Takano single-byte delta/idempotence differs')
    entry=next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id==10992)
    raw=entry.decode_payload(after);end=source.evidence.source.roster.native_player(raw,10992)['name_end']
    if raw[end+8]^0x61!=plan['native_country_code']:raise ValueError('actual decoded Takano country is not Japan')
    left={r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if left.keys()!=right.keys() or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('country-only repair changed another game file')
    if source.bind(source.pipeline.read_json_file(base.package_path),plan)!=source.pipeline.read_json_file(actual.package_path):
        raise ValueError('actual country recipe changes outside declared nationality/fallback/provenance')
    return dict(season=SEASON,release_id=actual.release_id,manifest_sha256=actual.manifest_sha256,
        native_byte_changes=1,native_country='JAPAN',all_birthdays_skills_names_roles_orders_rosters_and_other_game_files_unchanged=True,
        optional_birthday_dispute_retained=True,all_opening_squad_fixes_preserved=True,global_historical_RC=False)


def main():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'country-plan.json').exists() or source.registry.locator_path(SEASON,RELEASE).exists():
        raise ValueError('existing Takano country build needs inspection, not regeneration')
    base=source.registry.load_registered_release(SEASON,BASE)
    plan=source.prepare(base);retained(ROOT/'country-plan.json',plan)
    descriptor=ROOT/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(source.registry.ROOT).free<8.15*1024**3:raise ValueError('country build needs normal free-space reserve')
    publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=base.release_id,profile_assignment_plan_path=ROOT/'country-plan.json')
    actual=source.registry.load_registered_release(SEASON,RELEASE)
    retained(ROOT/'native-byte-proof.json',verify_native(base,actual,plan))
    replay=source.reconstruction(actual,REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('country full SOURCE proof incomplete')
    share_verified(actual,source.registry.load_registered_release(SEASON,REPLAY),ROOT)
    retained(ROOT/'complete-SOURCE-replay.json',replay)
    print(dict(actual_Japan_country_and_SOURCE_built=True,native_byte_changes=1,runtime_pending=True,preferred_changed=False),flush=True)


if __name__=='__main__':main()
