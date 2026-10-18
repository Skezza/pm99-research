"""Actual startup and representative source-bound nationality profiles."""
import os
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/woking-nationalities-v1'
RELEASE='sourced-woking-nationalities-20261011-r99a'
TAG='woking_nationalities_2003_r99a_20261011'
PROFILES=((11149,'louis','Louis'),(11150,'bayes','Bayes'),(11143,'nade','Nade'))

def main():
    release=registry.load_registered_release('2003-04',RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season='2003-04',worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    captured(command,evidence,ROOT/'startup-transport.json',release,env)
    players={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier,label,token in PROFILES:
        target=ROOT/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',players[carrier]['name'],
            '--player-label',label,'--profile-name-token',token,'--profile-only',
            '--provenance-file',str(release.compiler_receipt_path)]
        if label=='louis':command.extend(['--player-row-click','120,182,1'])
        captured(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(captured_player=players[carrier]['name'],carrier=carrier),flush=True)

if __name__=='__main__':main()
