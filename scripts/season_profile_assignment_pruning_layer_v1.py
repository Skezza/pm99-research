"""Source-bound reserve-only duplicate input pruning, without player rewrites.

The original annual shirt identity and first-match numeric profile must prove
each input collision. This narrow layer cannot remove a starter, replace a
person or approve a historical squad merely by making a candidate disappear.
"""
import copy
import hashlib

from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from scripts import review_profile_addition_duplicate_assignments_v1 as source
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-source-bound-reserve-input-assignment-pruning-v1'
PREFIX = 'sourced-profile-assignment-pruning-'
FILENAME = 'sourced-profile-assignment-pruning.json'


def filename(plan):
    suffix = plan.get('layer_suffix', '')
    return 'sourced-profile-assignment-pruning' + ('-' + suffix if suffix else '') + '.json'


def artifact_id(plan):
    suffix = plan.get('layer_suffix', '')
    return PREFIX + plan['season'] + ('-' + suffix if suffix else '')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(release, cases):
    cases = sorted(copy.deepcopy(cases), key=lambda c: c['id'])
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('pruning needs unique nonempty fixed cases')
    reviews = []
    for case in cases:
        try:
            review = source.prepare(release, case)
        except ValueError as exc:
            if str(exc) != 'annual unknown-DOB row lacks identical original match shirt':
                raise
            review = source.prepare(release, case, numeric_annual=True)
        reviews.append(review)
    if any(r['removed_is_current_native_starter'] for r in reviews):
        raise ValueError('reserve policy cannot remove a native starter')
    removed = [r['removed_player']['carrier_id'] for r in reviews]
    retained = [r['retained_player']['carrier_id'] for r in reviews]
    if len(set(removed)) != len(removed) or set(removed) & set(retained):
        raise ValueError('duplicate or overlapping pruning identities')
    result = dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(pipeline.read_json_file(release.package_path))),
        jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        fixed_cases=cases, reviews=reviews,
        scope='Remove only source-proved duplicate reserve roster links and recipe assignments; every native player, startup order, skill, fact, manager, tactic and asset unchanged.')
    if any(a['id'].startswith(PREFIX) for a in pipeline.read_json_file(release.package_path)['artifacts']):
        result['layer_suffix'] = result['package_sha256'][:12]
    return result


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release, plan['fixed_cases']) != plan:
        raise ValueError('original reserve assignment proof no longer reproduces')


def groups(plan):
    if plan.get('schema') != SCHEMA or not plan.get('reviews'):
        raise ValueError('unsupported reserve assignment pruning plan')
    groups = {}
    removed_all, kept_all = set(), set()
    for r in plan['reviews']:
        bad, keep = r['removed_player'], r['retained_player']
        if (r.get('schema') not in (source.SCHEMA, source.NUMERIC_SCHEMA) or not r.get('duplicate_input_assignment_proved')
                or r.get('removed_is_current_native_starter') is not False
                or r['native_before'][str(bad['carrier_id'])]['startup_order'] <= 11
                or r['season'] != plan['season'] or r['release_id'] != plan['release_id']
                or any(r[k] != plan[k] for k in ('package_sha256', 'jug_sha256', 'eq_sha256'))
                or bad['carrier_id'] == keep['carrier_id'] or bad['carrier_id'] in removed_all):
            raise ValueError('unapproved reserve removal or mismatched baseline')
        removed_all.add(bad['carrier_id'])
        kept_all.add(keep['carrier_id'])
        g = groups.setdefault(r['club_carrier_id'], dict(before=r['native_roster_before'], removed=[]))
        if g['before'] != r['native_roster_before']:
            raise ValueError('same club has inconsistent native roster preimages')
        g['removed'].append(bad['carrier_id'])
    if removed_all & kept_all:
        raise ValueError('a retained identity is also marked for removal')
    for g in groups.values():
        g['before'] = [tuple(r) for r in g['before']]
        if any(g['before'].count((id, 0)) != 1 for id in g['removed']):
            raise ValueError('exact reserve roster link missing or repeated')
        g['after'] = [r for r in g['before'] if r[0] not in set(g['removed'])]
        if len(g['after']) < 16:
            raise ValueError('pruning would violate capacity-fitting matchday minimum')
    return groups


def apply(jug, eq, plan):
    reviewed = groups(plan)
    if digest(jug) != plan['jug_sha256']:
        raise ValueError('reserve pruning cannot change or substitute the native player file')
    replacements, states = {}, []
    index = None
    for club_id, g in reviewed.items():
        index, raw, rows = native.roster_rows(eq, club_id)
        if rows == g['before']:
            states.append('before')
            changed = prune_visible_mode1_roster_payload(raw,
                expected_rows=g['before'], removed_player_ids=g['removed'])
            replacements[club_id] = compiler.xor_decode(changed)
        elif rows == g['after']:
            states.append('after')
        else:
            raise ValueError('reserve roster preimage differs')
    if len(set(states)) != 1:
        raise ValueError('partially applied reserve batch is not an approved preimage')
    if replacements and digest(eq) != plan['eq_sha256']:
        raise ValueError('whole club database preimage differs')
    if not replacements:
        # Idempotence accepts only the exact complete postimage, not a game
        # with matching target rows but unrelated edits hidden elsewhere.
        baseline = registry.load_registered_release(plan['season'], plan['release_id'])
        original = (baseline.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
        if digest(original) != plan['eq_sha256']:
            raise ValueError('immutable reserve pruning baseline changed')
        expected_replacements = {}
        for club_id, g in reviewed.items():
            original_index, raw, rows = native.roster_rows(original, club_id)
            if rows != g['before']:
                raise ValueError('immutable reserve roster baseline changed')
            changed = prune_visible_mode1_roster_payload(raw,
                expected_rows=g['before'], removed_player_ids=g['removed'])
            expected_replacements[club_id] = compiler.xor_decode(changed)
        expected = compiler._rebuild_indexed(original, original_index, expected_replacements)
        if eq != expected:
            raise ValueError('reserve pruning postimage has unrelated native changes')
    result = compiler._rebuild_indexed(eq, index, replacements) if replacements else eq
    preserve_other_records(eq, result, set(reviewed))
    for club_id, g in reviewed.items():
        if native.roster_rows(result, club_id)[2] != g['after']:
            raise ValueError('pruning readback differs from exact approved roster')
    return jug, result


def bind(package, plan):
    groups(plan)
    if digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('whole reserve recipe preimage differs')
    result = copy.deepcopy(package)
    removed_ids = set()
    for r in plan['reviews']:
        bad, keep = r['removed_player'], r['retained_player']
        for expected in (bad, keep):
            actual = [p for p in result['players'] if p['id'] == expected['id']]
            if actual != [expected]:
                raise ValueError('reserve recipe person preimage differs')
        clubs = [c for c in result['clubs'] if bad['id'] in c['roster_player_ids']]
        if (len(clubs) != 1 or clubs[0]['id'] != r['club_id']
                or clubs[0]['carrier_id'] != r['club_carrier_id']
                or keep['id'] not in clubs[0]['roster_player_ids']
                or bad['id'] in clubs[0].get('starting_xi_player_ids', [])):
            raise ValueError('reserve recipe owner or opening XI differs')
        clubs[0]['roster_player_ids'].remove(bad['id'])
        if 'shared_preserve_player_ids' in clubs[0]:
            clubs[0]['shared_preserve_player_ids'] = [id for id in clubs[0]['shared_preserve_player_ids'] if id != bad['id']]
        removed_ids.add(bad['id'])
    result['players'] = [p for p in result['players'] if p['id'] not in removed_ids]
    for owner in (result, result.get('assets', {})):
        if 'portraits' in owner:
            owner['portraits'] = [p for p in owner['portraits'] if p['player_id'] not in removed_ids]
    id = artifact_id(plan)
    if any(a['id'] == id for a in result['artifacts']):
        raise ValueError('reserve assignment layer already present')
    result['artifacts'].append(dict(id=id, kind='season-input', relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('reserve pruning recipe requires source-bound reconstruction; factory compilation must not drop this layer')


def reconstruction(previous, release_id):
    if not getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path'):
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    package = pipeline.read_json_file(previous.package_path)
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    from scripts import season_authored_country_delta_v1 as authored_country
    if plan.get('schema') == authored_country.SCHEMA:
        return authored_country.reconstruction(previous, release_id)
    from scripts import season_source_bound_reserve_transfer_v1 as reserve_transfer
    if plan.get('schema') == reserve_transfer.SCHEMA:
        return reserve_transfer.reconstruction(previous, release_id)
    from scripts import season_source_bound_fixture_membership_v1 as fixture_membership
    if plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
        return fixture_membership.reconstruction(previous, release_id)
    from scripts import season_source_bound_birthday_disagreements_v1 as birthdays
    if plan.get('schema') == birthdays.SCHEMA:
        return birthdays.reconstruction(previous, release_id)
    from scripts import season_source_bound_shirt_numbers_v1 as shirts
    if plan.get('schema') == shirts.SCHEMA:
        return shirts.reconstruction(previous, release_id)
    from scripts import season_arsenal_2021_owned_opening_v1 as arsenal
    if plan.get('schema') == arsenal.SCHEMA:
        return arsenal.reconstruction(previous, release_id)
    from scripts import season_quality_only_delta_v1 as quality_only
    if plan.get('schema') == quality_only.SCHEMA:
        return quality_only.reconstruction(previous, release_id)
    from scripts import season_city_2024_opening_exchange_v1 as city
    if plan.get('schema') == city.SCHEMA:
        return city.reconstruction(previous, release_id)
    from scripts import season_woking_2003_owned_opening_v1 as woking
    if plan.get('schema') == woking.SCHEMA:
        return woking.reconstruction(previous, release_id)
    from scripts import season_source_bound_duplicate_opening_v1 as opening
    if plan.get('schema') == opening.SCHEMA:
        return opening.reconstruction(previous, release_id)
    from scripts import season_source_bound_namesake_dates_v1 as dates
    if plan.get('schema') == dates.SCHEMA:
        return dates.reconstruction(previous, release_id)
    from scripts import season_original_secondary_facts_v1 as secondary_facts
    if plan.get('schema') == secondary_facts.SCHEMA:
        return secondary_facts.reconstruction(previous, release_id)
    from scripts import season_stevenage_opening_repair_v1 as stevenage
    if plan.get('schema') == stevenage.SCHEMA:
        return stevenage.reconstruction(previous, release_id)
    from scripts import season_boreham_opening_repair_v1 as boreham
    if plan.get('schema') == boreham.SCHEMA:
        return boreham.reconstruction(previous, release_id)
    from scripts import season_barrow_opening_repair_v1 as barrow
    if plan.get('schema') == barrow.SCHEMA:
        return barrow.reconstruction(previous, release_id)
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('reserve pruning replay locator is not the exact local layer')
    artifacts = [a for a in package['artifacts'] if a['id'] == artifact_id(plan)]
    if len(artifacts) != 1 or artifacts[0]['relative_path'] != filename(plan):
        raise ValueError('reserve pruning replay requires one exact current layer')
    if registry.sha256_file(path) != artifacts[0]['sha256']:
        raise ValueError('reserve pruning replay artifact changed')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path), plan)) != packages.canonical_json_bytes(package):
        raise ValueError('edited recipe cannot use exact reserve pruning replay; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('reserve pruning replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(package):
        raise ValueError('reserve pruning replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-reserve-assignment-known-good-reconstruction-not-factory-compile')
