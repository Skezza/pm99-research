"""Explicit source-backed player field edits over a known-good native game.

The first admitted field mask is nationality-only completion of an explicit XXX.
No identity, rating, role, roster, tactical or unknown byte may change. Other
edit kinds must acquire their own source and native guards before admission.
"""
import copy
from datetime import date
from pathlib import Path
from scripts import season_disk_budget_v1 as disk_budget
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_package_compiler_v2 as compiler
from app.fdi_indexed import IndexedFDIFile
from scripts import season_quality_only_delta_v1 as native
from scripts import season_soccerbase_secondary_facts_v2 as source
from scripts import season_opening_order_repair_v1 as ownership
from scripts.season_frozen_fixture_reserve_v2 import heading_name
from scripts.season_historical_roster_audit_v1 import native_player,normalise

SCHEMA='pm99-explicit-source-backed-player-field-changes-v1'
INPUT_SCHEMA='pm99-explicit-source-backed-player-change-input-v1'
PREFIX='source-backed-player-changes-'
MODE='known-good-baseline-explicit-source-backed-player-changes-v1'
KIND='missing-profile-nationality'
KNOWN_WRONG_KIND='known-wrong-profile-nationality'
HEIGHT_KIND='published-adult-profile-height'
ADJUDICATED_KIND='adjudicated-source-player-facts'
DATED_ROLE_KIND='dated-roster-compatible-profile-roles'
PRIMARY_ROLE_KIND='compatible-biography-conflicting-role-set-repair'
EDITORIAL_FACTORY_ROLE_KIND='reviewed-editorial-compatible-fine-role-projection'
DATED_PARENT_FACTS_ROLE_KIND='dated-parent-facts-editorial-compatible-fine-role-projection-v3'
NATIONAL_TEAM_KIND='dated-national-squad-single-game-country'
DOB_DISAGREEMENT_KIND='source-backed-known-dob-disagreement'
ANNUAL_BROAD_KIND='annual-literal-broad-position-only'
MULTI_FIELD_KINDS=(ADJUDICATED_KIND,DATED_ROLE_KIND,PRIMARY_ROLE_KIND,NATIONAL_TEAM_KIND,DOB_DISAGREEMENT_KIND,EDITORIAL_FACTORY_ROLE_KIND,DATED_PARENT_FACTS_ROLE_KIND)
HEIGHT_SCOPE='Only selected adult published-height recipe fields and one height byte per changed native player; names, DOBs, countries, roles, ratings, orders, clubs, managers, photos, kits, EXE and opaque bytes unchanged. Published adult biography height is not a dated target-season measurement claim.'
SCOPE='Only selected explicit missing nationality recipe fields and one country byte per selected native player; all names, DOBs, roles, ratings, orders, ownership, tactics, managers, photos, kits, EXE and opaque data unchanged.'
digest=native.digest

def filename(plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.filename(plan)
    if plan.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.filename(plan)
    return 'source-backed-player-changes-'+plan['transaction_id']+'.json'
def artifact_id(plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.artifact_id(plan)
    return PREFIX+plan['transaction_id']
def binding(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))

def original_path(relative):
    path=registry.ROOT/relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(registry.ROOT.resolve()) or not path.is_file():
        raise ValueError('source input must be a retained workspace file')
    return path

def prepare(base,input_path):
    path=Path(input_path)
    original_path(registry.relative_workspace_path(path))
    request=pipeline.read_json_file(path)
    if request.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.prepare(base, path)
    if request.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.prepare(base, path)
    if request.get('kind') == EDITORIAL_FACTORY_ROLE_KIND:
        from scripts import season_editorial_factory_role_projection_v1 as editorial_roles
        return editorial_roles.prepare(base, path)
    if request.get('kind') == NATIONAL_TEAM_KIND:
        from scripts import season_dated_national_team_country_v1 as national_country
        return national_country.prepare(base, path, request)
    if request.get('kind') == PRIMARY_ROLE_KIND:
        from scripts import season_compatible_primary_role_v1 as primary_role
        return primary_role.prepare(base, path, request)
    if request.get('kind') == DATED_ROLE_KIND:
        from scripts import season_dated_roster_roles_v1 as dated_roles
        return dated_roles.prepare(base, path, request)
    if request.get('kind') == ADJUDICATED_KIND:
        from scripts import season_adjudicated_player_facts_v1 as adjudicated
        return adjudicated.prepare(base, path, request)
    if request.get('kind') == HEIGHT_KIND:
        return prepare_height(base, path, request)
    if request.get('kind') == KNOWN_WRONG_KIND:
        # The 11v11 policy is a typed source branch of the existing byte-only
        # nationality change. Keep the common schema, binder, native mask and
        # SOURCE replay contract; only source admission is provider-specific.
        if any(isinstance(change.get('source'), dict)
               and change['source'].get('provider') == '11v11'
               for change in request.get('changes', []) if isinstance(change, dict)):
            from scripts import season_11v11_profile_nationality_v1 as elevenv
            return elevenv.prepare(base, path)
        from scripts import season_known_wrong_profile_nationality_v1 as known_wrong
        return known_wrong.prepare(base, path, request)
    if request.get('kind') == DOB_DISAGREEMENT_KIND:
        from scripts import season_soccerbase_birthday_disagreement_v1 as dob_disagreement
        return dob_disagreement.prepare(base, path)
    if (request.get('schema')!=INPUT_SCHEMA or request.get('season')!=base.season
            or request.get('release_id')!=base.release_id or request.get('kind')!=KIND
            or not request.get('changes')):
        raise ValueError('explicit supported field-change source input and exact parent required')
    actors={p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
    clubs={c['id']:c for c in pipeline.read_json_file(base.package_path)['clubs']}
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners=ownership.native_owners(eq)
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    updates=[];seen=set()
    for selection in request['changes']:
        carrier=selection['carrier_id']
        if type(carrier)is not int or carrier in seen or selection.get('field_mask')!=['nationality']:
            raise ValueError('unique literal carriers and nationality-only field mask required')
        seen.add(carrier);actor=actors[carrier];club=clubs[actor['club_id']]
        raw=entries[carrier].decode_payload(jug);observed=native_player(raw,carrier);end=observed['name_end']
        if (actor['facts']['nationality']!='XXX' or (raw[end+8]^0x61)!=codes['XXX']
                or owners.get(carrier)!={club['carrier_id']}
                or normalise(observed['name'])!=normalise(actor['name'])):
            raise ValueError('only an explicitly unknown country on the exact exclusively owned actor may be completed')
        original=selection['source'];body=original_path(original['path'])
        receipt_path=body.with_suffix(body.suffix+'.source.json')
        receipt=pipeline.read_json_file(receipt_path)
        if (registry.sha256_file(body)!=original['sha256'] or receipt.get('url')!=original['url']
                or receipt.get('sha256')!=original['sha256']):
            raise ValueError('original profile body/URL receipt differs')
        identity=source.country(body.read_bytes(),person_id=original['provider_player_id'],
            name=heading_name(actor.get('source_name') or actor['name']),birth_date=actor['facts']['birth_date'],url=original['url'])
        # Read the actual native date too: recipe agreement alone is insufficient.
        from scripts.season_within_club_reserve_repair_v1 import native_facts
        if native_facts(jug,carrier)['birth_date']!=actor['facts']['birth_date']:
            raise ValueError('actual native biography does not identify this source person')
        code=compiler._country_code(identity['nationality'],codes)
        if code==codes['XXX']:raise ValueError('unsupported native countries are documented, not guessed')
        updates.append(dict(carrier_id=carrier,before=copy.deepcopy(actor),nationality=identity['nationality'],
            field_mask=['nationality'],native_mask=dict(file='DBDAT/JUG98030.FDI',record_offset=end+8,
                file_offset=entries[carrier].payload_offset+end+8,
                before=jug[entries[carrier].payload_offset+end+8],after=code),
            source_identity=identity,source=binding(body),source_receipt=binding(receipt_path),
            expected_owner=club['carrier_id']))
    result=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,kind=KIND,
        source_input=binding(path),package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),
        eq_sha256=digest(eq),textos_sha256=registry.sha256_file(base.game_path/'DBDAT/TEXTOS.PKF'),
        updates=updates,scope=SCOPE,source_policy=source.POLICY)
    result['transaction_id']=digest(packages.canonical_json_bytes(result))[:24]
    return result


def prepare_height(base, path, request):
    from scripts.season_opening_identity_exchange_v1 import read_transfermarkt_profile, published_name_key
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    if (request.get('schema') != INPUT_SCHEMA or request.get('season') != base.season
            or request.get('release_id') != base.release_id or not request.get('changes')):
        raise ValueError('adult-height input needs an exact registered parent and selections')
    package = pipeline.read_json_file(base.package_path)
    actors = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    updates, seen = [], set()
    for selection in request['changes']:
        carrier = selection['carrier_id']
        if type(carrier) is not int or carrier in seen or selection.get('field_mask') != ['height_cm']:
            raise ValueError('adult-height input requires unique height-only selections')
        seen.add(carrier)
        actor = actors[carrier]
        original = selection['source']
        original_path(original['path'])
        profile = read_transfermarkt_profile(original, original['provider_player_id'])
        birthday = profile['published_birth_date']
        observed = native_facts(jug, carrier)
        if (published_name_key(profile['published_full_name']) != published_name_key(actor.get('source_name') or actor['name'])
                or birthday != actor['facts']['birth_date'] or birthday != observed['birth_date']
                or observed['name'].casefold() != actor['name'].casefold()
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}):
            raise ValueError('adult height source/native identity or exclusive club differs')
        born = date.fromisoformat(birthday)
        snapshot = date(int(base.season[:4]), 8, 1)
        age = snapshot.year - born.year - ((snapshot.month, snapshot.day) < (born.month, born.day))
        height = profile['published_height_cm']
        if age < 18 or type(height) is not int or not 130 <= height <= 230:
            raise ValueError('height transfer requires a published valid measurement and a target-season adult')
        raw = entries[carrier].decode_payload(jug)
        end = native_player(raw, carrier)['name_end']
        offset = entries[carrier].payload_offset + end + 16
        if jug[offset] != (raw[end + 16] ^ 0x61):
            raise ValueError('height byte does not match the proven native field boundary')
        updates.append(dict(carrier_id=carrier, before=copy.deepcopy(actor), height_cm=height,
            field_mask=['height_cm'], native_mask=dict(file='DBDAT/JUG98030.FDI', record_offset=end + 16,
                file_offset=offset, before=jug[offset], after=height), source=binding(original_path(original['path'])),
            source_identity=dict(name=profile['published_full_name'], birth_date=birthday,
                provider_player_id=original['provider_player_id'], profile_url=original['url'], height_cm=height,
                policy='published-adult-biography-height; not a dated-period measurement'),
            expected_owner=clubs[actor['club_id']]['carrier_id']))
    result = dict(schema=SCHEMA, season=base.season, release_id=base.release_id, kind=HEIGHT_KIND,
        source_input=binding(path), package_sha256=registry.sha256_file(base.package_path), jug_sha256=digest(jug),
        eq_sha256=digest(eq), updates=updates, scope=HEIGHT_SCOPE,
        source_policy='exact-original-profile-ID-full-name-DOB-target-adult-and-height-only-v1')
    result['transaction_id'] = digest(packages.canonical_json_bytes(result))[:24]
    return result

def verify(base,plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.verify(base, plan)
    if plan.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.verify(base, plan)
    if (plan.get('schema')!=SCHEMA or registry.sha256_file(original_path(plan['source_input']['path']))!=plan['source_input']['sha256']
            or prepare(base,original_path(plan['source_input']['path']))!=plan):
        raise ValueError('source-backed field plan does not independently reproduce')

def validate_mask(plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.validate_mask(plan)
    if plan.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.validate_mask(plan)
    if plan.get('kind') == EDITORIAL_FACTORY_ROLE_KIND:
        from scripts import season_editorial_factory_role_projection_v1 as editorial_roles
        return editorial_roles.validate_mask(plan)
    if plan.get('kind') == NATIONAL_TEAM_KIND:
        from scripts import season_dated_national_team_country_v1 as national_country
        return national_country.validate_mask(plan)
    if plan.get('kind') == PRIMARY_ROLE_KIND:
        from scripts import season_compatible_primary_role_v1 as primary_role
        return primary_role.validate_mask(plan)
    if plan.get('kind') == DATED_ROLE_KIND:
        from scripts import season_dated_roster_roles_v1 as dated_roles
        return dated_roles.validate_mask(plan)
    if plan.get('kind') == ADJUDICATED_KIND:
        from scripts import season_adjudicated_player_facts_v1 as adjudicated
        return adjudicated.validate_mask(plan)
    if plan.get('kind') == KNOWN_WRONG_KIND:
        if any(isinstance(row.get('source_identity'), dict)
               and row['source_identity'].get('provider') == '11v11'
               for row in plan.get('updates', []) if isinstance(row, dict)):
            from scripts import season_11v11_profile_nationality_v1 as elevenv
            return elevenv.validate_plan(plan)
        from scripts import season_known_wrong_profile_nationality_v1 as known_wrong
        return known_wrong.validate_plan(plan)
    if plan.get('kind') == DOB_DISAGREEMENT_KIND:
        from scripts import season_soccerbase_birthday_disagreement_v1 as dob_disagreement
        return dob_disagreement.validate_mask(plan)
    rows=plan.get('updates',[])
    height = plan.get('kind') == HEIGHT_KIND
    field = 'height_cm' if height else 'nationality'
    if plan.get('schema')!=SCHEMA or plan.get('kind') not in (KIND, HEIGHT_KIND) or not rows or len({r['carrier_id'] for r in rows})!=len(rows):
        raise ValueError('nonempty unique supported source-backed field changes required')
    allowed={'carrier_id','before','nationality','field_mask','native_mask','source_identity','source','source_receipt','expected_owner'}
    if height:
        allowed = (allowed - {'nationality', 'source_receipt'}) | {'height_cm'}
    if any(set(r)!=allowed or r['field_mask']!=[field] or r['native_mask']['file']!='DBDAT/JUG98030.FDI' for r in rows):
        raise ValueError('source-backed field/native mask cannot authorise other profile edits')
    offsets=set()
    for row in rows:
        mask=row['native_mask']
        if height and (type(row['height_cm']) is not int or not 130 <= row['height_cm'] <= 230
                       or mask.get('after') != row['height_cm']):
            raise ValueError('adult-height native mask must write the exact published measurement')
        if (set(mask)!={'file','record_offset','file_offset','before','after'}
                or type(row['carrier_id']) is not int
                or any(type(mask[k]) is not int for k in ('record_offset','file_offset','before','after'))
                or mask['record_offset']<0 or mask['file_offset']<mask['record_offset']
                or not 0<=mask['before']<=255 or not 0<=mask['after']<=255
                or (not height and mask['before']==mask['after']) or mask['file_offset'] in offsets):
            raise ValueError('exact distinct one-byte native pre/post masks required')
        offsets.add(mask['file_offset'])

def bind(package,plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.bind(package, plan)
    if plan.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.bind(package, plan)
    validate_mask(plan)
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    if pipeline.read_json_file(base.package_path)!=package or registry.sha256_file(base.package_path)!=plan['package_sha256']:
        raise ValueError('exact source-backed recipe preimage required')
    result=copy.deepcopy(package);actors={p['carrier_id']:p for p in result['players']}
    for row in plan['updates']:
        actor=actors[row['carrier_id']]
        if actor!=row['before']:raise ValueError('selected actor preimage differs')
        fields = row['values'] if plan['kind'] in MULTI_FIELD_KINDS else {
            ('height_cm' if plan['kind'] == HEIGHT_KIND else 'nationality'):
            row['height_cm' if plan['kind'] == HEIGHT_KIND else 'nationality']}
        actor['facts'].update(fields)
        if 'fact_fallbacks' in actor:actor['fact_fallbacks']=[f for f in actor['fact_fallbacks'] if f['field'] not in fields]
    result['artifacts'].append(dict(id=artifact_id(plan),kind='season-input',relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result

def apply(jug,eq,plan):
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.apply(jug, eq, plan)
    if plan.get('kind') == DATED_PARENT_FACTS_ROLE_KIND:
        from scripts import season_dated_parent_facts_editorial_role_v1 as dated_parent_role
        return dated_parent_role.apply(jug, eq, plan)
    validate_mask(plan);base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    if digest(eq)!=plan['eq_sha256']:raise ValueError('source-backed exact EQ required')
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    masks = [m for row in plan['updates'] for m in (
        row['native_masks'] if plan['kind'] in MULTI_FIELD_KINDS else [row['native_mask']])]
    if plan['kind'] in (HEIGHT_KIND, KNOWN_WRONG_KIND, *MULTI_FIELD_KINDS):
        candidate = bytearray(before)
        for mask in masks:
            candidate[mask['file_offset']] = mask['after']
        after, after_eq = bytes(candidate), eq
        if jug not in (before, after):
            raise ValueError('adult height patch accepts only exact complete pre/postimages')
    else:
        after,after_eq=native.apply(jug,eq,plan)
    allowed={m['file_offset'] for m in masks if m['before'] != m['after']}
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    if len(before)!=len(after) or changed!=allowed or (plan['kind'] in (KIND, KNOWN_WRONG_KIND) and len(allowed)!=len(plan['updates'])):
        raise ValueError('source-backed change altered bytes outside the exact native field mask')
    for mask in masks:
        if before[mask['file_offset']]!=mask['before'] or after[mask['file_offset']]!=mask['after']:
            raise ValueError('source-backed native pre/post value differs')
    return after,after_eq

def reject_factory_recipe(package):
    from scripts import season_annual_literal_broad_position_v1 as annual_broad
    annual_broad.reject_factory_recipe(package)
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('source-backed field recipe requires exact SOURCE reconstruction')

def reconstruction(previous,release_id,*,minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    disk_budget.validate_reserve(minimum_free_bytes)
    relative=getattr(previous,'locator',{}).get('sourced_profile_assignment_plan_path')
    if not relative:return None
    path=registry.ROOT/relative;plan=pipeline.read_json_file(path)
    if plan.get('kind') == ANNUAL_BROAD_KIND:
        from scripts import season_annual_literal_broad_position_v1 as annual_broad
        return annual_broad.reconstruction(previous, release_id, minimum_free_bytes=minimum_free_bytes)
    if plan.get('schema')!=SCHEMA:return None
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    receipt=pipeline.read_json_file(previous.compiler_receipt_path)
    if (receipt.get('compilation_mode')!=MODE or path.resolve()!=(previous.package_path.parent/filename(plan)).resolve()
            or registry.sha256_file(path)!=receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('source-backed SOURCE receipt/plan binding differs')
    package=pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('SOURCE would discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('exact inert SOURCE descriptor required')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path,minimum_free_bytes=minimum_free_bytes)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('whole SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True)
