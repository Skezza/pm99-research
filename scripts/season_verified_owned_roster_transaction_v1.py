"""Atomic, source-bound complete squad refresh plus displaced reserve repairs.

No club is renamed or removed. Complete source XI/bench/reserves are allocated
freely to that same club's carriers, then the complete owned order is rewritten.
Partial replacements must remove someone positively assigned to another full
source group in this same transaction. No intermediate duplicate may publish.
"""
import copy
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement,read_initial_order,patch_owned_mode1_complete_orders
from scripts import season_source_verified_player_changes_v1 as fields
from scripts import season_verified_opening_roster_sources_v1 as sources
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import prepare_duplicate_club_disposition_v1 as allocator
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA='pm99-source-bound-complete-owned-roster-transaction-v1'
INPUT_SCHEMA='pm99-source-bound-complete-owned-roster-input-v1'
PREFIX='source-owned-roster-'
MODE='known-good-baseline-source-bound-complete-owned-roster-transaction-v1'
SCOPE='Only selected sourced identity records, their stale portraits and complete owned startup orders; no club labels, roster ownership links, managers, tactics, kits, EXE or unselected player data changed.'
registry=fields.registry
pipeline=fields.pipeline
packages=fields.packages
digest=fields.digest


def filename(plan):return PREFIX+plan['transaction_id']+'.json'
def artifact_id(plan):return PREFIX+plan['transaction_id']
def identity(actor):return fields.normalise(actor.get('source_name') or actor['name']),actor['facts']['birth_date']
def desired_identity(person):return fields.normalise(person['source_player']['name']),person['source_player']['birth_date']


def main_package(base):
    effective=layers.package_layers(base)
    if len(effective)!=1 or effective[0][0]!='main':
        raise ValueError('owned-roster transaction does not yet support effective recipe overlays')
    return effective[0][1]


def refuse_correct_people(before,desired):
    if any(identity(p)==desired_identity(d) for p in before for d in desired):
        raise ValueError('existing correct people require a retained-field plan, not identity replacement')


def prepare(base,input_path):
    request=pipeline.read_json_file(input_path)
    if (request.get('schema')!=INPUT_SCHEMA or request.get('season')!=base.season
            or request.get('release_id')!=base.release_id or not request.get('groups')):
        raise ValueError('exact parent and explicit owned-roster input required')
    package=main_package(base)
    clubs={c['carrier_id']:c for c in package['clubs']}
    actors={p['carrier_id']:p for p in package['players']}
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=fields.ownership.native_owners(eq)
    rows=[];groups=[];selected=set();full_incoming={};partial_displaced=[]
    for selection in request['groups']:
        club=clubs[selection['club_carrier_id']]
        path=fields.original_path(selection['source_input']['path'])
        if registry.sha256_file(path)!=selection['source_input']['sha256']:
            raise ValueError('original source group input changed')
        group=pipeline.read_json_file(path)
        # Explicit stable-name aliases, not season-specific roster decisions.
        labels={fields.normalise(group['club_name'])}
        if group['club_name']=='Accrington':labels.add(fields.normalise('Accrington Stanley'))
        if fields.normalise(club['name']) not in labels:
            raise ValueError('source group does not identify the retained native club')
        complete=selection['mode']=='complete-opening-squad'
        if not complete and selection['mode']!='displaced-opening-reserves':
            raise ValueError('unsupported owned-roster source selection')
        chosen=None if complete else [r['provider_player_id'] for r in selection['replacements']]
        verified=sources.read(base.season,group,selected_person_ids=chosen)
        desired=verified['desired']
        before=[p for p in package['players'] if p['club_id']==club['id']]
        refuse_correct_people(before,desired)
        if complete:
            if {p['id'] for p in before}!=set(club['roster_player_ids']) or len(before)!=len(desired):
                raise ValueError('complete original source must fill the exact owned roster')
            allocation=allocator.allocate(jug,before,desired,{})
        else:
            before=[actors[r['carrier_id']] for r in selection['replacements']]
            allocation=[]
            for replacement,actor in zip(selection['replacements'],before):
                candidate=[d for d in desired if d['source_person']['provider_player_id']==replacement['provider_player_id']]
                observed=facts.native_facts(jug,actor['carrier_id'])
                if (len(candidate)!=1 or candidate[0]['membership']!='published_bench'
                        or actor['club_id']!=club['id'] or observed['startup_order']<=11
                        or observed['position']=='G' or observed['position']!=candidate[0]['source_player']['position']
                        or observed['birth_date']!=actor['facts']['birth_date']
                        or fields.normalise(observed['name'])!=fields.normalise(actor['name'])):
                    raise ValueError('partial correction requires a positively sourced same-role bench actor and exact displaced native reserve')
                allocation+=allocator.allocate(jug,[actor],candidate,{},opening_slot_orders={actor['carrier_id']:observed['startup_order']})
                partial_displaced.append((identity(actor),club['carrier_id']))
        mapping={r['replacement']['source_person']['provider_player_id']:r['carrier_id'] for r in allocation}
        for row in allocation:
            carrier=row['carrier_id']
            if carrier in selected or owners.get(carrier)!={club['carrier_id']}:
                raise ValueError('selected carriers must have one exact exclusive owner')
            selected.add(carrier)
            rows.append(dict(player_id=row['player_id'],carrier_id=carrier,layer='main',before=row['before_recipe'],
                replacement=row['replacement'],display=row['display'],
                replacement_opening_evidence=dict(date=verified['fixture']['date'])))
            if complete:full_incoming[desired_identity(row['replacement'])]=club['carrier_id']
        orders=[]
        if complete:
            for order,person in enumerate(desired,1):
                carrier=mapping[person['source_person']['provider_player_id']]
                orders.append(dict(carrier_id=carrier,before=facts.native_facts(jug,carrier)['startup_order'],after=order))
        groups.append(dict(club_carrier_id=club['carrier_id'],complete=complete,source=verified,orders=orders))
    if not full_incoming or any(key not in full_incoming or full_incoming[key]==club for key,club in partial_displaced):
        raise ValueError('partial displaced people must have positive different-club ownership in this same complete transaction')
    incoming=[desired_identity(row['replacement']) for row in rows]
    if len(set(incoming))!=len(incoming):raise ValueError('transaction introduces a duplicate source person')
    if any(identity(actor) in incoming for carrier,actor in actors.items() if carrier not in selected):
        raise ValueError('source person remains at an unselected outside owner; couple every copy')
    plan=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        source_input=fields.binding(input_path),package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=digest(jug),eq_sha256=digest(eq),updates=rows,groups=groups,
        bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        source_title='Original first league squads and positively dated opening reserves',
        proof_covers=['source-complete-owned-roster-and-coupled-opening-ownership'],scope=SCOPE)
    plan['transaction_id']=digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def verify(base,plan):
    if (plan.get('schema')!=SCHEMA
            or registry.sha256_file(fields.original_path(plan['source_input']['path']))!=plan['source_input']['sha256']
            or prepare(base,fields.original_path(plan['source_input']['path']))!=plan):
        raise ValueError('owned-roster source transaction does not reproduce')


def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    if package!=pipeline.read_json_file(base.package_path):raise ValueError('exact recipe preimage required')
    result=delta.updated_package(package,plan)
    artifact=next(a for a in result['artifacts'] if a['relative_path']==delta.plan_filename(plan))
    old=artifact['id'];aid=artifact_id(plan)
    artifact.update(id=aid,relative_path=filename(plan),sha256=digest(packages.canonical_json_bytes(plan)))
    for player in result['players']:
        for row in plan['updates']:
            if row['carrier_id']==player['carrier_id']:player['name']=row['display']['display_name']
        for value in [player.get('proof',{})]+[f.get('proof',{}) for f in player.get('fact_fallbacks',[])]:
            if value.get('artifact_id')==old:value['artifact_id']=aid
    for collection in ('sources','proofs'):
        for row in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if row.get(key)==old:row[key]=aid
    for row in result['assets']['portraits']:
        if row.get('proof',{}).get('artifact_id')==old:row['proof']['artifact_id']=aid
    for group in plan['groups']:
        if group['complete']:
            next(c for c in result['clubs'] if c['carrier_id']==group['club_carrier_id'])['opening']['proof']=dict(artifact_id=aid,grade='source-receipt')
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    initial=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(initial)!=plan['jug_sha256'] or digest(eq)!=plan['eq_sha256']:
        raise ValueError('exact whole native baseline/EQ required')
    package=bind(pipeline.read_json_file(base.package_path),plan)
    countries=fields.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    candidate=delta.compile_players(initial,package,{r['player_id'] for r in plan['updates']},countries)
    for group in plan['groups']:
        if group['orders']:
            entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
            orders=[OrderReplacement(r['carrier_id'],read_initial_order(entries[r['carrier_id']].decode_payload(candidate)).name,r['before'],r['after']) for r in group['orders']]
            candidate=patch_owned_mode1_complete_orders(candidate,eq,club_record_id=group['club_carrier_id'],replacements=orders)
    preserve_other_records(initial,candidate,{r['carrier_id'] for r in plan['updates']})
    if jug not in (initial,candidate):raise ValueError('only whole native preimage/postimage accepted')
    return candidate,eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('owned-roster recipe requires exact source reconstruction')


def reconstruction(previous,release_id):
    relative=previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:return None
    path=registry.ROOT/relative;plan=pipeline.read_json_file(path)
    if plan.get('schema')!=SCHEMA:return None
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    receipt=pipeline.read_json_file(previous.compiler_receipt_path)
    if (receipt.get('compilation_mode')!=MODE
            or path.resolve()!=(previous.package_path.parent/filename(plan)).resolve()
            or registry.sha256_file(path)!=receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('owned-roster SOURCE receipt/plan binding differs')
    if bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(previous.package_path):
        raise ValueError('owned-roster SOURCE would discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('exact inert SOURCE descriptor required')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,
        source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('whole owned-roster SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True)
