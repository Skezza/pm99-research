"""Exact Morecambe opening correction with seventeen fixed-person profiles."""
import copy
from datetime import date
import hashlib
from pathlib import Path
from bs4 import BeautifulSoup

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.player_initial_order import OrderReplacement,patch_owned_mode1_complete_orders,read_initial_order
from scripts import prepare_morecambe_owned_opening_20261017 as admission
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_package_v2 as packages
from scripts.build_woking_owned_opening_20261011 import skills

pipeline,registry,roster=admission.pipeline,admission.registry,admission.roster
SCHEMA='pm99-original-Morecambe2000-fixed-person-opening-v1'
PREFIX='sourced-morecambe2000-owned-opening-'
FILENAME='sourced-morecambe2000-owned-opening.json'
MODE='known-good-baseline-original-Morecambe2000-fixed-person-opening-v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME
def selected_carriers(plan):return {11002}


def prepare(base):
    proposal=admission.prepare(base)
    original=pipeline.read_json_file(admission.ROOT/'same-carrier-opening-assignment-v2.json')
    if proposal!=original:raise ValueError('Morecambe fixed-person source assignment changed')
    keeper=next(r for r in proposal['rows'] if r['identity_changed'])
    witness=keeper['replacement']['source_identity_resolution']['external_biography']
    raw=admission.birthdays.publisher_original(witness)
    paragraphs=[p.get_text(' ',strip=True) for p in BeautifulSoup(raw,'lxml').select('p')]
    if not any(p.startswith('Mark Allen Smith (born 2 January 1973) is an English former footballer') for p in paragraphs):
        raise ValueError('new keeper nationality lacks an explicit exact-person original statement')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=proposal['package_sha256'],jug_sha256=proposal['jug_sha256'],eq_sha256=proposal['eq_sha256'],
        assignment=proposal,keeper_nationality='ENG',keeper_nationality_original=witness,
        implementation=admission.bind(Path(__file__)),scope=proposal['scope'])


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:
        raise ValueError('Morecambe complete original source transaction does not reproduce')


def bind(package,plan):
    if digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        raise ValueError('Morecambe package preimage changed')
    row=next(r for r in plan['assignment']['rows'] if r['identity_changed'])
    composition=dict(season=plan['season'],bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        updates=[dict(layer='main',player_id=row['player_id'],carrier_id=11002,before=row['before'],
            replacement=row['replacement'],replacement_opening_evidence=plan['assignment']['original_fixture'])])
    # Fixture field is already an original date, never today's date.
    composition['updates'][0]['replacement_opening_evidence']={'date':plan['assignment']['original_fixture']['date']}
    composition['updates'][0]['replacement']=copy.deepcopy(row['replacement'])
    composition['updates'][0]['replacement']['source_player']['nationality']=plan['keeper_nationality']
    result=delta.updated_package(package,composition)
    old_aid=next(a['id'] for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(composition))
    aid=PREFIX+plan['season'];proof=dict(artifact_id=aid,grade='source-receipt')
    result['artifacts']=[a for a in result['artifacts'] if a['id']!=old_aid]
    result['artifacts'].append(dict(id=aid,kind='season-input',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    for collection in (result['players'],result['assets']['portraits']):
        for p in collection:
            if p.get('proof',{}).get('artifact_id')==old_aid:p['proof']['artifact_id']=aid
            for f in p.get('fact_fallbacks',[]):
                if f['proof']['artifact_id']==old_aid:f['proof']['artifact_id']=aid
    for collection in ('sources','proofs'):
        for p in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if p.get(key)==old_aid:p[key]=aid
    by={p['carrier_id']:p for p in result['players']}
    for decision in plan['assignment']['rows']:
        p=by[decision['carrier_id']]
        if not decision['identity_changed'] and p!=decision['before']:
            raise ValueError('retained Morecambe person was recomposed')
        p['facts'].update(birth_date=decision['birth_date'],primary_position=decision['primary_position'],
            fine_roles=decision['fine_roles'])
        p['fact_fallbacks']=[f for f in p.get('fact_fallbacks',[])
            if f['field'] not in ('birth_date','primary_position','fine_roles')]
        p['proof']=copy.deepcopy(proof)
        if decision['identity_changed']:
            p['ratings']=dict(profile='pm99-visible-skills-v1',values=decision['new_person_ratings'],
                provenance=dict(method='identity-club-role-age-optional-editorial-calibration-v3',
                    proof_grade='reviewed-editorial',source_ids=[admission.ratings.SOURCE_ID]))
    club=next(c for c in result['clubs'] if c['carrier_id']==3312)
    club['roster_player_ids']=[r['player_id'] for r in plan['assignment']['rows']]
    club['proof']=copy.deepcopy(proof)
    result['artifacts'].sort(key=lambda a:a['id'])
    packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']):
        raise ValueError('Morecambe immutable native preimage changed')
    before=pipeline.read_json_file(base.package_path);package=bind(before,plan)
    by={p['carrier_id']:p for p in package['players']}
    countries=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    # Only the new identity uses the full writer. Every retained person keeps
    # native secondary facts, names, skills and opaque bytes exactly.
    candidate=delta.compile_players(original,package,{by[11002]['id']},countries)
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    changes={}
    broad_changes={}
    for row in plan['assignment']['rows']:
        carrier=row['carrier_id']
        if row['identity_changed']:continue
        payload=entries[carrier].decode_payload(candidate)
        actor=roster.native_player(payload,carrier);end=actor['name_end']
        old_date=date(int.from_bytes(bytes(b^0x61 for b in payload[end+14:end+16]),'little'),
            payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
        if old_date!=row['birth_date']:
            if isinstance(row['before']['facts']['birth_date'],str):
                raise ValueError('retained known birthday unexpectedly differs from native')
            changes[carrier]=dict(native_name=actor['name'],before_birth_date=old_date,birth_date=row['birth_date'])
        if actor['position']!=row['primary_position']:
            # Same-person source-backed broad class only; compile using actual
            # preserved native facts/skills and identical compact layout.
            broad_changes[carrier]=bytearray(payload)
            broad_changes[carrier][end+11]=delta.compiler.POSITION[row['primary_position']] ^ 0x61
    if broad_changes:
        candidate=delta.compiler._rebuild_indexed(candidate,IndexedFDIFile.from_bytes(candidate),
            {k:bytes(v) for k,v in broad_changes.items()})
    candidate,_=rewrite_indexed_native_birth_dates(candidate,changes)
    candidate,_=rewrite_indexed_native_roles(candidate,{r['carrier_id']:r['fine_roles'] for r in plan['assignment']['rows']})
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    replacements=[OrderReplacement(r['carrier_id'],roster.native_player(entries[r['carrier_id']].decode_payload(candidate),r['carrier_id'])['name'],
        read_initial_order(entries[r['carrier_id']].decode_payload(candidate)).order,r['opening_order']) for r in plan['assignment']['rows']]
    candidate=patch_owned_mode1_complete_orders(candidate,original_eq,club_record_id=3312,replacements=replacements)
    changed_eq=native.rewrite_roster(original_eq,3312,[r['carrier_id'] for r in plan['assignment']['rows']])
    native.preserve_other_records(original,candidate,set(range(10986,11004)))
    native.preserve_other_records(original_eq,changed_eq,{3312})
    for row in plan['assignment']['rows']:
        if not row['identity_changed'] and skills(original,row['carrier_id'])!=skills(candidate,row['carrier_id']):
            raise ValueError('retained Morecambe ten native skills changed')
    if (jug,eq) not in ((original,original_eq),(candidate,changed_eq)):
        raise ValueError('Morecambe accepts only exact full native pre/postimages')
    return candidate,changed_eq


def reconstruction(previous,release_id):
    if pipeline.read_json_file(previous.compiler_receipt_path).get('compilation_mode')!=MODE:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if (path.resolve()!=(previous.package_path.parent/FILENAME).resolve()
            or registry.sha256_file(path)!=artifact['sha256'] or bind(pipeline.read_json_file(base.package_path),plan)!=package):
        raise ValueError('Morecambe edited recipe cannot be silently reconstructed')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected=dict(season=previous.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor)!=expected:raise ValueError('Morecambe inert descriptor differs')
    for release in (base,previous):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('complete Morecambe SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,compilation_mode=MODE)
