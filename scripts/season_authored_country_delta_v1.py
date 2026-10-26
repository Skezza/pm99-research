"""Compile a frozen, reviewed country recipe through existing native writers.

Historical sourcing belongs to the bound authoring receipt. This adapter proves
the declared recipe-to-native delta, scope preservation and exact SOURCE replay;
it does not turn an editorial decision into historical evidence.
"""
import copy
import hashlib
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders
from app.ent_manager_profiles import parse_indexed_ent_manager_profile, replace_indexed_ent_manager_names
from app.xor import xor_decode
from scripts import season_pipeline_v2 as p, season_package_v2 as packages, season_release_registry_v1 as r
from scripts import season_package_compiler_v2 as compiler
from scripts import season_opening_cohort_delta_core_v1 as cohort
from scripts.season_historical_roster_audit_v1 import club_group
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts import season_source_bound_fixture_membership_v1 as paths
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-reviewed-country-recipe-native-delta-v1'
MODE = 'known-good-reviewed-country-recipe-native-delta-v1'
PREFIX = 'reviewed-country-recipe-delta-'
_CACHE = {}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return PREFIX + plan['transaction_id'] + '.json'


def _bound(row):
    path = paths._source_path(row['path'])
    if r.sha256_file(path) != row['sha256']:
        raise ValueError('country input hash changed: ' + row['path'])
    return path


def _parent(base):
    return dict(season=base.season, release_id=base.release_id, manifest_sha256=base.manifest_sha256,
                package_sha256=r.sha256_file(base.package_path),
                native_sha256={name: r.sha256_file(base.game_path/'DBDAT'/name)
                    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF', 'TEXTOS.PKF')})


def verify_recipe_mask(before, after, request):
    """Close unrelated rows; retain country carrier totals and each club size."""
    if set(before) != set(after):
        raise ValueError('country delta cannot change package top-level shape')
    selected = set(request['club_carrier_ids'])
    oldclubs = {c['carrier_id']: c for c in before['clubs']}
    newclubs = {c['carrier_id']: c for c in after['clubs']}
    if set(oldclubs) != set(newclubs) or selected != {cid for cid,c in oldclubs.items() if club_group(c)==request['country']}:
        raise ValueError('country delta must select exactly the existing country club graph')
    people = {pid for cid in selected for pid in oldclubs[cid]['roster_player_ids']}
    managers = {oldclubs[cid]['manager_id'] for cid in selected}
    for key in before.keys()-{'package_id','players','clubs','managers','artifacts','proofs','sources','assets'}:
        if before[key] != after[key]:
            raise ValueError('closed package field changed: '+key)
    if before['package_id'] == after['package_id']:
        raise ValueError('country child recipe needs its own package identity')
    for cid,club in oldclubs.items():
        changed = {key for key in club.keys()|newclubs[cid].keys() if club.get(key)!=newclubs[cid].get(key)}
        if cid not in selected and changed:
            raise ValueError('unselected club row changed')
        if cid in selected and changed-{'name','full_name','identity_id','proof','ground_policy','ground_name','opening','roster_player_ids'}:
            raise ValueError('country correction changed club links, tactics or fixed roster')
    newpeople=[pid for cid in selected for pid in newclubs[cid]['roster_player_ids']]
    if len(newpeople)!=len(set(newpeople)) or set(newpeople)!=people:
        raise ValueError('country roster exchange must preserve the complete unique carrier partition')
    for cid in selected:
        if len(oldclubs[cid]['roster_player_ids'])!=len(newclubs[cid]['roster_player_ids']):
            raise ValueError('country roster exchange cannot resize a club')
    newowners={pid:newclubs[cid]['id'] for cid in selected for pid in newclubs[cid]['roster_player_ids']}
    for section, allowed in [('players',people),('managers',managers)]:
        old={row['id']:row for row in before[section]};new={row['id']:row for row in after[section]}
        if set(old)!=set(new):
            raise ValueError('country correction must retain all recipe row IDs')
        for id,row in old.items():
            if id not in allowed and new[id]!=row:
                raise ValueError('unselected '+section+' row changed')
            if id in allowed:
                if section=='players' and new[id]['club_id']!=newowners[id]:
                    raise ValueError('country player owner differs from the selected roster partition')
                for field in (('carrier_id','carrier_family') if section=='players' else ('carrier_id',)):
                    if row[field]!=new[id][field]:
                        raise ValueError('country correction changed a fixed carrier or owner')
    for section in ('artifacts','proofs','sources'):
        new={row['id']:row for row in after[section]}
        if any(new.get(row['id'])!=row for row in before[section]):
            raise ValueError('country correction removed or altered existing provenance')
    if before['assets'].keys()!=after['assets'].keys():
        raise ValueError('country correction changed asset sections')
    for section in before['assets']:
        if section!='portraits' and before['assets'][section]!=after['assets'][section]:
            raise ValueError('country correction cannot change kits or other assets')
    oldphotos={row['player_id']:row for row in before['assets'].get('portraits',[])}
    newphotos={row['player_id']:row for row in after['assets'].get('portraits',[])}
    if oldphotos.keys()!=newphotos.keys():
        raise ValueError('country correction cannot add or remove portrait declarations')
    for id,row in oldphotos.items():
        if row!=newphotos[id] and (id not in people or newphotos[id].get('status')!='native-no-photo'):
            raise ValueError('country portrait changes are limited to selected no-photo declarations')
    packages.validate_package(after)
    return selected, people, managers


def _reconstruct(base, request):
    if request.get('schema')!=SCHEMA+'-input' or request['parent']!=_parent(base):
        raise ValueError('country request does not pin its immutable parent')
    childpath=_bound(request['child_recipe']);receiptpath=_bound(request['authoring_receipt'])
    authoring=p.read_json_file(receiptpath)
    if authoring.get('country')!=request['country'] or authoring.get('child_recipe_sha256')!=r.sha256_file(childpath):
        raise ValueError('country authoring receipt belongs to another recipe')
    for source in authoring['source_bindings']:
        _bound(source)
    # Every cache hit still verifies the complete immutable parent and each
    # authoring/source hash above. Avoid repeating full recipe schema validation
    # for the same pinned transaction inside one publication process.
    key=(digest(packages.canonical_json_bytes(request)),r.sha256_file(Path(__file__)))
    if key in _CACHE:
        return copy.deepcopy(_CACHE[key])
    before=p.read_json_file(base.package_path);after=p.read_json_file(childpath)
    selected,people,managers=verify_recipe_mask(before,after,request)
    oldeq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes();oldjug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();oldent=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    rosters,owners=cohort._owner_rosters(oldeq)
    oldclubs={c['carrier_id']:c for c in before['clubs']};newclubs={c['carrier_id']:c for c in after['clubs']};newplayers={a['id']:a for a in after['players']}
    for cid in selected:
        expected=[newplayers[id]['carrier_id'] for id in oldclubs[cid]['roster_player_ids']]
        if rosters.get(cid)!=expected or any(owners[pid]!={cid} for pid in expected):
            raise ValueError('country parent has a shared or stale native membership graph')
    selected_rows=[a for a in after['players'] if a['id'] in people];selected_clubs=[c for c in after['clubs'] if c['carrier_id'] in selected]
    inputs={'players':selected_rows,'clubs':selected_clubs,'managers':[a for a in after['managers'] if a['id'] in managers]}
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    prepared_jug=oldjug
    if request.get('name_capacity'):
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        from app.player_name_capacity import recover_compact_name_window
        binding=request['name_capacity'];factory=capacity.verify_bundle(binding['bundle']).read_bytes()
        originals={e.record_id:e for e in IndexedFDIFile.from_bytes(factory).entries}
        current={e.record_id:e for e in IndexedFDIFile.from_bytes(oldjug).entries};recovered={}
        for claim in binding['claims']:
            carrier=claim['carrier_id']
            if carrier not in {a['carrier_id'] for a in selected_rows} or carrier in recovered:
                raise ValueError('name capacity scope is outside the selected country or repeated')
            raw=current[carrier].decode_payload(oldjug)
            restored,proof=recover_compact_name_window(originals[carrier].decode_payload(factory),raw)
            expected=dict(carrier_id=carrier,current_sha256=digest(raw),recovered_sha256=digest(restored),proof=proof)
            if expected!=claim:
                raise ValueError('same-carrier original capacity claim does not reproduce')
            recovered[carrier]=restored
        prepared_jug=compiler._rebuild_indexed(oldjug,IndexedFDIFile.from_bytes(oldjug),recovered)
    replacements,handling,*_=compiler._player_replacements(package=inputs,jug_data=prepared_jug,country_codes=codes,club_modes={c['id']:1 for c in selected_clubs})
    if handling or set(replacements)!={a['carrier_id'] for a in selected_rows}:
        raise ValueError('country writer supports the checked dd6360 mode1 lane only')
    jug=compiler._rebuild_indexed(prepared_jug,IndexedFDIFile.from_bytes(prepared_jug),replacements)
    order_eq=oldeq
    from app.xor import xor_encode
    eqindex=IndexedFDIFile.from_bytes(oldeq);eqentries={e.record_id:e for e in eqindex.entries};roster_changes={}
    for cid in selected:
        carriers=[newplayers[id]['carrier_id'] for id in newclubs[cid]['roster_player_ids']]
        if carriers!=rosters[cid]:
            raw=xor_encode(eqentries[cid].decode_payload(oldeq));changed=compiler._rewrite_roster_tail(raw,carriers)
            if len(raw)!=len(changed):
                raise ValueError('country roster exchange changed fixed native record length')
            roster_changes[cid]=xor_decode(changed)
    if roster_changes:
        order_eq=compiler._rebuild_indexed(oldeq,eqindex,roster_changes)
    for cid in sorted(selected):
        ids=request['complete_order_carriers'][str(cid)]
        club=newclubs[cid];opening=club['opening'];ordered=opening['starting_xi_player_ids']+opening['substitute_player_ids'];ordered += [pid for pid in club['roster_player_ids'] if pid not in set(ordered)]
        if ids != [newplayers[pid]['carrier_id'] for pid in ordered]:
            raise ValueError('country complete order must come from the visible recipe opening selection')
        if len(ids)!=len(set(ids)) or set(ids)!={newplayers[id]['carrier_id'] for id in newclubs[cid]['roster_player_ids']}:
            raise ValueError('country complete order differs from fixed roster')
        entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries};changes=[]
        for order,pid in enumerate(ids,1):
            field=read_initial_order(entries[pid].decode_payload(jug))
            changes.append(OrderReplacement(pid,field.name,field.order,order))
        jug=patch_owned_mode1_complete_orders(jug,order_eq,club_record_id=cid,replacements=changes)
    entids={e.record_id for e in IndexedFDIFile.from_bytes(oldent).entries}
    eqreplacements,*_=compiler._team_replacements(package=inputs,eq_data=order_eq,ent_carriers=entids)
    if set(eqreplacements)!=selected:
        raise ValueError('country EQ writer selected another scope')
    eq=compiler._rebuild_indexed(order_eq,IndexedFDIFile.from_bytes(order_eq),eqreplacements)
    from scripts import season_contextual_tactics_v1 as tactics
    contexts=[{'carrier_id':c['carrier_id'],'context':c['opening']['tactics_context']} for c in selected_clubs if 'tactics_context' in c.get('opening',{})]
    if contexts:
        eq=tactics.apply_layer(eq,jug,{'schema_version':tactics.SCHEMA,'clubs':contexts})
    holders,_=_manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    oldman={a['id']:a for a in before['managers']};newman={a['id']:a for a in after['managers']};entindex=IndexedFDIFile.from_bytes(oldent);entries={e.record_id:e for e in entindex.entries};entreplacements={}
    for mid in managers:
        record=newman[mid];pid=record['carrier_id'];cid=next(c for c in selected if oldclubs[c]['manager_id']==mid)
        if [h['carrier_id'] for h in holders.get(pid,[])]!=[cid]:
            raise ValueError('country coach does not have exclusive native ownership')
        raw=oldent[entries[pid].payload_offset:entries[pid].payload_offset+entries[pid].payload_length];profile=parse_indexed_ent_manager_profile(raw,record_id=pid);names=record['native_names']
        changed=replace_indexed_ent_manager_names(raw,record_id=pid,expected_surname=profile.surname,expected_display_name=profile.display_name,surname=names['surname'],display_name=names['display_name'])
        entreplacements[pid]=xor_decode(changed)
    ent=compiler._rebuild_indexed(oldent,entindex,entreplacements)
    preserve_other_records(oldjug,jug,set(replacements));preserve_other_records(oldeq,eq,selected);preserve_other_records(oldent,ent,set(entreplacements))
    result=dict(package=after,jug=jug,eq=eq,ent=ent,selected_players=sorted(replacements),selected_clubs=sorted(selected),selected_managers=sorted(entreplacements))
    _CACHE.clear();_CACHE[key]=copy.deepcopy(result)
    return result


def prepare(base,input_path):
    path=paths._source_path(r.relative_workspace_path(Path(input_path).resolve()));request=p.read_json_file(path);_reconstruct(base,request)
    plan=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,parent=request['parent'],source_input=dict(path=r.relative_workspace_path(path),sha256=r.sha256_file(path)),package_sha256=r.sha256_file(base.package_path),jug_sha256=r.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),scope='Reviewed country recipe only: fixed country carrier totals and club capacities, explicit selected-country carrier exchanges, selected facts/skills/names and startup orders; selected club/coach names, grounds and contextual tactics; all other native records, memberships and kits preserved.')
    plan['transaction_id']=digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def _outputs(plan):
    if plan.get('schema')!=SCHEMA:
        raise ValueError('unsupported country delta schema')
    path=_bound(plan['source_input']);base=r.load_registered_release(plan['season'],plan['release_id'])
    if prepare(base,path)!=plan:
        raise ValueError('country plan does not reproduce')
    return _reconstruct(base,p.read_json_file(path))


def verify(base,plan):
    if (base.season,base.release_id)!=(plan['season'],plan['release_id']):
        raise ValueError('country plan has another parent')
    _outputs(plan)


def bind(package,plan):
    if digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        raise ValueError('country recipe parent differs')
    out=copy.deepcopy(_outputs(plan)['package']);out['artifacts'].append(dict(id=PREFIX+plan['transaction_id'],kind='season-input',relative_path=filename(plan),sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'));out['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(out);return out


def apply(jug,eq,plan):
    base=r.load_registered_release(plan['season'],plan['release_id']);out=_outputs(plan);before=((base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),(base.game_path/'DBDAT/EQ98030.FDI').read_bytes());after=(out['jug'],out['eq'])
    if (jug,eq) not in (before,after):
        raise ValueError('country writer accepts complete parent or complete postimage only')
    return after


def apply_ent(ent,plan):
    base=r.load_registered_release(plan['season'],plan['release_id']);after=_outputs(plan)['ent']
    if ent not in ((base.game_path/'DBDAT/ENT98030.FDI').read_bytes(),after):
        raise ValueError('country ENT preimage differs')
    return after


def apply_minifoto(archive,plan):
    from scripts.season_duplicate_ownership_delta_v1 import no_photo_archive
    after=_outputs(plan)['package'];base=r.load_registered_release(plan['season'],plan['release_id']);before=p.read_json_file(base.package_path);old={x['player_id']:x for x in before['assets']['portraits']};actors={a['id']:a['carrier_id'] for a in after['players']};clear={actors[x['player_id']] for x in after['assets']['portraits'] if x!=old[x['player_id']] and x['status']=='native-no-photo'}
    parent_archive=(base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    expected, offsets=no_photo_archive(parent_archive,clear)
    if archive not in (parent_archive,expected):
        raise ValueError('country portrait archive differs from the complete parent/postimage')
    return expected, offsets


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('reviewed country deltas require immutable-parent SOURCE replay')


def reconstruction(previous,release_id,*,minimum_free_bytes=8*1024**3):
    from scripts import publish_historical_role_delta_v1 as publisher
    path=r.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=p.read_json_file(path);base=r.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    receipt=p.read_json_file(previous.compiler_receipt_path)
    if path.resolve()!=(previous.package_path.parent/filename(plan)).resolve() or r.sha256_file(path)!=receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('country SOURCE child-owned plan hash/path differs')
    if p.read_json_file(previous.package_path)!=bind(p.read_json_file(base.package_path),plan):
        raise ValueError('country SOURCE recipe differs from its reviewed input')
    publisher.publish(base.season,previous.package_path.parent/'role-delta-input.json',release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path,minimum_free_bytes=minimum_free_bytes)
    child=r.load_registered_release(base.season,release_id);p.assert_tree_matches_inventory(child.game_path,p.read_json_file(previous.inventory_path))
    if child.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('country SOURCE recipe bytes differ')
    return dict(complete_recipe_identical=True,complete_game_inventory_identical=True)


def copy_new_inputs(workspace,plan):
    request=p.read_json_file(_bound(plan['source_input']));package=_outputs(plan)['package'];artifacts={a.get('relative_path'):a for a in package['artifacts'] if a.get('relative_path')}
    for row in request.get('new_recipe_artifacts',[]):
        relative=Path(row['relative_path'])
        if relative.is_absolute() or '..' in relative.parts or artifacts.get(str(relative),{}).get('sha256')!=row['sha256']:
            raise ValueError('new country artifact is not an exact confined child recipe input')
        raw=_bound(row).read_bytes();target=Path(workspace)/relative
        if target.exists():
            raise ValueError('new country source input would overwrite an existing file')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
