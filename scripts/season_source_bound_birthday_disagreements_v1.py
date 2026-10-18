"""Correct nine explicit birthday disagreements using existing bounded writer."""
import copy
import hashlib
from pathlib import Path

from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from scripts import midson_odubade_birthday_admission_v1 as admission
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

SCHEMA = 'pm99-source-bound-original-birthday-disagreement-only-v1'
MODE = 'known-good-baseline-source-bound-birthday-disagreement-only-v1'
PREFIX = 'source-bound-birthday-disagreements-'
FILENAME = 'source-bound-birthday-disagreements.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return FILENAME


def prepare(base):
    return dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI'),
        updates=[admission.admit(base)],
        implementation_bindings=[dict(path=registry.relative_workspace_path(p), sha256=registry.sha256_file(p))
            for p in (Path(__file__), Path(admission.__file__),
                      registry.ROOT / 'upstream/pm99-skezmod-db-editor/app/indexed_jug_birth_date.py')],
        scope='Exact four-byte native birthday field and source recipe birthday only. Names, ownership, all ten skills, roles, tactics, managers, pictures, kits, other facts and every unrelated file are preserved. No duplicate cases closed; original247 date denominator unchanged.')


def verify(base, plan):
    if plan.get('schema') != SCHEMA or prepare(base) != plan:
        raise ValueError('original birthday/identity/club/preimage proof did not reproduce')


def bind(package, plan):
    if plan.get('schema') != SCHEMA or digest(packages.canonical_json_bytes(package)) != registry.canonical_document_sha256(
            registry.load_registered_release(plan['season'], plan['release_id']).package_path):
        raise ValueError('birthday whole recipe preimage differs')
    result = copy.deepcopy(package)
    for row in plan['updates']:
        matches = [p for p in result['players'] if p['carrier_id'] == row['carrier_id']]
        if matches != [row['before_player']]:
            raise ValueError('birthday exact person preimage differs')
        matches[0]['facts']['birth_date'] = row['birth_date']
        if 'fact_fallbacks' in matches[0]:
            matches[0]['fact_fallbacks'] = [f for f in matches[0]['fact_fallbacks'] if f['field'] != 'birth_date']
    aid = PREFIX + plan['season']
    if any(a['id'] == aid for a in result['artifacts']):
        raise ValueError('birthday source layer already exists')
    result['artifacts'].append(dict(id=aid, kind='season-input', relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['sources'].append(dict(id=aid + '-source', title='Original numeric biography and dated August club interval; explicit contradictory provider birthday resolution',
        uri=plan['updates'][0]['original_numeric_profile']['url'], proof_grade='source-receipt', evidence_artifact_id=aid))
    result['proofs'].append(dict(id='proof-' + aid, artifact_id=aid, grade='source-receipt',
        covers=['explicit original numeric player birthday only; unrelated identity/club/rating/photo approval not implied']))
    for key in ('artifacts', 'sources', 'proofs'):
        result[key].sort(key=lambda r: r['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if plan.get('schema') != SCHEMA or digest(original) != plan['jug_sha256'] or digest(eq) != plan['eq_sha256']:
        raise ValueError('birthday immutable native baseline differs')
    updates = {r['carrier_id']: r for r in plan['updates']}
    if not updates or len(updates) != len(plan['updates']):
        raise ValueError('empty or duplicate birthday target')
    candidate, _ = rewrite_indexed_native_birth_dates(original, updates)
    if jug not in (original, candidate) or rewrite_indexed_native_birth_dates(candidate, updates) != (candidate, []):
        raise ValueError('birthday accepts only complete pre/postimages and must be idempotent')
    return candidate, eq


def reconstruction(previous, release_id):
    path_receipt = getattr(previous, 'compiler_receipt_path', None)
    if path_receipt is None or pipeline.read_json_file(path_receipt).get('compilation_mode') != MODE:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    if path.resolve() != (previous.package_path.parent / FILENAME).resolve():
        raise ValueError('birthday original plan locator differs')
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited birthday recipe cannot be silently replayed')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=base.release_id,
            package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]):
        raise ValueError('birthday reconstruction descriptor differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('complete birthday SOURCE recipe differs')
    return dict(season=previous.season, release_id=release_id, complete_game_inventory_identical=True,
        complete_recipe_identical=True, reused=False, compilation_mode=MODE)
