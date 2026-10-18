#!/usr/bin/env python3
"""Continue from each immutable season plan's exact source inputs and policies.

Do not reconstruct a long CLI from memory: supplemental 2015 fixtures and
provider-specific original evidence remain bound per season. Newly reviewed
policies must be explicitly enabled; existing policies are never silently lost.
This command plans only, does not fetch sources, regenerate games or promote.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def bound_path(binding,path_key='path',hash_key='sha256'):
    path=registry.ROOT/binding[path_key]
    registry.relative_workspace_path(path)
    if registry.sha256_file(path)!=binding[hash_key]:
        raise ValueError('continuation original source input changed: '+str(path))
    return path


def parameters(plan,dated_position_policy=False):
    bindings=plan['bindings'];season=plan['season']
    opening=bound_path(bindings,'opening_path','opening_sha256')
    root=opening.parents[2]
    if opening!=root/'opening'/season/'opening-review.json':
        raise ValueError('continuation opening path has no exact season source-root contract')
    review=bound_path(bindings,'review_path','review_sha256')
    if review not in (root/'reviews'/season/'report.json',root/'reviews'/season/'roster-audit.json'):
        raise ValueError('continuation roster review does not belong to the same exact source root/season')
    result={'source_root':root,'supplemental_opening_path':None,
        'with_opening_person_supplement':bool(bindings.get('opening_person_supplement_policy')),
        'published_person_path':None,'published_transfer_path':None,
        'allow_sourced_outfield_reserve_role_changes':bool(plan.get('allow_sourced_outfield_reserve_role_changes')),
        'allow_published_display_aliases':bool(plan.get('allow_published_display_aliases')),
        'allow_dated_reserve_owners':bool(plan.get('allow_dated_reserve_owners')),
        'allow_dated_outfield_reserve_role_changes':bool(plan.get('allow_dated_outfield_reserve_role_changes')),
        'soccerbase_review_path':None,'soccerbase_club_entities_path':None}
    if bindings.get('supplemental_opening'):
        result['supplemental_opening_path']=bound_path(bindings['supplemental_opening'])
        if json.loads(result['supplemental_opening_path'].read_text())['season']!=season:
            raise ValueError('continuation supplemental fixture source belongs to another season')
    for key,arg in (('published_person_supplement','published_person_path'),
                    ('published_transfer_supplement','published_transfer_path')):
        if bindings.get(key):result[arg]=bound_path(bindings[key])
    if bindings.get('soccerbase_opening_sources'):
        item=bindings['soccerbase_opening_sources']
        result['soccerbase_review_path']=bound_path(item['review'])
        result['soccerbase_club_entities_path']=bound_path(item['club_entities'])
    if dated_position_policy:
        if not result['allow_sourced_outfield_reserve_role_changes']:
            raise ValueError('new dated position policy requires the existing explicit outfield reserve policy')
        result['allow_dated_outfield_reserve_role_changes']=True
    return result


def run(input_root,output_root,season='all',dated_position_policy=False):
    selected=registry.supported_seasons() if season=='all' else [season]
    inputs=[]
    for season in selected:
        path=input_root/season/'ownership-plan.json';plan=json.loads(path.read_text())
        if plan['season']!=season:raise ValueError('continuation input season differs from its directory')
        params=parameters(plan,dated_position_policy)
        inputs.append((plan,params,{'season':season,'prior_plan_path':registry.relative_workspace_path(path),
            'prior_plan_sha256':registry.sha256_file(path),
            'parameters':{k:registry.relative_workspace_path(v) if isinstance(v,Path) else v for k,v in params.items()}}))
    pins=[plan['bindings']['snapshot'] for plan,_,_ in inputs]
    if any(pin!=pins[0] for pin in pins):raise ValueError('continuation cannot silently mix source snapshots')
    run_config={'schema_version':'pm99-duplicate-ownership-exact-input-continuation-v1',
        'native_writes':0,'source_downloads':0,'explicit_dated_position_policy_upgrade':dated_position_policy,
        'seasons':[receipt for _,_,receipt in inputs]}
    config_path=output_root/'run-inputs.json'
    if config_path.exists():
        if json.loads(config_path.read_text())!=run_config:raise ValueError('immutable continuation inputs changed')
    else:
        config_path.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(config_path,run_config)
    people,events,binding=context.load_snapshot(registry.ROOT/pins[0]['path'],registry.ROOT/pins[0]['pinned_receipt_path'])
    if binding!=pins[0]:raise ValueError('continuation original snapshot binding changed')
    for plan,params,_ in inputs:
        result=planner.plan(plan['season'],people,events,binding,output=output_root,**params)
        print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True);p.add_argument('--season',default='all')
    p.add_argument('--apply-dated-position-policy',action='store_true');args=p.parse_args()
    run(args.input_root,args.output_root,args.season,args.apply_dated_position_policy)
