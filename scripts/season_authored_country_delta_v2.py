"""Versioned selected-player name-capacity support; v1 remains byte-for-byte intact.

Compile a frozen, reviewed country recipe through existing native writers.

Historical sourcing belongs to the bound authoring receipt. This adapter proves
the declared recipe-to-native delta, scope preservation and exact SOURCE replay;
it does not turn an editorial decision into historical evidence.
"""
import copy
import hashlib
import tempfile
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders
from app.ent_manager_profiles import parse_indexed_ent_manager_profile, replace_indexed_ent_manager_names
from app.xor import xor_decode, xor_encode
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.editor_actions import edit_team_roster_eq_jug_linked
from scripts import json_storage_io_v1 as storage_io
from scripts import season_pipeline_v2 as p, season_package_v2 as packages, season_release_registry_v1 as r
from scripts import season_package_compiler_v2 as compiler
from scripts import season_opening_cohort_delta_core_v1 as cohort
from scripts.season_historical_roster_audit_v1 import club_group
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts import season_source_bound_fixture_membership_v1 as paths
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-reviewed-country-recipe-native-delta-v2'
MODE = 'known-good-reviewed-country-recipe-native-delta-v2'
PREFIX = 'reviewed-country-recipe-delta-'
_CACHE = {}
SHARED_FALLBACK_OMISSION_SCHEMA = 'source-selected-shared-fallback-omissions-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return PREFIX + plan['transaction_id'] + '.json'


def _bound(row):
    path = paths._source_path(row['path'])
    if r.sha256_file(path) != row['sha256']:
        raise ValueError('country input hash changed: ' + row['path'])
    return path


def _new_input_source(row):
    if not all(isinstance(row.get(key), str) and row[key] for key in ('path', 'relative_path', 'sha256')):
        raise ValueError('new country artifact needs path, relative_path and sha256')
    return _bound(row)


def new_input_payloads(request, package):
    """Validate the publication copy contract before any native staging."""
    rows = request.get('new_recipe_artifacts', [])
    if not rows:
        return []
    artifacts = {a.get('relative_path'): a for a in package['artifacts'] if a.get('relative_path')}
    result, seen = [], set()
    for row in rows:
        source = _new_input_source(row)
        relative = Path(row['relative_path'])
        if (relative.is_absolute() or not relative.parts or '..' in relative.parts
                or str(relative) in seen or artifacts.get(str(relative), {}).get('sha256') != row['sha256']):
            raise ValueError('new country artifact is not an exact unique confined child recipe input')
        seen.add(str(relative))
        result.append((relative, storage_io.read_bytes(source)))
    return result


def _parent(base):
    return dict(season=base.season, release_id=base.release_id, manifest_sha256=base.manifest_sha256,
                package_sha256=r.sha256_file(base.package_path),
                native_sha256={name: r.sha256_file(base.game_path/'DBDAT'/name)
                    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF', 'TEXTOS.PKF')})


def _shared_fallback_omissions(before, after, request):
    """Validate an explicit, parent-pinned roster-link omission exception.

    Absence from a source roster never authorizes an omission. The caller must
    bind a positive supported cohort and enumerate every omitted fallback row.
    This is deliberately separate from the default fixed-count behavior.
    """
    policy = request.get('source_selected_shared_fallback_omissions')
    if policy is None:
        return {}, {}
    if request.get('selection_kind') != 'clubs' or not isinstance(policy, dict):
        raise ValueError('shared fallback omissions require explicit selected-club country input')
    if policy.get('schema') != SHARED_FALLBACK_OMISSION_SCHEMA:
        raise ValueError('unsupported shared fallback omission policy')
    allowed_policy_fields={'schema','parent_package_sha256','parent_eq_sha256','parent_jug_sha256',
        'source_binding_artifact_id','source_supported_player_ids_by_club','capacity_extra_player_ids_by_club','omissions',
        'factory_flag_authorization'}
    if set(policy)!=allowed_policy_fields:
        raise ValueError('shared fallback omission policy has unsupported or missing fields')
    parent = request.get('parent', {})
    if (policy.get('parent_package_sha256') != parent.get('package_sha256')
            or policy.get('parent_eq_sha256') != parent.get('native_sha256', {}).get('EQ98030.FDI')
            or policy.get('parent_jug_sha256') != parent.get('native_sha256', {}).get('JUG98030.FDI')):
        raise ValueError('shared fallback omission policy does not bind the exact package/EQ/JUG parent')
    rows = policy.get('omissions')
    if not isinstance(rows, list) or not rows:
        raise ValueError('shared fallback omissions need explicit rows')
    oldclubs = {c['carrier_id']: c for c in before['clubs']}
    newclubs = {c['carrier_id']: c for c in after['clubs']}
    oldplayers = {a['id']: a for a in before['players']}
    newplayers = {a['id']: a for a in after['players']}
    if set(oldplayers) != set(newplayers):
        raise ValueError('shared fallback omissions cannot add or remove player recipe objects')
    supported_by=policy.get('source_supported_player_ids_by_club')
    capacity_by=policy.get('capacity_extra_player_ids_by_club')
    omission_clubs={str(row.get('club_carrier_id')) for row in rows if isinstance(row,dict)}
    if (not isinstance(supported_by,dict) or set(supported_by)!=omission_clubs
            or not isinstance(capacity_by,dict) or set(capacity_by)!=omission_clubs):
        raise ValueError('source cohorts and capacity extras must be explicit per omission target')
    supported_all=[]
    for key,ids in supported_by.items():
        if (not isinstance(ids,list) or not ids or len(ids)!=len(set(ids))
                or any(id not in newplayers for id in ids)):
            raise ValueError('each omission target needs unique child-bound source-supported players')
        capacity=capacity_by[key]
        if (not isinstance(capacity,list) or len(capacity)!=len(set(capacity))
                or any(id not in ids for id in capacity)):
            raise ValueError('capacity extras must be explicit members of their club source cohort')
        supported_all.extend(ids)
    if len(supported_all)!=len(set(supported_all)):
        raise ValueError('source-supported actor cannot be assigned to multiple target clubs')
    supported=set(supported_all)
    supported_carriers={newplayers[id]['carrier_id'] for id in supported}
    if policy.get('source_binding_artifact_id') not in {a.get('id') for a in after.get('artifacts', [])}:
        raise ValueError('source-supported cohort must bind a child recipe evidence artifact')
    omitted_by_club = {}
    omitted_player_ids = {}
    owner_specs = {}
    for row in rows:
        required = {'club_carrier_id', 'player_id', 'native_carrier_id',
                    'parent_native_owners', 'parent_roster_slot','parent_row_preimage_hex','target_roster_flag'}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError('shared fallback omission row has an unsupported or missing field')
        cid, player_id, carrier = row['club_carrier_id'], row['player_id'], row['native_carrier_id']
        if type(cid) is not int or type(carrier) is not int or cid not in request['club_carrier_ids']:
            raise ValueError('shared fallback omission is outside the selected club set')
        if type(row['parent_roster_slot']) is not int or type(row['target_roster_flag']) is not int:
            raise ValueError('shared omission slot and flag must use exact JSON integers')
        if player_id not in oldplayers or oldplayers[player_id]['carrier_id'] != carrier:
            raise ValueError('omitted recipe player does not identify its fixed native carrier')
        oldclub, newclub = oldclubs[cid], newclubs[cid]
        if player_id not in oldclub['roster_player_ids'] or player_id in newclub['roster_player_ids']:
            raise ValueError('omission must remove one exact parent target-club link')
        if oldplayers[player_id].get('policy') != 'preserve-existing-mode1' or newplayers[player_id] != oldplayers[player_id]:
            raise ValueError('omitted whole-actor fallback must remain exact in recipe')
        if player_id in supported or carrier in supported_carriers:
            raise ValueError('source-supported opening or capacity actors cannot be omitted')
        if row['target_roster_flag'] not in (0,1):
            raise ValueError('omitted target row must bind its exact visible parent flag')
        owners = row['parent_native_owners']
        if (not isinstance(owners, list) or len(owners) < 2 or len(owners) != len(set(owners))
                or any(type(x) is not int for x in owners) or cid not in owners
                or set(owners) & set(request['club_carrier_ids']) - {cid}):
            raise ValueError('omitted shared actor needs exact external parent owners outside selected clubs')
        if carrier in owner_specs or player_id in {x for values in omitted_player_ids.values() for x in values}:
            raise ValueError('duplicate shared fallback omission')
        owner_specs[carrier] = set(owners)
        omitted_by_club.setdefault(cid, set()).add(carrier)
        omitted_player_ids.setdefault(cid, []).append(player_id)
    for cid in request['club_carrier_ids']:
        oldclub, newclub = oldclubs[cid], newclubs[cid]
        omitted = omitted_player_ids.get(cid, [])
        if omitted:
            expected_roster = [id for id in oldclub['roster_player_ids'] if id not in set(omitted)]
            if (newclub['roster_player_ids'] != expected_roster
                    or len(newclub['roster_player_ids']) < 16):
                raise ValueError('selected roster must be the ordered parent roster minus declared omissions')
        elif newclub['roster_player_ids'] != oldclub['roster_player_ids']:
            raise ValueError('shared omission policy cannot authorize other club roster edits')
    for cid, ids in omitted_player_ids.items():
        support=supported_by[str(cid)];capacity=capacity_by[str(cid)]
        if set(support) != set(newclubs[cid]['roster_player_ids']):
            raise ValueError('the source-supported cohort must equal the active target roster exactly')
        starters = set(newclubs[cid].get('opening', {}).get('starting_xi_player_ids', []))
        subs = set(newclubs[cid].get('opening', {}).get('substitute_player_ids', []))
        if not starters or not starters <= set(supported) or not subs <= set(supported):
            raise ValueError('source opening XI and listed bench must be protected by source support')
        if not set(capacity) <= set(newclubs[cid]['roster_player_ids']):
            raise ValueError('declared capacity extras must remain rostered')
        protected_opening=starters|subs
        if starters & subs or not starters or not subs or set(capacity) != set(support)-protected_opening:
            raise ValueError('source XI/bench and explicit capacity extras must partition the supported roster')
    _validate_factory_flag_authorization(before,after,request,policy)
    return omitted_by_club, omitted_player_ids


def validate_shared_parent_native(eq_data, before, after, request):
    """Prove exact parent owners, row order, and flags for selected clubs."""
    omitted_by_club, _ = _shared_fallback_omissions(before, after, request)
    policy = request.get('source_selected_shared_fallback_omissions') or {}
    expected_owners = {row['native_carrier_id']: set(row['parent_native_owners'])
                       for row in policy.get('omissions', [])}
    rosters, owners = cohort._owner_rosters(eq_data)
    clubs_before = {c['carrier_id']: c for c in before['clubs']}
    players_after = {p['id']: p for p in after['players']}
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(eq_data).entries}
    parent_rows = {}
    omission_rows=policy.get('omissions',[])
    for cid in request['club_carrier_ids']:
        expected = [players_after[id]['carrier_id'] for id in clubs_before[cid]['roster_player_ids']]
        if rosters.get(cid) != expected:
            raise ValueError('country parent native roster order differs from exact recipe preimage')
        removed = omitted_by_club.get(cid, set())
        for carrier in expected:
            required = expected_owners.get(carrier, {cid})
            if owners.get(carrier) != required:
                raise ValueError('country parent native owner set differs from explicit exact-owner policy')
        child_club = next(c for c in after['clubs'] if c['carrier_id'] == cid)
        child_carriers = [players_after[id]['carrier_id'] for id in child_club['roster_player_ids']]
        if child_carriers != [carrier for carrier in expected if carrier not in removed]:
            raise ValueError('country child must retain parent carrier order after exact omissions')
        entry = entries[cid]
        raw = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None:
            raise ValueError('selected native roster is not parser-visible')
        actual_by_carrier={row.player_record_id:row for row in parsed.rows}
        for omission in [row for row in omission_rows if row['club_carrier_id']==cid]:
            row=actual_by_carrier.get(omission['native_carrier_id'])
            if (row is None or row.slot_index!=omission['parent_roster_slot']
                    or row.flag!=omission['target_roster_flag']
                    or raw[row.raw_row_offset:row.raw_row_offset+5].hex()!=omission['parent_row_preimage_hex']):
                raise ValueError('shared omission does not bind the exact parent slot/flag/row bytes')
        rows = [(row.player_record_id, row.flag) for row in parsed.rows]
        if [carrier for carrier, _ in rows] != expected:
            raise ValueError('selected native row IDs differ from parent recipe carriers')
        for carrier in removed:
            flags = [flag for row_id, flag in rows if row_id == carrier]
            expected_flag=next(row['target_roster_flag'] for row in omission_rows
                if row['club_carrier_id']==cid and row['native_carrier_id']==carrier)
            if flags != [expected_flag]:
                raise ValueError('omitted selected-club link flag differs from exact parent witness')
        parent_rows[cid] = rows
    return omitted_by_club, parent_rows, owners


def prune_shared_fallback_native_rosters(eq_data, parent_rows, omitted_by_club, omission_rows):
    """Remove only request-bound mode1 rows; prove exact postimage and outside owners."""
    if not omitted_by_club:
        return eq_data
    index = IndexedFDIFile.from_bytes(eq_data)
    entries = {e.record_id: e for e in index.entries}
    replacements = {}
    for cid, omitted in omitted_by_club.items():
        entry = entries[cid]
        raw = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
        from app.eq_roster_pruning import prune_exact_mode1_roster_payload
        parsed=parse_eq_external_team_roster_payload(raw,{})
        expected_rows=tuple((row.slot_index,row.player_record_id,row.flag) for row in parsed.rows)
        bound=[row for row in omission_rows if row['club_carrier_id']==cid]
        removed_rows=[(row['parent_roster_slot'],row['native_carrier_id'],row['target_roster_flag'],
                       row['parent_row_preimage_hex']) for row in bound]
        changed = prune_exact_mode1_roster_payload(raw,expected_rows=expected_rows,removed_rows=removed_rows)
        readback = parse_eq_external_team_roster_payload(changed, {})
        expected_after = [row for row in parent_rows[cid] if row[0] not in omitted]
        if readback is None or [(row.player_record_id, row.flag) for row in readback.rows] != expected_after:
            raise ValueError('shared fallback native prune did not preserve retained roster rows/order/flags')
        replacements[cid] = xor_decode(changed)
    result = compiler._rebuild_indexed(eq_data, index, replacements)
    preserve_other_records(eq_data, result, set(omitted_by_club))
    return result


def _validate_factory_flag_authorization(before,after,request,policy):
    """Bind narrow source-authored 1->0 resets to exact factory row copies."""
    auth=policy.get('factory_flag_authorization')
    required={'schema','factory_eq_path','factory_jug_path','factory_eq_sha256','factory_jug_sha256','club_carrier_id',
        'factory_club_payload_sha256','resets'}
    if not isinstance(auth,dict) or set(auth)!=required or auth.get('schema')!='pm99-source-authored-factory-row-flag-resets-v1':
        raise ValueError('shared omission requires exact source-authored factory-row flag authorization')
    if type(auth['club_carrier_id']) is not int or auth['club_carrier_id'] not in request['club_carrier_ids']:
        raise ValueError('factory flag authorization is outside selected clubs')
    rows=auth['resets']; allowed_row_fields={'player_id','native_carrier_id','source_name',
        'source_person_id','source_birth_date','membership_scope','source_order','factory_slot_index',
        'factory_row_preimage_hex','factory_jug_name','factory_jug_birth_date','before_flag','after_flag'}
    if not isinstance(rows,list) or not rows:
        raise ValueError('factory flag authorization needs explicit source participants')
    newplayers={a['id']:a for a in after['players']}
    target=next(c for c in after['clubs'] if c['carrier_id']==auth['club_carrier_id'])
    supported=set(policy['source_supported_player_ids_by_club'][str(auth['club_carrier_id'])])
    capacity=set(policy['capacity_extra_player_ids_by_club'][str(auth['club_carrier_id'])])
    xi=target['opening']['starting_xi_player_ids'];subs=target['opening']['substitute_player_ids']
    seen_ids=set();seen_carriers=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!=allowed_row_fields:
            raise ValueError('factory flag reset row has unsupported or missing fields')
        pid=row['player_id'];carrier=row['native_carrier_id'];scope=row['membership_scope'];order=row['source_order']
        if (type(carrier) is not int or type(order) is not int or type(row['factory_slot_index']) is not int
                or type(row['before_flag']) is not int or type(row['after_flag']) is not int
                or row['before_flag']!=1 or row['after_flag']!=0 or pid not in supported
                or pid in seen_ids or carrier in seen_carriers or pid not in newplayers
                or newplayers[pid].get('carrier_id')!=carrier or pid not in target['roster_player_ids']):
            raise ValueError('factory flag reset is not bound to a unique active source-supported actor')
        actor=newplayers[pid]
        if (actor.get('source_name')!=row['source_name'] or actor.get('person_id')!=row['source_person_id']
                or actor.get('facts',{}).get('birth_date')!=row['source_birth_date']):
            raise ValueError('factory flag reset source identity differs from the authored child actor')
        if scope=='opening-xi':
            if order<1 or order>11 or order>len(xi) or xi[order-1]!=pid:
                raise ValueError('factory flag reset source membership differs from the positive opening XI')
        elif scope=='opening-sub':
            if order<=11 or order>11+len(subs) or subs[order-12]!=pid:
                raise ValueError('factory flag reset source membership differs from the positive opening bench')
        elif scope=='preopener-capacity-extra':
            if pid not in capacity or order<=11+len(subs):
                raise ValueError('factory flag reset capacity actor is not in the declared positive cohort')
        else:
            raise ValueError('factory flag reset has an unsupported source membership class')
        seen_ids.add(pid);seen_carriers.add(carrier)
    if not seen_carriers <= {newplayers[pid]['carrier_id'] for pid in supported}:
        raise ValueError('factory flag reset exceeds the positive source cohort')


def validate_factory_flag_preimage(eq_data,before,after,request,policy):
    """Check exact clean-factory and parent EQ row bytes before mutation."""
    auth=policy['factory_flag_authorization']
    factory_eq=storage_io.resolve(r.ROOT / auth['factory_eq_path'])
    factory_jug=storage_io.resolve(r.ROOT / auth['factory_jug_path'])
    if (r.relative_workspace_path(factory_eq)!=auth['factory_eq_path']
            or r.relative_workspace_path(factory_jug)!=auth['factory_jug_path']):
        raise ValueError('factory source path must be an exact workspace-relative binding')
    if r.sha256_file(factory_eq)!=auth['factory_eq_sha256']:
        raise ValueError('clean factory EQ hash differs from the source-authored flag authorization')
    if r.sha256_file(factory_jug)!=auth['factory_jug_sha256']:
        raise ValueError('clean factory JUG hash differs from the source-authored flag authorization')
    def raw_team(data,cid):
        index=IndexedFDIFile.from_bytes(data);matches=[e for e in index.entries if e.record_id==cid]
        if len(matches)!=1: raise ValueError('factory or parent EQ team record is absent/ambiguous')
        entry=matches[0];raw=data[entry.payload_offset:entry.payload_offset+entry.payload_length]
        parsed=parse_eq_external_team_roster_payload(raw,{})
        if parsed is None: raise ValueError('factory or parent EQ team record has no parsed mode1 rows')
        return raw,parsed
    cid=auth['club_carrier_id'];factory_raw,factory_team=raw_team(storage_io.read_bytes(factory_eq),cid)
    parent_raw,parent_team=raw_team(eq_data,cid)
    if digest(factory_raw)!=auth['factory_club_payload_sha256']:
        raise ValueError('registered factory club record differs from its exact row preimage binding')
    factory_rows=[(row.slot_index,row.player_record_id,row.flag) for row in factory_team.rows]
    parent_rows=[(row.slot_index,row.player_record_id,row.flag) for row in parent_team.rows]
    factory_row_bytes=[factory_raw[row.raw_row_offset:row.raw_row_offset+5] for row in factory_team.rows]
    parent_row_bytes=[parent_raw[row.raw_row_offset:row.raw_row_offset+5] for row in parent_team.rows]
    if factory_rows!=parent_rows or factory_row_bytes!=parent_row_bytes:
        raise ValueError('parent native roster links differ from exact registered factory row preimages')
    authorized_carriers={row['native_carrier_id'] for row in auth['resets']}
    factory_flag_one={row.player_record_id for row in factory_team.rows if row.flag==1}
    if authorized_carriers!=factory_flag_one:
        raise ValueError('factory flag reset authorization must cover the exact set of flag-one rows')
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    fjug=storage_io.read_bytes(factory_jug)
    for reset in auth['resets']:
        old=native_facts(fjug,reset['native_carrier_id'])
        if old.get('name')!=reset['factory_jug_name'] or old.get('birth_date')!=reset['factory_jug_birth_date']:
            raise ValueError('factory original JUG identity differs from its explicit flag-reset witness')
    for reset in auth['resets']:
        slot=reset['factory_slot_index']
        matches=[row for row in factory_team.rows if row.slot_index==slot]
        if len(matches)!=1 or (matches[0].player_record_id,matches[0].flag)!=(reset['native_carrier_id'],reset['before_flag']):
            raise ValueError('factory flag reset does not match its exact factory slot/carrier preimage')
        if factory_row_bytes[slot].hex()!=reset['factory_row_preimage_hex']:
            raise ValueError('factory flag reset row bytes differ from the bound preimage')
    return factory_team


def apply_source_authored_factory_flag_resets(eq_data,jug_data,club,authorization):
    """Reset only explicitly source-authored copied flags through canonical editor API."""
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    with tempfile.TemporaryDirectory(prefix='source-factory-row-flag-reset-') as directory:
        root=Path(directory);eq_path=root/'EQ98030.FDI';jug_path=root/'JUG98030.FDI'
        storage_io.write_bytes(eq_path, eq_data);storage_io.write_bytes(jug_path, jug_data);current=eq_data
        index=IndexedFDIFile.from_bytes(current);entry=next(e for e in index.entries if e.record_id==club['carrier_id'])
        team=parse_eq_external_team_roster_payload(current[entry.payload_offset:entry.payload_offset+entry.payload_length],{})
        if team is None: raise ValueError('post-prune selected EQ roster is unreadable')
        for reset in authorization['resets']:
            matches=[row for row in team.rows if row.player_record_id==reset['native_carrier_id']]
            if len(matches)!=1 or matches[0].flag!=reset['before_flag']:
                raise ValueError('post-prune source actor flag differs from its authorized factory state')
            expected_offset=entry.payload_offset+matches[0].raw_row_offset
            before=current
            edit_team_roster_eq_jug_linked(team_file=str(eq_path),player_file=str(jug_path),
                eq_record_id=club['carrier_id'],slot_number=matches[0].slot_index+1,
                player_record_id=reset['native_carrier_id'],flag=reset['after_flag'],write_changes=True)
            current=storage_io.read_bytes(eq_path)
            diffs=[i for i,(old,new) in enumerate(zip(before,current)) if old!=new]
            if len(before)!=len(current) or diffs!=[expected_offset] or current[expected_offset]!=0:
                raise ValueError('canonical editor did not change only the authorized native flag byte')
            idx=IndexedFDIFile.from_bytes(current);rowentry=next(e for e in idx.entries if e.record_id==club['carrier_id'])
            team=parse_eq_external_team_roster_payload(current[rowentry.payload_offset:rowentry.payload_offset+rowentry.payload_length],{})
            if team is None or any(row.player_record_id==reset['native_carrier_id'] and row.flag!=0 for row in team.rows):
                raise ValueError('canonical editor flag reset failed exact native readback')
        if storage_io.read_bytes(jug_path)!=jug_data:
            raise ValueError('native EQ flag reset unexpectedly changed JUG')
        return current


def _selected_mode1_metadata_eq(eq_data, clubs, managers, ent_carriers):
    """Write only selected mode1 club names/links, leaving roster tails intact."""
    index=IndexedFDIFile.from_bytes(eq_data);entries={e.record_id:e for e in index.entries}
    manager_rows={row['id']:row for row in managers};replacements={}
    for club in clubs:
        carrier=club['carrier_id'];entry=entries.get(carrier)
        if entry is None:
            raise ValueError('selected club carrier is absent from EQ')
        decoded=entry.decode_payload(eq_data)
        manager=manager_rows[club['manager_id']]
        raw=xor_encode(decoded)
        meta=compiler.extract_indexed_team_payload_metadata(raw)
        if meta.get('record_mode')!=1:
            raise ValueError('shared fallback omission metadata path supports mode1 clubs only')
        stadium=(compiler._pm99_text(club.get('ground_name'),label=f"club {club['id']} ground_name")
                 if club.get('ground_policy')!='preserve-existing-mode1'
                 else compiler._preserved_eq_stadium_name(decoded))
        decoded=compiler._rewrite_eq_strings(
            decoded,short_name=compiler._pm99_text(club['name'],label=f"club {club['id']} name"),
            full_name=compiler._pm99_text(club.get('full_name') or club['name'],label=f"club {club['id']} full_name"),
            stadium_name=stadium)
        raw=xor_encode(decoded)
        if club.get('capacity_policy')!='preserve-existing-mode1':
            raw=compiler.patch_indexed_team_seated_capacity(raw,int(club.get('seated_capacity',0)))
        if manager.get('policy')!='preserve-existing-mode1':
            mid=int(manager['carrier_id'])
            if mid not in ent_carriers:
                raise ValueError('selected manager carrier is absent from ENT')
            raw=compiler.patch_indexed_eq_active_manager_id(raw,mid)
        # Assert the mode1 linked roster tail is unchanged before rebuilding.
        before_tail=compiler._mode1_roster_tails(eq_data).get(carrier)
        after_tail=compiler._mode1_roster_tails(compiler._rebuild_indexed(eq_data,index,{carrier:xor_decode(raw)})).get(carrier)
        if before_tail!=after_tail:
            raise ValueError('metadata-only EQ edit changed a mode1 roster tail')
        replacements[carrier]=xor_decode(raw)
    return compiler._rebuild_indexed(eq_data,index,replacements)


def opening_order_carriers(club,players_by_id):
    opening=club['opening'];ids=list(opening['starting_xi_player_ids'])+list(opening['substitute_player_ids'])
    ids.extend(pid for pid in club['roster_player_ids'] if pid not in set(ids))
    if len(ids)!=len(club['roster_player_ids']) or len(set(ids))!=len(ids):
        raise ValueError('opening order does not partition the full selected roster')
    return [players_by_id[pid]['carrier_id'] for pid in ids]


def validate_complete_order_carriers(club,players_by_id,carriers):
    """Validate a full native order while allowing declared capacity rows between subs."""
    if not isinstance(carriers,list) or len(carriers)!=len(club['roster_player_ids']) or len(set(carriers))!=len(carriers):
        raise ValueError('complete native order must cover every unique selected roster carrier')
    roster={players_by_id[pid]['carrier_id'] for pid in club['roster_player_ids']}
    if set(carriers)!=roster:
        raise ValueError('complete native order does not match the selected package roster')
    opening=club.get('opening',{});xi=opening.get('starting_xi_player_ids',[]);subs=opening.get('substitute_player_ids',[])
    xi_carriers=[players_by_id[pid]['carrier_id'] for pid in xi]
    sub_carriers=[players_by_id[pid]['carrier_id'] for pid in subs]
    if len(xi_carriers)!=11 or not sub_carriers or carriers[:11]!=xi_carriers:
        raise ValueError('complete native order must preserve the source opening XI in slots1-11')
    positions={carrier:index for index,carrier in enumerate(carriers)}
    sub_positions=[positions[c] for c in sub_carriers]
    if any(position<11 for position in sub_positions) or sub_positions!=sorted(sub_positions):
        raise ValueError('complete native order must preserve the listed source bench sequence')
    return carriers


def apply_complete_native_order(jug_data,eq_data,club,players_by_id,carriers):
    """Apply the established full-roster order writers after exact request validation."""
    carriers=validate_complete_order_carriers(club,players_by_id,carriers)
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug_data).entries};changes=[]
    for position,pid in enumerate(carriers,1):
        field=read_initial_order(entries[pid].decode_payload(jug_data))
        changes.append(OrderReplacement(pid,field.name,field.order,position))
    from scripts import season_opening_order_repair_v1 as opening_orders
    records=opening_orders.tactics.payloads(eq_data)
    if records[club['carrier_id']][0x29]==0:
        return opening_orders.apply_layer(eq_data,jug_data,{
            'schema_version':opening_orders.SCHEMA,'clubs':[{'carrier_id':club['carrier_id'],'players':[
                dict(native_player_id=row.record_id,native_name=row.expected_name,
                    before=row.before,after=row.after) for row in changes]}]},allow_compact=True)
    return patch_owned_mode1_complete_orders(jug_data,eq_data,club_record_id=club['carrier_id'],replacements=changes)


def apply_selected_complete_orders(jug_data,eq_data,selected,omitted_by_club,clubs_by_id,
                                   players_by_id,request):
    """Write every selected club's complete order, including non-omission peers."""
    order_map=request.get('complete_order_carriers',{})
    opening_selected={str(cid) for cid in selected
        if clubs_by_id[cid].get('opening',{}).get('starting_xi_player_ids')
        and clubs_by_id[cid].get('opening',{}).get('substitute_player_ids')}
    if set(order_map)!=opening_selected:
        raise ValueError('complete order map must cover every selected source opening exactly once')
    startup_map=request.get('source_startup_order_carriers',{})
    if set(startup_map)!={str(cid) for cid in omitted_by_club}:
        raise ValueError('source startup map must cover every shared-omission target exactly once')
    for cid in sorted(selected-set(omitted_by_club)):
        key=str(cid)
        if key in order_map:
            if order_map[key]!=opening_order_carriers(clubs_by_id[cid],players_by_id):
                raise ValueError('country complete order differs from the visible recipe opening selection')
            jug_data=apply_complete_native_order(jug_data,eq_data,clubs_by_id[cid],
                                                 players_by_id,order_map[key])
    return jug_data


def verify_recipe_mask(before, after, request):
    """Close unrelated rows; retain country carrier totals and each club size."""
    if set(before) != set(after):
        raise ValueError('country delta cannot change package top-level shape')
    selected = set(request['club_carrier_ids'])
    oldclubs = {c['carrier_id']: c for c in before['clubs']}
    newclubs = {c['carrier_id']: c for c in after['clubs']}
    players_only=request.get('selection_kind') in ('players-only','players-and-openings')
    if request.get('selection_kind') not in (None,'clubs','players-only','players-and-openings'):
        raise ValueError('unsupported reviewed recipe selection kind')
    if set(oldclubs)!=set(newclubs):
        raise ValueError('reviewed recipe cannot add or remove clubs')
    if players_only:
        people=set(request.get('player_ids',[]));managers=set()
        oldplayers={a['id']:a for a in before['players']}
        if (request.get('selection_kind')=='players-only' and selected) or not people or len(people)!=len(request['player_ids']) or not people<=oldplayers.keys():
            raise ValueError('player-only selection needs unique existing players and no clubs')
    else:
        country_clubs = {cid for cid,c in oldclubs.items() if club_group(c)==request['country']}
        if request.get('selection_kind') == 'clubs':
            if (not isinstance(request['country'], str) or not request['country']
                    or not selected or len(selected) != len(request['club_carrier_ids'])
                    or not selected <= country_clubs):
                raise ValueError('club selection needs unique existing clubs within one country')
        elif selected != country_clubs:
            raise ValueError('country delta must select exactly the existing country club graph')
        people={pid for cid in selected for pid in oldclubs[cid]['roster_player_ids']}
        managers={oldclubs[cid]['manager_id'] for cid in selected}
        if any(c['manager_id'] in managers for cid,c in oldclubs.items() if cid not in selected):
            raise ValueError('selected manager is shared with an unselected club')
    omitted_by_club, omitted_player_ids = _shared_fallback_omissions(before, after, request)
    omitted_ids = {player_id for ids in omitted_player_ids.values() for player_id in ids}
    if omitted_ids:
        people -= omitted_ids
        newpeople_check = [pid for cid in selected for pid in newclubs[cid]['roster_player_ids']]
        if len(newpeople_check) != len(set(newpeople_check)) or set(newpeople_check) != people:
            raise ValueError('selected child player partition must equal the parent partition minus exact omissions')
    for key in before.keys()-{'package_id','players','clubs','managers','artifacts','proofs','sources','assets'}:
        if before[key] != after[key]:
            raise ValueError('closed package field changed: '+key)
    if before['package_id'] == after['package_id']:
        raise ValueError('country child recipe needs its own package identity')
    for cid,club in oldclubs.items():
        changed = {key for key in club.keys()|newclubs[cid].keys() if club.get(key)!=newclubs[cid].get(key)}
        if cid not in selected and changed:
            raise ValueError('unselected club row changed')
        if players_only and changed-({'opening'} if cid in selected else set()):
            raise ValueError('reviewed player/opening changes cannot alter club metadata or rosters')
        club_allowed={'name','full_name','identity_id','proof','ground_policy','ground_name','opening','roster_player_ids'}
        if omitted_player_ids.get(cid):
            club_allowed.add('shared_preserve_player_ids')
        if cid in selected and changed-club_allowed:
            raise ValueError('country correction changed club links, tactics or fixed roster')
    newpeople=[pid for cid in selected for pid in newclubs[cid]['roster_player_ids']]
    if not players_only and (len(newpeople)!=len(set(newpeople)) or set(newpeople)!=people):
        raise ValueError('country roster exchange must preserve the complete unique carrier partition')
    for cid in selected:
        if (not omitted_player_ids.get(cid)
                and len(oldclubs[cid]['roster_player_ids'])!=len(newclubs[cid]['roster_player_ids'])):
            raise ValueError('country roster exchange cannot resize a club')
    newowners=({pid:oldplayers[pid]['club_id'] for pid in people} if players_only else {pid:newclubs[cid]['id'] for cid in selected for pid in newclubs[cid]['roster_player_ids']})
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


def prepare_name_capacity(oldjug, request, selected_carriers):
    prepared_jug=oldjug
    if request.get('name_capacity'):
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        from app.player_name_capacity import recover_compact_name_window
        binding=request['name_capacity'];factory=storage_io.read_bytes(capacity.verify_bundle(binding['bundle']))
        originals={e.record_id:e for e in IndexedFDIFile.from_bytes(factory).entries}
        current={e.record_id:e for e in IndexedFDIFile.from_bytes(oldjug).entries};recovered={}
        for claim in binding['claims']:
            carrier=claim['carrier_id']
            if carrier not in set(selected_carriers) or carrier in recovered:
                raise ValueError('name capacity scope is outside the selected country or repeated')
            raw=current[carrier].decode_payload(oldjug)
            restored,proof=recover_compact_name_window(originals[carrier].decode_payload(factory),raw)
            expected=dict(carrier_id=carrier,current_sha256=digest(raw),recovered_sha256=digest(restored),proof=proof)
            if expected!=claim:
                raise ValueError('same-carrier original capacity claim does not reproduce')
            recovered[carrier]=restored
        prepared_jug=compiler._rebuild_indexed(oldjug,IndexedFDIFile.from_bytes(oldjug),recovered)
    return prepared_jug


def _mode0_shirt_carriers(eq, oldplayers, clubs, people):
    """Grant the extra shirt write only for an exact visible mode-0 row."""
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(eq).entries}
    result=set()
    for id in people:
        actor=oldplayers[id];cid=clubs[actor['club_id']]['carrier_id'];entry=entries[cid]
        roster=parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset+entry.payload_length],{})
        if roster is None or roster.mode_byte not in (0,1):
            raise ValueError('selected player owner has no supported native roster mode')
        if roster.mode_byte==0:
            flags=[row.flag for row in roster.rows if row.player_record_id==actor['carrier_id']]
            if flags!=[0]:
                raise ValueError('mode0 shirt write needs one exact visible player row')
            result.add(actor['carrier_id'])
    return result


def static_native_opening_snapshot(eq, jug, club_carrier):
    """Witness existing controls, without asserting a historical fixture XI."""
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    from scripts.season_historical_roster_audit_v1 import native_player
    entry = next(e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == club_carrier)
    raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
    roster = parse_eq_external_team_roster_payload(raw, {})
    if roster is None or roster.mode_byte != 1 or any(row.flag != 0 for row in roster.rows):
        raise ValueError('static opening witness requires visible mode1 rows')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    rows = []
    for row in roster.rows:
        payload = entries[row.player_record_id].decode_payload(jug)
        native = native_player(payload, row.player_record_id)
        rows.append(dict(carrier_id=row.player_record_id,
            order=read_initial_order(payload).order, roles=native['roles'], position=native['position']))
    if len(rows) != len({row['carrier_id'] for row in rows}):
        raise ValueError('static opening witness has repeated carriers')
    return dict(eq_payload_sha256=digest(raw), rows=rows,
        policy='preserve-current-native-controls-not-a-historical-fixture')


def _static_identity_roles(actor, replacement, row, *, repair_defender=False,
                           repair_forward=False):
    """Keep static controls strict; optionally repair an incompatible seed role.

    This is not evidence of a historical XI or a specific defensive position.
    The defender opt-in admits one compatible source-reviewed role. A separate
    opt-in admits only generic F/12 for a new sourced forward identity. Both
    require an unchanged explicit broad role and wholly incompatible old roles.
    """
    roles = [role for role in row['roles'] if role != 98]
    parent_roles = actor['facts'].get('fine_roles')
    desired = replacement['facts'].get('fine_roles')
    if (parent_roles not in (roles, {'policy': 'preserve-existing-mode1'})
            or actor['facts'].get('primary_position') != row['position']
            or replacement['facts'].get('primary_position') != row['position']):
        raise ValueError('static opening identity replacement must preserve matching native roles')
    if repair_defender and repair_forward:
        raise ValueError('static role repair kinds must not overlap')
    if not repair_defender and not repair_forward:
        if desired != roles:
            raise ValueError('static opening identity replacement must preserve matching native roles')
        return roles
    from scripts.season_exact_fifa_role_delta_v1 import compatible
    if repair_forward:
        if (row['position'] != 'F' or not roles
                or any(type(role) is not int or not 0 <= role <= 17 for role in roles)
                or any(compatible('F', role) for role in roles)
                or desired != [12] or type(desired[0]) is not int
                or not replacement.get('person_id')
                or replacement.get('person_id') == actor.get('person_id')
                or replacement.get('proof', {}).get('grade') != 'source-receipt'):
            raise ValueError('static forward repair needs a new source-backed forward identity and incompatible inherited roles; only generic F/12 is permitted')
        return desired[:]
    if (row['position'] != 'D' or not roles
            or any(type(role) is not int or not 0 <= role <= 17 for role in roles)
            or any(compatible('D', role) for role in roles)
            or not isinstance(desired, list) or len(desired) != 1
            or type(desired[0]) is not int or not compatible('D', desired[0])
            or replacement.get('proof', {}).get('grade') != 'source-receipt'):
        raise ValueError('static defender repair needs contradictory roles and a source-backed compatible D role')
    return desired[:]


def _static_repair_proof(actor, package, request, authoring, *, parent_artifact_ids,
                         parent_artifact_paths):
    """A grade string cannot relabel an inherited static artifact as evidence."""
    proof = actor.get('proof', {})
    matches = [a for a in package.get('artifacts', [])
               if a.get('id') == proof.get('artifact_id')]
    if (proof.get('artifact_id') in parent_artifact_ids
            or len(matches) != 1 or matches[0].get('kind') != 'season-input'):
        raise ValueError('static defender repair needs a new hash-bound source input artifact')
    artifact = matches[0]
    relative = artifact.get('relative_path')
    if (not relative or relative in parent_artifact_paths
            or sum(a.get('relative_path') == relative
                   for a in package.get('artifacts', [])) != 1):
        raise ValueError('static defender repair needs a new unique hash-bound source input path')
    inputs = [row for row in request.get('new_recipe_artifacts', [])
              if row.get('relative_path') == artifact.get('relative_path')
              and row.get('sha256') == artifact.get('sha256')]
    if (len(inputs) != 1 or not any(
            row.get('path') == inputs[0].get('path')
            and row.get('sha256') == inputs[0].get('sha256')
            for row in authoring.get('source_bindings', []))):
        raise ValueError('static defender repair needs a new hash-bound source input artifact')


def _reconstruct(base, request):
    if request.get('schema')!=SCHEMA+'-input' or request['parent']!=_parent(base):
        raise ValueError('country request does not pin its immutable parent')
    childpath=_bound(request['child_recipe']);receiptpath=_bound(request['authoring_receipt'])
    authoring=p.read_json_file(receiptpath)
    if authoring.get('country')!=request['country'] or authoring.get('child_recipe_sha256')!=r.sha256_file(childpath):
        raise ValueError('country authoring receipt belongs to another recipe')
    for source in authoring['source_bindings']:
        _bound(source)
    for source in request.get('new_recipe_artifacts', []):
        _new_input_source(source)
    # Every cache hit still verifies the complete immutable parent and each
    # authoring/source hash above. Avoid repeating full recipe schema validation
    # for the same pinned transaction inside one publication process.
    key=(digest(packages.canonical_json_bytes(request)),r.sha256_file(Path(__file__)))
    if key in _CACHE:
        return copy.deepcopy(_CACHE[key])
    before=p.read_json_file(base.package_path);after=p.read_json_file(childpath)
    new_input_payloads(request, after)
    selected,people,managers=verify_recipe_mask(before,after,request)
    omission_policy=request.get('source_selected_shared_fallback_omissions')
    if omission_policy is not None:
        artifact_id=omission_policy['source_binding_artifact_id']
        artifact=next(a for a in after['artifacts'] if a['id']==artifact_id)
        copied=[x for x in request.get('new_recipe_artifacts',[])
                if x.get('relative_path')==artifact.get('relative_path')
                and x.get('sha256')==artifact.get('sha256')]
        source=[x for x in authoring['source_bindings']
                if len(copied)==1 and x.get('path')==copied[0].get('path')
                and x.get('sha256')==artifact.get('sha256')]
        if len(copied)!=1 or len(source)!=1:
            raise ValueError('shared fallback source cohort artifact must be copied and receipt-bound exactly once')
    if ('static_defender_fine_role_repairs' in request
            and (request.get('selection_kind') != 'players-only'
                 or not isinstance(request['static_defender_fine_role_repairs'], list))):
        raise ValueError('static defender repairs are restricted to explicit player-only witnesses')
    if ('static_forward_fine_role_repairs' in request
            and (request.get('selection_kind') != 'players-only'
                 or not isinstance(request['static_forward_fine_role_repairs'], list))):
        raise ValueError('static forward repairs are restricted to explicit player-only witnesses')
    oldeq=storage_io.read_bytes(base.game_path / 'DBDAT/EQ98030.FDI');oldjug=storage_io.read_bytes(base.game_path / 'DBDAT/JUG98030.FDI');oldent=storage_io.read_bytes(base.game_path / 'DBDAT/ENT98030.FDI')
    if request.get('selection_kind') in ('players-only','players-and-openings'):
        from scripts import season_duplicate_ownership_delta_v1 as native_players
        from scripts.season_opening_order_repair_v1 import native_owners
        ownership=native_owners(oldeq);oldplayers={a['id']:a for a in before['players']}
        clubs={c['id']:c for c in before['clubs']};entries={e.record_id:e for e in IndexedFDIFile.from_bytes(oldjug).entries}
        static = request.get('static_native_openings', {})
        if static and request.get('selection_kind') != 'players-only':
            raise ValueError('static opening witness is restricted to unchanged player-only club rows')
        actor_clubs = {clubs[oldplayers[id]['club_id']]['carrier_id'] for id in people}
        if not isinstance(static, dict) or any(str(cid) not in {str(x) for x in actor_clubs} for cid in static):
            raise ValueError('static opening witness is outside selected actors')
        for cid, snapshot in static.items():
            if snapshot != static_native_opening_snapshot(oldeq, oldjug, int(cid)):
                raise ValueError('static opening witness differs from the complete native parent')
        repairs = request.get('static_defender_fine_role_repairs', [])
        forward_repairs = request.get('static_forward_fine_role_repairs', [])
        actor_carriers = {oldplayers[id]['carrier_id'] for id in people}
        if (not isinstance(repairs, list) or any(type(cid) is not int for cid in repairs)
                or len(repairs) != len(set(repairs)) or not set(repairs) <= actor_carriers
                or any(str(clubs[oldplayers[id]['club_id']]['carrier_id']) not in static
                       for id in people if oldplayers[id]['carrier_id'] in repairs)):
            raise ValueError('static defender repairs need unique selected carriers and complete witnesses')
        if (any(type(cid) is not int for cid in forward_repairs)
                or len(forward_repairs) != len(set(forward_repairs))
                or not set(forward_repairs) <= actor_carriers
                or set(forward_repairs) & set(repairs)
                or any(str(clubs[oldplayers[id]['club_id']]['carrier_id']) not in static
                       for id in people if oldplayers[id]['carrier_id'] in forward_repairs)):
            raise ValueError('static forward repairs need unique selected carriers and complete witnesses')
        all_repairs = set(repairs) | set(forward_repairs)
        expected_static = copy.deepcopy(static)
        newplayers = {a['id']: a for a in after['players']}
        for actor in newplayers.values():
            if actor['carrier_id'] in all_repairs:
                _static_repair_proof(actor, after, request, authoring,
                    parent_artifact_ids={a['id'] for a in before.get('artifacts', [])},
                    parent_artifact_paths={a.get('relative_path')
                                           for a in before.get('artifacts', [])})
        for id in people:
            actor=oldplayers[id];carrier=actor['carrier_id'];club=clubs[actor['club_id']]
            static_club = str(club['carrier_id']) in static
            if static_club:
                row = next(x for x in static[str(club['carrier_id'])]['rows'] if x['carrier_id'] == carrier)
                roles = _static_identity_roles(actor, newplayers[id], row,
                    repair_defender=carrier in repairs,
                    repair_forward=carrier in forward_repairs)
                if carrier in all_repairs:
                    expected_row = next(x for x in expected_static[str(club['carrier_id'])]['rows']
                                        if x['carrier_id'] == carrier)
                    expected_row['roles'] = roles + [98] * (6 - len(roles))
            if ownership.get(carrier)!={club['carrier_id']} or ((read_initial_order(entries[carrier].decode_payload(oldjug)).order<=11 or id in club.get('opening',{}).get('starting_xi_player_ids',[])) and club['carrier_id'] not in selected and not static_club):
                raise ValueError('reviewed reserve replacement needs exclusive ownership and a native nonstarter')
        codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
        prepared_jug=prepare_name_capacity(oldjug,request,[oldplayers[id]['carrier_id'] for id in people])
        mode0_carriers=_mode0_shirt_carriers(oldeq,oldplayers,clubs,people)
        jug=native_players.compile_players(prepared_jug,after,people,codes,mode0_carriers=mode0_carriers)
        for cid, snapshot in expected_static.items():
            if snapshot != static_native_opening_snapshot(oldeq, jug, int(cid)):
                raise ValueError('static opening correction changed native startup controls or roles')
        newclubs={c['carrier_id']:c for c in after['clubs']};newactors={a['id']:a for a in after['players']}
        if set(request.get('complete_order_carriers',{}))!={str(cid) for cid in selected}:
            raise ValueError('reviewed opening orders must cover exactly the selected clubs')
        for cid in sorted(selected):
            club=newclubs[cid];opening=club['opening'];order=opening['starting_xi_player_ids']+opening['substitute_player_ids'];order += [id for id in club['roster_player_ids'] if id not in set(order)]
            carriers=[newactors[id]['carrier_id'] for id in order]
            if carriers!=request['complete_order_carriers'][str(cid)] or len(carriers)!=len(set(carriers)) or set(order)!=set(club['roster_player_ids']):
                raise ValueError('reviewed complete opening order differs from its visible recipe')
            index={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries};changes=[]
            for position,pid in enumerate(carriers,1):
                field=read_initial_order(index[pid].decode_payload(jug));changes.append(OrderReplacement(pid,field.name,field.order,position))
            from scripts import season_opening_order_repair_v1 as opening_orders
            records = opening_orders.tactics.payloads(oldeq)
            if records[cid][0x29] == 0:
                jug = opening_orders.apply_layer(oldeq, jug, {
                    'schema_version': opening_orders.SCHEMA,
                    'clubs': [{'carrier_id': cid, 'players': [dict(
                        native_player_id=change.record_id,
                        native_name=change.expected_name,
                        before=change.before, after=change.after)
                        for change in changes]}]}, allow_compact=True)
            else:
                jug=patch_owned_mode1_complete_orders(jug,oldeq,club_record_id=cid,replacements=changes)
        result=dict(package=after,jug=jug,eq=oldeq,ent=oldent,selected_players=sorted(oldplayers[id]['carrier_id'] for id in people),selected_clubs=sorted(selected),selected_managers=[])

        _CACHE.clear();_CACHE[key]=copy.deepcopy(result)
        return result
    oldclubs={c['carrier_id']:c for c in before['clubs']};newclubs={c['carrier_id']:c for c in after['clubs']};newplayers={a['id']:a for a in after['players']}
    omitted_by_club,omitted_player_ids=_shared_fallback_omissions(before,after,request)
    omitted_carriers={cid:ids for cid,ids in omitted_by_club.items()}
    omitted_owner_specs={row['native_carrier_id']:set(row['parent_native_owners'])
        for row in (omission_policy or {}).get('omissions',[])}
    eqindex=IndexedFDIFile.from_bytes(oldeq);eqentries={e.record_id:e for e in eqindex.entries}
    parent_rows={}
    if omission_policy is not None:
        omitted_by_club,parent_rows,owners=validate_shared_parent_native(oldeq,before,after,request)
        validate_factory_flag_preimage(oldeq,before,after,request,omission_policy)
        omitted_carriers={cid:ids for cid,ids in omitted_by_club.items()}
    else:
        rosters,owners=cohort._owner_rosters(oldeq)
        for cid in selected:
            expected=[newplayers[id]['carrier_id'] for id in oldclubs[cid]['roster_player_ids']]
            if rosters.get(cid)!=expected or any(owners[pid]!={cid} for pid in expected):
                raise ValueError('country parent has a shared or stale native membership graph')
    selected_rows=[a for a in after['players'] if a['id'] in people];selected_clubs=[c for c in after['clubs'] if c['carrier_id'] in selected]
    inputs={'players':selected_rows,'clubs':selected_clubs,'managers':[a for a in after['managers'] if a['id'] in managers]}
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    prepared_jug=prepare_name_capacity(oldjug,request,[a['carrier_id'] for a in selected_rows])
    replacements,handling,*_=compiler._player_replacements(package=inputs,jug_data=prepared_jug,country_codes=codes,club_modes={c['id']:1 for c in selected_clubs})
    if handling or set(replacements)!={a['carrier_id'] for a in selected_rows}:
        raise ValueError('country writer supports the checked dd6360 mode1 lane only')
    jug=compiler._rebuild_indexed(prepared_jug,IndexedFDIFile.from_bytes(prepared_jug),replacements)
    order_eq=oldeq
    if omitted_by_club:
        # Write selected mode1 metadata without exposing the shorter roster to
        # the generic fixed-count team writer, then prune only explicit links.
        entids={e.record_id for e in IndexedFDIFile.from_bytes(oldent).entries}
        order_eq=_selected_mode1_metadata_eq(oldeq,selected_clubs,inputs['managers'],entids)
        # Re-parse metadata output before applying only the declared roster rows.
        meta_index=IndexedFDIFile.from_bytes(order_eq);meta_entries={e.record_id:e for e in meta_index.entries}
        for cid,rows in parent_rows.items():
            meta_entry=meta_entries[cid]
            meta_raw=order_eq[meta_entry.payload_offset:meta_entry.payload_offset+meta_entry.payload_length]
            parsed=parse_eq_external_team_roster_payload(meta_raw,{})
            if parsed is None or [(row.player_record_id,row.flag) for row in parsed.rows]!=rows:
                raise ValueError('selected metadata writer changed parent roster rows or flags')
        order_eq=prune_shared_fallback_native_rosters(order_eq,parent_rows,omitted_by_club,
            omission_policy['omissions'])
        authorization=omission_policy['factory_flag_authorization']
        flag_club=newclubs[authorization['club_carrier_id']]
        order_eq=apply_source_authored_factory_flag_resets(order_eq,oldjug,flag_club,authorization)
        entids={e.record_id for e in IndexedFDIFile.from_bytes(oldent).entries}
        eqreplacements,*_=compiler._team_replacements(package=inputs,eq_data=order_eq,ent_carriers=entids)
        if set(eqreplacements)!=selected:
            raise ValueError('post-prune country team writer selected another EQ scope')
        eq=compiler._rebuild_indexed(order_eq,IndexedFDIFile.from_bytes(order_eq),eqreplacements)
    else:
        from app.xor import xor_encode
        roster_changes={}
        for cid in selected:
            carriers=[newplayers[id]['carrier_id'] for id in newclubs[cid]['roster_player_ids']]
            if carriers!=rosters[cid]:
                raw=xor_encode(eqentries[cid].decode_payload(oldeq));changed=compiler._rewrite_roster_tail(raw,carriers)
                if len(raw)!=len(changed):
                    raise ValueError('country roster exchange changed fixed native record length')
                roster_changes[cid]=xor_decode(changed)
        if roster_changes:
            order_eq=compiler._rebuild_indexed(oldeq,eqindex,roster_changes)
    if not omitted_by_club:
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
    if omitted_by_club:
        order_map=request.get('complete_order_carriers',{})
        opening_selected={str(cid) for cid in selected
            if newclubs[cid].get('opening',{}).get('starting_xi_player_ids')
            and newclubs[cid].get('opening',{}).get('substitute_player_ids')}
        if set(order_map)!=opening_selected:
            raise ValueError('complete order map must cover every selected source opening exactly once')
        startup_map=request.get('source_startup_order_carriers',{})
        if set(startup_map)!={str(cid) for cid in omitted_by_club}:
            raise ValueError('source startup map must cover every shared-omission target exactly once')
        jug=apply_selected_complete_orders(jug,eq,selected,omitted_by_club,newclubs,newplayers,request)
        post_rosters,post_owners=cohort._owner_rosters(eq)
        for cid,removed in omitted_by_club.items():
            wanted=[carrier for carrier,flag in parent_rows[cid] if carrier not in removed]
            if post_rosters.get(cid)!=wanted:
                raise ValueError('post-prune target roster differs from exact retained carrier order')
            for carrier in removed:
                expected=omitted_owner_specs[carrier]-{cid}
                if post_owners.get(carrier)!=expected:
                    raise ValueError('outside-club owners changed after selected-link pruning')
            source_ids=set(request['source_selected_shared_fallback_omissions']['source_supported_player_ids_by_club'][str(cid)])
            ordered_ids=newclubs[cid]['opening']['starting_xi_player_ids']+newclubs[cid]['opening']['substitute_player_ids']
            expected_order=[newplayers[pid]['carrier_id'] for pid in ordered_ids]
            if startup_map[str(cid)]!=expected_order:
                raise ValueError('source startup order differs from the source-bound XI and matchday bench')
            complete=order_map
            expected_complete=opening_order_carriers(newclubs[cid],newplayers)
            if complete[str(cid)]!=expected_complete or len(expected_complete)!=len(post_rosters[cid]):
                raise ValueError('complete 25-actor order differs from recipe roster/source XI and bench')
            jug=apply_complete_native_order(jug,eq,newclubs[cid],newplayers,expected_complete)
    else:
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
    path=paths._source_path(r.relative_workspace_path(storage_io.resolve(Path(input_path))));request=p.read_json_file(path);_reconstruct(base,request)
    plan=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,parent=request['parent'],source_input=dict(path=r.relative_workspace_path(path),sha256=r.sha256_file(path)),package_sha256=r.sha256_file(base.package_path),jug_sha256=r.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),scope='Reviewed country recipe only: fixed country carrier totals and club capacities, explicit selected-country carrier exchanges, selected facts/skills/names and startup orders; selected club/coach names, grounds and contextual tactics; all other native records, memberships and kits preserved.')
    if request.get('selection_kind') == 'clubs':
        plan['scope']='Reviewed explicit clubs within one existing country only; fixed selected club capacities and carrier partition; selected actors, exclusive coaches and metadata; every unselected same-country or foreign club, player, coach and all kits preserved.'
    if request.get('source_selected_shared_fallback_omissions') is not None:
        plan['scope']='Source-selected club cohorts with explicit parent-pinned shared fallback omissions; omitted whole actors, portraits, JUG rows and outside owners remain exact. The target mode1 roster is pruned only at declared links; only explicitly source-authored clean-factory flag bytes are reset. Complete native startup orders are written through the standard guarded writer for every selected source opening, including declared capacity rows; every unselected native record remains exact.'
        plan['source_selected_shared_fallback_omissions_sha256']=digest(packages.canonical_json_bytes(request['source_selected_shared_fallback_omissions']))
    if request.get('selection_kind') in ('players-only','players-and-openings'):
        plan['scope']='Reviewed source-bound reserve identities/facts/skills/names and their stale portraits only; complete country/club memberships, startup orders, all club/manager/tactics records, kits and unrelated actors preserved.'
    if request.get('selection_kind')=='players-and-openings':
        plan['scope']='Reviewed identity replacements and explicitly source-bound complete opening orders for selected existing clubs; EQ/ENT, roster memberships, tactics grids, kits and all unselected facts/skills/names preserved.'
    if request.get('static_native_openings'):
        plan['scope']='Source-bound identity/fact/skill corrections in unchanged slots, with every witnessed native startup order, all six roles and primary position preserved; all club recipe rows, EQ/ENT, roster membership, tactics grids and kits exact. The static controls are not a historical fixture or XI claim.'
    if request.get('static_defender_fine_role_repairs'):
        # Retain existing immutable generic-D/4 plan text byte-for-byte.
        plan['scope']='Source-bound unchanged-slot corrections with explicit generic D/4 repair only for listed defenders whose inherited fine roles are all incompatible. Every native startup order and broad position, all unlisted fine roles, all club rows, EQ/ENT, memberships, tactics and kits remain exact. Static controls are not a historical XI claim.'
        child=p.read_json_file(_bound(request['child_recipe']))
        if any(a['carrier_id'] in request['static_defender_fine_role_repairs']
               and a['facts']['fine_roles'] != [4] for a in child['players']):
            plan['scope']=plan['scope'].replace('generic D/4 repair', 'single compatible source-reviewed defender-role repair')
    if request.get('static_forward_fine_role_repairs'):
        plan['scope'] += ' Listed new forward identities may replace wholly incompatible inherited fine roles with generic F/12 only, using a new hash-bound source input; all other witnessed controls remain exact.'
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
    base=r.load_registered_release(plan['season'],plan['release_id']);out=_outputs(plan);before=(storage_io.read_bytes(base.game_path / 'DBDAT/JUG98030.FDI'),storage_io.read_bytes(base.game_path / 'DBDAT/EQ98030.FDI'));after=(out['jug'],out['eq'])
    if (jug,eq) not in (before,after):
        raise ValueError('country writer accepts complete parent or complete postimage only')
    return after


def apply_ent(ent,plan):
    base=r.load_registered_release(plan['season'],plan['release_id']);after=_outputs(plan)['ent']
    if ent not in (storage_io.read_bytes(base.game_path / 'DBDAT/ENT98030.FDI'),after):
        raise ValueError('country ENT preimage differs')
    return after


def apply_minifoto(archive,plan):
    from scripts.season_duplicate_ownership_delta_v1 import no_photo_archive
    after=_outputs(plan)['package'];base=r.load_registered_release(plan['season'],plan['release_id']);before=p.read_json_file(base.package_path);old={x['player_id']:x for x in before['assets']['portraits']};actors={a['id']:a['carrier_id'] for a in after['players']};clear={actors[x['player_id']] for x in after['assets']['portraits'] if x!=old[x['player_id']] and x['status']=='native-no-photo'}
    parent_archive=storage_io.read_bytes(base.game_path / 'DBDAT/MINIFOTO.PKF')
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
    if storage_io.resolve(path)!=storage_io.resolve(previous.package_path.parent / filename(plan)) or r.sha256_file(path)!=receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('country SOURCE child-owned plan hash/path differs')
    if p.read_json_file(previous.package_path)!=bind(p.read_json_file(base.package_path),plan):
        raise ValueError('country SOURCE recipe differs from its reviewed input')
    publisher.publish(base.season,previous.package_path.parent/'role-delta-input.json',release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path,minimum_free_bytes=minimum_free_bytes)
    child=r.load_registered_release(base.season,release_id);p.assert_tree_matches_inventory(child.game_path,p.read_json_file(previous.inventory_path))
    if storage_io.read_bytes(child.package_path)!=storage_io.read_bytes(previous.package_path):
        raise ValueError('country SOURCE recipe bytes differ')
    return dict(complete_recipe_identical=True,complete_game_inventory_identical=True)


def copy_new_inputs(workspace,plan):
    request=p.read_json_file(_bound(plan['source_input']));package=_outputs(plan)['package']
    for relative, raw in new_input_payloads(request, package):
        target=Path(workspace)/relative
        if storage_io.exists(target):
            raise ValueError('new country source input would overwrite an existing file')
        target.parent.mkdir(parents=True,exist_ok=True);storage_io.write_bytes(target, raw)
