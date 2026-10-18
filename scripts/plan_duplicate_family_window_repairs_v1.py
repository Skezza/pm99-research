#!/usr/bin/env python3
"""Revisit only the completed name-window queue, with whole sourced surnames.

Replays the existing sources; never fetches, rebuilds, changes starters, enlarges
records or shortens surnames. Other completed corrections are not replanned.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_duplicate_source_context_v1 as source
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_published_family_component_v1 as family
from scripts import season_published_display_names_v1 as display
from scripts import season_dated_reserve_owner_v1 as annual
from scripts import season_sourced_reserve_role_policy_v1 as roles
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile

REASON='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window'


def unused(replacement,used_people,used_identity,used_dates,undated_names,provider_guard):
    person=replacement['source_person']
    identity=(roster.normalise(person['name']),person['birth_date'])
    return (person['source_player_id'] not in used_people and identity not in used_identity
        and not (provider_guard and roster.normalise(replacement['source_player']['name']) in undated_names)
        and not (person.get('source_provider')=='soccerbase' and person['birth_date'] in used_dates))


def prepare_one(path,output,snapshot_people,snapshot_events,pin,claims,display_claims,capacity_bundle=None):
    target=output/path.parent.name/'ownership-plan.json'
    if target.exists():raise ValueError('family-window proposal already exists; never overwrite')
    old=json.loads(path.read_text());pending=[r for r in old['unresolved'] if r['reason']==REASON]
    if not pending:return None
    print(json.dumps({'family_source_replay':old['season'],'pending_name_slots':len(pending)}),flush=True)
    ctx=source.context(old,snapshot_people,snapshot_events,pin)
    release=registry.load_preferred_release(old['season'])
    if release.release_id!=old['release_id']:
        raise ValueError('rebase completed plans to the current release before revisiting names')
    players=list(ctx['players'].values());groups=planner.candidate_groups(players,ctx['people'])
    by_player={p['id']:group for group in groups for p in group}
    used_people={p['source_player_id'] for row in players if (p:=transfer.unique_person(row,ctx['people']))}
    used_identity={roster.person_identity_key(p) for p in players}
    used_dates,undated_names=soccerbase.existing_identity_protection(players)
    native=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    result=copy.deepcopy(old);result['updates']=[];completed=set();refused=[]
    result['allow_published_family_components']=True
    result['bindings']['published_family_component_policy']=family.POLICY
    for queued in pending:
        loser=ctx['players'].get(queued['player_id']);group=by_player.get(queued['player_id'])
        if loser is None or group is None:
            refused.append({'player_id':queued['player_id'],'reason':'no-current-duplicate-group'});continue
        person=transfer.unique_person(loser,ctx['people'])
        if old.get('allow_dated_reserve_owners'):
            winner,basis,witness=annual.decide(group,ctx['evidence'],person,
                ctx['events'].get(person['source_player_id'],[]) if person else [],
                ctx['clubs'],ctx['captures'],ctx['verifier'],ctx['people'])
        else:
            winner,basis=planner.decide_owner(group,ctx['evidence'],person,
                ctx['events'].get(person['source_player_id'],[]) if person else [])
            witness=None
        if winner is None or winner['id']==loser['id']:
            refused.append({'player_id':loser['id'],'reason':'current-positive-owner-not-another-slot'});continue
        club=ctx['clubs'][loser['club_id']]
        if (ctx['layer_by_id'][loser['id']]!='main' or ctx['carrier_layers'][loser['carrier_id']]!={'main'}
                or loser['id'] in club.get('opening',{}).get('starting_xi_player_ids',[])):
            refused.append({'player_id':loser['id'],'reason':'shared-layer-or-declared-starter'});continue
        try:starters=source.actual_starters(ctx,club['id'])
        except (ValueError,RuntimeError) as error:
            refused.append({'player_id':loser['id'],'reason':'native-XI-not-proven','detail':str(error)});continue
        if loser['carrier_id'] in starters:
            refused.append({'player_id':loser['id'],'reason':'actual-native-starter'});continue
        eligible=[r for r in source.reserves(ctx,club['id']) if r['source_person']['source_player_id'] in claims
            and unused(r,used_people,used_identity,used_dates,undated_names,bool(old['bindings'].get('soccerbase_opening_sources')))
            and roles.eligible(loser,r,bool(old.get('allow_sourced_outfield_reserve_role_changes')),
                               bool(old.get('allow_dated_outfield_reserve_role_changes')))]
        eligible.sort(key=lambda r:(r['source_player']['position']!=loser['facts']['primary_position'],
            r['opening_eligibility']['method']!='positive-first-fixture-substitute-id',
            soccerbase.person_sort_key(r['source_person']['source_player_id'])))
        streams=[(native,None)]
        if capacity_bundle is not None:
            from scripts import season_same_carrier_name_capacity_v1 as capacity
            try:streams.append(capacity.recover_slot(native,loser['carrier_id'],capacity_bundle))
            except (ValueError,RuntimeError):pass
        selected=None
        for replacement in eligible:
            person_id=replacement['source_person']['source_player_id'];claim=claims[person_id]
            if claim['birth_date']!=replacement['source_person']['birth_date']:continue
            trial={'player_id':loser['id'],'carrier_id':loser['carrier_id'],'replacement':replacement,
                   'published_family_component':claim}
            alias=display_claims.get(person_id)
            if alias is not None and alias['birth_date']==replacement['source_person']['birth_date']:
                trial['published_display_names']=alias
            view={'players':[{'id':loser['id'],'source_name':replacement['source_player']['name'],
                'name':delta.compiler._pm99_text(replacement['source_player']['name'],label='replacement')} ]}
            for prepared,capacity_claim in streams:
                try:delta.fit_display_names(prepared,view,{'updates':[trial]})
                except (ValueError,RuntimeError):continue
                selected=(replacement,trial,capacity_claim);break
            if selected is not None:break
        if selected is None:
            refused.append({'player_id':loser['id'],'reason':'no-distinct-sourced-whole-surname-fits-current-window'});continue
        replacement,trial,capacity_claim=selected
        row={'player_id':loser['id'],'carrier_id':loser['carrier_id'],'club_id':club['id'],
            'club':club['name'],'layer':'main','before':copy.deepcopy(loser),'ownership_basis':basis,
            'duplicate_source_person':copy.deepcopy(person),'retained_owner_player_id':winner['id'],
            'owner_evidence':copy.deepcopy(ctx['evidence'][winner['club_id']]),
            'transfer_intervals':[transfer.transfer_interval(ctx['events'].get(person['source_player_id'],[]),
                ctx['evidence'][p['club_id']]['date']) for p in group],
            'replacement':copy.deepcopy(replacement),'replacement_opening_evidence':copy.deepcopy(ctx['evidence'][club['id']]),
            'portrait_policy':'remove-displaced-person-portrait-native-no-photo',
            'published_family_component':copy.deepcopy(trial['published_family_component'])}
        if capacity_claim is not None:
            row['same_carrier_name_capacity']=copy.deepcopy(capacity_claim)
        if trial.get('published_display_names'):row['published_display_names']=copy.deepcopy(trial['published_display_names'])
        if witness is not None:row['retained_owner_squad_membership']=copy.deepcopy(witness)
        before,after=loser['facts']['primary_position'],replacement['source_player']['position']
        if before!=after:row['reserve_role_change']={'before':before,'after':after,'policy':roles.policy_for(result)}
        result['updates'].append(row);completed.add(loser['id'])
        used_people.add(replacement['source_person']['source_player_id']);used_dates.add(replacement['source_person']['birth_date'])
        used_identity.add((roster.normalise(replacement['source_person']['name']),replacement['source_person']['birth_date']))
    result['unresolved']=[r for r in old['unresolved'] if not (r['reason']==REASON and r['player_id'] in completed)]
    result['summary'].update(replacement_slots=len(result['updates']),unresolved_entries=len(result['unresolved']),
        unresolved_reasons=dict(collections.Counter(r['reason'] for r in result['unresolved'])))
    result['continued_name_window_queue']={'path':registry.relative_workspace_path(path),'sha256':registry.sha256_file(path),
        'source_downloads':0,'native_writes':0,'refused':refused,'scope':'only previous name-window slots revisited'}
    if capacity_bundle is not None:
        result['continued_name_window_queue']['capacity_policy_bundle']=copy.deepcopy(capacity_bundle)
    family.verify_plan(result)
    if any(row.get('same_carrier_name_capacity') for row in result['updates']):
        result['allow_same_carrier_name_capacity']=True
        result['bindings']['same_carrier_name_capacity']=copy.deepcopy(capacity_bundle)
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        capacity.validate_binding(result)
    target.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(target,result)
    print(json.dumps({'family_window_planned':old['season'],'new_slots':len(result['updates'])}),flush=True)
    return result


def native_feasible(doc,claims,capacity_bundle=None):
    """A cheap negative prefilter, not approval of ownership or a replacement."""
    pending=[r for r in doc['unresolved'] if r['reason']==REASON]
    if not pending:return False
    release=registry.load_preferred_release(doc['season'])
    if release.release_id!=doc['release_id']:raise ValueError('native feasibility baseline changed')
    data=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
    for queued in pending:
        loser=next(p for p in queued['candidates'] if p['player_id']==queued['player_id'])
        raw=entries[loser['carrier_id']].decode_payload(data);streams=[raw]
        if capacity_bundle is not None:
            from scripts import season_same_carrier_name_capacity_v1 as capacity
            try:
                prepared,_=capacity.recover_slot(data,loser['carrier_id'],capacity_bundle)
                streams.append(entries[loser['carrier_id']].decode_payload(prepared))
            except (ValueError,RuntimeError):pass
        for id in queued.get('eligible_source_person_ids',[]):
            claim=claims.get(id)
            if claim is None:continue
            person={'source_player_id':id,'birth_date':claim['birth_date']}
            for alias in family.native_candidates(claim,person):
                name=delta.compiler._pm99_text(alias['name'],label='original entire surname')
                for raw in streams:
                    current=delta.compiler._player_name(raw,record_id=loser['carrier_id'])
                    try:delta.compiler._patch_indexed_player_variable_name_payload(raw,current,name)
                    except (ValueError,RuntimeError):continue
                    return True
    return False


def run(input_root,output,resume=False,capacity_bundle=None):
    paths=sorted(input_root.glob('*/ownership-plan.json'));documents=[json.loads(p.read_text()) for p in paths]
    if not documents:raise ValueError('no completed input plans')
    public=documents[0]['bindings']['published_person_supplement']
    if any(d['bindings']['published_person_supplement']!=public for d in documents):raise ValueError('different original-person inputs')
    person_path=ROOT/public['path']
    if registry.sha256_file(person_path)!=public['sha256']:raise ValueError('original-person input changed')
    wanted={id for d in documents for r in d['unresolved'] if r['reason']==REASON
            for id in r.get('eligible_source_person_ids',[]) if type(id) is int}
    claims=family.claims(person_path,wanted);display_claims=display.claims(person_path)
    pin=documents[0]['bindings']['snapshot']
    if any(d['bindings']['snapshot']!=pin for d in documents):raise ValueError('different immutable snapshots')
    people,events,binding=source.load_snapshot(ROOT/pin['path'],ROOT/pin['pinned_receipt_path'])
    if binding!=pin:raise ValueError('immutable source snapshot binding changed')
    for path,doc in zip(paths,documents):
        existing=output/doc['season']/'ownership-plan.json'
        if existing.exists():
            saved=json.loads(existing.read_text());continued=saved['continued_name_window_queue']
            if (not resume or continued['sha256']!=registry.sha256_file(path)
                    or continued['path']!=registry.relative_workspace_path(path)
                    or continued.get('capacity_policy_bundle')!=capacity_bundle):
                raise ValueError('existing family proposal differs from the bound original input')
            print(json.dumps({'family_proposal_reused':doc['season'],'slots':len(saved['updates'])}),flush=True)
            continue
        if native_feasible(doc,claims,capacity_bundle):
            prepare_one(path,output,people,events,binding,claims,display_claims,capacity_bundle)
        else:print(json.dumps({'family_native_fit_skipped':doc['season'],'native_writes':0}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true')
    p.add_argument('--capacity-pilot',type=Path)
    p.add_argument('--capacity-runtime-evidence',type=Path)
    a=p.parse_args();bundle=None
    if bool(a.capacity_pilot)!=bool(a.capacity_runtime_evidence):p.error('capacity pilot and actual runner evidence are both required')
    if a.capacity_pilot:
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        bundle=capacity.runtime_bundle(a.capacity_pilot,a.capacity_runtime_evidence)
    run(a.input_root,a.output,a.resume,bundle)
