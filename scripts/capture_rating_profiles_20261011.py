"""Actual identity/ten-skill spot checks across eras and both native families."""
import os
import time
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id
from scripts.capture_all_rating_calibrations_20261011 import tag

PROFILES=(('2024-25',9244,'walker','Walker'),('2000-01',3380,'xavier','Xavier'),
    ('2003-04',11150,'bayes','Bayes'),('2014-15',9261,'arnautovic','Arnautovic'),
    ('2015-16',1790,'messi','Messi'),('2022-23',1870,'neuer','Manuel'),('2025-26',1790,'yamal','Yamal'))

def main():
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season,carrier,label,token in PROFILES:
        root=ROOT/season;deadline=time.monotonic()+7200
        while not (root/'complete-SOURCE-replay.json').exists():
            if time.monotonic()>deadline:raise ValueError('bounded profile wait expired for '+season)
            time.sleep(10)
        release=registry.load_registered_release(season,release_id(season))
        player=next(p for p in pipeline.read_json_file(release.package_path)['players'] if p['carrier_id']==carrier)
        target=root/'runtime'/(label+'-retry1' if label=='neuer' else label)
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',tag(season)+'_'+label+('_retry1' if label=='neuer' else ''),'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',player['name'],
            '--player-label',label,'--profile-name-token',token,'--profile-only',
            '--provenance-file',str(release.compiler_receipt_path)]
        captured(command,target,root/(label+'-profile-transport.json'),release,env)
        print(dict(season=season,carrier=carrier,label=label,original_image_review_pending=True),flush=True)

if __name__=='__main__':main()
