"""Replay reviewed original Boreham2017 identities; no name-only deduplication."""
import copy
from pathlib import Path

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders, read_initial_order
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import season_stevenage_opening_repair_v1 as core
from scripts import replay_original_soccerbase_openings_v1 as original
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
from scripts import capture_soccerbase_august_squads_v1 as august
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-reviewed-Boreham-2017-source-priority-opening-repair-v1'
PREFIX = 'sourced-boreham-opening-'
FILENAME = 'sourced-boreham-opening.json'
CASE = 'b85bdcbde3ddacab82d4c3f0f956fc4036ac76791590f3fe6d6fdf55a96bba44'
ROOT = registry.ROOT / '.local/consolidated-audit-20261009/primary-club-history-followup'
CLUB = 3304
REPLACE = {10854: 'Ollie Harfield', 10855: 'Joe Quigley', 10859: 'Michael Folivi'}
KEEP = {'Grant Smith': 10843, 'David Stephens': 10844, 'Jamie Turley': 10845,
        'Kane Smith': 10846, 'Dan Woodards': 10847, 'Tom Champion': 10848,
        'Mark Ricketts': 10849, 'Kieran Murtagh': 10850, 'Ricky Shakes': 10851,
        'Angelo Balanta': 10852, 'Paul Benson': 10853, 'Bradley Ash': 10856,
        'Shaun Jeffers': 10857, 'Bradley Sach': 10858, 'Fred Burbidge': 10860}
PREIMAGE_ALIASES = {'Dan Woodards': 'Danny Woodards', 'Shaun Jeffers': 'Sean Jeffers'}


def source(key, receipt_name):
    receipt = ROOT / receipt_name
    rows = pipeline.read_json_file(receipt)['cache_files']
    matches = [r for r in rows if r['cache_path'] == 'boreham/' + key]
    if len(matches) != 1:
        raise ValueError('one hash-bound original club source required')
    row = matches[0]; path = ROOT / row['cache_path']
    if not row['url'].startswith('https://www.borehamwoodfootballclub.co.uk/') or registry.sha256_file(path) != row['sha256']:
        raise ValueError('original club authority or source bytes changed')
    soup = BeautifulSoup(path.read_bytes(), 'lxml')
    return soup.get_text(' ', strip=True), dict(path=registry.relative_workspace_path(path),
        sha256=row['sha256'], url=row['url'], receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt))


def profile(id):
    path = registry.ROOT / f'.local/season-2017-18/soccerbase-august-cache-v1/player/{id}.html'
    receipt = path.with_suffix('.html.source.json')
    row = pipeline.read_json_file(receipt)
    url = f'https://www.soccerbase.com/players/player.sd?player_id={id}'
    if row['url'] != url or registry.sha256_file(path) != row['sha256']:
        raise ValueError('original numeric source person changed')
    facts = august.player_profile(path.read_bytes(), fallback_name='', fallback_position='?')
    return facts, dict(path=registry.relative_workspace_path(path), sha256=row['sha256'],
        url=url, receipt_path=registry.relative_workspace_path(receipt), receipt_sha256=registry.sha256_file(receipt)), BeautifulSoup(path.read_bytes(), 'lxml').get_text(' ', strip=True)


def prepare(release):
    if release.season != '2017-18':
        raise ValueError('reviewed Boreham2017 admission only')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['carrier_id'] == CLUB)
    if club['name'] != 'Boreham Wood':
        raise ValueError('cannot rename or remap this club')
    path = registry.ROOT / '.local/season-2017-18/soccerbase-august-english-nonleague-v1.json'
    cap = next(c for c in pipeline.read_json_file(path)['clubs'] if c['source_path'] == 'soccerbase/team/364/august')
    actual = original.replay_club(release.season, cap, {}, True, allow_missing_birth_date=True)
    if actual['fixture']['date'] != '2017-08-05' or actual['fixture']['game_id'] != 753824:
        raise ValueError('original opening fixture changed')
    squad, squad_proof = source('opening-squad-numbers-2017-08-03.html', 'boreham-official-opening-squad-source-receipt-v1.json')
    loan, loan_proof = source('ryan-johnson-2017.html', 'primary-source-receipt-v1.json')
    report, report_proof = source('opener-2017-08-05.html', 'primary-source-receipt-v2.json')
    if not all(s in report for s in ('5 August 2017', 'Bruno Andrade had replaced Woodards', 'Woodards (Andrade 72')):
        raise ValueError('original club report does not explicitly identify the Andrade display surname')
    keeper, keeper_proof = source('erbil-bozkurt-2017.html', 'boreham-erbil-2017-original-source-receipt-v1.json')
    if not all(s in squad for s in ('3 August 2017', 'The full list can be seen below:', '12 Ryan Johnson', '1 Grant Smith (GK)', '2 Kane Smith', '11 Bruno Andrade')):
        raise ValueError('dated original squad numbers changed')
    if not all(s in squad for s in ('3 Danny Woodards', '15 Shaun Jeffers',
                                    '14 Bradley Ash', '21 Fred Burbidge (GK)')):
        raise ValueError('published retained aliases and preseason reserves changed')
    if not all(s in loan for s in ('14 July 2017', 'Ryan Johnson', 'Northern Ireland under-21', '20-year-old', 'Stevenage in 2013', 'long-term loan')):
        raise ValueError('primary young defender identity is unresolved')
    if not all(s in keeper for s in ('15 August 2017', 'Erbil Bozkurt', '27-year-old', 'beginning of pre-season')):
        raise ValueError('primary preseason reserve keeper identity unresolved')
    young, young_proof, young_text = profile(73680)
    erbil, erbil_proof, erbil_text = profile(87582)
    if young['name'] != 'Ryan Johnson' or young['birth_date'] != '1996-10-02' or 'Stevenage' not in young_text:
        raise ValueError('young numerical biography does not match primary history')
    if erbil['name'] != 'Erbil Bozkurt' or erbil['birth_date'] != '1990-04-04' or 'Boreham W 01 Jul, 17 01 Jun, 18' not in erbil_text:
        raise ValueError('preseason reserve keeper numeric career unresolved')
    desired = []
    for group in ('starting_xi', 'published_bench'):
        for row in actual['identity_bridges'][group]:
            bio = copy.deepcopy(row['soccerbase_person'])
            if group == 'published_bench' and bio['name'] == 'Ryan Johnson':
                if bio['provider_player_id'] != 100023 or bio['birth_date'] != '1987-01-15':
                    raise ValueError('reviewed wrong provider link changed')
                facts = copy.deepcopy(young); raw = young_proof
                bio.update(provider_player_id=73680, source_player_id='soccerbase:73680',
                    source_profile_url=young_proof['url'], birth_date='1996-10-02')
            else:
                facts, raw, _ = profile(bio['provider_player_id'])
            if facts['name'] != bio['name'] or facts['birth_date'] != bio['birth_date']:
                raise ValueError('literal numeric biography differs from opening identity')
            facts['position'] = row['dated_match_position']
            bio['source_provider'] = 'soccerbase'
            if bio['name'] == 'Bruno Andrade':
                # Both the primary report's full substitution name and its
                # same-event surname are explicit. This is NOT last-token
                # surname guessing or a provider-ID/name-only ownership bridge.
                bio.update(given_name='Bruno', family_name='Andrade',
                    native_component_authority=report_proof,
                    native_component_basis='primary-original-same-substitution-full-name-and-surname')
            desired.append(dict(source_person=bio, source_player=facts, membership=group,
                raw_evidence=dict(status='raw-source-reparsed', local_path=raw['path'], source_sha256=raw['sha256']),
                source_display_aliases=dict(policy=policy.POLICY,
                    source_provider_person_id=bio['source_player_id'], source_person_id=bio['source_player_id'],
                    birth_date=bio['birth_date'], names=[dict(field='dated-match-label', name=row['published_match_name'])])))
    players = [p for p in package['players'] if p['club_id'] == club['id']]
    if {p['carrier_id'] for p in players} != set(REPLACE) | set(KEEP.values()):
        raise ValueError('eighteen private carrier preimage changed')
    for p in players:
        expected = REPLACE.get(p['carrier_id']) or next(n for n, id in KEEP.items() if id == p['carrier_id'])
        if (p.get('source_name') or p['name']) != PREIMAGE_ALIASES.get(expected, expected):
            raise ValueError('current full identity preimage changed')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    from scripts import season_italian_opening_layer_v1 as linked
    from scripts import season_opening_order_repair_v1 as ownership
    owners = ownership.native_owners(eq)
    if set(linked.roster_rows(eq,CLUB)[2]) != {(p['carrier_id'],0) for p in players} or any(
            owners.get(p['carrier_id']) != {CLUB} for p in players):
        raise ValueError('exclusive native roster preimage changed')
    new = [p for p in desired if p['source_player']['name'] not in KEEP]
    if len(new) != 3:
        raise ValueError('three positive source identities required')
    for row in new:
        if any(p['club_id'] != club['id'] and (p['person_id'] == policy.person_id(row['source_person'])
                or p.get('source_name') == row['source_player']['name']) for p in package['players']):
            raise ValueError('another native club already owns a new source person')
    bundle = pipeline.read_json_file(core.CAPACITY_PROOF)['bindings']['same_carrier_name_capacity']
    capacity.verify_bundle(bundle)
    replacements = allocation.allocate(jug,[p for p in players if p['carrier_id'] in REPLACE],new,{},capacity_bundle=bundle)
    mapping = KEEP | {r['replacement']['source_player']['name']:r['carrier_id'] for r in replacements}
    entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    roles = []
    positions = {r['source_player']['name']:r['source_player']['position'] for r in desired}
    positions.update({'Bradley Ash': 'F', 'Fred Burbidge': 'G'})
    broad_updates = []
    birthdays = []
    desired_by_name = {r['source_player']['name']: r for r in desired}
    for name,id in KEEP.items():
        before = core.native(jug,entries,id)
        if before['position'] != positions[name]:
            if name != 'Angelo Balanta' or before['position'] != 'M' or positions[name] != 'F':
                raise ValueError('retained broad position needs explicit independent repair')
            broad_updates.append(dict(carrier_id=id, before='M', after='F', authority=desired_by_name[name]['source_person']))
        if name in desired_by_name:
            dob = desired_by_name[name]['source_player']['birth_date']
            if before['birth_date'] != dob:
                if name not in ('David Stephens', 'Bradley Sach'):
                    raise ValueError('unreviewed retained numerical birthday mismatch')
                birthdays.append(dict(carrier_id=id, native_name=before['name'], before_birth_date=before['birth_date'], birth_date=dob))
            elif name in PREIMAGE_ALIASES and next(p for p in players if p['carrier_id']==id)['facts']['birth_date'] != dob:
                raise ValueError('explicit retained spelling bridge birthday differs')
        target = {'G':0,'D':4,'M':9,'F':12}[positions[name]]
        after = [target] + [r for r in before['roles'][1:] if r not in (98,target)]
        after += [98]*(6-len(after))
        if after != before['roles']: roles.append(dict(carrier_id=id,before=before['roles'],after=after,
            policy='conservative broad-compatible editorial; secondary roles retained'))
    ordered = [mapping[r['source_player']['name']] for r in desired] + [10856,10860]
    return dict(schema=SCHEMA,season=release.season,release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), package_canonical_sha256=registry.canonical_document_sha256(release.package_path),
        jug_sha256=core.digest(jug),eq_sha256=core.digest(eq),club_id=club['id'],club_carrier_id=CLUB,
        capture_binding=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        original_opening=actual, supplemental_sources=[squad_proof,loan_proof,report_proof,keeper_proof,young_proof,erbil_proof],
        retained_players=[p for p in players if p['carrier_id'] in KEEP.values()],
        replacements=[dict(**r,kind='wrong-person-facts') for r in replacements],
        starting_xi=[dict(carrier_id=mapping[r['source_player']['name']],source=r['source_player'],source_person=r['source_person']) for r in desired[:11]],
        original_published_bench=[mapping[r['source_player']['name']] for r in desired[11:16]],
        orders=[dict(carrier_id=id,before=core.native(jug,entries,id)['startup_order'],after=n) for n,id in enumerate(ordered,1)],
        retained_primary_role_updates=roles,retained_broad_position_updates=broad_updates,
        birthday_updates=birthdays,retained_source_aliases=PREIMAGE_ALIASES,
        capacity_policy_bundle=bundle,fixed_duplicate_case_ids=[CASE],
        provider_link_adjudication='Original unused-bench older100023 contradicted by primary dated20-year-old Stevenage loanee plus unique opening #12; use numeric73680/1996-10-02. Not zero-appearance or name-only deduplication.',
        scope='Retained real Boreham3304: three private replacements restore young Ryan, Bruno and Frank. Original XI/five bench followed by primary dated preseason Ash/Burbidge. Two numeric birthdays and Balanta opening forward role repaired. Retained Dan/Danny and Shaun/Sean aliases require literal numeric birthdays and primary club list. False duplicate3329 retirement is a separate preceding transaction; this layer alone does not close the duplicate case. Stale portraits removed. Unknown reserve birthday remains declared. Managers/kits/opaque tactics/retained other facts and ratings not approved.',
        historical_verification_complete=False)


def verify(release,plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('reviewed primary-source opening decision does not reproduce')


def filename(plan):
    if plan.get('schema') != SCHEMA: raise ValueError('unsupported Boreham source layer')
    return FILENAME


def bind(package,plan, *, prefix=PREFIX, filename=FILENAME, retained=KEEP,
         aliases=PREIMAGE_ALIASES, source_date='2017-08-05',
         source_title='Boreham primary-source-priority opening people',
         proof_covers=None):
    if core.digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('recipe preimage changed')
    composition = dict(season=plan['season'],bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        updates=[dict(player_id=r['player_id'],carrier_id=r['carrier_id'],layer='main',before=r['before_recipe'],
            replacement=r['replacement'],replacement_opening_evidence=dict(date=source_date)) for r in plan['replacements']],
        source_title=source_title, proof_covers=(proof_covers if proof_covers is not None
            else ['three-source-positive-identities; not overall historical approval']))
    result=delta.updated_package(package,composition)
    artifact=next(a for a in result['artifacts'] if a['relative_path']==delta.plan_filename(composition))
    old=artifact['id'];aid=prefix+plan['season']
    artifact.update(id=aid,relative_path=filename,sha256=core.digest(packages.canonical_json_bytes(plan)))
    for player in result['players']:
        if player.get('proof',{}).get('artifact_id')==old:player['proof']['artifact_id']=aid
        for fallback in player.get('fact_fallbacks',[]):
            if fallback.get('proof',{}).get('artifact_id')==old:fallback['proof']['artifact_id']=aid
        role=next((r for r in plan['retained_primary_role_updates'] if r['carrier_id']==player['carrier_id']),None)
        if role:player['facts']['fine_roles']=[r for r in role['after'] if r!=98]
        birthday=next((r for r in plan['birthday_updates'] if r['carrier_id']==player['carrier_id']),None)
        if birthday:
            player['facts']['birth_date']=birthday['birth_date']
            player['proof']=dict(artifact_id=aid,grade='source-receipt')
            player['fact_fallbacks']=[f for f in player.get('fact_fallbacks',[]) if f['field']!='birth_date']
        broad=next((r for r in plan['retained_broad_position_updates'] if r['carrier_id']==player['carrier_id']),None)
        if broad:player['facts']['primary_position']=broad['after']
        if player['carrier_id'] in retained.values():
            name=next(n for n,id in retained.items() if id==player['carrier_id'])
            if name in aliases:
                player['source_name']=name
                player['proof']=dict(artifact_id=aid,grade='source-receipt')
    for row in plan['replacements']:
        next(p for p in result['players'] if p['id']==row['player_id'])['name']=row['display']['display_name']
    for collection in ('sources','proofs'):
        for row in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if row.get(key)==old:row[key]=aid
    for row in result['assets']['portraits']:
        if row.get('proof',{}).get('artifact_id')==old:row['proof']['artifact_id']=aid
    next(c for c in result['clubs'] if c['id']==plan['club_id'])['opening']['proof']=dict(artifact_id=aid,grade='source-receipt')
    result['artifacts'].sort(key=lambda r:r['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan, *, club=CLUB, replace=REPLACE, keep=KEEP, bind_recipe=bind):
    baseline=registry.load_registered_release(plan['season'],plan['release_id'])
    initial=(baseline.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if core.digest(initial)!=plan['jug_sha256'] or core.digest(eq)!=plan['eq_sha256']:
        raise ValueError('native source baseline changed')
    prepared=initial
    for row in plan['replacements']:
        if row.get('same_carrier_name_capacity'):
            prepared,claim=capacity.recover_slot(prepared,row['carrier_id'],plan['capacity_policy_bundle'])
            if claim!=row['same_carrier_name_capacity']:raise ValueError('capacity claim changed')
    package=bind_recipe(pipeline.read_json_file(baseline.package_path),plan)
    countries=delta.compiler._extract_country_codes_from_textos(baseline.game_path/'DBDAT/TEXTOS.PKF')
    changed={r['player_id'] for r in plan['replacements']} | {
        p['id'] for p in package['players'] if any(r['carrier_id']==p['carrier_id'] for r in plan['retained_broad_position_updates'])}
    candidate=delta.compile_players(prepared,package,changed,countries)
    candidate,_=rewrite_indexed_native_birth_dates(candidate,{r['carrier_id']:r for r in plan['birthday_updates']})
    candidate,_=rewrite_indexed_native_roles(candidate,{r['carrier_id']:[v for v in r['after'] if v!=98] for r in plan['retained_primary_role_updates']})
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    orders=[OrderReplacement(r['carrier_id'],read_initial_order(entries[r['carrier_id']].decode_payload(candidate)).name,r['before'],r['after']) for r in plan['orders']]
    candidate=patch_owned_mode1_complete_orders(candidate,eq,club_record_id=club,replacements=orders)
    preserve_other_records(initial,candidate,set(replace)|set(keep.values()))
    old_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(initial).entries}
    new_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    for carrier in keep.values():
        before=old_entries[carrier].decode_payload(initial)
        after=new_entries[carrier].decode_payload(candidate)
        end=core.roster.native_player(before,carrier)['name_end']
        allowed={end}
        if any(r['carrier_id']==carrier for r in plan['retained_primary_role_updates']):allowed.update(range(end+2,end+8))
        if any(r['carrier_id']==carrier for r in plan['birthday_updates']):allowed.update(range(end+12,end+16))
        if any(r['carrier_id']==carrier for r in plan['retained_broad_position_updates']):allowed.update((end+10,end+11))
        if len(before)!=len(after) or any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(before,after))):
            raise ValueError('retained Boreham player changed outside declared controls, roles or sourced date')
    if jug not in (initial,candidate):raise ValueError('only complete native preimage/postimage accepted')
    return candidate,eq


def reconstruction(previous,release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    if path.resolve()!=(previous.package_path.parent/filename(plan)).resolve():raise ValueError('source locator differs')
    package=pipeline.read_json_file(previous.package_path)
    artifact=[a for a in package['artifacts'] if a['id']==PREFIX+previous.season]
    if len(artifact)!=1 or artifact[0]['relative_path']!=FILENAME or registry.sha256_file(path)!=artifact[0]['sha256']:raise ValueError('source artifact changed')
    baseline=registry.load_registered_release(previous.season,plan['release_id']);verify(baseline,plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path),plan))!=packages.canonical_json_bytes(package):raise ValueError('edited recipe cannot use exact reconstruction; edits not discarded')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected=dict(season=previous.season,release_id=baseline.release_id,package_sha256=registry.sha256_file(baseline.package_path),jug_sha256=registry.sha256_file(baseline.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor)!=expected:raise ValueError('replay descriptor differs')
    for release in (baseline,previous):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,profile_assignment_plan_path=path,source_release_id=baseline.release_id)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path))!=packages.canonical_json_bytes(package):raise ValueError('exact recipe replay differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True,reused=False,compilation_mode='source-bound-Boreham-in-place-opening-reconstruction-not-factory-compile')


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Boreham source repair requires exact source-bound reconstruction')
