"""Explicit source-bound Trabzon2000 duplicate-link/full-XI recipe delta.

This opt-in layer is separate from the frozen Italian and TFF policies. It
replays against its registered known-good baseline; it is not a factory build.
"""
import copy
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_primary_roles
from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders
from scripts import season_trabzon_opening_review_v1 as source
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_release_registry_v1 as registry
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

PREFIX = 'sourced-trabzon-opening-xi-'
FILENAME = 'sourced-trabzon-opening-xi.json'
ROLE_SCHEMA = 'pm99-Trabzon-2000-original-opening-duplicate-link-primary-roles-v2'
ROLE_POLICY = 'original-positive-matchday-broad-role-conservative-primary-only-v2'


def prepare(release):
    plan = source.prepare(release)
    package = json.loads(release.package_path.read_text())
    people = {p['carrier_id']: p for p in package['players']}
    jug = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    # Five source-present substitutes fit PM99's matchday bench. Preserve the
    # original published bench order, goalkeeper first; missing two stay gaps.
    bench = {r['source_player_id']: r for r in plan['bench_witnesses']}
    reserves = []
    for source_id in plan['original_fixture']['substitutes']:
        witness = bench[source_id]
        matches = witness['current_carriers']
        if len(matches) > 1:
            raise ValueError('ambiguous original substitute carrier')
        reserves.extend(matches)
    if len(reserves) != 5 or source.facts.native_facts(jug, reserves[0])['position'] != 'G':
        raise ValueError('original source-present five-player bench lacks goalkeeper first')
    xi_ids = [p['carrier_id'] for p in plan['starting_xi']]
    remaining = [r['carrier_id'] for r in plan['orders'] if r['carrier_id'] not in set(xi_ids+reserves)]
    old_orders = {r['carrier_id']: r for r in plan['orders']}
    plan['orders'] = [dict(old_orders[id], after=n) for n,id in enumerate(xi_ids+reserves+remaining,1)]
    plan['source_present_substitute_carriers'] = reserves
    plan['startup_order_policy'] = 'original published XI; five source-present substitutes in published order; other reserves stable old-order/ID'
    capture, _ = source.facts.annual_capture(release.season, plan['before_club'])
    changes = []
    for id in xi_ids+reserves:
        person = people[id]
        rows = [r for r in capture['players'] if source.key(r['name']) == source.key(person.get('source_name') or person['name'])]
        if len(rows) != 1 or rows[0]['position'] != person['facts']['primary_position']:
            raise ValueError('original matchday identity/broad position differs')
        _, before = read_indexed_native_roles(entries[id].decode_payload(jug), id)
        target = native.conservative_primary_role(rows[0]['position'], before[0])
        if target is None:
            continue
        after = [target]+before[1:]
        recipe_after = [r for r in after if r != 98]
        if len(recipe_after) != len(set(recipe_after)):
            raise ValueError('primary correction cannot introduce repeated recipe roles')
        changes.append(dict(carrier_id=id, player_id=person['id'], before=before[0], after=target,
            native_roles_before=before, native_roles_after=after, source_position=rows[0]['position'],
            recipe_fine_roles_before=person['facts'].get('fine_roles'), recipe_fine_roles_after=recipe_after))
    plan.update(schema=ROLE_SCHEMA, primary_role_policy=ROLE_POLICY, primary_role_changes=changes)
    return plan


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('Trabzon recipe requires supported known-good reconstruction via pm99-season build; factory compilation must not silently drop this source layer')


def verify(release, plan):
    expected = prepare(release) if plan.get('schema') == ROLE_SCHEMA else source.prepare(release)
    if plan.get('schema') not in (source.SCHEMA, ROLE_SCHEMA) or expected != plan:
        raise ValueError('Trabzon original-source plan does not reproduce against its baseline')


def apply(jug, eq, plan):
    if (plan.get('schema') not in (source.SCHEMA, ROLE_SCHEMA) or plan.get('club_carrier_id') != 1002
            or plan.get('season') != '2000-01' or plan.get('removed_link') != 32505):
        raise ValueError('unsupported Trabzon source policy/club/removal')
    index, raw, rows = native.roster_rows(eq, 1002)
    before = [tuple(r) for r in plan['before_rows']]
    after = [tuple(r) for r in plan['after_rows']]
    if after != [r for r in before if r[0] != 32505] or before.count((32505, 0)) != 1:
        raise ValueError('Trabzon removal is not its exact reviewed link')
    if rows == before:
        if hashlib.sha256(eq).hexdigest() != plan['eq_sha256'] or hashlib.sha256(jug).hexdigest() != plan['jug_sha256']:
            raise ValueError('Trabzon native baseline preimage changed')
        changed = prune_visible_mode1_roster_payload(raw, expected_rows=before, removed_player_ids=[32505])
        result_eq = compiler._rebuild_indexed(eq, index, {1002: compiler.xor_decode(changed)})
    elif rows == after:
        result_eq = eq
    else:
        raise ValueError('Trabzon native roster preimage changed')
    orders = plan['orders']
    xi = [r['carrier_id'] for r in plan['starting_xi']]
    if (len(xi) != 11 or len(set(xi)) != 11 or
            [r['carrier_id'] for r in orders[:11]] != xi):
        raise ValueError('Trabzon startup permutation disagrees with original starters')
    replacements = []
    for row in orders:
        actual = source.facts.native_facts(jug, row['carrier_id'])
        if any(actual[k] != row[k] for k in ('name', 'birth_date', 'position')):
            raise ValueError('Trabzon native player identity/facts changed')
        replacements.append(OrderReplacement(row['carrier_id'], row['name'], row['startup_order'], row['after']))
    result_jug = patch_owned_mode1_complete_orders(jug, result_eq, club_record_id=1002, replacements=replacements)
    if plan.get('schema') == ROLE_SCHEMA:
        if plan.get('primary_role_policy') != ROLE_POLICY:
            raise ValueError('unapproved Trabzon primary-role policy')
        permitted = set(xi+plan['source_present_substitute_carriers'])
        changes = plan['primary_role_changes']
        if len({r['carrier_id'] for r in changes}) != len(changes) or any(r['carrier_id'] not in permitted for r in changes):
            raise ValueError('primary changes require unique source-present matchday identities')
        entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(result_jug).entries}
        for row in changes:
            _, roles = read_indexed_native_roles(entries[row['carrier_id']].decode_payload(result_jug), row['carrier_id'])
            if (roles not in (row['native_roles_before'], row['native_roles_after']) or
                    native.conservative_primary_role(row['source_position'], row['before']) != row['after']):
                raise ValueError('Trabzon primary role preimage or source-compatible target differs')
        result_jug, _ = rewrite_indexed_native_primary_roles(result_jug,
            {r['carrier_id']: (r['before'], r['after']) for r in changes})
    elif plan.get('primary_role_changes'):
        raise ValueError('v1 Trabzon plan cannot authorize role changes')
    preserve_other_records(eq, result_eq, {1002})
    preserve_other_records(jug, result_jug, {r['carrier_id'] for r in orders})
    return result_jug, result_eq


def bind(package, plan):
    if plan.get('schema') not in (source.SCHEMA, ROLE_SCHEMA) or plan.get('season') != '2000-01':
        raise ValueError('unsupported Trabzon recipe source policy')
    result = copy.deepcopy(package)
    club = next(c for c in result['clubs'] if c['id'] == plan['club_id'])
    if club != plan['before_club']:
        raise ValueError('Trabzon recipe club preimage changed')
    people = {p['id']: p for p in result['players']}
    removed = [id for id in club['roster_player_ids'] if people[id]['carrier_id'] == 32505]
    if len(removed) != 1 or any(removed[0] in c['roster_player_ids'] for c in result['clubs'] if c['id'] != club['id']):
        raise ValueError('Trabzon removed recipe person is not uniquely owned')
    club['roster_player_ids'].remove(removed[0])
    if 'shared_preserve_player_ids' in club:
        club['shared_preserve_player_ids'] = [id for id in club['shared_preserve_player_ids'] if id not in removed]
    result['players'] = [p for p in result['players'] if p['id'] not in removed]
    if plan.get('schema') == ROLE_SCHEMA:
        if plan.get('primary_role_policy') != ROLE_POLICY:
            raise ValueError('unapproved Trabzon recipe primary-role policy')
        for row in plan['primary_role_changes']:
            p = people[row['player_id']]
            if p['facts'].get('fine_roles') != row['recipe_fine_roles_before']:
                raise ValueError('Trabzon recipe primary-role preimage differs')
            p['facts']['fine_roles'] = list(row['recipe_fine_roles_after'])
    elif plan.get('primary_role_changes'):
        raise ValueError('v1 Trabzon recipe cannot authorize primary changes')
    for owner in (result, result.get('assets', {})):
        if 'portraits' in owner:
            owner['portraits'] = [p for p in owner['portraits'] if p['player_id'] not in removed]
    artifact_id = PREFIX + plan['season'] + '-1002'
    if any(a['id'] == artifact_id for a in result['artifacts']):
        raise ValueError('Trabzon layer already exists; never append a second replay')
    result['artifacts'].append({'id': artifact_id, 'kind': 'season-input', 'relative_path': FILENAME,
        'sha256': hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest(), 'media_type': 'application/json'})
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reconstruction(previous, release_id):
    """Supported normal-build dispatch, refusing arbitrary edited recipes."""
    if getattr(previous, 'season', None) != '2000-01':
        return None
    from scripts import season_pipeline_v2 as pipeline
    from scripts import publish_historical_role_delta_v1 as publisher
    package = pipeline.read_json_file(previous.package_path)
    artifacts = [a for a in package['artifacts'] if a['id'].startswith(PREFIX)]
    if not artifacts:
        return None
    if len(artifacts) != 1 or artifacts[0]['relative_path'] != FILENAME:
        raise ValueError('Trabzon rebuild requires exactly one explicit local source layer')
    path = previous.package_path.parent / FILENAME
    if registry.sha256_file(path) != artifacts[0]['sha256']:
        raise ValueError('Trabzon replay artifact hash changed')
    plan = pipeline.read_json_file(path)
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if packages.canonical_json_bytes(expected) != packages.canonical_json_bytes(package):
        raise ValueError('edited Trabzon recipe cannot use exact reconstruction; no edits discarded')
    descriptor_path = previous.package_path.parent / 'role-delta-input.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    expected_descriptor = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if descriptor != expected_descriptor:
        raise ValueError('Trabzon replay baseline descriptor changed')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        register=False, trabzon_opening_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    return dict(season=previous.season, release_id=release_id, previous_release_id=previous.release_id,
        source_release_id=baseline.release_id, complete_game_inventory_identical=True, reused=False,
        compilation_mode='source-bound-Trabzon-known-good-reconstruction-not-factory-compile',
        release_manifest_sha256=registry.sha256_file(rebuilt.release_manifest_path))
