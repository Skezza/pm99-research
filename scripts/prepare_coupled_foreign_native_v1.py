"""Source-bound OFK/Celta carrier exchange through the existing native writers.

Private candidate only. Two fixed roster capacities, all availability flags and
every unrelated native record preserved. No name-capacity guard is relaxed.
"""
import copy
from pathlib import Path
import tempfile

from scripts import prepare_ofk_2004_private_native_v1 as ofk_native
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_ofk_2015_verified_inputs_v1 as inputs
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.season_art_transaction_v1 import atomic_bytes
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _patch_indexed_eq_team_string_payload
from app.player_initial_order import read_initial_order,patch_initial_orders,OrderReplacement,patch_owned_mode1_complete_orders


def compose_recipe(package,proposal):
    initial,ofk_composition,old_slots=ofk_native.compose_recipe(package,proposal)
    exchange=proposal['coupled_native_carrier_exchange']
    moves=proposal['coupled_Celta_allocation']+proposal['coupled_OFK_transferred_allocation']
    # Ratings must use the destination club's strength, not the old carrier's
    # owner. Apply the explicitly sourced exchange to the symbolic recipe
    # before the unchanged deterministic rating/fact composer runs.
    outgoing,incoming=exchange['OFK_to_Celta'],exchange['Celta_to_OFK']
    outgoing_player=next(p for p in initial['players'] if p['carrier_id']==outgoing)
    incoming_player=next(p for p in initial['players'] if p['carrier_id']==incoming)
    outgoing_player['club_id']='club-48';incoming_player['club_id']='club-706'
    for club,old_id,new_id in [(next(c for c in initial['clubs'] if c['carrier_id']==706),outgoing_player['id'],incoming_player['id']),
            (next(c for c in initial['clubs'] if c['carrier_id']==48),incoming_player['id'],outgoing_player['id'])]:
        club['roster_player_ids']=[new_id if id==old_id else id for id in club['roster_player_ids']]
    players={p['id']:p for p in initial['players']}
    updates=[dict(player_id=r['player_id'],carrier_id=r['carrier_id'],layer='main',
        before=copy.deepcopy(players[r['player_id']]),replacement=r['replacement'],
        replacement_opening_evidence={'date':'2015-08-01'}) for r in moves]
    composition=dict(season='2015-16',source_title='Original OFK first XI and positive Celta preseason ownership: fixed-capacity carrier exchange',
        bindings={'snapshot':{'project_url':'https://www.transfermarkt.co.uk/'}},
        source_transaction=proposal,carrier_exchange=exchange,updates=updates,
        proof_covers=['dated-source-person-and-two-club-ownership','fixed18-and25-capacities',
            'NOT complete Celta historical XI or opaque foreign tactics'])
    final=delta.updated_package(initial,composition)
    players={p['id']:p for p in final['players']}
    for row in moves: players[row['player_id']]['name']=row['display']['display_name']
    outgoing,incoming=exchange['OFK_to_Celta'],exchange['Celta_to_OFK']
    outgoing_player=next(p for p in final['players'] if p['carrier_id']==outgoing)
    incoming_player=next(p for p in final['players'] if p['carrier_id']==incoming)
    outgoing_player['club_id']='club-48';incoming_player['club_id']='club-706'
    target=next(c for c in final['clubs'] if c['carrier_id']==706)
    celta=next(c for c in final['clubs'] if c['carrier_id']==48)
    target['roster_player_ids']=[incoming_player['id'] if id==outgoing_player['id'] else id for id in target['roster_player_ids']]
    celta['roster_player_ids']=[outgoing_player['id'] if id==incoming_player['id'] else id for id in celta['roster_player_ids']]
    if len(target['roster_player_ids'])!=18 or len(celta['roster_player_ids'])!=25:
        raise ValueError('source carrier exchange changed a fixed roster capacity')
    packages.validate_package(final)
    return final,[ofk_composition,composition],set(old_slots)|{incoming_player['id']}


def compile_files(baseline,proposal):
    package=pipeline.read_json_file(baseline.package_path)
    result,compositions,changed_ids=compose_recipe(package,proposal)
    before={n:(baseline.game_path/'DBDAT'/n).read_bytes() for n in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF')}
    old_index=IndexedFDIFile.from_bytes(before['EQ98030.FDI'])
    owners={}
    rosters={}
    for e in old_index.entries:
        raw=before['EQ98030.FDI'][e.payload_offset:e.payload_offset+e.payload_length]
        roster=native.parse_eq_external_team_roster_payload(raw,{})
        if roster is None:
            if len(raw)>=600 and len(raw)>0x29 and raw[0x29] in (0,1):
                raise ValueError('unreadable club prevents carrier-exchange ownership proof')
            continue
        rosters[e.record_id]=roster
        for row in roster.rows: owners.setdefault(row.player_record_id,set()).add(e.record_id)
    exchange=proposal['coupled_native_carrier_exchange']
    outgoing,incoming=exchange['OFK_to_Celta'],exchange['Celta_to_OFK']
    if owners.get(outgoing)!={706} or owners.get(incoming)!={48}:
        raise ValueError('carrier exchange lacks exclusive original native owners')
    eq_replacements={}
    players={p['id']:p for p in result['players']}
    for cid in (48,706):
        entry=next(e for e in old_index.entries if e.record_id==cid)
        raw=before['EQ98030.FDI'][entry.payload_offset:entry.payload_offset+entry.payload_length]
        club=next(c for c in result['clubs'] if c['carrier_id']==cid)
        ordered=[players[id]['carrier_id'] for id in club['roster_player_ids']]
        old=rosters[cid]
        expected={r.player_record_id for r in old.rows}-{incoming if cid==48 else outgoing}|{outgoing if cid==48 else incoming}
        if old.mode_byte!=1 or len(ordered)!=len(old.rows) or set(ordered)!=expected:
            raise ValueError('carrier exchange changed undeclared roster membership')
        new=delta.compiler._rewrite_roster_tail(raw,ordered)
        parsed=native.parse_eq_external_team_roster_payload(new,{})
        first=old.rows[0].raw_row_offset
        if (len(new)!=len(raw) or raw[:first]!=new[:first]
                or [r.flag for r in old.rows]!=[r.flag for r in parsed.rows]):
            raise ValueError('carrier exchange changed capacity, flags, tactics or opaque team bytes')
        eq_replacements[cid]=delta.compiler.xor_decode(new)
    eq=delta.compiler._rebuild_indexed(before['EQ98030.FDI'],old_index,eq_replacements)
    dated=proposal['dated_manager_ground']
    eq_index=IndexedFDIFile.from_bytes(eq)
    target_entry=next(e for e in eq_index.entries if e.record_id==706)
    new,_=_patch_indexed_eq_team_string_payload(target_entry.decode_payload(eq),
        short_name='OFK Beograd',full_club_name='OFK Beograd',stadium_name=dated['ground'])
    eq=delta.compiler._rebuild_indexed(eq,eq_index,{706:new})
    codes=delta.compiler._extract_country_codes_from_textos(baseline.game_path/'DBDAT/TEXTOS.PKF')
    jug=delta.compile_players(before['JUG98030.FDI'],result,changed_ids,codes)
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    target=next(c for c in result['clubs'] if c['carrier_id']==706)
    ordered=[players[id]['carrier_id'] for id in target['roster_player_ids']]
    orders=[]
    for n,id in enumerate(ordered,1):
        field=read_initial_order(entries[id].decode_payload(jug))
        orders.append(OrderReplacement(id,field.name,field.order,n))
    jug=patch_owned_mode1_complete_orders(jug,eq,club_record_id=706,replacements=orders)
    old_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before['JUG98030.FDI']).entries}
    old_order=read_initial_order(old_entries[incoming].decode_payload(before['JUG98030.FDI'])).order
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    field=read_initial_order(entries[outgoing].decode_payload(jug))
    jug=patch_initial_orders(jug,[OrderReplacement(outgoing,field.name,field.order,old_order)],allow_compact=True)
    holders,_=_manager_graph(eq_path=baseline.game_path/'DBDAT/EQ98030.FDI',ent_path=baseline.game_path/'DBDAT/ENT98030.FDI')
    manager=next(m for m in result['managers'] if m['id']==target['manager_id'])
    mid=manager['carrier_id']
    if [c['carrier_id'] for c in holders.get(mid,[])]!=[706]:
        raise ValueError('dated OFK manager native owner is not exclusive')
    ent_index=IndexedFDIFile.from_bytes(before['ENT98030.FDI'])
    ent_entry=next(e for e in ent_index.entries if e.record_id==mid)
    names={'surname':'Petrovic','display_name':'Petrovic'}
    new=delta.compiler._patch_ent_name(ent_entry.decode_payload(before['ENT98030.FDI']),mid,dated['manager'],native_names=names)
    ent=delta.compiler._rebuild_indexed(before['ENT98030.FDI'],ent_index,{mid:new})
    artifact='ofk-original-manager-ground-2015'
    manager.update(name=dated['manager'],policy='write',native_names=names,person_id='manager-transfermarkt-5229',
        proof={'artifact_id':artifact,'grade':'source-receipt'})
    target.update(ground_policy='write',ground_name=dated['ground'])
    result['artifacts'].append(dict(id=artifact,kind='season-input',relative_path='ofk-original-opening-2015.html',
        sha256=proposal['dated_manager_ground_binding']['sha256'],media_type='text/html'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    carriers={players[id]['carrier_id'] for id in changed_ids}
    photo,_=delta.no_photo_archive(before['MINIFOTO.PKF'],carriers)
    after={'JUG98030.FDI':jug,'EQ98030.FDI':eq,'ENT98030.FDI':ent,'MINIFOTO.PKF':photo}
    for name,ids in [('JUG98030.FDI',carriers),('EQ98030.FDI',{48,706}),('ENT98030.FDI',{mid})]:
        native.preserve_other_records(before[name],after[name],ids)
    if [(e.record_id,e.payload_offset,e.payload_length) for e in old_entries.values()] != [
            (e.record_id,e.payload_offset,e.payload_length) for e in IndexedFDIFile.from_bytes(jug).entries]:
        raise ValueError('coupled native player write moved the fixed directory/windows')
    return result,compositions,before,after,dict(ordered_native_carriers=ordered,corrected_native_carriers=sorted(carriers),
        Celta_replacement_carrier=outgoing,Celta_preserved_initial_order=old_order,manager_carrier_id=mid,
        carrier_exchange=exchange,dated_manager_ground=dated,unselected_native_records_identical=True)


def prepare(output):
    if output.exists(): raise ValueError('private coupled foreign candidate is immutable')
    path=source.AUDIT/'ofk-2015-celta-verified-source-inputs-v1.json'
    proposal=pipeline.read_json_file(path)
    with tempfile.TemporaryDirectory(prefix='pm99-coupled-foreign-source-') as temporary:
        if inputs.prepare(Path(temporary)/'source.json')!=proposal:
            raise ValueError('coupled foreign source inputs do not reproduce')
    baseline=registry.load_registered_release('2015-16',proposal['baseline_release_id'])
    if registry.sha256_file(baseline.package_path)!=proposal['baseline_package']['sha256']:
        raise ValueError('coupled foreign known-good baseline recipe changed')
    first=compile_files(baseline,proposal);second=compile_files(baseline,proposal)
    if first!=second: raise ValueError('source-backed coupled native transaction is not deterministic')
    package,compositions,before,after,detail=first
    output.mkdir(parents=True)
    for name,raw in after.items():atomic_bytes(output/'DBDAT'/name,raw)
    for plan in compositions:pipeline.write_canonical_json(output/delta.plan_filename(plan),plan)
    pipeline.write_canonical_json(output/'season-package.json',package)
    receipt=dict(schema_version='pm99-private-coupled-foreign-native-v1',season='2015-16',
        baseline_release_id=baseline.release_id,source_proposal_sha256=registry.sha256_file(path),
        source_plan=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        recipe_sha256=registry.sha256_file(output/'season-package.json'),
        native_hashes={n:registry.sha256_file(output/'DBDAT'/n) for n in after},
        before_hashes={n:registry.sha256_file(baseline.game_path/'DBDAT'/n) for n in before},
        detail=detail,deterministic_native_and_recipe=True,registered=False,publication_authorised=False,
        remaining=['Independent native/person/ownership readback','3period kit sizes','complete source reconstruction',
            'actual profiles/native kit pixels and fresh normal startup'],
        scope='OFK18 plus one positively sourced Celta player, fixed roster-carrier exchange. Not complete historical Celta XI or opaque foreign tactics approval.')
    pipeline.write_canonical_json(output/'native-proof.json',receipt)
    return receipt


if __name__=='__main__':
    x=prepare(source.AUDIT/'ofk-2015-celta-private-native-v1')
    print(dict(native_people=len(x['detail']['corrected_native_carriers']),registered=False,
        carrier_exchange=x['detail']['carrier_exchange']),flush=True)
