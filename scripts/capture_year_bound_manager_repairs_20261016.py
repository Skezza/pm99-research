"""Capture the selected exact coach game, reusing only bound safe evidence."""
import argparse
import os
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts import season_cached_manager_repairs_v2_20261016 as source
from scripts import build_year_bound_manager_repairs_20261016 as batch
from scripts import build_cached_manager_repairs_20261016 as prior
from scripts.capture_cached_manager_repairs_20261016 import tag as prior_tag
from scripts.capture_city_opening_exchange_20261011 import captured


def selection(season):
    root=batch.ROOT/season
    base=registry.load_registered_release(season,prior.BASE)
    decision=source.decision(base)
    if pipeline.read_json_file(root/'source-acceptance-decision.json')!=decision:
        raise ValueError('saved source acceptance differs from fresh exact-source decision')
    selected=pipeline.read_json_file(root/'selected-delivery.json')
    reused=selected['reuse_exact_completed_private_build']
    expected_root=prior.ROOT/season if reused else root
    expected_release=prior.RELEASE if reused else batch.RELEASE
    if (selected['season']!=season or selected['release_id']!=expected_release
        or selected['evidence_root']!=registry.relative_workspace_path(expected_root)
        or (reused and not decision['reuse_exact_existing_private_plan'])):
        raise ValueError('selected manager delivery is not an approved exact private plan')
    if pipeline.read_json_file(expected_root/'manager-plan.json')!=decision['selected_plan']:
        raise ValueError('selected actual build uses another source plan')
    for name in ('native-byte-proof.json','complete-SOURCE-replay.json'):
        if not (expected_root/name).exists():raise ValueError('selected manager game not complete')
    run_tag=prior_tag(season) if reused else 'year_bound_managers_'+season.replace('-','_')+'_r110a_20261016'
    return expected_root,expected_release,run_tag,decision


def main(seasons):
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season in seasons:
        root,release_id,run_tag,_=selection(season)
        release=registry.load_registered_release(season,release_id)
        receipt=root/'startup-transport.json'
        if receipt.exists():
            saved=pipeline.read_json_file(receipt)
            if (saved['exit_code']!=0 or saved['release_manifest_sha256']!=release.manifest_sha256
                or saved['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/run_tag)):
                raise ValueError('existing transport is failed or belongs to another selected game')
            print(dict(season=season,reused_exact_original_startup=True),flush=True)
            continue
        command,evidence=capture.capture_command(season=season,worker='default',run_tag=run_tag,
            compact_evidence=True,release_id=release_id)
        captured(command,evidence,receipt,release,env)
        print(dict(season=season,actual_startup_complete=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='+')
    main(parser.parse_args().seasons)
