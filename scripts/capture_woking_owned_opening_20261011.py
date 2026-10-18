"""Capture the actual delivered Woking/Oxford players and normal startup."""
import os
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.build_woking_owned_opening_20261011 import ROOT,SEASON,RELEASE

PROFILES=((11149,'louis-row2','J Louis','Louis'),
          (33060,'winters','Tom Winters','Winters'),
          (11150,'bayes','Ashley Bayes','Bayes'))
TAG='woking_owned_2003_r98a_20261011'


def main():
    if not (ROOT/'native-byte-proof.json').exists():
        raise ValueError('actual native proof required before runner')
    # Runtime can run alongside the non-mutating-source replay build. Both
    # independent results remain mandatory before preferred promotion.
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    captured(command,evidence,ROOT/'startup-transport.json',release,env)
    players={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier,label,_,token in PROFILES:
        target=ROOT/'runtime'/label;name=players[carrier]['name']
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',name,'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        if carrier==11149:
            # ROOT inspected the original search frame: Louis-Jean first,
            # Jefferson Louis second. Name-token success alone is inadequate.
            command.extend(['--player-row-click','120,182,1'])
        captured(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(captured_player=name,carrier=carrier,visually_approved=False),flush=True)


if __name__=='__main__':main()
