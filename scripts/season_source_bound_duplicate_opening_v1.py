"""Remove a proved starter duplicate while restoring its sourced complete XI.

Source identities come from the exact original allocation, numeric match IDs
and independently cached profiles. Other reserves stay in their existing order;
they are not relabelled as the original match bench. Only startup/primary-role
bytes and the duplicate roster link change. One redundant promoted secondary
role may be cleared; all other secondary roles remain. Birthdays/skills stay queued.
"""
import copy
import hashlib
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_primary_roles, rewrite_indexed_native_roles
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders
from scripts import review_profile_addition_duplicate_assignments_v1 as source
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-source-bound-duplicate-starter-complete-opening-primary-roles-v1'
PREFIX = 'sourced-duplicate-opening-'
FILENAME = 'sourced-duplicate-opening.json'
ROLE_MAP = {'Goalkeeper': ('G', 0), 'Right-Back': ('D', 1),
    'Left-Back': ('D', 2), 'Centre-Back': ('D', 4),
    'Defensive Midfield': ('M', 14), 'Central Midfield': ('M', 9),
    'Attacking Midfield': ('M', 9), 'Right Midfield': ('M', 6),
    'Left Midfield': ('M', 10), 'Right Winger': ('M', 11),
    'Left Winger': ('M', 13), 'Centre-Forward': ('F', 8)}


def filename(plan):
    return 'sourced-duplicate-opening-' + plan['layer_suffix'] + '.json' if plan.get('layer_suffix') else FILENAME


def digest(data):
    return hashlib.sha256(data).hexdigest()


def removed_carriers(review):
    from scripts import review_factory_fallthrough_duplicate_v1 as factory
    extra = review.get('additional_shared_membership_retirements', [])
    if (extra or review.get('shared_removed_membership')) and review.get('schema') != factory.SCHEMA:
        raise ValueError('shared link retirement requires the independently rederived factory source policy')
    ids = [review['removed_player']['carrier_id']] + [r['player']['carrier_id'] for r in extra]
    if len(set(ids)) != len(ids):
        raise ValueError('shared retirement repeats the duplicate carrier')
    return ids


def original_profile_identity(profile, row, person, actual):
    """Only one explicitly source-ID/DOB-bound omitted-middle-name alias."""
    published = source.identity.key(profile['published_full_name'])
    annual = source.identity.key(row['facts']['name'])
    recipe = source.identity.key(person.get('source_name') or person['name'])
    if published == annual == recipe and profile['published_birth_date']:
        return None
    if (profile['source_player_id'] == row['opening_source_player_id'] == '16907'
            and person['carrier_id'] == 4392
            and profile['published_full_name'] == 'Fabian Natale Valtolina'
            and row['facts']['name'] == person.get('source_name') == 'Fabian Valtolina'
            and profile['published_birth_date'] == row['facts']['birth_date']
                == person['facts']['birth_date'] == actual['birth_date'] == '1971-06-10'):
        return dict(policy='explicit-original-numeric-ID-literal-birthday-middle-name-omission',
                    published=profile['published_full_name'], annual=row['facts']['name'])
    raise ValueError('original numeric profile does not identify assigned full name')


def prepare(release, case, profile_root, profile_receipt):
    package = pipeline.read_json_file(release.package_path)
    candidates = [p for p in package['players'] if p['carrier_id'] in {p['carrier_id'] for p in case['players']}]
    if any(p.get('policy') == 'preserve-existing-mode1' for p in candidates):
        from scripts import review_factory_fallthrough_duplicate_v1 as factory
        review = factory.prepare(release, case, profile_root, profile_receipt)
    else:
        review = source.prepare(release, case)
    if not review['removed_is_current_native_starter']:
        raise ValueError('starter policy cannot replace the existing reserve-only policy')
    club = next(c for c in package['clubs'] if c['id'] == review['club_id'])
    root = registry.ROOT / '.local/transfermarkt-opening-plans-current-v1' / release.season
    pre = pipeline.read_json_file(root / 'opening-squad-preallocation.json')
    cap, annual = source.bound_annual_capture(release, club, pre, root)
    projections = [c for c in pre['source_clubs'] if all(c['selector'][k] == cap[k]
        for k in ('club_name', 'country_catalog', 'competition_catalog'))]
    if len(projections) != 1 or not projections[0]['opening_xi_complete']:
        raise ValueError('one complete original projected XI required')
    projected = projections[0]
    if projected['opening_fixture_date'] != review['first_fixture']['date']:
        raise ValueError('original first XI date differs')
    starters = sorted((r for r in projected['players'] if isinstance(r.get('opening_xi_order'), int)),
                      key=lambda r: r['opening_xi_order'])
    if (len(starters) != 11 or len({r['opening_source_player_id'] for r in starters}) != 11
            or {r['opening_source_player_id'] for r in starters} != set(review['first_fixture']['starting_xi'])):
        raise ValueError('projected XI does not reproduce eleven original numeric match IDs')
    lineup = pipeline.read_json_file(root / 'opening-lineups.json')
    raw_match, _ = source.opening.verified_page(root / 'cache', lineup['source']['cache_files'],
                                              review['first_fixture']['source_url'])
    slugs = source.identity.original_person_links(raw_match, set(review['first_fixture']['starting_xi']))
    receipt = pipeline.read_json_file(profile_receipt)
    people = [p for p in package['players'] if p['club_id'] == club['id']]
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = source.ownership.native_owners(eq)
    roster = review['native_roster_before']
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    xi, roles = [], []
    for row in starters:
        assigned = [p for p in people if p['person_id'] == 'person-source-' + row['source_row_sha256']]
        if len(assigned) != 1:
            raise ValueError('original XI assignment is not one current carrier')
        person = assigned[0]
        id = row['opening_source_player_id']
        url = 'https://www.transfermarkt.co.uk/' + slugs[id] + '/profil/spieler/' + id
        raw, proof = source.opening.verified_page(profile_root, receipt['cache_files'], url)
        profile = source._profile_facts(raw, player={'source_player_id': id})
        carrier = person['carrier_id']
        actual = source.facts.native_facts(jug, carrier)
        alias = original_profile_identity(profile, row, person, actual)
        broad, primary = ROLE_MAP[profile['published_profile_position']]
        if broad != row['facts']['position'] or broad != person['facts']['primary_position']:
            raise ValueError('published profile broad position contradicts dated assignment')
        if actual['position'] != broad or owners.get(carrier) != {club['carrier_id']}:
            raise ValueError('native XI broad position or exclusive club ownership differs')
        _, before = read_indexed_native_roles(entries[carrier].decode_payload(jug), carrier)
        after = [primary] + [98 if r == primary else r for r in before[1:]]
        cleaned = [r for r in after if r != 98]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError('primary role correction would repeat a secondary role')
        if after != cleaned + [98] * (6 - len(cleaned)):
            raise ValueError('secondary correction would reorder another native role')
        xi.append(dict(carrier_id=carrier, player_id=person['id'], source_player_id=id,
            original_assignment=row, original_profile=proof, profile=profile,
            native_before=actual, native_birthday_matches=actual['birth_date'] == profile['published_birth_date']))
        if alias:
            xi[-1]['published_name_alias'] = alias
        if before != after:
            roles.append(dict(carrier_id=carrier, player_id=person['id'], before=before[0], after=primary,
                native_roles_before=before, native_roles_after=after,
                recipe_fine_roles_before=person['facts']['fine_roles'], recipe_fine_roles_after=cleaned,
                published_profile_position=profile['published_profile_position']))
    removed = removed_carriers(review)
    xi_ids = [r['carrier_id'] for r in xi]
    retained_in_bench = (review.get('retained_positive_fixture_surface') == 'published-bench'
                        and review.get('retained_source_player_id') in review['first_fixture']['substitutes'])
    if any(id in xi_ids for id in removed) or (review['retained_player']['carrier_id'] not in xi_ids and not retained_in_bench):
        raise ValueError('retained identity must replace duplicate inside original XI')
    remaining = [id for id, flag in roster if id not in removed]
    if len(remaining) < 16 or len(set(remaining)) != len(remaining) or any(flag for id, flag in roster):
        raise ValueError('opening policy requires distinct visible capacity-fitting players')
    natives = {id: source.facts.native_facts(jug, id) for id in remaining}
    if any(owners.get(id) != {club['carrier_id']} for id in remaining):
        raise ValueError('shared reserve prevents safe complete order repair')
    reserves = sorted((id for id in remaining if id not in xi_ids),
                      key=lambda id: (natives[id]['startup_order'], id))
    orders = [dict(carrier_id=id, **natives[id], after=n)
              for n, id in enumerate(xi_ids + reserves, 1)]
    result = dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(package)),
        jug_sha256=digest(jug), eq_sha256=digest(eq), case=case, review=review,
        before_club=club, starting_xi=xi, orders=orders, primary_role_changes=roles,
        original_annual_source=annual, profile_root=registry.relative_workspace_path(profile_root),
        profile_receipt=source.binding(profile_receipt),
        source_order_policy='Original positive first-XI assignments; other current reserves preserve relative old order. Original substitute bench NOT reconstructed.',
        primary_role_policy='Published exact numeric profile position, dated matching broad position; conservative central midfielder for attacking midfield. Other secondary roles unchanged; a promoted duplicate secondary is cleared to native unassigned.',
        historical_verification_complete=False)
    if any(a['id'].startswith(PREFIX) for a in package['artifacts']):
        result['layer_suffix'] = result['package_sha256'][:12]
    return result


def verify(release, plan):
    if (plan.get('schema') != SCHEMA or
            prepare(release, plan['case'], registry.ROOT / plan['profile_root'],
                    registry.ROOT / plan['profile_receipt']['path']) != plan):
        raise ValueError('original starter duplicate/opening proof does not reproduce')


def _apply_before(jug, eq, plan):
    review = plan['review']
    if digest(jug) != plan['jug_sha256'] or digest(eq) != plan['eq_sha256']:
        raise ValueError('whole source opening native preimage differs')
    validate_opening_shape(plan)
    club_id = review['club_carrier_id']
    index, raw, rows = source.native.roster_rows(eq, club_id)
    if rows != [tuple(r) for r in review['native_roster_before']]:
        raise ValueError('source opening roster preimage differs')
    changed = prune_visible_mode1_roster_payload(raw, expected_rows=rows,
        removed_player_ids=removed_carriers(review))
    new_eq = compiler._rebuild_indexed(eq, index, {club_id: compiler.xor_decode(changed)})
    new_jug = patch_owned_mode1_complete_orders(jug, new_eq, club_record_id=club_id,
        replacements=[OrderReplacement(r['carrier_id'], r['name'], r['startup_order'], r['after'])
                      for r in plan['orders']])
    new_jug, _ = rewrite_indexed_native_primary_roles(new_jug,
        {r['carrier_id']: (r['before'], r['after']) for r in plan['primary_role_changes']})
    secondary = {r['carrier_id']: r['recipe_fine_roles_after'] for r in plan['primary_role_changes']
                 if r['native_roles_before'][1:] != r['native_roles_after'][1:]}
    new_jug, _ = rewrite_indexed_native_roles(new_jug, secondary)
    preserve_other_records(eq, new_eq, {club_id})
    preserve_other_records(jug, new_jug, {r['carrier_id'] for r in plan['orders']})
    return new_jug, new_eq


def validate_opening_shape(plan):
    review = plan['review']
    xi = plan['starting_xi']
    orders = plan['orders']
    removed = removed_carriers(review)
    xi_ids = [r['carrier_id'] for r in xi]
    original_ids = {r['source_player_id'] for r in xi}
    from scripts import review_factory_fallthrough_duplicate_v1 as factory
    retained_bench = (review.get('schema') == factory.SCHEMA
        and review.get('retained_positive_fixture_surface') == 'published-bench'
        and review.get('retained_source_player_id') in review['first_fixture'].get('substitutes', {}))
    if (len(xi_ids) != 11 or len(set(xi_ids)) != 11
            or original_ids != set(review['first_fixture']['starting_xi'])
            or len(original_ids) != 11 or any(id in xi_ids for id in removed)
            or review['retained_player']['carrier_id'] not in {r['carrier_id'] for r in orders}
            or (review['retained_player']['carrier_id'] not in xi_ids and not retained_bench)
            or [r['carrier_id'] for r in orders[:11]] != xi_ids):
        raise ValueError('native opening targets differ from original positive XI')
    before = review['native_roster_before']
    if (not review['duplicate_input_assignment_proved'] or not review['removed_is_current_native_starter']
            or any(before.count([id, 0]) != 1 for id in removed) or any(flag for id, flag in before)
            or {r['carrier_id'] for r in orders} != {id for id, flag in before if id not in removed}
            or len(orders) != len(before) - len(removed) or len(orders) < 16
            or [r['after'] for r in orders] != list(range(1, len(orders) + 1))):
        raise ValueError('native opening order/roster coverage is not exact')
    reserve_rows = orders[11:]
    if reserve_rows != sorted(reserve_rows, key=lambda r: (r['startup_order'], r['carrier_id'])):
        raise ValueError('native opening reserves were reordered without source authority')
    by_carrier = {r['carrier_id']: r for r in xi}
    seen = set()
    for row in plan['primary_role_changes']:
        carrier = row['carrier_id']
        if carrier in seen or carrier not in by_carrier:
            raise ValueError('primary changes require unique original starter identities')
        seen.add(carrier)
        broad, expected = ROLE_MAP[by_carrier[carrier]['profile']['published_profile_position']]
        before_roles = row['native_roles_before']
        after_roles = [expected] + [98 if r == expected else r for r in before_roles[1:]]
        if (row['before'] != before_roles[0] or row['after'] != expected
                or row['native_roles_after'] != after_roles
                or row['recipe_fine_roles_after'] != [r for r in after_roles if r != 98]
                or by_carrier[carrier]['native_before']['position'] != broad):
            raise ValueError('primary/secondary role target differs from published profile policy')


def apply(jug, eq, plan):
    if plan.get('schema') != SCHEMA or not plan['review']['removed_is_current_native_starter']:
        raise ValueError('unapproved starter-removal source policy')
    baseline = registry.load_registered_release(plan['season'], plan['release_id'])
    original = ((baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
                (baseline.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    expected = _apply_before(*original, plan)
    if (jug, eq) not in (original, expected):
        raise ValueError('whole opening pre/postimage changed or partially applied')
    return expected


def bind(package, plan):
    if plan.get('schema') != SCHEMA or digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('whole opening recipe preimage differs')
    result = copy.deepcopy(package)
    r = plan['review']
    if r.get('shared_removed_membership') or r.get('additional_shared_membership_retirements'):
        removed_carriers(r)
    club = next(c for c in result['clubs'] if c['id'] == r['club_id'])
    bad = r['removed_player']['id']
    shared = r.get('shared_removed_membership')
    if (club != plan['before_club'] or (not shared and
            any(bad in c['roster_player_ids'] for c in result['clubs'] if c['id'] != club['id']))):
        raise ValueError('opening recipe club/removed owner differs')
    people = {p['id']: p for p in result['players']}
    if people.get(bad) != r['removed_player'] or people.get(r['retained_player']['id']) != r['retained_player']:
        raise ValueError('opening recipe duplicate identity preimage differs')
    retired_memberships = list(r.get('additional_shared_membership_retirements', []))
    if shared:
        retired_memberships.append(shared)
    for membership in retired_memberships:
        person = people.get(membership['player']['id'])
        survivor = next(c for c in result['clubs'] if c['id'] == membership['surviving_club_id'])
        owners = [c for c in result['clubs'] if person and person['id'] in c['roster_player_ids']]
        if (person != membership['player'] or survivor != membership['surviving_club_before']
                or sorted(c['carrier_id'] for c in owners) != membership['native_owners_before']
                or {c['id'] for c in owners} != {club['id'], survivor['id']}
                or person['id'] in club.get('starting_xi_player_ids', [])):
            raise ValueError('shared membership recipe preimage/survivor differs')
        club['roster_player_ids'].remove(person['id'])
        club['shared_preserve_player_ids'] = [id for id in club.get('shared_preserve_player_ids', [])
                                             if id != person['id']]
        if person['club_id'] == club['id']:
            person['club_id'] = survivor['id']
            survivor['shared_preserve_player_ids'] = [id for id in survivor.get('shared_preserve_player_ids', [])
                                                       if id != person['id']]
    if not shared:
        club['roster_player_ids'].remove(bad)
    if 'shared_preserve_player_ids' in club:
        club['shared_preserve_player_ids'] = [p for p in club['shared_preserve_player_ids'] if p != bad]
    if bad in club.get('starting_xi_player_ids', []):
        raise ValueError('unsupported explicitly declared duplicate starter list')
    for change in plan['primary_role_changes']:
        person = people[change['player_id']]
        if person['facts']['fine_roles'] != change['recipe_fine_roles_before']:
            raise ValueError('opening recipe fine-role preimage differs')
        person['facts']['fine_roles'] = change['recipe_fine_roles_after']
    if not shared:
        result['players'] = [p for p in result['players'] if p['id'] != bad]
        for owner in (result, result.get('assets', {})):
            if 'portraits' in owner:
                owner['portraits'] = [p for p in owner['portraits'] if p['player_id'] != bad]
    id = PREFIX + plan['season'] + '-' + str(club['carrier_id'])
    if any(a['id'] == id for a in result['artifacts']):
        raise ValueError('opening source layer already present')
    result['artifacts'].append(dict(id=id, kind='season-input', relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('source opening recipe requires known-good reconstruction; factory compilation must not drop this layer')


def reconstruction(previous, release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA or path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('opening source locator schema/path differs')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if packages.canonical_json_bytes(expected) != packages.canonical_json_bytes(pipeline.read_json_file(previous.package_path)):
        raise ValueError('edited opening recipe cannot use exact reconstruction; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('opening replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(expected):
        raise ValueError('opening replay complete recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-duplicate-opening-known-good-reconstruction-not-factory-compile')
