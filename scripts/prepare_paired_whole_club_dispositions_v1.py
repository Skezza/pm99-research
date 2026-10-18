#!/usr/bin/env python3
"""Plan a coupled disposition; singleton collision diagnostics cannot publish."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline

SCHEMA='pm99-source-only-paired-whole-club-disposition-v1'
SINGLETON_SCHEMA='pm99-source-only-complete-singleton-whole-club-disposition-v1'


def validate_group(proposals, *, allow_singleton=False):
    if len(proposals)<2 and not (allow_singleton and len(proposals)==1):
        raise ValueError('paired disposition needs at least two complete source proposals')
    context={(p['season'],p['release_id'],p['package_sha256'],p['jug_sha256'],p['eq_sha256']) for p in proposals}
    if len(context)!=1:raise ValueError('paired dispositions must share the exact unchanged baseline')
    if any(p.get('schema_version')!='pm99-whole-club-collision-diagnostic-only-v1'
            or p.get('collision_inspection_only') is not True
            or p.get('approved_for_native_publication') is not False for p in proposals):
        raise ValueError('paired disposition requires explicit source-only diagnostics')
    retired={p['before_club']['id'] for p in proposals}
    carriers=[p['before_club']['carrier_id'] for p in proposals]
    if len(retired)!=len(proposals) or len(set(carriers))!=len(carriers):
        raise ValueError('paired disposition repeats an old club or native carrier')
    targets=[whole.roster.normalise(p['new_club']) for p in proposals]
    if len(set(targets))!=len(targets):raise ValueError('paired disposition introduces duplicate target clubs')
    slots={};desired_ids=set();desired_keys=set();covered=[]
    native_carriers=set()
    for p in proposals:
        club_full_names=set()
        whole.validate_opening_birth_dates(p['desired_people'],p['original_opening']['fixture']['date'])
        if p.get('club_witness',{}).get('historical_identity_selection_basis')=='complete-original-provider-matchday-only-v1':
            if not p.get('allow_original_matchday_only_club_identity') or (
                    whole.original_matchday_club_witness(p['original_opening'],p['desired_people'])!=p['club_witness']):
                raise ValueError('complete original matchday-only identity is not explicitly bound or reproducible')
        if p.get('club_witness',{}).get('historical_identity_selection_basis')=='complete-original-provider-matchday-and-dated-career-reserves-v1':
            if not (p.get('allow_original_matchday_only_club_identity') and p.get('allow_original_provider_career_reserves')) or (
                    whole.original_matchday_career_club_witness(p['original_opening'],p['desired_people'])!=p['club_witness']):
                raise ValueError('complete original matchday/career identity lacks bound source authority')
        if p.get('allocation_gap') or not p['allocation'] or len(p['allocation'])!=len(p['desired_people']):
            raise ValueError('paired disposition has an incomplete fixed-capacity allocation')
        expected=set(p['before_club']['roster_player_ids'])
        if len(expected)!=len(p['allocation']) or {r['player_id'] for r in p['allocation']}!=expected:
            raise ValueError('paired disposition omits a fixed native roster slot')
        if p.get('allow_keeper_order_exchange'):
            exchange=whole.keeper_exchange(p['allocation'])
            if exchange!=p.get('startup_order_exchange'):
                raise ValueError('paired keeper exchange differs from the full sourced XI')
            targets={r['carrier_id']:r['after'] for r in exchange}
            if any(r.get('native_startup_order_after')!=targets.get(r['carrier_id'],r['native_startup_order_before'])
                    or not whole.opening_edge(r['native_startup_order_after'],r['replacement']) for r in p['allocation']):
                raise ValueError('paired keeper exchange moves reserves or leaves an incorrect goalkeeper')
        elif p.get('startup_order_exchange'):
            raise ValueError('paired starter exchange lacks its explicit bounded policy')
        for row in p['allocation']:
            if row['player_id'] in slots:raise ValueError('paired disposition repeats a native player slot')
            if row['carrier_id'] in native_carriers:raise ValueError('paired disposition repeats a native player carrier')
            native_carriers.add(row['carrier_id'])
            slots[row['player_id']]=p['before_club']['id']
        for person in p['desired_people']:
            if person.get('membership')=='positive-original-provider-dated-opening-reserve':
                if not p.get('allow_original_provider_career_reserves'):
                    raise ValueError('original provider reserve lacks explicit whole-club authority')
                from scripts import season_original_soccerbase_reserves_v1 as originals
                originals.verify_reserve(person,p['original_opening'])
            id=person['source_person']['source_player_id']
            key=(whole.roster.normalise(person['source_player']['name']),person['source_player']['birth_date'])
            if key[0] in club_full_names:
                raise ValueError('complete club repeats a full player name; resolve provider identity/DOB conflict first')
            club_full_names.add(key[0])
            if id in desired_ids or key in desired_keys:raise ValueError('paired disposition introduces a cross-club player copy')
            desired_ids.add(id);desired_keys.add(key)
    for p in proposals:
        for collision in p['outside_collisions']:
            if (collision['other_club_id'] not in retired
                    or slots.get(collision['other_player_id'])!=collision['other_club_id']):
                raise ValueError('incoming player has a copy outside the complete paired retirement')
            covered.append(collision)
    # An old duplicated club must retain another carrier after this transaction.
    for p in proposals:
        if not any(c['id'] not in retired for c in p['retained_duplicate_clubs']):
            raise ValueError('paired disposition would remove every copy of an existing real club')
    return {'retired_club_ids':sorted(retired),'corrected_slots':len(slots),
        'source_people':len(desired_ids),'covered_other_club_copies':covered,
        'native_publication_authorised':False}


def source_guard(document, proposals):
    """A singleton is explicit and cannot cover an outside-club copy."""
    schema=document.get('schema_version')
    if schema==SINGLETON_SCHEMA:
        if len(proposals)!=1 or proposals[0].get('outside_collisions'):
            raise ValueError('complete singleton must have one full club and zero outside copies')
        return validate_group(proposals,allow_singleton=True)
    if schema!=SCHEMA:
        raise ValueError('unsupported complete whole-club transaction schema')
    return validate_group(proposals)


def prepare(season, pairs, prior_plan, output, *, capacity_bundle=None, keeper_exchange_carriers=()):
    if output.exists():raise ValueError('paired source proposal is immutable')
    plan=json.loads(prior_plan.read_text());bindings=plan['bindings']
    if not set(keeper_exchange_carriers)<={c for c,n in pairs}:
        raise ValueError('keeper exchange must name one of the explicitly replaced whole clubs')
    release=registry.load_preferred_release(season)
    proposed=[];paths=[]
    for carrier,target in pairs:
        path=output.parent/f'{carrier}-source-collision-diagnostic.json'
        if not path.exists():
            whole.prepare(season,carrier,target,ROOT/bindings['published_person_supplement']['path'],
                ROOT/bindings['published_transfer_supplement']['path'],
                ROOT/bindings['soccerbase_opening_sources']['club_entities']['path'],path,
                capacity_bundle=capacity_bundle or bindings.get('same_carrier_name_capacity'),
                baseline_release_id=release.release_id,inspect_collisions=True,snapshot_binding=bindings['snapshot'],
                allow_keeper_order_exchange=carrier in keeper_exchange_carriers)
        proposed.append(json.loads(path.read_text()));paths.append(path)
        if proposed[-1]['bindings'].get('snapshot')!=bindings['snapshot']:
            raise ValueError('saved paired diagnostic lacks the exact original person/history snapshot')
        if capacity_bundle is not None and proposed[-1].get('capacity_policy_bundle')!=capacity_bundle:
            raise ValueError('saved paired diagnostic lacks the explicitly selected capacity evidence')
        if bool(proposed[-1].get('allow_keeper_order_exchange'))!=(carrier in keeper_exchange_carriers):
            raise ValueError('saved paired diagnostic has a different explicit keeper exchange policy')
    guard=validate_group(proposed)
    if any(p['release_id']!=release.release_id for p in proposed):raise ValueError('saved paired diagnostics have a stale baseline')
    doc={'schema_version':SCHEMA,'season':season,'release_id':release.release_id,
        'proposals':[{'path':registry.relative_workspace_path(path),'sha256':registry.sha256_file(path)} for path in paths],
        'source_guard':guard,'native_writes':0,'registered':False,'publication_authorised':False,
        'remaining':['independent full coupled source replay','dated managers','native compilation/preservation',
            'kit/ground identity','runner actual rosters','no-new-duplicates','normal release publication']}
    pipeline.write_canonical_json(output,doc);print(json.dumps(guard),flush=True)
    return doc


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--season',required=True)
    p.add_argument('--pair',nargs=2,action='append',required=True,metavar=('CARRIER','CLUB'))
    p.add_argument('--prior-plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--capacity-plan',type=Path,
        help='Explicit older source plan carrying the independently runtime-proven same-carrier capacity bundle')
    p.add_argument('--keeper-order-exchange-carrier',type=int,action='append',default=[],
        help='Explicit owned mode1 whole-club keeper exchange; never moves a reserve into the XI')
    a=p.parse_args();bundle=None
    if a.capacity_plan is not None:
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        bundle=json.loads(a.capacity_plan.read_text())['bindings']['same_carrier_name_capacity']
        capacity.verify_bundle(bundle)
    prepare(a.season,[(int(c),n) for c,n in a.pair],a.prior_plan,a.output,capacity_bundle=bundle,
        keeper_exchange_carriers=a.keeper_order_exchange_carrier)
