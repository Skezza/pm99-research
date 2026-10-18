"""Retry inspected empty search only; preserve failed evidence and valid startup."""
import os
from scripts import build_kiraly_period_profiles_20261017 as b
from scripts.capture_kiraly_period_profiles_20261017 import tag
from scripts.capture_shinnie_country_20261017 import verify_existing_startup
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture


def main():
    season='2004-05';folder=b.ROOT/season;label='kiraly_hungary_keeper'
    release=b.source.registry.load_registered_release(season,b.RELEASE)
    failed=b.source.pipeline.read_json_file(folder/(label+'-failed-unaccented-transport.json'))
    if failed['exit_code']!=1 or failed['release_manifest_sha256']!=release.manifest_sha256:
        raise ValueError('retry requires exact inspected failed capture')
    summaries=list((b.source.registry.ROOT/failed['evidence']).rglob('summary.json'))
    if len(summaries)!=1:raise ValueError('one failed original profile required')
    summary=b.source.pipeline.read_json_file(summaries[0])
    if summary.get('success') is not False or summary.get('crash_detected') or summary.get('wine_debugger_detected'):
        raise ValueError('not the inspected empty-search failure')
    if summary.get('player_profile',{}).get('expected_name_token_satisfied') is not False:
        raise ValueError('original search did not fail identity verification')
    plan=b.source.pipeline.read_json_file(folder/'profile-plan.json')
    if plan['before_native']['name']!='Gabor KIRÁLY':raise ValueError('native accented name changed')
    verify_existing_startup(folder,b.source.registry.ROOT/'.local/runlogs/pm99_runner'/tag(season),release)
    target=folder/'runtime'/(label+'_accented_retry');receipt=folder/(label+'-profile-transport.json')
    if target.exists() or receipt.exists():raise ValueError('retry already attempted; inspect before continuing')
    command=[str(b.source.registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker','default','--run-tag',tag(season)+'_'+label+'_accented_retry',
        '--local-game-dir',str(release.game_path),'--local-artifact-dir',str(target),
        '--player-search','KIRÁLY','--player-label',label,'--profile-name-token','Kiraly',
        '--profile-only','--provenance-file',str(release.compiler_receipt_path)]
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    bound_capture(command,target,receipt,release,env)


if __name__=='__main__':main()
