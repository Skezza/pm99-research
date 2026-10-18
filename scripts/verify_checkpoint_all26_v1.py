"""Read-only all26 binding/playable check for any completed fixed checklist."""
import argparse
from datetime import UTC,datetime
from pathlib import Path
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify(checklist,output):
    if output.exists():raise ValueError('completed all26 evidence must not be overwritten')
    document=pipeline.read_json_file(checklist);expected=document['current_release_bindings']
    if bindings()!=expected:raise ValueError('actual preferred bindings differ from completed checklist')
    rows=[]
    for season in registry.supported_seasons():
        result=registry.validate_preferred_release(season,level='playable')
        if not result['valid']:raise ValueError('preferred season fails playable check: '+season)
        release=registry.load_preferred_release(season)
        rows.append(dict(season=season,release_id=release.release_id,manifest_sha256=release.manifest_sha256,playable=True))
    if bindings()!=expected:raise ValueError('preferred bindings advanced during the check; preserve evidence')
    result=dict(utc=datetime.now(UTC).isoformat(),checklist=dict(path=registry.relative_workspace_path(checklist),sha256=registry.sha256_file(checklist)),
        catalog_sha256=registry.sha256_file(registry.CATALOG_PATH),all26_actual_bindings_exact=True,rows=rows,
        native_writes=0,regenerated_seasons=0,global_historical_RC=False,
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4')
    retained(output,result);print(dict(actual_bindings_checked=len(rows),playable=True,regenerated_seasons=0),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checklist',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify(args.checklist,args.output)
