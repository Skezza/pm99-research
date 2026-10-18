"""Capture each actual new game once; retain failed evidence, never overwrite."""
import os
import time
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id

def tag(season):
    base='rating_calibration_'+season.replace('-','_')+'_r101a_20261011'
    return base+'_retry1' if season=='2013-14' else base

def main():
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    seasons=sorted(registry.supported_seasons(),key=lambda s:(s!='2024-25',s))
    for season in seasons:
        root=ROOT/season
        # Wait only for this exact built/native-proved/full-SOURCE candidate,
        # not an old preferred release or an unrelated worker's readiness.
        deadline=time.monotonic()+7200
        while not (root/'complete-SOURCE-replay.json').exists():
            if time.monotonic()>deadline:raise ValueError('bounded wait expired for '+season)
            time.sleep(10)
        release=registry.load_registered_release(season,release_id(season))
        command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag(season),
            compact_evidence=True,release_id=release.release_id)
        captured(command,evidence,root/'startup-transport.json',release,env)
        print(dict(season=season,actual_candidate=release.release_id,startup_transport_complete=True,
            original_image_review_pending=True),flush=True)

if __name__=='__main__':main()
