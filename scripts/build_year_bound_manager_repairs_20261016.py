"""Reuse safe completed coach candidates; replace rejected-date private trials."""
import argparse
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_v2_20261016 as source
from scripts import build_cached_manager_repairs_20261016 as prior
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/cached-manager-delivery-20261016-v2'
RELEASE='sourced-year-bound-managers-20261016-r110a'
REPLAY='replayed-year-bound-managers-20261016-r110b'


def build(season):
    base=registry.load_registered_release(season,prior.BASE)
    decision=source.decision(base);root=ROOT/season;root.mkdir(parents=True,exist_ok=True)
    retained(root/'source-acceptance-decision.json',decision)
    old=prior.ROOT/season
    if decision['reuse_exact_existing_private_plan'] and (old/'complete-SOURCE-replay.json').exists():
        if pipeline.read_json_file(old/'manager-plan.json')!=decision['selected_plan']:
            raise ValueError('existing safe private plan differs; no evidence reuse')
        retained(root/'selected-delivery.json',dict(season=season,release_id=prior.RELEASE,
            evidence_root=registry.relative_workspace_path(old),reuse_exact_completed_private_build=True))
        print(dict(season=season,reused_complete_private_game=True,accepted=decision['accepted_proposals'],
            rejected_date_or_owner_witnesses=0),flush=True);return
    prior.build(season,batch_root=ROOT,release_id=RELEASE,replay_id=REPLAY,source_module=source)
    retained(root/'selected-delivery.json',dict(season=season,release_id=RELEASE,
        evidence_root=registry.relative_workspace_path(root),reuse_exact_completed_private_build=False))
    print(dict(season=season,accepted=decision['accepted_proposals'],
        rejected_date_or_owner_witnesses=len(decision['deferred']),preferred_unchanged=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='*',default=['2000-01'])
    args=parser.parse_args()
    for season in registry.supported_seasons() if args.seasons==['all'] else args.seasons:
        if season=='2015-16':continue
        build(season)
