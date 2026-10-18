"""Publish mixed reused/new coach games with all495 proposals accounted for.

Deferred witnesses stay open. This does not certify all managers or legacy2015.
Every selected game is checked before any preferred catalogue is changed.
"""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_v2_20261016 as source
from scripts import checkpoint_cached_managers_20261016 as checks
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.build_year_bound_manager_repairs_20261016 import ROOT
from scripts.capture_year_bound_manager_repairs_20261016 import selection
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify(season):
    root,release_id,run_tag,decision=selection(season)
    row=checks.verify(season,evidence_root=root,release_id=release_id,
        source_module=source,run_tag=run_tag)
    if (row['canonical_manager_updates']!=decision['accepted_proposals']
        or decision['original_proposals']!=decision['accepted_proposals']+len(decision['deferred'])):
        raise ValueError('manager source dispositions do not account for all original proposals')
    return dict(row,evidence_root=registry.relative_workspace_path(root),run_tag=run_tag,
        original_proposals=decision['original_proposals'],deferred_proposals=len(decision['deferred']),
        acceptance_decision=binding(ROOT/season/'source-acceptance-decision.json'),
        selected_delivery=binding(ROOT/season/'selected-delivery.json'))


def run():
    previous=ROOT.parent/'release-delivery-checklist-v48.json'
    output=ROOT.parent/'release-delivery-checklist-v49.json'
    if output.exists():raise ValueError('completed manager checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(previous))
    originals={r['season']:r for r in result['current_release_bindings']}
    seasons=[s for s in registry.supported_seasons() if s!='2015-16']
    if len(seasons)!=25:raise ValueError('manager batch must remain exact25 plus unchanged legacy2015')
    rows=[verify(s) for s in seasons]
    proposed=sum(r['original_proposals'] for r in rows)
    accepted=sum(r['canonical_manager_updates'] for r in rows)
    deferred=sum(r['deferred_proposals'] for r in rows)
    if proposed!=495 or accepted+deferred!=495:
        raise ValueError('frozen495 proposals must be delivered or explicitly deferred, never discarded')
    selected={r['season']:r for r in rows}
    for season in registry.supported_seasons():
        actual=registry.load_preferred_release(season);parent=originals[season]
        expected=selected.get(season)
        if actual.release_id==parent['release_id']:
            if actual.manifest_sha256!=parent['manifest_sha256']:
                raise ValueError('parent manifest changed')
        elif expected is None or (actual.release_id,actual.manifest_sha256)!=(expected['release_id'],expected['manifest_sha256']):
            raise ValueError('unexpected preferred transition during manager batch')
    evidence=[]
    for row in rows:
        season=row['season'];root=registry.ROOT/row['evidence_root']
        retained(root/'prepublication-proof-v2.json',row)
        publisher.register_completed_delta(season,row['release_id'])
        if not (root/'final-attestation-v2.json').exists():
            retained(root/'final-attestation-v2.json',runtime.attest(season=season,
                evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/row['run_tag']))
        valid=registry.validate_preferred_release(season,level='playable')
        if not valid['valid']:raise ValueError('manager default failed playable validation')
        retained(root/'preferred-playable-validation-v2.json',valid)
        evidence.extend(binding(root/n) for n in ('manager-plan.json','native-byte-proof.json',
            'complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
            'prepublication-proof-v2.json','final-attestation-v2.json','preferred-playable-validation-v2.json'))
        evidence.extend((row['acceptance_decision'],row['selected_delivery']))
    finding=dict(id='year-bound-cached-manager-corrections-v2',
        state='delivered-native-SOURCE-and-runner-verified',seasons=25,
        original_proposals=495,canonical_updates=accepted,deferred_proposals=deferred,
        actual_ENT_records_changed=sum(r['actual_ENT_records_changed'] for r in rows),
        actual_visible_short_names_changed=sum(r['actual_visible_short_names_changed'] for r in rows),
        legacy2015_separate_source_review_remaining=True,global_manager_approval=False,
        cross_club_cases_closed=0,all_player_ratings_tactics_ownership_and_artwork_preserved=True)
    result['additional_confirmed_findings'].append(finding)
    result['delivered_evidence'].extend(evidence)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous),
        current_release_bindings=bindings(),fresh_runtime_runs_this_checklist=seasons,
        all_required_work_complete=False,
        next_batch='Continue deferred coach witnesses,288 earlier source ambiguities and separate legacy2015; Arsenal2021 coupled ownership/opening squad and broader checklist remain. Cross-club2808 unchanged by coach corrections.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(finding,checklist=binding(output),
        legacy2015_preferred_unchanged=True,season_evidence=rows,global_historical_RC=False))
    print(dict(checklist=binding(output),accepted=accepted,deferred=deferred,delivered=True),flush=True)


if __name__=='__main__':run()
