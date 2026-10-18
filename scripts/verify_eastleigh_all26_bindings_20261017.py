"""Postpublication read-only check; never build or change another season."""
from datetime import UTC,datetime
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.publish_eastleigh_private_20261017 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    output=ROOT/'Eastleigh2014-native-delivery-v1/postpublication-all26-bindings.json'
    if output.exists():raise ValueError('completed all26 check must not repeat')
    checklist=ROOT/'release-delivery-checklist-v57.json';expected=pipeline.read_json_file(checklist)['current_release_bindings']
    if bindings()!=expected:raise ValueError('actual all26 bindings differ from published checkpoint')
    rows=[]
    for season in registry.supported_seasons():
        result=registry.validate_preferred_release(season,level='playable')
        if not result['valid']:raise ValueError('current game failed playable gate: '+season)
        release=registry.load_preferred_release(season)
        rows.append(dict(season=season,release_id=release.release_id,manifest_sha256=release.manifest_sha256,playable=True))
    if bindings()!=expected:raise ValueError('preferred bindings changed during independent check')
    retained(output,dict(utc=datetime.now(UTC).isoformat(),checklist=dict(path=registry.relative_workspace_path(checklist),sha256=registry.sha256_file(checklist)),
        catalog_sha256=registry.sha256_file(registry.CATALOG_PATH),all26_actual_bindings_exact=True,rows=rows,
        native_writes=0,regenerated_seasons=0,global_historical_RC=False,
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))
    print(dict(actual_bindings_checked=len(rows),playable=True,regenerated_seasons=0),flush=True)


if __name__=='__main__':main()
