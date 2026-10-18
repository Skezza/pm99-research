"""Build the exact sourced midfield correction atop the private country fix."""
import shutil

from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_exact_primary_position_delta_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_shinnie_country_20261017 as country
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = country.ROOT/'position-delivery'
BASE = country.RELEASE
RELEASE = 'sourced-shinnie-exact-midfield-20261017-r126a'
REPLAY = 'replayed-shinnie-exact-midfield-20261017-r126b'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if registry.locator_path(country.SEASON, RELEASE).exists():
        raise ValueError('existing position game needs inspection, never automatic rebuild')
    base = registry.load_registered_release(country.SEASON, BASE)
    plan = source.prepare(base, [9718])
    row = plan['updates'][0]
    if len(plan['updates']) != 1 or row['primary_position'] != 'M' or row['fine_roles'] != [14,9]:
        raise ValueError('one source-proven CDM/CM correction expected')
    path = ROOT/'position-plan.json'; retained(path,plan)
    descriptor = ROOT/'inert.json'
    retained(descriptor,dict(season=country.SEASON,release_id=BASE,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free < 8.15*1024**3:
        raise ValueError('retain source plan before unchanged8GiB reserve is threatened')
    publisher.publish(country.SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,
        profile_assignment_plan_path=path)
    actual = registry.load_registered_release(country.SEASON,RELEASE)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    entry=entries[9718];payload=entry.decode_payload(after)
    native=source.roster.native_player(payload,9718);end=native['name_end']
    allowed={entry.payload_offset+end+offset for offset in (*range(2,8),11)}
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    if (len(before)!=len(after) or not changed or not changed<=allowed
            or native['position']!='M' or native['roles']!=[14,9,98,98,98,98]
            or payload[end+10]!=entry.decode_payload(before)[end+10]):
        raise ValueError('independent native broad/fine midfield readback differs')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left)!=set(right) or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('position edit changes another game file')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('position recipe differs from exact two-field source transaction')
    retained(ROOT/'native-byte-proof.json',dict(carrier_id=9718,native=native,
        native_bytes_changed=len(changed),all_other_native_bytes_identical=True,all_other_game_files_identical=True,
        all_skills_country_identity_and_tactical_coordinates_unchanged=True,
        manifest_sha256=actual.manifest_sha256,source_plan_sha256=registry.sha256_file(path)))
    replay=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(country.SEASON,REPLAY)
    share_verified(actual,rebuilt,ROOT)
    retained(ROOT/'complete-SOURCE-replay.json',replay)
    retained(ROOT/'build-summary.json',dict(actual_native_midfield_and_SOURCE_complete=True,
        source_roles=['CDM','CM'],native_roles=[14,9],preferred_changed=False,
        country_fix_inherited=True,source_ownership_and_tactical_deployment_approval=False,runtime_pending=True))
    print(dict(actual_midfield_game_built=True,complete_SOURCE=True,runtime_pending=True),flush=True)


if __name__=='__main__':
    main()
