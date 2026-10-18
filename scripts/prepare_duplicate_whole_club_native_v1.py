#!/usr/bin/env python3
"""Prepare, but never register, one independently replayed whole-club repair.

This is not a reserve-swap loophole: the complete fixed roster, original XI,
outside-copy exclusion and dated coach are verified together. Mode-1 opaque
tactics, ground and kit bytes remain declared fallbacks, NOT historical proof.
The candidate requires its own runtime/asset review before normal publication.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import prepare_duplicate_club_disposition_v1 as source
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_club_label_plan_v1 as labels
from scripts import season_source_package_builder_v1 as builder
from scripts import capture_soccerbase_opening_managers_v1 as managers
from scripts import season_manager_display_repair_v1 as manager_display
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.ent_manager_profiles import parse_indexed_ent_manager_profile

SCHEMA='pm99-private-whole-club-native-candidate-v1'


def original(binding):
    path=registry.ROOT/binding['path'];registry.relative_workspace_path(path)
    if registry.sha256_file(path)!=binding['sha256']:raise ValueError('whole-club source binding changed')
    return path


def validate_allocation(package,proposal):
    club=next((c for c in package['clubs'] if c['id']==proposal['before_club']['id']),None)
    if club!=proposal['before_club']:raise ValueError('whole-club native baseline recipe changed')
    slots={p['id']:p for p in package['players'] if p['club_id']==club['id']}
    allocation=proposal['allocation'];desired=proposal['desired_people']
    if not allocation or len(allocation)!=len(slots) or len(desired)!=len(slots):
        raise ValueError('whole-club native repair requires every fixed slot allocated')
    if {r['player_id'] for r in allocation}!=set(slots) or len({r['carrier_id'] for r in allocation})!=len(slots):
        raise ValueError('whole-club allocation omits or duplicates native slots')
    people=[r['replacement']['source_person']['source_player_id'] for r in allocation]
    if len(set(people))!=len(people) or set(people)!={r['source_person']['source_player_id'] for r in desired}:
        raise ValueError('whole-club allocation differs from complete sourced people')
    for row in allocation:
        if row['before_recipe']!=slots[row['player_id']] or row['carrier_id']!=slots[row['player_id']]['carrier_id']:
            raise ValueError('whole-club allocation references a stale or other-club carrier')
        wanted=next(r for r in desired if r['source_person']['source_player_id']==row['replacement']['source_person']['source_player_id'])
        if row['replacement']!=wanted or row['display']['source_name']!=wanted['source_player']['name']:
            raise ValueError('whole-club replacement no longer matches its dated source')
    starters=[r for r in desired if r['membership']=='starting_xi']
    if len(starters)!=11 or starters[0]['source_player']['position']!='G' or sum(
            r['source_player']['position']=='G' for r in starters)!=1:
        raise ValueError('whole-club source lacks the exact one-keeper first XI')
    return club,slots


def compile_recipe(package,proposal):
    """Reuse the pure ratings/fact composer, not reserve ownership authorisation."""
    club,slots=validate_allocation(package,proposal)
    copied=copy.deepcopy(package)
    target=next(c for c in copied['clubs'] if c['id']==club['id'])
    target.update(name=proposal['new_club'],full_name=proposal['new_club'],
        identity_id=builder._source_club_identity_id('england',proposal['new_club']))
    day=proposal['original_opening']['fixture']['date']
    updates=[{'player_id':r['player_id'],'carrier_id':r['carrier_id'],'layer':'main',
        'before':r['before_recipe'],'replacement':r['replacement'],
        'replacement_opening_evidence':{'date':day}} for r in proposal['allocation']]
    composition={'season':proposal['season'],'bindings':{'snapshot':{'project_url':'https://www.soccerbase.com/'}},
        'whole_club_original_source':proposal,'updates':updates}
    result=delta.updated_package(copied,composition)
    by_id={p['id']:p for p in result['players']}
    for row in proposal['allocation']:by_id[row['player_id']]['name']=row['display']['display_name']
    target=next(c for c in result['clubs'] if c['id']==club['id'])
    ids={r['replacement']['source_person']['source_player_id']:r['player_id'] for r in proposal['allocation']}
    ordered=[ids[r['source_person']['source_player_id']] for r in proposal['desired_people']]
    target['roster_player_ids']=ordered
    # The actual XI/bench is in the immutable whole-club artifact, and the
    # roster order follows it. Do not smuggle unproven tactical deployment
    # into the two-field mode-1 preserve contract or widen its schema.
    artifact=next(a for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(composition))
    target['proof']={'artifact_id':artifact['id'],'grade':'source-receipt'}
    for item in result['sources']:
        if item.get('evidence_artifact_id')==artifact['id']:
            item['title']='Complete original opening roster replacing a duplicated non-playable club'
    for item in result['proofs']:
        if item.get('artifact_id')==artifact['id']:
            item['covers']=['complete-original-XI-bench-and-dated-reserves; NOT mode1-tactical-deployment']
    package_v2.validate_package(result,strict=False)
    return result,composition


def rewrite_roster(eq,carrier,ordered):
    index=IndexedFDIFile.from_bytes(eq);entry=next(e for e in index.entries if e.record_id==carrier)
    raw=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
    before=parse_eq_external_team_roster_payload(raw,{})
    if before is None or before.mode_byte!=1:raise ValueError('whole-club route is non-playable mode1 only')
    if len(ordered)!=len(before.rows) or set(ordered)!={r.player_record_id for r in before.rows}:
        raise ValueError('whole-club order must preserve this club exact fixed carrier set')
    if any(r.flag for r in before.rows):raise ValueError('mode1 availability flags need separate semantic evidence')
    new=delta.compiler._rewrite_roster_tail(raw,ordered)
    first=before.rows[0].raw_row_offset
    if raw[:first]!=new[:first] or len(raw)!=len(new):raise ValueError('whole-club order changed opaque club/tactics bytes')
    return delta.compiler._rebuild_indexed(eq,index,{carrier:delta.compiler.xor_decode(new)})


def preserve_other_records(before,after,permitted):
    old={e.record_id:e.decode_payload(before) for e in IndexedFDIFile.from_bytes(before).entries}
    new={e.record_id:e.decode_payload(after) for e in IndexedFDIFile.from_bytes(after).entries}
    if old.keys()!=new.keys() or not set(permitted)<=set(old):
        raise ValueError('whole-club transaction changed the fixed native carrier directory')
    if any(new[id]!=raw for id,raw in old.items() if id not in permitted):
        raise ValueError('whole-club transaction changed an unrelated native record')


def prepare(proposal_path,manager_path,output,input_overrides=None):
    if output.exists():raise ValueError('whole-club native candidate is immutable; never overwrite')
    implementations={'whole_club_source':Path(source.__file__),'candidate_builder':Path(__file__),
        'fact_composer':Path(delta.__file__),'native_compiler':Path(delta.compiler.__file__),
        'original_opening_replayer':Path(source.replay.__file__),'public_input_binder':Path(source.public.__file__),
        'published_person_reader':Path(source.persons.__file__),'published_history_reader':Path(source.histories.__file__),
        'published_display_reader':Path(source.aliases.__file__),'published_family_reader':Path(source.families.__file__),
        'capacity_checker':Path(capacity.__file__),'dated_manager_reader':Path(managers.__file__),
        'manager_display_policy':Path(manager_display.__file__)}
    implementation_hashes={key:registry.sha256_file(path) for key,path in implementations.items()}
    proposal=json.loads(proposal_path.read_text())
    if proposal.get('schema_version')!=source.SCHEMA or proposal.get('approved_for_native_publication') is not False:
        raise ValueError('whole-club candidate requires an explicit source-only proposal')
    # A PRIVATE candidate can use a registered, not-yet-promoted baseline.
    # Future publication must separately require that exact current baseline.
    release=registry.load_registered_release(proposal['season'],proposal['release_id'])
    if release.release_id!=proposal['release_id'] or any(registry.sha256_file(path)!=expected for path,expected in (
        (release.package_path,proposal['package_sha256']),
        (release.game_path/'DBDAT/JUG98030.FDI',proposal['jug_sha256']),
        (release.game_path/'DBDAT/EQ98030.FDI',proposal['eq_sha256']))):
        raise ValueError('whole-club source proposal baseline changed')
    # Reconstruct the entire source decision, full fixed assignment and outside
    # collisions. A JSON claim, cached count or earlier allocation is not proof.
    with tempfile.TemporaryDirectory(prefix='pm99-whole-club-replay-') as temporary:
        replay_path=Path(temporary)/'original-replay.json'
        source.prepare(proposal['season'],proposal['before_club']['carrier_id'],proposal['new_club'],
            original(proposal['bindings']['published_person_supplement']),
            original(proposal['bindings']['published_transfer_supplement']),original(proposal['entity_binding']),
            replay_path,capacity_bundle=proposal.get('capacity_policy_bundle'),
            baseline_release_id=proposal['release_id'],snapshot_binding=proposal['bindings'].get('snapshot'))
        if json.loads(replay_path.read_text())!=proposal:raise ValueError('whole-club original source replay differs')
    receipt=json.loads(manager_path.with_name(manager_path.name+'.source.json').read_text())
    actual=proposal['original_opening'];team_id=actual['source_capture']['source_path'].split('/')[2]
    expected_url=f'https://www.soccerbase.com/teams/team.sd?team_id={team_id}&teamTabs=managers'
    if receipt!={'url':expected_url,'sha256':registry.sha256_file(manager_path)}:
        raise ValueError('dated manager source does not identify the same original team')
    from scripts.prepare_paired_whole_club_native_v1 import dated_manager_identity, recipe_inputs
    from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
    manager_name, source_manager_id=dated_manager_identity(manager_path.read_bytes(),actual['fixture']['date'])
    short,_=manager_display.short_name(manager_name)
    if short is None:raise ValueError('dated manager needs an unambiguous native display name')
    native_names={'surname':short,'display_name':short}
    package=json.loads(release.package_path.read_text());club,slots=validate_allocation(package,proposal)
    holdings,names=_manager_graph(eq_path=release.game_path/'DBDAT/EQ98030.FDI',ent_path=release.game_path/'DBDAT/ENT98030.FDI')
    manager=next(m for m in package['managers'] if m['id']==club['manager_id']);mid=manager['carrier_id']
    if [c['carrier_id'] for c in holdings.get(mid,[])]!=[club['carrier_id']]:
        raise ValueError('whole-club target does not exclusively own its native coach')
    result,composition=compile_recipe(package,proposal)
    patched_source=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    for row in proposal['allocation']:
        if row.get('same_carrier_name_capacity') is not None:
            patched_source,claim=capacity.recover_slot(patched_source,row['carrier_id'],proposal['capacity_policy_bundle'])
            if claim!=row['same_carrier_name_capacity']:raise ValueError('whole-club capacity claim changed')
    countries=delta.compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    jug=delta.compile_players(patched_source,result,set(slots),countries)
    before_orders=source.startup_orders((release.game_path/'DBDAT/JUG98030.FDI').read_bytes(),list(slots.values()))
    after_orders=source.startup_orders(jug,list(slots.values()))
    if before_orders!=after_orders:raise ValueError('whole-club repair changed native startup control bytes')
    for row in proposal['allocation']:
        order=after_orders[row['carrier_id']]
        if row.get('native_startup_order_before')!=order or not source.opening_edge(order,row['replacement']):
            raise ValueError('whole-club repair did not place the sourced XI and keeper in actual startup slots')
    target=next(c for c in result['clubs'] if c['id']==club['id']);players={p['id']:p for p in result['players']}
    eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    eq=rewrite_roster(eq,club['carrier_id'],[players[p]['carrier_id'] for p in target['roster_player_ids']])
    e=next(e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id==club['carrier_id'])
    short,full,_=labels.prefix_parts(e.decode_payload(eq))
    eq,_=labels.rewrite_club_labels(eq,[{'carrier_id':club['carrier_id'],'native_before':short,
        'native_full_before':full,'native_after':delta.compiler._pm99_text(proposal['new_club'],label='sourced new club')}])
    ent=(release.game_path/'DBDAT/ENT98030.FDI').read_bytes();ei=IndexedFDIFile.from_bytes(ent)
    me=next(e for e in ei.entries if e.record_id==mid)
    changed=delta.compiler._patch_ent_name(me.decode_payload(ent),mid,
        delta.compiler._pm99_text(manager_name,label='dated whole-club manager'),native_names=native_names)
    ent=delta.compiler._rebuild_indexed(ent,ei,{mid:changed})
    manager_artifact='whole-club-dated-manager-'+proposal['season']
    next(m for m in result['managers'] if m['id']==manager['id']).update(name=manager_name,policy='write',
        person_id=f'manager-soccerbase-{source_manager_id}',
        native_names=native_names,proof={'artifact_id':manager_artifact,'grade':'source-receipt'})
    result['artifacts'].append({'id':manager_artifact,'kind':'season-input','sha256':receipt['sha256'],
        'media_type':'text/html','relative_path':'manager-original.html'})
    result['artifacts'].sort(key=lambda a:a['id'])
    for filename,data,permitted in (
        ('JUG98030.FDI',jug,{r['carrier_id'] for r in proposal['allocation']}),
        ('EQ98030.FDI',eq,{club['carrier_id']}),('ENT98030.FDI',ent,{mid})):
        preserve_other_records((release.game_path/'DBDAT'/filename).read_bytes(),data,permitted)
    archive,photo_offsets=delta.no_photo_archive((release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes(),
                                               {r['carrier_id'] for r in proposal['allocation']})
    inputs=recipe_inputs(result,release.package_path.parent,input_overrides)
    predicted=len(jug)+len(eq)+len(ent)+len(archive)+32*1024**2
    if shutil.disk_usage(release.game_path).free-predicted<8*1024**3:
        raise ValueError('whole-club candidate would cross the 8-GiB reserve')
    output.mkdir(parents=True);shutil.copytree(release.game_path,output/'game',copy_function=os.link)
    for name,data in (('JUG98030.FDI',jug),('EQ98030.FDI',eq),('ENT98030.FDI',ent),('MINIFOTO.PKF',archive)):
        path=output/'game/DBDAT'/name
        if path.read_bytes()!=data:
            temporary=output/(name+'.partial');temporary.write_bytes(data);os.replace(temporary,path)
    for carrier in photo_offsets:
        path=output/'game/DBDAT/MINIFOTO'/f'J96{carrier:05d}.BMP'
        if path.exists():path.unlink()
    pipeline.write_canonical_json(output/'season-package.json',result)
    pipeline.write_canonical_json(output/delta.plan_filename(composition),composition)
    os.link(manager_path,output/'manager-original.html')
    for artifact in result['artifacts']:
        if not (relative:=artifact.get('relative_path')):continue
        relative=Path(relative)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe inherited recipe input')
        target=output/relative
        if not target.exists():
            previous,bound=inputs[relative]
            if verify_recipe_artifact(previous,artifact['sha256'])!=bound:
                raise ValueError('inherited whole-club recipe input changed')
            target.parent.mkdir(parents=True,exist_ok=True);os.link(previous,target)
        verify_recipe_artifact(target,artifact['sha256'])
    holders_after,names_after=_manager_graph(eq_path=output/'game/DBDAT/EQ98030.FDI',ent_path=output/'game/DBDAT/ENT98030.FDI')
    if names_after.get(mid)!=native_names['display_name'] or [c['carrier_id'] for c in holders_after.get(mid,[])]!=[club['carrier_id']]:
        raise ValueError('whole-club coach name/ownership failed native readback')
    if any(registry.sha256_file(path)!=implementation_hashes[key] for key,path in implementations.items()):
        raise ValueError('whole-club source or compiler changed during independent replay')
    from scripts.closeout_duplicate_ownership_batch_v1 import freeze_implementations
    frozen=freeze_implementations(implementations,implementation_hashes,output/'frozen-implementations')
    proof={'schema_version':SCHEMA,'season':proposal['season'],'source_release_id':release.release_id,
        'source_proposal':{'path':registry.relative_workspace_path(proposal_path),'sha256':registry.sha256_file(proposal_path)},
        'source_manager':{'path':registry.relative_workspace_path(manager_path),'sha256':registry.sha256_file(manager_path)},
        'old_club':club['name'],'new_club':proposal['new_club'],'club_carrier_id':club['carrier_id'],
        'corrected_slots':len(slots),'manager':manager_name,'original_source_replayed_exactly':True,
        'manager_native_names':native_names,'source_manager_id':source_manager_id,
        'unrelated_native_records_byte_identical':True,
        'historical_XI_sourced':True,'runtime_XI_verified':False,
        'native_startup_XI_membership_verified':True,'startup_controls_byte_identical':True,
        'implementation_bindings':{key:{'path':registry.relative_workspace_path(frozen[key]),
            'sha256':implementation_hashes[key]} for key in implementations},
        'registered':False,'historical_release':False,'publication_authorised':False,
        'remaining':['runtime named-player and roster proof','kit/ground fallback review','mode1 deployment not proven',
                     'independent full-record preservation and no-new-duplicate audit','normal release publication'],
        'native_hashes':{name:registry.sha256_file(output/'game/DBDAT'/name)
            for name in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF')}}
    pipeline.write_canonical_json(output/'candidate-receipt.json',proof)
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-proposal',type=Path,required=True)
    p.add_argument('--manager-original',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recipe-input',action='append',default=[],help='Explicit exact inherited input RELATIVE=PATH')
    a=p.parse_args();overrides={}
    for value in a.recipe_input:
        relative,path=value.split('=',1)
        if relative in overrides:raise ValueError('duplicate inherited recipe input override')
        overrides[relative]=Path(path)
    print(json.dumps(prepare(a.source_proposal,a.manager_original,a.output,overrides)),flush=True)
