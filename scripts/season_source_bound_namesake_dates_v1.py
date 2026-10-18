"""Correct exact birthdays of two independently sourced first-XI namesakes.

Never removes a player. Original numeric profile and dated fixture assignments
disambiguate the names; an annual full-name join alone cannot authorize writes.
Other facts/roles/ratings/photos remain explicit separate review queues.
"""
import copy
from datetime import date
import hashlib

from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from scripts import review_original_match_namesakes_v1 as original
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-original-numeric-first-XI-namesake-exact-birthday-repair-v1'
PREFIX = 'sourced-namesake-exact-birthdays-'
FILENAME = 'sourced-namesake-exact-birthdays.json'


def filename(plan):
    return FILENAME


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(release, case, extra_root, extra_receipt):
    review = original.prepare(release, case, extra_root, extra_receipt,
                              allow_recipe_birthday_conflicts=True)
    package = pipeline.read_json_file(release.package_path)
    updates = []
    for row in review['players']:
        birthday = date.fromisoformat(row['published_birth_date'])
        age = (date.fromisoformat(review['first_fixture']['date']) - birthday).days / 365.2425
        if not 14 <= age <= 50 or birthday.year >= 2000:
            raise ValueError('namesake birthday outside this pre-2000 literal-date policy')
        if not row['native_birthday_matches'] or not row['recipe_birthday_matches']:
            if row['recipe_person'].get('policy') == 'preserve-existing-mode1':
                raise ValueError('cannot mutate a whole-record preserve declaration')
            updates.append(dict(carrier_id=row['carrier_id'],
                native_name=row['native_before']['name'],
                before_birth_date=row['native_before']['birth_date'],
                birth_date=row['published_birth_date'], before_player=row['recipe_person']))
    if not updates:
        raise ValueError('namesake birthdays need no correction')
    return dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(package)),
        jug_sha256=review['jug_sha256'], eq_sha256=review['eq_sha256'],
        fixed_case=copy.deepcopy(case), review=review, updates=updates,
        original_profile_root=registry.relative_workspace_path(extra_root),
        original_profile_receipt=original.sources.binding(extra_receipt),
        scope='Exact source-profile birthdays only in native player and recipe. Both distinct first-XI players retained. Roles, other facts, ratings, portraits, managers, tactics, EXE and assets remain unchanged and are NOT approved.')


def verify(release, plan):
    root = registry.ROOT / plan['original_profile_root']
    receipt = registry.ROOT / plan['original_profile_receipt']['path']
    if (registry.sha256_file(receipt) != plan['original_profile_receipt']['sha256']
            or prepare(release, plan['fixed_case'], root, receipt) != plan):
        raise ValueError('namesake birthday original identity proof did not reproduce')


def apply(jug, eq, plan):
    if plan.get('schema') != SCHEMA or digest(eq) != plan['eq_sha256']:
        raise ValueError('namesake birthday schema/whole club preimage differs')
    baseline = registry.load_registered_release(plan['season'], plan['release_id'])
    before = (baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before) != plan['jug_sha256']:
        raise ValueError('immutable namesake birthday baseline changed')
    updates = {row['carrier_id']: row for row in plan['updates']}
    if len(updates) != len(plan['updates']) or not updates:
        raise ValueError('empty/duplicate namesake birthday updates')
    after, _ = rewrite_indexed_native_birth_dates(before, updates)
    if jug not in (before, after):
        raise ValueError('namesake birthday whole player preimage/postimage differs')
    return after, eq


def bind(package, plan):
    if (plan.get('schema') != SCHEMA
            or digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']):
        raise ValueError('namesake birthday whole recipe preimage differs')
    result = copy.deepcopy(package)
    carriers = set()
    for row in plan['updates']:
        actual = [p for p in result['players'] if p['carrier_id'] == row['carrier_id']]
        if actual != [row['before_player']] or row['carrier_id'] in carriers:
            raise ValueError('namesake birthday person preimage differs')
        carriers.add(row['carrier_id'])
        actual[0]['facts']['birth_date'] = row['birth_date']
        # A newly sourced literal must not retain a contradictory old
        # preserve-existing birthday declaration. Other fallbacks stay exact.
        if 'fact_fallbacks' in actual[0]:
            actual[0]['fact_fallbacks'] = [f for f in actual[0]['fact_fallbacks'] if f['field'] != 'birth_date']
    identifier = PREFIX + plan['season']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('namesake birthday source layer already present')
    result['artifacts'].append(dict(id=identifier, kind='season-input',
        relative_path=FILENAME, sha256=digest(packages.canonical_json_bytes(plan)),
        media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('namesake birthday recipe requires source-bound known-good replay; factory compile must not discard the layer')


def reconstruction(previous, release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA or path.resolve() != (previous.package_path.parent / FILENAME).resolve():
        raise ValueError('namesake birthday source locator differs')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if packages.canonical_json_bytes(expected) != packages.canonical_json_bytes(pipeline.read_json_file(previous.package_path)):
        raise ValueError('edited namesake birthday recipe cannot use exact replay; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('namesake birthday replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(expected):
        raise ValueError('namesake birthday replay complete recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-exact-namesake-birthdays-known-good-reconstruction-not-factory-compile')
