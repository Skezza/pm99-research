"""One source-replayed Stevenage opening repair, not a roster-swap loophole.

Keep ten existing identities. Replace only eight late-season carryovers using
the original numeric opening sheet; never inherit their photographs. The
original eleven and five bench players precede two existing August reserves.
Managers, tactics, kits and unrelated records are separate work, not approved.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders, read_initial_order
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import replay_original_soccerbase_openings_v1 as original
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import capture_soccerbase_august_squads_v1 as august
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-reviewed-Stevenage-2002-original-opening-in-place-repair-v1'
PREFIX = 'sourced-stevenage-opening-'
FILENAME = 'sourced-stevenage-opening.json'
ROOT = registry.ROOT / '.local/consolidated-audit-20261009/primary-club-history-followup/stevenage'
REPLACE = {10925: 'Ross Lafayette', 10926: 'Jack Midson', 10927: 'Lewis Noice',
           10928: 'Ben Strevens', 10929: 'Jack Alexander', 10930: 'Tony Lee',
           10931: 'Lee Cook', 18064: 'Andy Drury'}
KEEP = {'Scott Houghton': 10913, 'Matt Fisher': 10915, 'Jamie Campbell': 10916,
        'Kirk Jackson': 10917, 'Phil Wilson': 10918, 'DJ Campbell': 10919,
        'Graeme Tomlinson': 10920, 'Stuart Fraser': 10921,
        'Jack Midson': 10922, 'Robin Trott': 10923}
CAPACITY_PROOF = registry.ROOT / '.local/historical-role-deltas-v1/2016-17/opening-same-carrier-capacity-repairs-20261006-r39a/ownership-plan-027efd0f02a8.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def supplemental(key):
    """Read one URL/hash-bound cache entry, not an unverified HTML filename."""
    receipts = ('stevenage-2002-source-person-profiles-receipt-v1.json',
                'stevenage-secondary-facts-original-receipt-v1.json')
    matches = []
    for name in receipts:
        path = ROOT.parent / name
        doc = pipeline.read_json_file(path)
        rows = doc.get('cache_files', doc.get('sources', []))
        if isinstance(rows, dict):
            rows = list(rows.values())
        for row in rows:
            if row.get('cache_path') == 'stevenage/' + key:
                matches.append((row, path))
    if len(matches) != 1:
        raise ValueError('one original supplemental URL/SHA receipt required: ' + key)
    row, receipt = matches[0]
    path = ROOT / key
    if registry.sha256_file(path) != row['sha256']:
        raise ValueError('supplemental historical source changed')
    return BeautifulSoup(path.read_bytes(), 'lxml'), dict(path=registry.relative_workspace_path(path),
        sha256=row['sha256'], url=row['url'], receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt))


def secondary_dates():
    oxford, a = supplemental('phil-wilson-oxford-history.html')
    rows = [[c.get_text(' ', strip=True) for c in r.find_all(['th', 'td'], recursive=False)]
            for r in oxford.select('table tr')]
    if [r[1] for r in rows if r and r[0] == 'Phil Wilson'] != ['17/10/1982']:
        raise ValueError('official Oxford player table lacks the literal Wilson birthday')
    luton, b = supplemental('stuart-fraser-luton-history.html')
    text = luton.get_text(' ', strip=True)
    if not all(s in text for s in ('Stuart Thomas Fraser', 'Born: 9th January 1980',
                                   'moving to Stevenage')):
        raise ValueError('Luton primary biography does not identify the Stevenage Fraser')
    wiki, c = supplemental('jamie-campbell-wikipedia.html')
    boxes = wiki.select('table.infobox')
    if (len(boxes) != 1 or [x.get_text(strip=True) for x in boxes[0].select('.bday')] != ['1972-10-21']
            or '2002–2003 Stevenage Borough' not in boxes[0].get_text(' ', strip=True)):
        raise ValueError('Campbell biography lacks exact birthday and Stevenage career')
    return {'Phil Wilson': '1982-10-17', 'Stuart Fraser': '1980-01-09',
            'Jamie Campbell': '1972-10-21'}, [a, b, c]


def primary_role(name, expected):
    page, proof = supplemental(name.lower().replace(' ', '-') + '.html')
    text = page.get_text(' ', strip=True)
    if ('Factfile Position ' + expected + ' Years') not in text or name not in text:
        raise ValueError('club history does not identify its published historical role')
    if not proof['url'].startswith('https://www.boroguide.co.uk/players/'):
        raise ValueError('wrong historical club biography authority')
    return proof


def native(data, entries, carrier):
    raw = entries[carrier].decode_payload(data)
    parsed = roster.native_player(raw, carrier)
    end = parsed['name_end']
    born = date(int.from_bytes(bytes(b ^ 0x61 for b in raw[end+14:end+16]), 'little'),
                raw[end+13] ^ 0x61, raw[end+12] ^ 0x61).isoformat()
    return dict(name=parsed['name'], birth_date=born, position=parsed['position'],
                startup_order=raw[end] ^ 0x61, roles=parsed['roles'])


def prepare(release):
    if release.season != '2002-03':
        raise ValueError('this reviewed source admission is Stevenage 2002 only')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['carrier_id'] == 3308)
    if club['name'] != 'Stevenage':
        raise ValueError('in-place repair must not rename or remap a club')
    capture_path = registry.ROOT / '.local/season-2002-03/soccerbase-august-english-nonleague-v1.json'
    captures = pipeline.read_json_file(capture_path)
    selected = [c for c in captures['clubs'] if c['source_path'] == 'soccerbase/team/2499/august']
    if len(selected) != 1 or selected[0]['club_name'] != 'Stevenage':
        raise ValueError('one original target-season Stevenage capture required')
    cap = selected[0]
    actual = original.replay_club(release.season, cap, {}, True, allow_missing_birth_date=True)
    if actual['fixture']['date'] != '2002-08-17' or actual['fixture']['game_id'] != 365997:
        raise ValueError('original opening fixture changed')
    dates, proofs = secondary_dates()
    # Numeric source profile + dated match membership, not names alone.
    desired = []
    for group in ('starting_xi', 'published_bench'):
        for row in actual['identity_bridges'][group]:
            bio = copy.deepcopy(row['soccerbase_person'])
            name = bio['name']; birthday = bio['birth_date'] or dates.get(name)
            if not birthday:
                raise ValueError('unresolved identity birthday in this reviewed opening')
            annual = [p for p in cap['players'] if p['name'] == name]
            if len(annual) != 1 or annual[0]['birth_date'] not in (None, birthday):
                raise ValueError('original capture biography disagrees with numeric profile')
            raw = next(s for s in actual['raw_sources'] if s['url'] == bio['source_profile_url'])
            parsed_facts = august.player_profile((registry.ROOT / raw['path']).read_bytes(),
                fallback_name=row['published_match_name'], fallback_position=row['dated_match_position'])
            if parsed_facts != annual[0]:
                raise ValueError('original profile does not reproduce captured secondary facts')
            facts = copy.deepcopy(parsed_facts); facts['birth_date'] = birthday
            role = row['dated_match_position']
            if name == 'Stuart Fraser':
                proofs.append(primary_role(name, 'Defence')); role = 'D'
            # A historical full-back can be deployed in midfield. Keep the
            # original match's M for Travis; do not claim a sourced formation.
            if role not in ('G', 'D', 'M', 'F'):
                raise ValueError('unresolved original broad role')
            facts['position'] = role
            bio.update(birth_date=birthday, source_provider='soccerbase')
            desired.append(dict(source_person=bio, source_player=facts, membership=group,
                raw_evidence=dict(status='raw-source-reparsed', local_path=raw['path'], source_sha256=raw['sha256']),
                source_display_aliases=dict(policy=soccerbase.POLICY, source_provider_person_id=bio['source_player_id'],
                    source_person_id=bio['source_player_id'], birth_date=birthday,
                    names=[dict(field='dated-match-label', name=row['published_match_name'])])))
    if len(desired) != 16 or len({p['source_person']['source_player_id'] for p in desired}) != 16:
        raise ValueError('complete original XI and published five-player bench required')
    players = [p for p in package['players'] if p['club_id'] == club['id']]
    if {p['carrier_id'] for p in players} != set(REPLACE) | set(KEEP.values()):
        raise ValueError('reviewed private eighteen-slot roster changed')
    for p in players:
        expected = REPLACE.get(p['carrier_id']) or next(k for k, v in KEEP.items() if v == p['carrier_id'])
        if (p.get('source_name') or p['name']) != expected:
            raise ValueError('displaced or retained current full identity changed')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    from scripts import season_italian_opening_layer_v1 as linked
    from scripts import season_opening_order_repair_v1 as ownership
    owners = ownership.native_owners(eq)
    rows = linked.roster_rows(eq, 3308)[2]
    if set(rows) != {(p['carrier_id'], 0) for p in players} or len(rows) != 18:
        raise ValueError('visible native eighteen-slot roster differs')
    if any(owners.get(p['carrier_id']) != {3308} for p in players):
        raise ValueError('shared native person prevents this exclusive-club repair')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    new_people = [p for p in desired if p['source_player']['name'] not in KEEP]
    if len(new_people) != 8:
        raise ValueError('exact eight positive original missing people required')
    for replacement in new_people:
        name = roster.normalise(replacement['source_player']['name'])
        person_id = soccerbase.person_id(replacement['source_person'])
        if any(p['club_id'] != club['id'] and (p['person_id'] == person_id
                or roster.normalise(p.get('source_name') or p['name']) == name) for p in package['players']):
            raise ValueError('another-club identity prevents this in-place admission')
    bundle = pipeline.read_json_file(CAPACITY_PROOF)['bindings']['same_carrier_name_capacity']
    capacity.verify_bundle(bundle)
    replacements = allocation.allocate(jug, [p for p in players if p['carrier_id'] in REPLACE], new_people, {},
                                       capacity_bundle=bundle)
    mapping = {r['replacement']['source_player']['name']: r['carrier_id'] for r in replacements} | KEEP
    if len(set(mapping.values())) != 18:
        raise ValueError('source assignment repeats a native person')
    # Retain these already assigned August people, never pretend they were on
    # the first-match bench. Original career interval and club-history August
    # appearance remain additional ownership evidence, not fixture selection.
    for name in ('Jack Midson', 'Robin Trott'):
        proofs.append(primary_role(name, 'Forward' if name == 'Jack Midson' else 'Defence'))
        p = next(p for p in players if p['carrier_id'] == KEEP[name])
        source = next(a for a in cap['players'] if a['name'] == name)
        if p['facts']['birth_date'] != source['birth_date']:
            raise ValueError('retained August reserve literal identity differs')
    ordered = [mapping[r['source_player']['name']] for r in desired] + [10922, 10923]
    orders = [dict(carrier_id=id, before=native(jug, entries, id)['startup_order'], after=n)
              for n, id in enumerate(ordered, 1)]
    date_updates = []
    for name in ('Phil Wilson', 'Stuart Fraser', 'Jamie Campbell'):
        id = KEEP[name]; before = native(jug, entries, id)
        if before['birth_date'] != dates[name]:
            date_updates.append(dict(carrier_id=id, native_name=before['name'],
                before_birth_date=before['birth_date'], birth_date=dates[name]))
    primary_roles = []
    positions = {r['source_player']['name']: r['source_player']['position'] for r in desired}
    positions.update({'Jack Midson': 'F', 'Robin Trott': 'D'})
    for name, id in KEEP.items():
        before = native(jug, entries, id)
        if before['position'] != positions[name]:
            raise ValueError('retained broad position needs a separately sourced core repair')
        target = 2 if name == 'Stuart Fraser' else {'G': 0, 'D': 4, 'M': 9, 'F': 12}[positions[name]]
        after = [target] + [r for r in before['roles'][1:] if r != 98 and r != target]
        after += [98] * (6-len(after))
        if before['roles'] != after:
            primary_roles.append(dict(carrier_id=id, before=before['roles'], after=after,
                policy='conservative-source-broad-compatible-editorial-primary; other-secondary-roles-preserved'))
    return dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=registry.canonical_document_sha256(release.package_path),
        jug_sha256=digest(jug), eq_sha256=digest(eq), club_id=club['id'], club_carrier_id=3308,
        capture_binding=dict(path=registry.relative_workspace_path(capture_path), sha256=registry.sha256_file(capture_path)),
        original_opening=actual, supplemental_sources=proofs, before_club=club,
        retained_players=[p for p in players if p['carrier_id'] in KEEP.values()],
        replacements=[dict(**r, kind='wrong-person-facts') for r in replacements],
        starting_xi=[dict(carrier_id=mapping[r['source_player']['name']], source=r['source_player'],
                         source_person=r['source_person']) for r in desired[:11]],
        original_published_bench=[mapping[r['source_player']['name']] for r in desired[11:]],
        orders=orders, birthday_updates=date_updates,
        retained_primary_role_updates=primary_roles,
        capacity_policy_bundle=bundle,
        scope='Eight wrong legacy identities replaced using original numeric match people; ten existing identities retained. Original XI/bench, exclusive complete startup orders, three independent secondary-date authorities, and conservative broad-compatible editorial roles. Displaced photographs removed. Managers, kits, opaque tactics, unrelated records and existing retained-player skills are NOT approved.',
        historical_verification_complete=False)


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('original Stevenage opening source decision does not reproduce')


def updated_package(package, plan):
    if digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('Stevenage recipe preimage changed')
    updates = [dict(player_id=r['player_id'], carrier_id=r['carrier_id'], layer='main',
        before=r['before_recipe'], replacement=r['replacement'],
        replacement_opening_evidence=dict(date='2002-08-17')) for r in plan['replacements']]
    composition = dict(season=plan['season'], bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        updates=updates, source_title='Original Stevenage opening match people replacing later-season inherited identities',
        proof_covers=['eight-original-numeric-opening-people; NOT managers or exact tactical deployment'])
    result = delta.updated_package(package, composition)
    # Use the one source-replayed public layer; no unbound second plan artifact.
    aid = PREFIX + plan['season']
    generated = next(a for a in result['artifacts'] if a['relative_path'] == delta.plan_filename(composition))
    old_aid = generated['id']; generated.update(id=aid, relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)))
    dates = secondary_dates()[0]
    for player in result['players']:
        if player.get('proof', {}).get('artifact_id') == old_aid:
            player['proof']['artifact_id'] = aid
        for fallback in player.get('fact_fallbacks', []):
            if fallback.get('proof', {}).get('artifact_id') == old_aid:
                fallback['proof']['artifact_id'] = aid
        if player['carrier_id'] in KEEP.values():
            name = next(k for k, v in KEEP.items() if v == player['carrier_id'])
            if name in ('Phil Wilson', 'Stuart Fraser', 'Jamie Campbell'):
                player['facts']['birth_date'] = dates[name]
                player['proof'] = dict(artifact_id=aid, grade='source-receipt')
                player['fact_fallbacks'] = [r for r in player.get('fact_fallbacks', []) if r['field'] != 'birth_date']
            if name == 'Stuart Fraser':
                player['facts']['primary_position'] = 'D'
            role = next((r for r in plan['retained_primary_role_updates'] if r['carrier_id'] == player['carrier_id']), None)
            if role:
                player['facts']['fine_roles'] = [r for r in role['after'] if r != 98]
    for row in plan['replacements']:
        next(p for p in result['players'] if p['id'] == row['player_id'])['name'] = row['display']['display_name']
    for collection in ('sources', 'proofs'):
        for row in result[collection]:
            for key in ('artifact_id', 'evidence_artifact_id'):
                if row.get(key) == old_aid: row[key] = aid
    for row in result['assets']['portraits']:
        if row.get('proof', {}).get('artifact_id') == old_aid: row['proof']['artifact_id'] = aid
    target = next(c for c in result['clubs'] if c['id'] == plan['club_id'])
    target['opening']['proof'] = dict(artifact_id=aid, grade='source-receipt')
    result['artifacts'].sort(key=lambda r: r['id'])
    packages.validate_package(result)
    return result


def compile_native(jug, eq, package, country_codes, plan):
    baseline = registry.load_registered_release(plan['season'], plan['release_id'])
    original_jug = (baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if digest(original_jug) != plan['jug_sha256'] or digest(eq) != plan['eq_sha256']:
        raise ValueError('Stevenage native baseline changed')
    selected = {r['player_id'] for r in plan['replacements']}
    prepared = original_jug
    for row in plan['replacements']:
        if row.get('same_carrier_name_capacity'):
            prepared, claim = capacity.recover_slot(prepared, row['carrier_id'], plan['capacity_policy_bundle'])
            if claim != row['same_carrier_name_capacity']:
                raise ValueError('same-carrier original name-window recovery differs')
    candidate = delta.compile_players(prepared, package, selected, country_codes)
    candidate, _ = rewrite_indexed_native_birth_dates(candidate, {r['carrier_id']: r for r in plan['birthday_updates']})
    candidate, _ = rewrite_indexed_native_roles(candidate,
        {r['carrier_id']: [code for code in r['after'] if code != 98] for r in plan['retained_primary_role_updates']})
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(candidate).entries}
    orders = [OrderReplacement(r['carrier_id'], read_initial_order(entries[r['carrier_id']].decode_payload(candidate)).name,
                r['before'], r['after']) for r in plan['orders']]
    candidate = patch_owned_mode1_complete_orders(candidate, eq, club_record_id=3308, replacements=orders)
    preserve_other_records(original_jug, candidate, set(REPLACE) | set(KEEP.values()))
    if jug not in (original_jug, candidate):
        raise ValueError('Stevenage accepts only its exact complete preimage or postimage')
    return candidate


def filename(plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('unsupported Stevenage source layer')
    return FILENAME


def bind(package, plan):
    return updated_package(package, plan)


def apply(jug, eq, plan):
    baseline = registry.load_registered_release(plan['season'], plan['release_id'])
    package = updated_package(pipeline.read_json_file(baseline.package_path), plan)
    countries = delta.compiler._extract_country_codes_from_textos(baseline.game_path / 'DBDAT/TEXTOS.PKF')
    return compile_native(jug, eq, package, countries, plan), eq


def reconstruction(previous, release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('Stevenage replay locator differs from its exact current source layer')
    package = pipeline.read_json_file(previous.package_path)
    artifacts = [a for a in package['artifacts'] if a['id'] == PREFIX + previous.season]
    if len(artifacts) != 1 or artifacts[0]['relative_path'] != FILENAME or registry.sha256_file(path) != artifacts[0]['sha256']:
        raise ValueError('Stevenage replay requires one exact source artifact')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path), plan)) != packages.canonical_json_bytes(package):
        raise ValueError('edited recipe cannot use exact Stevenage reconstruction; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('Stevenage replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(package):
        raise ValueError('Stevenage exact replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-Stevenage-in-place-opening-reconstruction-not-factory-compile')


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('Stevenage source repair requires exact source-bound reconstruction')
