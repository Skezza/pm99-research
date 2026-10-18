"""Repair the existing Woking cohort; do not insert a second Woking club.

The current club3321 has a false Dover label. Replay the original eleven and
the verified bench, and atomically replace Oxford's departed/loaned Louis
reserve with its independently dated Oxford reserve Tom Winters. Counts and
native families stay fixed; managers are sourced, not inherited.
"""
import copy
import hashlib
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement,patch_owned_mode1_complete_orders,read_initial_order
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_v2 as packages,season_duplicate_ownership_delta_v1 as delta
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_published_family_component_v1 as families
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_historical_club_label_plan_v1 as labels
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA='pm99-original-Woking2003-existing-cohort-paired-Oxford-reserve-v1'
PREFIX='sourced-woking-owned-opening-'
FILENAME='sourced-woking-owned-opening.json'
MODE='known-good-baseline-source-bound-Woking-owned-cohort-paired-Oxford-reserve'
SOURCE_PROPOSAL=registry.ROOT/'.local/consolidated-audit-20261009/cross-club-next-delivery-v1/2003-04/woking3313-reserve-pool-v2.json'
URLS={
 'oxford-opening-winters-biography':'https://www.soccerbase.com/players/player.sd?player_id=38371',
 'woking-original-bbc-appointment':'https://news.bbc.co.uk/sport2/hi/football/teams/w/woking/2424871.stm',
 'woking-original-bbc-departure':'https://news.bbc.co.uk/sport2/hi/football/teams/w/woking/6506461.stm',
 'glenn-cockerill-original-wikipedia':'https://en.wikipedia.org/wiki/Glenn_Cockerill'}


def digest(data):return hashlib.sha256(data).hexdigest()


def raw_source(key,proofs):
    path,raw,binding=source_rows(key)
    receipt=path.with_suffix('.source.json');doc=pipeline.read_json_file(receipt)
    if doc['url']!=URLS[key]:raise ValueError('paired Woking original URL differs')
    proofs.append(dict(binding,url=doc['url'],receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt)))
    return raw,BeautifulSoup(raw,'lxml')


def require(page,*anchors):
    text=' '.join(page.get_text(' ',strip=True).split())
    if any(a not in text for a in anchors):raise ValueError('paired Woking original historical anchors differ')


def manager(proofs):
    _,page=raw_source('woking-original-bbc-appointment',proofs)
    require(page,'Friday, 8 November, 2002','Glenn Cockerill has been appointed the new manager',
        'nearly a month as acting manager','Geoff Chapple')
    _,page=raw_source('woking-original-bbc-departure',proofs)
    require(page,'Thursday, 29 March 2007','Woking have sacked manager Glenn Cockerill',
        'Cockerill replaced Geoff Chapple as caretaker manager at Kingfield in October 2002')
    _,page=raw_source('glenn-cockerill-original-wikipedia',proofs)
    if [h.get_text(' ',strip=True) for h in page.select('h1')]!=['Glenn Cockerill']:
        raise ValueError('manager biography heading differs')
    require(page,'2002–2007 Woking')
    return dict(name='Glenn Cockerill',native_names=dict(surname='Cockerill',display_name='Cockerill'),
        policy='primary-original-2002-appointment-2007-departure-plus-literal-biography-interior-year',
        exact_2003_matchday_source_claimed=False,
        rejected_history='Retain original Soccerbase manager history ending May2003 as a documented contradiction; no invented extension of those bytes.')


def winters(base,proofs):
    raw,page=raw_source('oxford-opening-winters-biography',proofs)
    from scripts import capture_soccerbase_august_squads_v1 as august,season_original_soccerbase_reserves_v1 as reserves
    source=august.player_profile(raw,fallback_name='',fallback_position='?')
    if (source['name'],source['birth_date'],source['position'])!=('Tom Winters','1985-12-11','M'):
        raise ValueError('Oxford reserve full biography/DOB/role differs')
    interval=reserves.career_interval(raw,1964,'2003-08-09')
    require(page,'Nationality England')
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==383)
    capture,annual_raw=facts.annual_capture('2003-04',club)
    annual=capture['players']
    matching=[p for p in annual if p['name']=='Tom Winters']
    if len(matching)!=1 or (matching[0]['birth_date'],matching[0]['position'])!=('1985-12-11','M'):
        raise ValueError('period annual and numerical Oxford reserve differ')
    source.update(nationality='ENG',height_cm=matching[0]['height_cm'],weight_kg=matching[0]['weight_kg'])
    proofs.append(dict(path=annual_raw['local_path'],sha256=annual_raw['source_sha256']))
    return dict(source_person=dict(name='Tom Winters',birth_date='1985-12-11',source_provider='soccerbase',
        source_player_id='soccerbase:38371',provider_player_id=38371,source_profile_url=URLS['oxford-opening-winters-biography']),
        source_player=source,raw_evidence=dict(status='raw-source-reparsed',local_path=proofs[-2]['path'],
            source_sha256=proofs[-2]['sha256']),original_provider_career_interval=interval,
        membership='positive-original-numeric-Oxford-opening-reserve-not-whole-season-guess')


def prepare(base):
    if base.season!='2003-04':raise ValueError('Woking ownership admission is 2003 only')
    source_proposal=pipeline.read_json_file(SOURCE_PROPOSAL)
    if source_proposal['release_id']!=base.release_id:raise ValueError('Woking discovery/source baseline differs')
    # Reuse the captured investigation, but independently rederive every raw
    # XI, identity, exclusion and dated reserve. Its failed3313 fit is not
    # publication authority; this exact current-cohort transaction is separate.
    from scripts.prepare_paired_whole_club_native_v1 import independently_replay_sources
    independently_replay_sources([source_proposal])
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==3321)
    if club['name']!='Dover Athletic' or any(c['name']=='Woking' for c in package['clubs']):
        raise ValueError('existing Woking cohort label/collision changed')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if {p['carrier_id'] for p in slots}!=set(range(11141,11157)):raise ValueError('sixteen resident carriers changed')
    # ALL resident identities came from the original Woking annual cohort;
    # this is not majority voting over nine desirable names.
    annual=source_proposal['annual_capture']['players']
    for p in slots:
        matching=[a for a in annual if roster.normalise(a['name'])==roster.normalise(p.get('source_name') or p['name'])]
        if len(matching)!=1:raise ValueError('resident is not one exact original Woking annual identity')
        if matching[0]['birth_date'] and p['facts']['birth_date']!=matching[0]['birth_date']:
            raise ValueError('resident original annual birthday changed')
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    from scripts import season_opening_order_repair_v1 as ownership
    owners=ownership.native_owners(eq)
    if any(owners.get(p['carrier_id'])!={3321} for p in slots):raise ValueError('resident is shared with another native club')
    desired=source_proposal['desired_people']
    public=registry.ROOT/source_proposal['bindings']['published_person_supplement']['path']
    selected_ids={p['source_person']['source_player_id'] for p in desired if type(p['source_person']['source_player_id']) is int}
    fitted=allocation.allocate(jug,slots,desired,{},published_families=families.claims(public,selected_ids),
        capacity_bundle=source_proposal['capacity_policy_bundle'],opening_slot_orders=allocation.startup_orders(jug,slots),
        allow_keeper_order_exchange=True,fit_reserve_pool=True)
    chosen={r['replacement']['source_person']['source_player_id'] for r in fitted}
    selected=[p for p in desired if p['source_person']['source_player_id'] in chosen]
    if len(selected)!=16 or sum(p['membership']=='starting_xi' for p in selected)!=11:
        raise ValueError('whole original XI was not retained')
    oxford=next(p for p in package['players'] if p['carrier_id']==33060)
    if (oxford['club_id'],roster.normalise(oxford['source_name']),oxford['facts']['birth_date'])!=('english-club-383','jeffersonlouis','1979-02-22') or owners.get(33060)!={383} or facts.native_facts(jug,33060)['startup_order']<=11:
        raise ValueError('Oxford displaced Louis is not an exact exclusively owned reserve')
    for wanted in selected:
        name=wanted['source_player']['name'];birthday=wanted['source_player']['birth_date']
        elsewhere=[p for p in package['players'] if p['club_id']!=club['id'] and
            roster.normalise(p.get('source_name') or p['name'])==roster.normalise(name) and p['facts'].get('birth_date')==birthday]
        if elsewhere!=([oxford] if name=='Jefferson Louis' else []):raise ValueError('another outside source-owner conflict needs a paired correction')
    proofs=[];coach=manager(proofs);reserve=winters(base,proofs)
    if any(roster.normalise(p.get('source_name') or p['name'])=='tomwinters' for p in package['players']):
        raise ValueError('new Oxford reserve is already represented')
    from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
    holders,names=_manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    if [c['carrier_id'] for c in holders.get(818,[])]!=[3321] or any(m['name']=='Glenn Cockerill' for m in package['managers']):
        raise ValueError('Woking native coach ownership/person collision changed')
    proposal=dict(before_club=club,new_club='Woking',allocation=fitted,desired_people=selected,
        season=base.season,original_opening=source_proposal['original_opening'])
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        ent_sha256=registry.sha256_file(base.game_path/'DBDAT/ENT98030.FDI'),
        source_proposal=dict(path=registry.relative_workspace_path(SOURCE_PROPOSAL),sha256=registry.sha256_file(SOURCE_PROPOSAL)),
        source_proofs=proofs,proposal=proposal,capacity_bundle=source_proposal['capacity_policy_bundle'],
        coach=coach,native_coach_before=names[818],Oxford_before=oxford,Oxford_replacement=reserve,
        scope='Existing16-person Woking cohort, original complete August9 XI/verified bench; one paired Oxford33060 reserve identity; exact native counts/families, source-named manager818, all unrelated people/clubs/manager records/EXE/assets/tactics unchanged. Present identities retain ten native skills. Portraits cleared where slots change. Native source-fixed roster/order, no global historical certification.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Woking original sources/paired ownership/preimage do not reproduce')


def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    if pipeline.read_json_file(base.package_path)!=package or registry.sha256_file(base.package_path)!=plan['package_sha256']:
        raise ValueError('Woking recipe preimage changed')
    result,composition=native.compile_recipe(package,plan['proposal'])
    # Keep existing people/abilities rather than re-rating the already sourced
    # nine residents and moved Louis as if they were newly discovered people.
    originals={roster.normalise(p.get('source_name') or p['name']):p for p in package['players']
        if p['club_id']=='club-3321' or p['carrier_id']==33060}
    for p in result['players']:
        if p['club_id']!='club-3321':continue
        old=originals.get(roster.normalise(p['source_name']))
        if old and old['facts']['birth_date']==p['facts']['birth_date']:
            p['ratings']=copy.deepcopy(old['ratings'])
            # Facts and their fallbacks remain the source composer's consistent
            # pair. Slot-relative preserve-existing dictionaries cannot be
            # moved between people: they would retain the destination's bytes.
    update=dict(layer='main',player_id=plan['Oxford_before']['id'],carrier_id=33060,
        club_id=plan['Oxford_before']['club_id'],before=plan['Oxford_before'],replacement=plan['Oxford_replacement'],
        replacement_opening_evidence=dict(date='2003-08-09'))
    oxford_composition=dict(season=plan['season'],bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        updates=[update],source_title='Positive numerical Oxford July2003-to-May2009 Tom Winters reserve, literal period DOB/role agreement')
    result=delta.updated_package(result,oxford_composition)
    aid=PREFIX+plan['season'];old_ids=[]
    for comp in (composition,oxford_composition):
        a=next(a for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(comp));old_ids.append(a['id'])
    result['artifacts']=[a for a in result['artifacts'] if a['id'] not in old_ids]
    result['artifacts'].append(dict(id=aid,kind='season-input',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    for collection in (result['players'],result['clubs'],result['assets']['portraits']):
        for row in collection:
            if row.get('proof',{}).get('artifact_id') in old_ids:row['proof']['artifact_id']=aid
            for f in row.get('fact_fallbacks',[]):
                if f['proof']['artifact_id'] in old_ids:f['proof']['artifact_id']=aid
    for collection in ('sources','proofs'):
        for row in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if row.get(key) in old_ids:row[key]=aid
    coach=next(m for m in result['managers'] if m['carrier_id']==818)
    coach.update(name='Glenn Cockerill',policy='write',native_names=plan['coach']['native_names'],
        person_id='manager-wikipedia-glenn-cockerill',proof=dict(artifact_id=aid,grade='source-receipt'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']):raise ValueError('Woking immutable native source changed')
    prepared=original
    for row in plan['proposal']['allocation']:
        if row.get('same_carrier_name_capacity'):
            prepared,claim=capacity.recover_slot(prepared,row['carrier_id'],plan['capacity_bundle'])
            if claim!=row['same_carrier_name_capacity']:raise ValueError('Woking original window recovery changed')
    package=bind(pipeline.read_json_file(base.package_path),plan)
    selected={p['id'] for p in package['players'] if p['club_id']=='club-3321' or p['carrier_id']==33060}
    countries=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    candidate=delta.compile_players(prepared,package,selected,countries)
    club=next(c for c in package['clubs'] if c['carrier_id']==3321)
    players={p['id']:p for p in package['players']}
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    orders=[OrderReplacement(players[id]['carrier_id'],read_initial_order(entries[players[id]['carrier_id']].decode_payload(candidate)).name,
        facts.native_facts(original,players[id]['carrier_id'])['startup_order'],n)
        for n,id in enumerate(club['roster_player_ids'],1)]
    candidate=patch_owned_mode1_complete_orders(candidate,original_eq,club_record_id=3321,replacements=orders)
    changed_eq=native.rewrite_roster(original_eq,3321,[players[id]['carrier_id'] for id in club['roster_player_ids']])
    entry=next(e for e in IndexedFDIFile.from_bytes(changed_eq).entries if e.record_id==3321)
    short,full,_=labels.prefix_parts(entry.decode_payload(changed_eq))
    changed_eq,_=labels.rewrite_club_labels(changed_eq,[dict(carrier_id=3321,native_before=short,native_full_before=full,native_after='Woking')])
    if (jug,eq) not in ((original,original_eq),(candidate,changed_eq)):
        raise ValueError('paired Woking accepts only exact complete native pre/postimages')
    native.preserve_other_records(original,candidate,set(range(11141,11157))|{33060})
    native.preserve_other_records(original_eq,changed_eq,{3321})
    return candidate,changed_eq


def apply_ent(ent,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/ENT98030.FDI').read_bytes()
    if digest(original)!=plan['ent_sha256']:raise ValueError('Woking original manager file changed')
    index=IndexedFDIFile.from_bytes(original);entry=next(e for e in index.entries if e.record_id==818)
    payload=delta.compiler._patch_ent_name(entry.decode_payload(original),818,'Glenn Cockerill',native_names=plan['coach']['native_names'])
    candidate=delta.compiler._rebuild_indexed(original,index,{818:payload})
    if ent not in (original,candidate):raise ValueError('Woking manager accepts only complete native pre/postimages')
    native.preserve_other_records(original,candidate,{818})
    return candidate


def selected_carriers(plan):return set(range(11141,11157))|{33060}
def filename(plan):return FILENAME
def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Woking paired ownership requires exact source-bound reconstruction')


def reconstruction(previous,release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    a=[a for a in package['artifacts'] if a['id']==PREFIX+previous.season]
    if len(a)!=1 or path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=a[0]['sha256']:
        raise ValueError('Woking exact layer artifact differs')
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('edited Woking recipe cannot silently discard edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    inert=pipeline.read_json_file(descriptor)
    if inert!=dict(season=base.season,release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[]):
        raise ValueError('Woking reconstruction descriptor is not exact inert input')
    for release in (base,previous):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('complete Woking source recipe replay differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
