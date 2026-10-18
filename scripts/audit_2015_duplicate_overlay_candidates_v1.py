#!/usr/bin/env python3
"""Prove source eligibility for the separately held 2015 English duplicate slots.

This is read-only feasibility evidence. No layer guard is disabled, and no
recipe, native player, registration or portrait is changed by this script.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_dated_reserve_owner_v1 as owners
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_published_display_names_v1 as aliases
from scripts import season_sourced_reserve_role_policy_v1 as roles
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def review(plan_path, output):
    if output.exists(): raise ValueError('overlay source evidence is immutable')
    plan=json.loads(plan_path.read_text())
    if plan['season']!='2015-16': raise ValueError('this bounded review is only for the 2015 English overlay')
    pin=plan['bindings']['snapshot']
    people,events,binding=context.load_snapshot(ROOT/pin['path'],ROOT/pin['pinned_receipt_path'])
    ctx=context.context(plan,people,events,binding)
    used={p['source_player_id'] for row in ctx['players'].values() if (p:=transfer.unique_person(row,ctx['people']))}
    used_identity={roster.person_identity_key(p) for p in ctx['players'].values()}
    dates,undated=soccerbase.existing_identity_protection(list(ctx['players'].values()))
    display_claims=aliases.claims(ROOT/plan['bindings']['published_person_supplement']['path'])
    original=(ctx['release'].game_path/'DBDAT/JUG98030.FDI').read_bytes()
    rows=[]
    for problem in plan['unresolved']:
        if problem['reason']!='english-overlay-requires-separately-bound-transaction': continue
        candidates=[ctx['players'][p['player_id']] for p in problem['candidates']]
        person=transfer.unique_person(candidates[0],ctx['people'])
        winner,basis,witness=owners.decide(candidates,ctx['evidence'],person,ctx['events'].get(person['source_player_id'],[]),
            ctx['clubs'],ctx['captures'],ctx['verifier'],ctx['people'])
        if winner is None: raise ValueError('known overlay owner no longer independently reproduces: '+basis)
        loser=ctx['players'][problem['player_id']]; club=ctx['clubs'][loser['club_id']]
        if ctx['layer_by_id'][loser['id']]!='english' or len(ctx['carrier_layers'][loser['carrier_id']])!=1:
            raise ValueError('overlay slot is not independently bound to exactly one layer')
        if loser['id'] in club.get('opening',{}).get('starting_xi_player_ids',[]) or loser['carrier_id'] in context.actual_starters(ctx,club['id']):
            raise ValueError('this overlay feasibility route must not change any opening starter')
        eligible=[]
        for replacement in context.reserves(ctx,club['id']):
            new=replacement['source_person']; identity=(roster.normalise(new['name']),new['birth_date'])
            if (new['source_player_id'] in used or identity in used_identity or
                    roster.normalise(replacement['source_player']['name']) in undated or
                    (new.get('source_provider')=='soccerbase' and new['birth_date'] in dates) or
                    not roles.eligible(loser,replacement,True,True)): continue
            trial={'player_id':loser['id'],'carrier_id':loser['carrier_id'],'replacement':replacement}
            claim=display_claims.get(new['source_player_id'])
            if claim and claim['birth_date']==new['birth_date']: trial['published_display_names']=claim
            view={'players':[{'id':loser['id'],'source_name':replacement['source_player']['name'],
                'name':delta.compiler._pm99_text(replacement['source_player']['name'],label='opening reserve')} ]}
            try: fitted=delta.fit_display_names(original,view,{'updates':[trial]})[0]
            except (ValueError,RuntimeError): continue
            eligible.append({'replacement':copy.deepcopy(replacement),'display':fitted,
                **({'published_display_names':claim} if 'published_display_names' in trial else {})})
        rows.append({'player_id':loser['id'],'carrier_id':loser['carrier_id'],'club':club['name'],'before':loser,
            'retained_owner_player_id':winner['id'],'ownership_basis':basis,'duplicate_source_person':person,
            'owner_evidence':ctx['evidence'][winner['club_id']],
            'replacement_opening_evidence':ctx['evidence'][club['id']],
            'retained_owner_squad_membership':witness,'actual_native_starter':False,
            'eligible_unused_reserves':eligible,'native_write':False})
    result={'schema_version':'pm99-2015-English-overlay-duplicate-source-feasibility-v1',
        'source_plan_path':registry.relative_workspace_path(plan_path),'source_plan_sha256':registry.sha256_file(plan_path),
        'rows':rows,'native_writes':0,'summary':{'reviewed_slots':len(rows),
            'slots_with_sourced_unused_reserve':sum(bool(r['eligible_unused_reserves']) for r in rows)}}
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,result)
    print(json.dumps(result['summary']),flush=True)
    for row in rows: print(json.dumps({'club':row['club'],'before':row['before']['name'],
        'eligible':[r['replacement']['source_player']['name'] for r in row['eligible_unused_reserves']]}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();review(args.plan,args.output)
