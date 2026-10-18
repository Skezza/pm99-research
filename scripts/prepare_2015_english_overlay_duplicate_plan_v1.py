#!/usr/bin/env python3
"""Create an explicit immutable overlay repair proposal from a read-only review.

Compilation still has to independently reparse every original source and prove
native preservation. This script alone never changes a game or a registration.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_duplicate_english_overlay_v1 as overlay
from scripts import season_sourced_reserve_role_policy_v1 as roles
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def prepare(feasibility_path,output):
    if output.exists():raise ValueError('English overlay repair proposal is immutable')
    doc=json.loads(feasibility_path.read_text());plan_path=ROOT/doc['source_plan_path']
    if doc['schema_version']!='pm99-2015-English-overlay-duplicate-source-feasibility-v1' or doc['native_writes']!=0:
        raise ValueError('English overlay proposal requires the explicit read-only source review')
    if registry.sha256_file(plan_path)!=doc['source_plan_sha256']:
        raise ValueError('reviewed original ownership proposal changed')
    plan=copy.deepcopy(json.loads(plan_path.read_text()))
    release=registry.load_preferred_release('2015-16')
    if (release.release_id,registry.sha256_file(release.package_path),registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'))!=(
            plan['release_id'],plan['package_sha256'],plan['jug_sha256']):
        raise ValueError('English overlay source baseline changed')
    targets=[r for r in plan['unresolved'] if r['reason']=='english-overlay-requires-separately-bound-transaction']
    if {r['player_id'] for r in targets}!={r['player_id'] for r in doc['rows']} or len(targets)!=len(doc['rows']):
        raise ValueError('English source review does not cover the exact unresolved cohort')
    public=plan['bindings']['published_transfer_supplement']; path=ROOT/public['path']
    if registry.sha256_file(path)!=public['sha256']:raise ValueError('original transfer source supplement changed')
    original=json.loads(path.read_text());wanted={r['duplicate_source_person']['source_player_id'] for r in doc['rows']}
    original['players']=[r for r in original['players'] if r['player_id'] in wanted]
    events,summary=histories.merge({},original)
    if wanted-set(summary['accepted_player_ids']):raise ValueError('known English owners lack original complete transfer histories')
    plan.update(resolution_policy=roles.DATED_RESOLUTION,allow_dated_outfield_reserve_role_changes=True,
                allow_sourced_outfield_reserve_role_changes=True,allow_english_overlay_replacements=True)
    plan['bindings']['reserve_role_policy']=roles.DATED_POLICY
    plan['bindings']['english_overlay']=overlay.binding(release)
    plan['continued_from_source_feasibility']={'path':registry.relative_workspace_path(feasibility_path),
        'sha256':registry.sha256_file(feasibility_path),'native_writes_in_source_review':0}
    updates=[];selected=set()
    for row in doc['rows']:
        options=sorted(row['eligible_unused_reserves'],key=lambda r:(
            r['replacement']['source_player']['position']!=row['before']['facts']['primary_position'],
            r['replacement']['opening_eligibility']['method']!='positive-first-fixture-substitute-id',
            soccerbase.person_sort_key(r['replacement']['source_person']['source_player_id'])))
        chosen=next((r for r in options if r['replacement']['source_person']['source_player_id'] not in selected),None)
        if chosen is None:raise ValueError('English overlay fixed slots lack distinct unused sourced replacements')
        selected.add(chosen['replacement']['source_person']['source_player_id'])
        update={k:copy.deepcopy(row[k]) for k in ('player_id','carrier_id','club','before','retained_owner_player_id',
            'ownership_basis','duplicate_source_person','owner_evidence','replacement_opening_evidence')}
        update.update(layer='english',club_id=row['before']['club_id'],replacement=copy.deepcopy(chosen['replacement']),
            portrait_policy='remove-displaced-person-portrait-native-no-photo')
        if chosen.get('published_display_names'):update['published_display_names']=copy.deepcopy(chosen['published_display_names'])
        old,new=row['before']['facts']['primary_position'],chosen['replacement']['source_player']['position']
        if old!=new:update['reserve_role_change']={'before':old,'after':new,'policy':roles.DATED_POLICY}
        if row['retained_owner_squad_membership'] is not None:
            update['retained_owner_squad_membership']=copy.deepcopy(row['retained_owner_squad_membership'])
        duplicate_id=row['duplicate_source_person']['source_player_id']
        candidates=next(r['candidates'] for r in targets if r['player_id']==row['player_id'])
        dates=[row['owner_evidence']['date'] if c['player_id']==row['retained_owner_player_id']
               else row['replacement_opening_evidence']['date'] for c in candidates]
        update['transfer_intervals']=[transfer.transfer_interval(events[duplicate_id],day) for day in dates]
        updates.append(update)
    plan['updates']=updates
    plan['unresolved']=[r for r in plan['unresolved'] if r['reason']!='english-overlay-requires-separately-bound-transaction']
    plan['summary'].update(replacement_slots=len(updates),unresolved_entries=len(plan['unresolved']),
        unresolved_reasons=dict(collections.Counter(r['reason'] for r in plan['unresolved'])))
    overlay.validate_binding(release,plan)
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,plan)
    print(json.dumps({'prepared_English_overlay_slots':len(updates),'native_writes':0,
        'replacements':[(r['club'],r['before']['name'],r['replacement']['source_player']['name']) for r in updates]}),flush=True)
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--review',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();prepare(args.review,args.output)
