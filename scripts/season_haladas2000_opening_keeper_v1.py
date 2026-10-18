"""Replace the proved Haladas opening Kiraly copy with sourced Kurucsai.

Explicit starter-keeper policy, not a relaxation of the reserve-only rules.
Retain Hertha's actual Kiraly; leave all other Haladas players unapproved.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
from statistics import median
from app.fdi_indexed import IndexedFDIFile
from scripts import adjudicate_haladas_opening_keeper_20261017 as admission
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_rating_calibration_v3 as ratings
from scripts import season_package_v2 as packages

pipeline,registry,roster=admission.pipeline,admission.registry,admission.roster
SCHEMA='pm99-original-Haladas2000-positive-first-fixture-keeper-v1'
PREFIX='sourced-haladas2000-opening-keeper-'
MODE='known-good-baseline-original-Haladas2000-positive-opening-keeper-v1'
FILENAME='sourced-haladas2000-opening-keeper.json'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME
def selected_carriers(plan):return {8507}


def prepare(base):
    source=admission.decision(base)
    package=pipeline.read_json_file(base.package_path);before=next(p for p in package['players'] if p['carrier_id']==8507)
    represented=[p for _,layer,_ in delta.planner.package_layers(base) for p in layer['players']]
    if any(roster.normalise(p.get('source_name') or p['name'])=='kornelkurucsai' for p in represented):
        raise ValueError('opening replacement already represented; no new duplicate permitted')
    copies={p['carrier_id'] for p in represented if roster.normalise(p.get('source_name') or p['name'])=='gaborkiraly'
        and p['facts'].get('birth_date')=='1976-04-01'}
    if copies!={2211,8507}:raise ValueError('additional Kiraly copies require a coupled ownership correction')
    path=admission.ROOT/'same-slot-published-surname-capacity-preflight.json'
    reviewed=pipeline.read_json_file(path);bundle=reviewed['factory_recovery_runtime_bundle']
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    _,claim=capacity.recover_slot(jug,8507,bundle)
    if claim!=reviewed['same_slot_recovery'] or reviewed['published_display_name']!='Kurucsai':
        raise ValueError('positive published surname capacity proof differs from exact current slot')
    club=next(c for c in package['clubs'] if c['id']==before['club_id'])
    prior=[p['ratings']['values']['quality'] for p in package['players'] if p['club_id']==club['id']]
    group=roster.club_group(club);tier=ratings.old.inputs.COUNTRY_STRENGTH.get(group,60)
    strength=max(tier-12,min(tier+12,round(median(prior))))
    actor=dict(name='Kurucsai',source_name='Kornél Kurucsai',person_id='person-transfermarkt-670636',club_id=club['id'],
        facts=dict(birth_date='1972-01-18',primary_position='G',height_cm=185,fine_roles=[0]))
    values=ratings.editorial(actor,strength,'starting_xi',date(2000,8,1))
    if set(values)!=set(ratings.old.MAPPING) or not 35<=values['handling']<=99:
        raise ValueError('new opening keeper ten-skill/handling contract failed')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=source['jug_sha256'],eq_sha256=source['eq_sha256'],
        source_decision=source,before_player=before,capacity_bundle=bundle,capacity_claim=claim,
        display_name='Kurucsai',fine_roles=[0],ratings=dict(profile='pm99-visible-skills-v1',values=values,
            provenance=dict(method='identity-club-role-age-optional-editorial-calibration-v3',proof_grade='reviewed-editorial',source_ids=[ratings.SOURCE_ID])),
        rating_basis=dict(club_strength=strength,method='explicit-native-club-prior-country-bounded-editorial-estimate',
            status='starting_xi',FIFA_values_claimed=False),
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(p)),sha256=registry.sha256_file(Path(p)))
            for p in (__file__,admission.__file__,capacity.__file__,delta.__file__,ratings.__file__,ratings.old.__file__,ratings.model.__file__)],
        scope='Only positively proved wrong opening keeper8507 person/facts/position-aware editorial skills and missing-photo fallback. Published surname retained using existing exact shrink-inverse capacity. Hertha2211, all other players, roster links, startup1, tactics, clubs, managers, kits and EXE unchanged. Whole Haladas/Hertha rosters and opening XI remain unapproved.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Haladas original opening keeper source/native decision differs')


def bind(package,plan):
    if plan.get('schema')!=SCHEMA or digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        raise ValueError('Haladas whole recipe preimage differs')
    before=plan['before_player'];source=plan['source_decision']['replacement']
    person=dict(name=source['published_full_name'],birth_date=source['birth_date'],source_player_id=source['source_player_id'])
    composition=dict(season=plan['season'],bindings=dict(snapshot=dict(project_url='https://tempofradi.hu/2000-vii-22-ferencvaros-haladas-4-0')),
        source_title='Original first-round Haladas keeper plus exact published full-name/date/country biography',
        proof_covers=['positive-original-first-fixture-keeper-replacement-not-full-XI'],
        updates=[dict(layer='main',player_id=before['id'],carrier_id=8507,before=before,
            replacement=dict(source_player=dict(name=source['published_full_name'],birth_date=source['birth_date'],position='G',
                nationality='HUN',height_cm=185,weight_kg=78),source_person=person),
            replacement_opening_evidence=dict(date='2000-07-22'))])
    result=delta.updated_package(package,composition)
    old_aid=next(a['id'] for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(composition))
    aid=PREFIX+plan['season']
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
    player=next(p for p in result['players'] if p['carrier_id']==8507)
    player['name']=plan['display_name'];player['ratings']=copy.deepcopy(plan['ratings'])
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(original)!=plan['jug_sha256'] or digest(eq)!=plan['eq_sha256']:raise ValueError('Haladas whole native preimage differs')
    package=bind(pipeline.read_json_file(base.package_path),plan)
    prepared,claim=capacity.recover_slot(original,8507,plan['capacity_bundle'])
    if claim!=plan['capacity_claim']:raise ValueError('Haladas exact same-slot recovery differs')
    codes=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    after=delta.compile_players(prepared,package,{plan['before_player']['id']},codes)
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(after).entries}
    if old.keys()!=new.keys():raise ValueError('Haladas keeper changed fixed player IDs')
    for carrier,e in old.items():
        if carrier!=8507 and e.decode_payload(original)!=new[carrier].decode_payload(after):
            raise ValueError('Haladas keeper changed another player including retained Hertha Kiraly')
    facts=admission.native.native_facts(after,8507)
    if (facts['startup_order'],facts['position'],facts['birth_date'],facts['name'])!=(1,'G','1972-01-18','Kurucsai'):
        raise ValueError('actual positive opening keeper/name/date/slot readback failed')
    if jug not in (original,after):raise ValueError('Haladas input neither complete preimage nor postimage')
    return after,eq


def reconstruction(previous,release_id):
    receipt=getattr(previous,'compiler_receipt_path',None)
    if receipt is None or pipeline.read_json_file(receipt).get('compilation_mode')!=MODE:return None
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path);artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if (path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']
            or bind(pipeline.read_json_file(base.package_path),plan)!=package):raise ValueError('Haladas SOURCE would discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Haladas SOURCE descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('Haladas complete SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
