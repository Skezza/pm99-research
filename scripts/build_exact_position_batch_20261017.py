"""Build an explicit already-source-admitted broad/fine position correction."""
import argparse
from pathlib import Path
import shutil

from app.fdi_indexed import IndexedFDIFile
from scripts import season_exact_primary_position_delta_v1 as source
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/explicit-primary-positions-20261017'
RELEASE='sourced-explicit-primary-positions-20261017-r132a'
REPLAY='replayed-explicit-primary-positions-20261017-r132b'


def main(season,parent,targets,input_plan,*,resume_source_only=False):
    folder=ROOT/season;folder.mkdir(parents=True,exist_ok=True)
    existing=(folder/'position-plan.json').exists()
    if registry.locator_path(season,RELEASE).exists():
        raise ValueError('existing position transaction needs inspection, never blind regeneration')
    if existing and not resume_source_only:
        raise ValueError('existing source-only position transaction requires explicit inspected resume')
    if resume_source_only:
        stop=folder/'source-only-reserve-stop.json'
        workspace=registry.ROOT/'.local/historical-role-deltas-v1'/season/RELEASE
        if (not existing or not stop.exists() or workspace.exists()
                or set(p.name for p in folder.iterdir())!={'position-plan.json','inert.json','source-only-reserve-stop.json'}):
            raise ValueError('not an exact inspected source-only reserve stop; do not resume partial native output')
        saved=pipeline.read_json_file(stop)
        if saved.get('native_build_started') is not False or saved.get('source_plan_sha256')!=registry.sha256_file(folder/'position-plan.json'):
            raise ValueError('source-only position stop evidence changed')
    base=registry.load_registered_release(season,parent)
    plan=pipeline.read_json_file(input_plan)
    if plan['targets']!=sorted(targets):
        raise ValueError('prepared source position targets differ from explicit build scope')
    source.verify(base,plan)
    path=folder/'position-plan.json';retained(path,plan)
    descriptor=folder/'inert.json'
    retained(descriptor,dict(season=season,release_id=parent,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free<8.15*1024**3:
        raise ValueError('source retained before unchanged8GiB reserve is threatened')
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=parent,
        profile_assignment_plan_path=path)
    actual=registry.load_registered_release(season,RELEASE)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed=set();observed=[]
    for row in plan['updates']:
        carrier=row['carrier_id'];entry=entries[carrier];payload=entry.decode_payload(after)
        native=source.roster.native_player(payload,carrier);end=native['name_end']
        allowed.update(entry.payload_offset+end+offset for offset in (*range(2,8),11))
        if (native['position']!=row['primary_position']
                or native['roles']!=row['fine_roles']+[98]*(6-len(row['fine_roles']))
                or payload[end+10]!=entry.decode_payload(before)[end+10]):
            raise ValueError('independent native broad/fine role or opaque neighbour differs')
        observed.append(dict(carrier_id=carrier,native=native))
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    if len(before)!=len(after) or not changed or not changed<=allowed:
        raise ValueError('position transaction changed an unrelated native byte')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left)!=set(right) or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('position transaction changes another game file')
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('position recipe differs beyond declared role fields')
    retained(folder/'native-byte-proof.json',dict(rows=observed,native_bytes_changed=len(changed),
        source_plan_sha256=registry.sha256_file(path),manifest_sha256=actual.manifest_sha256,
        country_skills_identity_ownership_tactics_managers_kits_and_photos_unchanged=True))
    replay=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(season,REPLAY);share_verified(actual,rebuilt,folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    retained(folder/'build-summary.json',dict(actual_position_game_and_SOURCE_complete=True,
        players_corrected=len(observed),preferred_changed=False,runtime_pending=True))
    print(dict(actual_position_game_and_SOURCE=True,players_corrected=len(observed),runtime_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True);parser.add_argument('--source-release',required=True)
    parser.add_argument('--target-carriers',type=int,nargs='+',required=True)
    parser.add_argument('--input-plan',type=Path,required=True)
    parser.add_argument('--resume-source-only',action='store_true')
    args=parser.parse_args();main(args.season,args.source_release,args.target_carriers,args.input_plan,
        resume_source_only=args.resume_source_only)
