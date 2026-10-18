"""Build one explicit versioned country-policy correction, without promotion."""
import argparse
import shutil

from app.fdi_indexed import IndexedFDIFile
from scripts import season_original_country_policy_v2 as source
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/original-country-policy-v2-delivery-20261017'
RELEASE='sourced-original-country-policy-v2-20261017-r128a'
REPLAY='replayed-original-country-policy-v2-20261017-r128b'
PEOPLE=registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json'


def build(season,parent,carriers):
    folder=ROOT/season;folder.mkdir(parents=True,exist_ok=True)
    if registry.locator_path(season,RELEASE).exists() or (folder/'country-plan.json').exists():
        raise ValueError('existing country policy plan/game needs inspection; no blind regeneration')
    base=registry.load_registered_release(season,parent)
    plan=source.prepare(base,PEOPLE,{str(n):['nationality'] for n in carriers})
    if plan['unresolved'] or len(plan['updates'])!=len(carriers):
        retained(folder/'source-gap.json',plan)
        raise ValueError('explicit country policy targets not all positively admitted')
    path=folder/'country-plan.json';retained(path,plan)
    control=folder/'inert.json';retained(control,dict(season=season,release_id=parent,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free<8.15*1024**3:
        raise ValueError('source retained before unchanged8GiB reserve is threatened')
    publisher.publish(season,control,release_id=RELEASE,source_release_id=parent,profile_assignment_plan_path=path)
    actual=registry.load_registered_release(season,RELEASE)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed=set();observed=[]
    for row in plan['updates']:
        entry=entries[row['carrier_id']];raw=entry.decode_payload(after)
        end=source.original.audit.native_player(raw,row['carrier_id'])['name_end']
        if raw[end+8]^0x61!=row['native_country_code']:
            raise ValueError('actual native country policy code differs')
        allowed.add(entry.payload_offset+end+8)
        observed.append(dict(carrier_id=row['carrier_id'],nationality=row['nationality'],
            native_country_code=raw[end+8]^0x61,native_label=row['native_label']))
    if len(before)!=len(after) or any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(before,after))):
        raise ValueError('country policy changed unrelated native bytes')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left)!=set(right) or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('country policy changed other game files')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('country policy recipe differs from bounded source transaction')
    retained(folder/'native-byte-proof.json',dict(season=season,release_id=RELEASE,rows=observed,
        source_plan_sha256=registry.sha256_file(path),manifest_sha256=actual.manifest_sha256,
        all_other_native_game_and_recipe_facts_unchanged=True))
    replay=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(season,REPLAY);share_verified(actual,rebuilt,folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    retained(folder/'build-summary.json',dict(season=season,source_parent=parent,actual_country_policy_game_complete=True,
        complete_SOURCE=True,preferred_changed=False,changed_countries=len(observed),runtime_pending=True))
    print(dict(season=season,actual_country_policy_game_and_SOURCE=True,runtime_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True);parser.add_argument('--source-release',required=True)
    parser.add_argument('--target-carriers',type=int,nargs='+',required=True)
    args=parser.parse_args();build(args.season,args.source_release,args.target_carriers)
