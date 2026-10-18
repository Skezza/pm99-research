"""Source-bound one-byte Commons shirt correction after the alias transaction.

Keep the immutable alias version reproducible. This separate field-only layer
does not regenerate players, ratings, roles, tactics, managers or artwork.
"""
import copy
import hashlib
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import season_opening_order_repair_v1 as ownership
from scripts import prepare_stoke_alias_identity_evidence_20261016 as sources
from scripts import season_stoke_original_alias_reserve_v1 as alias
from scripts.build_stoke_original_alias_reserve_20261016 import RELEASE as BASE

SCHEMA = 'pm99-original-Stoke2001-Commons-single-shirt-byte-v1'
MODE = 'known-good-source-bound-Stoke2001-Commons-single-shirt-byte-v1'
FILENAME = 'stoke-commons-original-shirt-number.json'
ARTIFACT = 'original-stoke-commons-shirt-2001-02'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return FILENAME


def native_guard(player, club, raw, owners, eq_records, target):
    if (club['carrier_id'] != 375 or club['name'] != 'Stoke City'
            or player['carrier_id'] != 27013 or player['club_id'] != club['id']
            or player['source_name'] != 'Kris Commons' or player['facts']['birth_date'] != '1983-08-30'
            or player['person_id'] != 'person-soccerbase-28633'
            or club['roster_player_ids'].count(player['id']) != 1
            or owners.get(27013) != {375} or eq_records[375][0x29] != 0
            or raw[2:5] != bytes.fromhex('dd6361') or read_initial_order(raw).name.casefold() != player['name'].casefold()
            or target != 24):
        raise ValueError('shirt correction lacks exact sourced identity/exclusive mode0 native owner')


def prepare(base):
    if (base.season, base.release_id) != ('2001-02', BASE):
        raise ValueError('Commons shirt correction requires the exact completed alias parent')
    original = sources.prepare()['positive_2001_reserve']
    package = pipeline.read_json_file(base.package_path)
    source_path = registry.ROOT / base.locator['ownership_plan_path']
    source_plan = pipeline.read_json_file(source_path)
    prior = registry.load_registered_release(base.season, source_plan['release_id'])
    alias.verify_plan(prior, source_plan)
    from scripts import season_duplicate_layered_packages_v1 as layered
    expected, english, _, _ = layered.prepare(prior, source_plan, (prior.game_path / 'DBDAT/JUG98030.FDI').read_bytes())
    if english is not None or expected != package:
        raise ValueError('actual Commons parent does not reproduce the entire alias recipe')
    player = next(p for p in package['players'] if p['carrier_id'] == 27013)
    club = next(c for c in package['clubs'] if c['id'] == player['club_id'])
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    raw = entries[27013].decode_payload(jug)
    number = original['annual']['person']['shirt_number']
    native_guard(player, club, raw, ownership.native_owners(eq), ownership.tactics.payloads(eq), number)
    return dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=digest(jug), eq_sha256=digest(eq),
        source_admission=original, alias_plan=dict(path=registry.relative_workspace_path(source_path), sha256=registry.sha256_file(source_path)),
        updates=[dict(carrier_id=27013, before_player=player, native_name=read_initial_order(raw).name,
            before_number=raw[7] ^ 0x61, number=number)], native_byte_changes=int((raw[7] ^ 0x61) != number),
        implementation_bindings=[dict(path=registry.relative_workspace_path(p), sha256=registry.sha256_file(p))
            for p in (Path(__file__), registry.ROOT / 'upstream/pm99-skezmod-db-editor/app/indexed_jug_shirt_number.py')],
        scope='Only Commons full-layout shirt header byte and explicit shirt fact. Entire alias/manager fixes, all other identities, skills, roles, order, tactics, kits and portraits preserved.')


def verify(base, plan):
    if plan.get('schema') != SCHEMA or prepare(base) != plan:
        raise ValueError('original Commons source number/native preimage does not independently reproduce')


def bind(package, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    if pipeline.read_json_file(base.package_path) != package or registry.sha256_file(base.package_path) != plan['package_sha256']:
        raise ValueError('shirt recipe preimage changed')
    result = copy.deepcopy(package)
    player = next(p for p in result['players'] if p['carrier_id'] == 27013)
    if player != plan['updates'][0]['before_player']:
        raise ValueError('shirt target exact previous player changed')
    proof = dict(artifact_id=ARTIFACT, grade='source-receipt')
    player['facts']['shirt_number'] = plan['updates'][0]['number']
    player['proof'] = proof
    player['fact_fallbacks'] = [f for f in player.get('fact_fallbacks', []) if f['field'] != 'shirt_number']
    result['artifacts'].append(dict(id=ARTIFACT, kind='season-input', media_type='application/json',
        relative_path=FILENAME, sha256=digest(packages.canonical_json_bytes(plan))))
    result['sources'].append(dict(id=ARTIFACT+'-source', title='Independently reparsed2001 Stoke Commons full-name/DOB/shirt row',
        uri=plan['source_admission']['original']['url'], proof_grade='source-receipt', evidence_artifact_id=ARTIFACT))
    result['proofs'].append(dict(id='proof-'+ARTIFACT, artifact_id=ARTIFACT, grade='source-receipt', covers=['one-source-bound-shirt-number-only']))
    for key in ('artifacts', 'sources', 'proofs'):
        result[key].sort(key=lambda r:r['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original), digest(original_eq)) != (plan['jug_sha256'], plan['eq_sha256']) or eq != original_eq:
        raise ValueError('shirt native preimage changed')
    updates = {r['carrier_id']:{k:r[k] for k in ('native_name', 'before_number', 'number')} for r in plan['updates']}
    candidate, changes = rewrite_indexed_native_shirt_numbers(original, updates)
    if len(changes) != plan['native_byte_changes'] or jug not in (original, candidate):
        raise ValueError('shirt actual byte count or pre/postimage differs')
    if rewrite_indexed_native_shirt_numbers(candidate, updates) != (candidate, []):
        raise ValueError('shirt delta is not idempotent')
    return candidate, original_eq


def reconstruction(previous, release_id):
    if pipeline.read_json_file(previous.compiler_receipt_path).get('compilation_mode') != MODE:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    if path.resolve() != (previous.package_path.parent / FILENAME).resolve():
        raise ValueError('shirt SOURCE input is not the exact release-local plan')
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited Commons recipe cannot silently drop edits in SOURCE replay')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=base.season, release_id=base.release_id, package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'], updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('shirt SOURCE inert descriptor changed')
    publisher.publish(base.season, descriptor, release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(base.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(previous.package_path):
        raise ValueError('entire Commons shirt SOURCE recipe differs')
    return dict(season=base.season, release_id=release_id, complete_game_inventory_identical=True, complete_recipe_identical=True)
