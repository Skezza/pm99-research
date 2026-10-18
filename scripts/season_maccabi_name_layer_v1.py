"""Source-bound name-only Maccabi correction, retaining every current fact.

The existing native writer and same-carrier exact-shrink inverse are reused.
No factory profile facts, whole-person replacement, arbitrary capacity growth
or inferred family truncation is permitted. This is not a factory compilation.
"""
import copy
import hashlib
import json

from bs4 import BeautifulSoup
from app.editor_actions import (
    _native_dd6360_role_start, _patch_indexed_dd6360_variable_name,
    _read_native_dd6360_fields,
)
from app.fdi_indexed import IndexedFDIFile
from app.player_name_capacity import recover_compact_name_window, stored_case_display
from scripts import season_maccabi_namesake_review_v1 as source
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_same_carrier_name_capacity_v1 as capacity

PREFIX = 'sourced-maccabi-name-only-'
FILENAME = 'sourced-maccabi-name-only.json'
SCHEMA = 'pm99-original-Maccabi-2015-name-only-layer-v1'
TARGETS = ((2027, 'Ben-Haim'), (32232, 'Tal Ben Chaim'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def records(data):
    index = IndexedFDIFile.from_bytes(data)
    entries = {e.record_id: e for e in index.entries}
    if len(entries) != len(index.entries):
        raise ValueError('ambiguous name-only native directory')
    return index, entries


def prepare(release):
    witness = source.prepare(release)
    archive = BeautifulSoup((source.SOURCE_ROOT / source.SOURCES[0][0]).read_bytes().decode('utf-8'), 'lxml')
    headings = {a.get('href'): ' '.join(a.get_text(' ', strip=True).split()) for a in archive.select('h1.entry-title a')}
    if (headings.get('https://www.maccabi-tlv.co.il/en/team/tal-ben-haim/') != 'Tal Ben Haim'
            or headings.get('https://www.maccabi-tlv.co.il/en/team/tal-ben-chaim/') != 'Tal Ben Chaim'):
        raise ValueError('original distinct full name headings differ')
    package = pipeline.read_json_file(release.package_path)
    people = {p['carrier_id']: p for p in package['players']}
    root = registry.ROOT / '.local/duplicate-ownership-v3'
    bundle = capacity.runtime_bundle(root / 'private-capacity-pilot-r1/private-pilot.json',
        root / 'capacity-runtime-pilot-evidence/factory_capacity_bugnet_profile_20261006t1457z')
    factory = capacity.verify_bundle(bundle).read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    _, before = records(jug)
    _, originals = records(factory)
    updates = []
    for id, display in TARGETS:
        p = people[id]
        if p['name'] != 'Tal' or p['source_name'] != 'Ben-Haim, Tal':
            raise ValueError('original Maccabi recipe name preimage differs')
        raw = before[id].decode_payload(jug)
        recovered, proof = recover_compact_name_window(originals[id].decode_payload(factory), raw)
        renamed, _ = _patch_indexed_dd6360_variable_name(recovered, stored_case_display(recovered), display)
        old_end, new_end = _native_dd6360_role_start(raw), _native_dd6360_role_start(renamed)
        fields = _read_native_dd6360_fields(raw, old_end)
        if fields != _read_native_dd6360_fields(renamed, new_end):
            raise ValueError('name-only native facts changed')
        # The complete old opaque suffix is retained, apart from exactly the
        # zero padding consumed by restoring the strings. No unknown tail loss.
        growth = new_end - old_end
        if growth <= 0 or raw[-growth:] != b'\x61' * growth or raw[old_end:-growth] != renamed[new_end:]:
            raise ValueError('name-only opaque suffix preservation failed')
        updates.append(dict(carrier_id=id, player_id=p['id'], before_player=copy.deepcopy(p),
            before_payload_sha256=digest(raw), after_payload_sha256=digest(renamed),
            display_name=display, recovery=proof, native_fields=fields))
    return dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), jug_sha256=digest(jug),
        source_witness=witness, capacity_bundle=bundle, updates=updates,
        scope='Exactly two source-backed display names; no DOB, role, skill, nationality, portrait, ownership or full-squad approval.')


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('name-only original-source plan no longer reproduces')


def apply(jug, plan):
    if (plan.get('schema') != SCHEMA or plan.get('season') != '2015-16'
            or tuple((r['carrier_id'], r['display_name']) for r in plan['updates']) != TARGETS):
        raise ValueError('unapproved name-only season/targets')
    factory = capacity.verify_bundle(plan['capacity_bundle']).read_bytes()
    index, entries = records(jug)
    _, originals = records(factory)
    replacements = {}
    changed = []
    for row in plan['updates']:
        id = row['carrier_id']
        raw = entries[id].decode_payload(jug)
        if digest(raw) == row['after_payload_sha256']:
            continue
        if digest(raw) != row['before_payload_sha256']:
            raise ValueError('name-only native record preimage differs')
        recovered, proof = recover_compact_name_window(originals[id].decode_payload(factory), raw)
        if proof != row['recovery']:
            raise ValueError('name-only recovery claim differs')
        renamed, _ = _patch_indexed_dd6360_variable_name(recovered, stored_case_display(recovered), row['display_name'])
        if (digest(renamed) != row['after_payload_sha256']
                or _read_native_dd6360_fields(renamed, _native_dd6360_role_start(renamed)) != row['native_fields']):
            raise ValueError('name-only native output differs')
        replacements[id] = renamed
        changed.append(id)
    if replacements and digest(jug) != plan['jug_sha256']:
        raise ValueError('name-only whole native baseline differs')
    result = compiler._rebuild_indexed(jug, index, replacements) if replacements else jug
    allowed = set()
    for id in changed:
        entry = entries[id]
        allowed.update(range(entry.payload_offset, entry.payload_offset + entry.payload_length))
    if len(result) != len(jug) or any(a != b and n not in allowed for n, (a, b) in enumerate(zip(jug, result))):
        raise ValueError('name-only delta changed another record or native directory')
    return result


def bind(package, plan):
    result = copy.deepcopy(package)
    people = {p['id']: p for p in result['players']}
    for row in plan['updates']:
        p = people[row['player_id']]
        if p != row['before_player']:
            raise ValueError('name-only recipe preimage differs')
        p['name'] = row['display_name']
    id = PREFIX + plan['season']
    if any(a['id'] == id for a in result['artifacts']):
        raise ValueError('name-only recipe layer already present')
    result['artifacts'].append(dict(id=id, kind='season-input', relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('name-only recipe requires source-bound pm99-season build reconstruction; factory compilation must not silently discard the name layer')


def reconstruction(previous, release_id):
    if getattr(previous, 'season', None) != '2015-16':
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    package = pipeline.read_json_file(previous.package_path)
    artifacts = [a for a in package['artifacts'] if a['id'].startswith(PREFIX)]
    if not artifacts:
        return None
    if len(artifacts) != 1 or artifacts[0]['relative_path'] != FILENAME:
        raise ValueError('name-only rebuild requires one exact local layer')
    path = previous.package_path.parent / FILENAME
    if registry.sha256_file(path) != artifacts[0]['sha256']:
        raise ValueError('name-only replay source artifact changed')
    plan = pipeline.read_json_file(path)
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path), plan)) != packages.canonical_json_bytes(package):
        raise ValueError('edited recipe cannot use exact name-only replay; no edits discarded')
    descriptor_path = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor_path) != expected:
        raise ValueError('name-only replay baseline descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        name_only_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, reused=False,
        compilation_mode='source-bound-name-only-known-good-reconstruction-not-factory-compile')
