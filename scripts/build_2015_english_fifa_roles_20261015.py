"""Build/verify the separate English role layer over the completed main pass."""
import os
from scripts import advance_exact_fifa_roles_20261015 as main
from scripts import season_2015_english_fifa_roles_v1 as source
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts import capture_registered_season_runtime_v1 as capture

BATCH=main.ROOT/'english-final'
ROOT=BATCH/'2015-16'
RELEASE='sourced-exact-fifa-english-roles-20261015-r105a'
REPLAY='replayed-exact-fifa-english-roles-20261015-r105b'
TAG='exact_fifa_english_roles_2015_16_r105a_20261015'
PROFILES=((9260,'afellay','Afellay'),(9277,'arnautovic','Arnautovic'))


def run():
    BATCH.mkdir(parents=True,exist_ok=True)
    retained(BATCH/'baseline.json',[dict(season='2015-16',release_id=main.RELEASE)])
    main.build('2015-16',batch_root=BATCH,release_id=RELEASE,replay_id=REPLAY,source_module=source,require_preferred=False)
    release=registry.load_registered_release('2015-16',RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season='2015-16',worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    captured(command,evidence,ROOT/'startup-transport.json',release,env)
    english,_=source.overlay(release)
    for carrier,label,token in PROFILES:
        person=next(p for p in english['players'] if p['carrier_id']==carrier)
        target=ROOT/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',person['name'],'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        captured(command,target,ROOT/(label+'-profile-transport.json'),release,env)
    print(dict(English_roles_built=True,complete_SOURCE_exact=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':run()
