"""Restore four original Barrow2012 substitutes within its authored squad.

The original first XI proves the wrongly labelled carrier's identity. This
layer preserves that label/manager until a separate dated correction; it never
uses a successful deduplication as overall historical approval. Already present
Flynn/Harvey reserves are retained, with opening ownership explicitly unapproved.
"""
import copy

from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_boreham_opening_repair_v1 as native
from scripts import season_stevenage_opening_repair_v1 as core
from scripts import season_historical_club_label_review_v1 as labels
from scripts import season_published_person_identity_v1 as public
from scripts import replay_original_soccerbase_openings_v1 as original
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
from scripts import capture_soccerbase_august_squads_v1 as provider
from scripts import season_package_v2 as packages
from scripts import season_published_family_component_v1 as families

SCHEMA = 'pm99-reviewed-Barrow-2012-original-opening-in-place-repair-v1'
PREFIX = 'sourced-barrow-opening-'
FILENAME = 'sourced-barrow-opening.json'
CASE = 'f8d528a3678e9b298ac1533d78693201f5d62e094df464a87dfb9791ffc59af7'
CLUB = 3325
REPLACE = {11225: 'Danny Rowe', 11226: 'Adam Dawson', 11228: 'Sam Hibbert', 26960: 'Steve Williams'}
KEEP = {'Danny Hurst':11211, '#26 Tom Anderson':11212, 'Sean Hessey':11213,
    'Mike Pearson':11214, 'James Owen':11215, 'Gavin Skelton':11216,
    'Garry Hunter':11217, 'Danny Rowe':11218, 'Paul Rutherford':11219,
    'Adam Boyes':11221, 'Joe Jackson':11222, 'Matthew Flynn':11223,
    'Richie Baker':11224, 'Alex-Ray Harvey':11227}
BENCH_IDS = {'Shaun Pearson':176322, 'Aaron Cole':209501,
    'Obi Anoruo':104684, 'Vinny Mukendi':106835}
BASE = registry.ROOT / '.local/consolidated-audit-20261009'


def authored_opening(release, package, players):
    audit = pipeline.read_json_file(BASE / 'barrow-2012-source-label-review/2012-13/club-label-review.json')
    b = audit['bindings']; path = registry.ROOT / b['source_row_path']
    aid = 'opening-squad-preallocation-' + release.season
    descriptor = [a for a in package['artifacts'] if a['id'] == aid]
    if len(descriptor) != 1 or descriptor[0]['sha256'] != registry.sha256_file(path):
        raise ValueError('original authored source artifact changed')
    pre = pipeline.read_json_file(path); index, sources = labels.indexed_claims(pre)
    club = next(c for c in package['clubs'] if c['carrier_id'] == CLUB)
    source, reason = labels.unanimous_claim(club, players, aid, index, sources)
    if reason or source['selector']['club_name'] != 'Barrow':
        raise ValueError('complete original authored XI does not identify Barrow')
    capture_path = registry.ROOT / b['original_capture_path']
    if registry.sha256_file(capture_path) != pre['sources']['opening_lineup_sha256']:
        raise ValueError('original first-fixture capture changed')
    capture = pipeline.read_json_file(capture_path)
    matches = [c for c in capture['clubs'] if labels.selector_key(c['source_selector'])[:3]
        == labels.selector_key(source['selector'])[:3]]
    if len(matches) != 1:
        raise ValueError('one exact original Barrow fixture required')
    proof = labels.opening.verify_opening(matches[0], capture, capture_path.parent / 'cache')
    ids = {str(p['opening_source_player_id']) for p in source['players']
        if isinstance(p.get('opening_xi_order'), int)}
    if (proof['date'] != '2012-08-11' or proof['source_club_id'] != 6168
            or ids != set(proof['starting_xi']) or proof['manager'] != 'David Bayliss'):
        raise ValueError('original Barrow date, club, XI or manager differs')
    return source, matches[0], proof


def prepare(release):
    if release.season != '2012-13':
        raise ValueError('reviewed Barrow2012 admission only')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['carrier_id'] == CLUB)
    if club['name'] != 'Aldershot Town':
        raise ValueError('unreviewed retained club label preimage')
    players = [p for p in package['players'] if p['club_id'] == club['id']]
    if {p['carrier_id'] for p in players} != set(REPLACE) | set(KEEP.values()):
        raise ValueError('eighteen private roster slots changed')
    for p in players:
        expected = REPLACE.get(p['carrier_id']) or next(n for n, id in KEEP.items() if id == p['carrier_id'])
        if (p.get('source_name') or p['name']) != expected:
            raise ValueError('private identity preimage changed')
    source, capture, proof = authored_opening(release, package, players)
    cap_path = registry.ROOT / '.local/season-2012-13/soccerbase-august-english-nonleague-v1.json'
    cap = next(c for c in pipeline.read_json_file(cap_path)['clubs'] if c['source_path'] == 'soccerbase/team/392/august')
    actual = original.replay_club(release.season, cap, {}, True, allow_missing_birth_date=True)
    if actual['fixture']['date'] != proof['date'] or actual['fixture']['game_id'] != 657949:
        raise ValueError('independent provider does not confirm the same first fixture')
    public_path = registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json'
    people, _ = public.merge({}, pipeline.read_json_file(public_path))
    by_id = {p['source_player_id']:p for rows in people.values() for p in rows.values()}
    desired = []
    for name, id in BENCH_IDS.items():
        # Positive same-fixture numeric IDs + exact full biography; no
        # absence-based ownership, name-only join or annual membership guess.
        if str(id) not in proof['substitutes'] or proof['substitutes'][str(id)] != name:
            raise ValueError('original numeric Barrow substitute changed')
        matches = [r for r in actual['identity_bridges']['published_bench']
            if r['soccerbase_person']['name'] == name]
        if len(matches) != 1 or by_id[id]['name'] != name:
            raise ValueError('independent full substitute name is ambiguous')
        row = matches[0]; bio = row['soccerbase_person']; person = by_id[id]
        if bio['birth_date'] not in (None, person['birth_date']):
            raise ValueError('original substitute biographies contradict each other')
        if bio['birth_date'] is None and name != 'Aaron Cole':
            raise ValueError('unreviewed missing provider birthday')
        raw = next(r for r in actual['raw_sources'] if r['url'] == bio['source_profile_url'])
        facts = provider.player_profile((registry.ROOT / raw['path']).read_bytes(),
            fallback_name='', fallback_position='?')
        facts.update(name=name, birth_date=person['birth_date'], position=row['dated_match_position'])
        if facts['position'] not in ('G','D','M','F'):
            raise ValueError('original substitute broad role unresolved')
        desired.append(dict(source_person=copy.deepcopy(person), source_player=facts,
            membership='published_bench', raw_evidence=dict(status='raw-source-reparsed',
                local_path=raw['path'], source_sha256=raw['sha256']),
            source_display_aliases=dict(policy=policy.POLICY,
                source_provider_person_id=bio['source_player_id'], source_person_id=person['source_player_id'],
                birth_date=person['birth_date'], names=[dict(field='dated-match-label', name=row['published_match_name'])]),
            source_identity_basis='two-original-same-first-fixture-substitute-IDs-and-public-confirmed-DOB; Aaron original unknown DOB retained in evidence'))
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    from scripts import season_italian_opening_layer_v1 as linked, season_opening_order_repair_v1 as ownership
    if set(linked.roster_rows(eq, CLUB)[2]) != {(p['carrier_id'],0) for p in players}:
        raise ValueError('native retained roster preimage changed')
    owners = ownership.native_owners(eq)
    if any(owners.get(p['carrier_id']) != {CLUB} for p in players):
        raise ValueError('retained native player is not exclusively owned')
    for row in desired:
        if any(p['club_id'] != club['id'] and (p['person_id'] == policy.person_id(row['source_person'])
                or (p.get('source_name'), p['facts'].get('birth_date'))
                    == (row['source_player']['name'], row['source_player']['birth_date']))
                for p in package['players']):
            raise ValueError('another native club owns a new substitute')
    bundle = pipeline.read_json_file(core.CAPACITY_PROOF)['bindings']['same_carrier_name_capacity']
    capacity.verify_bundle(bundle)
    replacements = allocation.allocate(jug, [p for p in players if p['carrier_id'] in REPLACE],
        desired, {}, capacity_bundle=bundle,
        published_families=families.claims(public_path, set(BENCH_IDS.values())))
    mapping = KEEP | {r['replacement']['source_player']['name']:r['carrier_id'] for r in replacements}
    starters = sorted((p for p in source['players'] if isinstance(p.get('opening_xi_order'),int)),
        key=lambda p:p['opening_xi_order'])
    ordered = [mapping[p['facts']['name']] for p in starters]
    ordered += [mapping[p['display_name']] for p in capture['substitutes']]
    ordered += [KEEP['Matthew Flynn'], KEEP['Alex-Ray Harvey']]
    if len(ordered) != 18 or len(set(ordered)) != 18:
        raise ValueError('complete original XI/bench ordering is not unique')
    entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    retained = [p for p in players if p['carrier_id'] in KEEP.values()]
    positions = {p['facts']['name']:p['facts']['position'] for p in starters}
    positions.update({'Richie Baker':'M', 'Matthew Flynn':'D', 'Alex-Ray Harvey':'M'})
    skelton = [r for r in actual['identity_bridges']['starting_xi']
        if r['soccerbase_person']['name'] == 'Gavin Skelton']
    if (len(skelton) != 1 or skelton[0]['soccerbase_person']['birth_date'] != '1981-03-27'
            or skelton[0]['dated_match_position'] != 'M'):
        raise ValueError('Skelton opening midfield role lacks the original dated biography')
    positions['Gavin Skelton'] = 'M'
    roles = []; broad = []
    for name, id in KEEP.items():
        before = core.native(jug,entries,id)
        if before['position'] != positions[name]:
            if name != 'Gavin Skelton' or before['position'] != 'D' or positions[name] != 'M':
                raise ValueError('unreviewed retained broad position mismatch')
            independent = next(r for r in actual['identity_bridges']['starting_xi']
                if r['soccerbase_person']['name'] == name)
            if independent['dated_match_position'] != 'M':
                raise ValueError('Skelton midfield role lacks original dated confirmation')
            broad.append(dict(carrier_id=id,before='D',after='M',authority=independent))
        target = {'G':0,'D':4,'M':9,'F':12}[positions[name]]
        after = [target] + [r for r in before['roles'][1:] if r not in (98,target)]
        after += [98] * (6-len(after))
        if after != before['roles']:
            roles.append(dict(carrier_id=id,before=before['roles'],after=after,
                policy='conservative broad-compatible editorial; secondary roles retained'))
    return dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=registry.canonical_document_sha256(release.package_path),
        jug_sha256=core.digest(jug), eq_sha256=core.digest(eq), club_id=club['id'], club_carrier_id=CLUB,
        source_authoring_opening=proof, original_opening=actual,
        capture_binding=dict(path=registry.relative_workspace_path(cap_path),sha256=registry.sha256_file(cap_path)),
        published_person_binding=dict(path=registry.relative_workspace_path(public_path),sha256=registry.sha256_file(public_path)),
        retained_players=retained, replacements=[dict(**r,kind='wrong-person-facts') for r in replacements],
        starting_xi=[dict(carrier_id=mapping[p['facts']['name']],source=p['facts']) for p in starters],
        original_published_bench=ordered[11:16],
        orders=[dict(carrier_id=id,before=core.native(jug,entries,id)['startup_order'],after=n)
            for n,id in enumerate(ordered,1)], retained_primary_role_updates=roles,
        retained_broad_position_updates=broad,birthday_updates=[],retained_source_aliases={},
        capacity_policy_bundle=bundle, fixed_duplicate_case_ids=[CASE],
        remaining=['Retained wrong club label and manager require the following independent correction.',
            'Existing Flynn/Harvey reserve ownership not historically approved.',
            'Existing authored #26 Tom Anderson source/native name formatting needs a separate name-only repair.',
            'Joe Jackson dated-provider defender versus authored forward conflict logged; forward unchanged.',
            'Retained facts, kits, portraits and opaque deployment not globally approved.'],
        scope='Four missing original Barrow substitutes replace late/stock slots, including older late-season Rowe. Complete original XI/five bench order restored; Skelton midfield role repaired. Four stale portraits cleared. All unrelated native records and retained skills/facts unchanged.',
        historical_verification_complete=False)


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('original Barrow opening proof does not reproduce')


def filename(plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('unsupported Barrow source layer')
    return FILENAME


def bind(package, plan):
    return native.bind(package, plan, prefix=PREFIX, filename=FILENAME, retained=KEEP, aliases={},
        source_date='2012-08-11', source_title='Original Barrow2012 opening substitutes',
        proof_covers=['four-positive-original-substitute-identities; not overall historical approval'])


def apply(jug, eq, plan):
    return native.apply(jug,eq,plan,club=CLUB,replace=REPLACE,keep=KEEP,bind_recipe=bind)


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Barrow source repair requires exact source-bound reconstruction')


def reconstruction(previous, release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('Barrow source locator differs')
    package = pipeline.read_json_file(previous.package_path)
    artifacts = [a for a in package['artifacts'] if a['id'] == PREFIX + previous.season]
    if (len(artifacts) != 1 or artifacts[0]['relative_path'] != FILENAME
            or registry.sha256_file(path) != artifacts[0]['sha256']):
        raise ValueError('Barrow source artifact changed')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path),plan)) != packages.canonical_json_bytes(package):
        raise ValueError('edited Barrow recipe cannot use exact reconstruction; edits not discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('Barrow replay descriptor differs')
    for release in (baseline,previous):
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,
        profile_assignment_plan_path=path,source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(package):
        raise ValueError('exact Barrow recipe replay differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,reused=False,
        compilation_mode='source-bound-Barrow-in-place-opening-reconstruction-not-factory-compile')
