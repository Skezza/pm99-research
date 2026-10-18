#!/usr/bin/env python3
"""Find bounded, positively sourced multi-slot repairs; never publish them.

An unused opening reserve can be blocked because his sole existing record is
at a wrong club. A two/three-slot chain can move that identity to its sourced
opening club while filling the displaced copy with another genuine reserve.
Every edge needs positive ownership, actual native-XI protection and name fit.
This report does NOT authorise a native write or bypass the ordinary planner.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_dated_reserve_owner_v1 as owners
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_published_display_names_v1 as aliases
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import season_sourced_reserve_role_policy_v1 as roles
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile

POLICY='source-only-bounded-positive-opening-replacement-chain-v1'


def fitted(ctx, loser, replacement):
    cache=ctx.setdefault('fit_cache',{}); person=replacement['source_person']
    key=(loser['carrier_id'],person['source_player_id'])
    if key in cache: return copy.deepcopy(cache[key])
    if 'native_index' not in ctx:
        raw=(ctx['release'].game_path/'DBDAT/JUG98030.FDI').read_bytes()
        ctx['native_original']=raw
        ctx['native_index']={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
    raw=ctx['native_index'][loser['carrier_id']].decode_payload(ctx['native_original'])
    text=delta.compiler._pm99_text
    names=[(text(replacement['source_player']['name'],label='opening reserve'),'full-sourced-name')]
    given,family=person.get('given_name'),person.get('family_name')
    if family:
        surname=text(family,label='published full surname')
        if given: names.append((text(given[0],label='published initial')+'. '+surname,'published-given-initial-and-full-surname'))
        names.append((surname,'published-full-surname'))
    claim=ctx['display_claims'].get(person['source_player_id'])
    if claim and claim['birth_date']==person['birth_date']:
        names += [(text(a['name'],label='original explicit display'),'original-explicit-'+a['field'])
                  for a in aliases.verify(claim,person)]
    names += [(text(a['name'],label='original match label'),'original-Soccerbase-'+a['field'])
              for a in soccerbase.explicit_display_names(replacement)]
    current=delta.compiler._player_name(raw,record_id=loser['carrier_id']); result=None
    for name,method in names:
        try:
            if name.casefold()!=current.casefold():
                delta.compiler._patch_indexed_player_variable_name_payload(raw,current,name)
        except (ValueError,RuntimeError): continue
        result={'carrier_id':loser['carrier_id'],'source_name':replacement['source_player']['name'],
                'display_name':name,'method':method};break
    cache[key]=result
    return copy.deepcopy(result)


def protected(ctx, player):
    club=ctx['clubs'][player['club_id']]
    if (ctx['layer_by_id'][player['id']]!='main' or
            len(ctx['carrier_layers'][player['carrier_id']])!=1 or
            player['id'] in ctx['blocked_slots'] or
            player['id'] in club.get('opening',{}).get('starting_xi_player_ids',[]) or
            player['club_id'] not in ctx['evidence']): return True
    try: return player['carrier_id'] in context.actual_starters(ctx,player['club_id'])
    except ValueError: return True


def path(ctx, loser, visited_slots, visited_people, remaining):
    if remaining<1 or loser['id'] in visited_slots or protected(ctx,loser): return None
    slots=visited_slots|{loser['id']}; club=ctx['clubs'][loser['club_id']]
    options=sorted(context.reserves(ctx,club['id']),key=lambda r:(
        r['source_player']['position']!=loser['facts']['primary_position'],
        r['opening_eligibility']['method']!='positive-first-fixture-substitute-id',
        soccerbase.person_sort_key(r['source_person']['source_player_id'])))
    for replacement in options:
        person=replacement['source_person']; id=person['source_player_id']
        if (id in visited_people or id in ctx['reserved_people'] or
                not roles.eligible(loser,replacement,True,True)): continue
        identity=(roster.normalise(person['name']),person['birth_date'])
        copies=ctx['occupied'].get(id,[])
        if (roster.normalise(replacement['source_player']['name']) in ctx['undated_names'] or
                (not copies and identity in ctx['occupied_identities']) or
                (person.get('source_provider')=='soccerbase' and person['birth_date'] in ctx['occupied_dates'])): continue
        display=fitted(ctx,loser,replacement)
        if display is None: continue
        edge={'before':copy.deepcopy(loser),'replacement':copy.deepcopy(replacement),'display':display,
            'replacement_opening_evidence':copy.deepcopy(ctx['evidence'][club['id']]),
            'actual_native_starter':False,'native_write':False}
        if not copies: return [edge]
        # Bound scope: one wrongly placed existing copy, never an already
        # correct local, multiple existing copies, keeper conversion or XI.
        if len(copies)!=1 or copies[0]['club_id']==club['id'] or remaining<2: continue
        old=copies[0]
        if protected(ctx,old): continue
        prospective={'id':loser['id'],'carrier_id':loser['carrier_id'],'club_id':club['id'],
            'name':person['name'],'source_name':person['name'],'facts':{'birth_date':person['birth_date']}}
        winner,basis,witness=owners.decide([prospective,old],ctx['evidence'],person,ctx['events'].get(id,[]),
            ctx['clubs'],ctx['captures'],ctx['verifier'],ctx['people'])
        if winner is None or winner['id']!=prospective['id']: continue
        tail=path(ctx,old,slots,visited_people|{id},remaining-1)
        if tail is None: continue
        edge['paired_existing_copy']={'player_id':old['id'],'ownership_basis':basis,
            'source_person':copy.deepcopy(person),'prospective_owner_slot':prospective['id'],
            'prospective_owner_is_new_replacement_not_current_native_identity':True,
            'transfer_intervals':[transfer.transfer_interval(ctx['events'].get(id,[]),ctx['evidence'][c]['date'])
                                  for c in (club['id'],old['club_id'])],
            'retained_owner_squad_membership':witness}
        return [edge]+tail
    return None


def review(plan_path,people,events,binding,output,max_depth=3):
    if output.exists(): raise ValueError('chain feasibility evidence is immutable')
    plan=json.loads(plan_path.read_text())
    progress=lambda stage:print(json.dumps({'season':plan['season'],'source_only_stage':stage}),flush=True)
    ctx=context.context(plan,people,events,binding,progress)
    ctx['display_claims']=aliases.claims(ROOT/plan['bindings']['published_person_supplement']['path'])
    occupied=collections.defaultdict(list)
    for p in ctx['players'].values():
        person=transfer.unique_person(p,ctx['people'])
        if person: occupied[person['source_player_id']].append(p)
    ctx['occupied']=occupied;ctx['occupied_identities']={roster.person_identity_key(p) for p in ctx['players'].values()}
    ctx['occupied_dates'],ctx['undated_names']=soccerbase.existing_identity_protection(list(ctx['players'].values()))
    ctx['blocked_slots']={u['player_id'] for u in plan['updates']}
    ctx['reserved_people']={u['replacement']['source_person']['source_player_id'] for u in plan['updates']}
    routes=[];reasons=collections.Counter()
    for index,problem in enumerate(plan['unresolved']):
        if problem['reason']!='owner-proven-but-no-unused-role-compatible-opening-substitute': continue
        progress('reviewing-source-only-queue-entry-'+str(index))
        candidates=[ctx['players'][p['player_id']] for p in problem['candidates']]
        person=transfer.unique_person(candidates[0],ctx['people'])
        if person is None: reasons['person-unresolved']+=1;continue
        winner,basis,witness=owners.decide(candidates,ctx['evidence'],person,ctx['events'].get(person['source_player_id'],[]),
            ctx['clubs'],ctx['captures'],ctx['verifier'],ctx['people'])
        if winner is None: reasons[basis]+=1;continue
        loser=ctx['players'][problem['player_id']]
        route=path(ctx,loser,{winner['id']},{person['source_player_id']},max_depth)
        if route is None: reasons['no-complete-source-and-native-safe-chain']+=1;continue
        if len(route)<2: reasons['ordinary-single-slot-route-not-a-chain']+=1;continue
        routes.append({'original_duplicate_source_person':person,'retained_original_owner_player_id':winner['id'],
            'original_ownership_basis':basis,'original_retained_owner_squad_membership':witness,'edges':route})
        ctx['blocked_slots'].update(e['before']['id'] for e in route)
        ctx['reserved_people'].update(e['replacement']['source_person']['source_player_id'] for e in route)
    result={'schema_version':'pm99-positive-opening-replacement-chain-feasibility-v1','policy':POLICY,
        'season':plan['season'],'source_plan_path':registry.relative_workspace_path(plan_path),
        'source_plan_sha256':registry.sha256_file(plan_path),'native_writes':0,'routes':routes,
        'summary':{'chains':len(routes),'proposed_slots':sum(len(r['edges']) for r in routes),'refusals':dict(reasons)}}
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,result)
    print(json.dumps({'season':plan['season'],**result['summary']}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True);p.add_argument('--season',default='all')
    args=p.parse_args();paths=sorted(args.plan_root.glob('*/ownership-plan.json'))
    if args.season!='all': paths=[p for p in paths if p.parent.name==args.season]
    if not paths: raise ValueError('no completed source-bound ownership plans')
    pin=json.loads(paths[0].read_text())['bindings']['snapshot']
    people,events,binding=context.load_snapshot(ROOT/pin['path'],ROOT/pin['pinned_receipt_path'])
    for plan_path in paths: review(plan_path,people,events,binding,args.output_root/plan_path.parent.name/'chains.json')
