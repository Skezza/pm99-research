"""Remove shirt labels/placeholder initials without changing player facts.

Both indexed families retain their string lengths, surname component, complete
suffix and all directory bytes. Original labels remain in the bound plan. This
formatting layer establishes neither historical identity nor roster ownership.
"""
import copy
import hashlib
import re
import unicodedata

from app.editor_actions import _indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_disk_budget_v1 as disk_budget

SCHEMA = 'pm99-numeric-player-display-format-only-v1'
FILENAME = 'sourced-numeric-name-format-only-v1.json'
PREFIX = 'sourced-numeric-name-format-only-v1-'
MODE = 'known-good-baseline-numeric-player-display-format-only-v1'
NUMBER = re.compile(r'^#\s*\d{1,3}\s+')
INITIAL = re.compile(r'^#\.\s*')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def literal(value):
    return unicodedata.normalize('NFC', ' '.join(value.split())).casefold()


def clean(value):
    return INITIAL.sub('', NUMBER.sub('', value)).strip()


def source_label(value):
    """Keep existing source spellings/aliases; remove only their own label."""
    if value is None or not (NUMBER.match(value) or INITIAL.match(value)):
        return value
    return clean(value) or value


def renamed_payload(raw, row):
    if raw[2:5] not in (b'\xdd\x63\x60', b'\xdd\x63\x61'):
        raise ValueError('numeric formatting requires a known indexed family')
    before = audit.native_player(raw, row['carrier_id'])
    if before['name'] != row['before_native_name']:
        raise ValueError('numeric formatting native name preimage differs')
    if not (NUMBER.match(before['name']) or INITIAL.match(before['name'])):
        raise ValueError('numeric formatting has no exact leading label')
    segments = _indexed_variable_name_runtime_segments(raw)
    start, end = segments['full_name_start'], segments['full_name_end']
    if segments['first_len_offset'] != 8:
        raise ValueError('numeric formatting requires the indexed prefix')
    surname = raw[segments['surname_start']:segments['surname_end']].decode('cp1252')
    if re.match(r'^#(?:\.|\s*\d)', surname):
        raise ValueError('numeric label also affects the protected surname component')
    old = raw[start:end].decode('cp1252')
    text = clean(old)
    if not text or literal(text) != literal(row['display_name']):
        raise ValueError('numeric formatting changes the remaining name text')
    encoded = text.encode('cp1252')
    removed = end - start - len(encoded)
    if not 0 < removed <= 8:
        raise ValueError('numeric formatting exceeds the exact label window')
    changed = raw[:start] + encoded + b' ' * removed + raw[end:]
    after = audit.native_player(changed, row['carrier_id'])
    if (len(changed) != len(raw) or changed[:start] != raw[:start]
            or changed[end:] != raw[end:] or after['name_end'] != before['name_end']
            or literal(after['name']) != literal(row['display_name'])):
        raise ValueError('numeric formatting changed a cursor, suffix or person text')
    return changed, dict(full_name_start=start, full_name_end=end,
        removed_label_bytes=removed, payload_length_unchanged=True,
        surname_header_and_complete_suffix_unchanged=True,
        padding='trailing-ASCII-space-inside-existing-full-display-window')


def prepare(release):
    package = pipeline.read_json_file(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for player in package['players']:
        if not (NUMBER.match(player['name']) or INITIAL.match(player['name'])):
            continue
        carrier = player['carrier_id']
        try:
            raw = entries[carrier].decode_payload(jug)
            before = audit.native_player(raw, carrier)
            if literal(before['name']) != literal(player['name']):
                raise ValueError('recipe/native display preimages disagree')
            display = clean(player['name'])
            if not display:
                raise ValueError('label has no remaining published name')
            row = dict(carrier_id=carrier, player_id=player['id'],
                before_player=copy.deepcopy(player), before_native_name=before['name'],
                display_name=display,
                source_name=source_label(player.get('source_name')),
                source_name_policy='Remove only the exact leading label from this same source field; retain its existing spelling/alias and original raw before_player. No source/display identity equivalence is asserted.',
                before_payload_sha256=digest(raw))
            changed, metadata = renamed_payload(raw, row)
            row.update(after_payload_sha256=digest(changed), name_metadata=metadata)
            updates.append(row)
        except (ValueError, KeyError, UnicodeError) as exc:
            unresolved.append(dict(player_id=player['id'], carrier_id=carrier, reason=str(exc)))
    plan = dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), jug_sha256=digest(jug),
        updates=updates, unresolved=unresolved,
        scope='Exact leading shirt-number/placeholder display labels only; no identity, ownership, DOB, role, rating, nationality, order, portrait, kit or historical correctness assertion. Original raw labels retained in before_player/native preimages.')
    if updates:
        plan['after_jug_sha256'] = digest(apply(jug, plan))
    return plan


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('numeric formatting source/native plan no longer reproduces')


def apply(jug, plan):
    if plan.get('schema') != SCHEMA or not plan.get('updates'):
        raise ValueError('numeric formatting schema, scope or whole baseline differs')
    actual_hash = digest(jug)
    if actual_hash == plan.get('after_jug_sha256'):
        return jug
    if actual_hash != plan['jug_sha256']:
        raise ValueError('numeric formatting whole baseline differs')
    index = IndexedFDIFile.from_bytes(jug)
    entries = {e.record_id: e for e in index.entries}
    replacements, allowed = {}, set()
    for row in plan['updates']:
        carrier = row['carrier_id']
        if carrier in replacements:
            raise ValueError('numeric formatting repeats a carrier')
        entry = entries[carrier]
        raw = entry.decode_payload(jug)
        if digest(raw) != row['before_payload_sha256']:
            raise ValueError('numeric formatting payload preimage differs')
        changed, metadata = renamed_payload(raw, row)
        if digest(changed) != row['after_payload_sha256'] or metadata != row['name_metadata']:
            raise ValueError('numeric formatting payload postimage differs')
        replacements[carrier] = changed
        allowed.update(range(entry.payload_offset + metadata['full_name_start'],
                             entry.payload_offset + metadata['full_name_end']))
    result = compiler._rebuild_indexed(jug, index, replacements)
    if len(result) != len(jug) or any(a != b and n not in allowed for n, (a, b) in enumerate(zip(jug, result))):
        raise ValueError('numeric formatting changed another field, record or directory')
    return result


def bind(package, plan):
    result = copy.deepcopy(package)
    people = {p['id']: p for p in result['players']}
    for row in plan['updates']:
        player = people[row['player_id']]
        if player != row['before_player']:
            raise ValueError('numeric formatting recipe preimage differs')
        player['name'] = row['display_name']
        if 'source_name' in player:
            player['source_name'] = row['source_name']
    identifier = PREFIX + plan['season']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('numeric formatting layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=FILENAME,
        media_type='application/json', sha256=digest(pipeline.canonical_json_bytes(plan))))
    result['artifacts'].sort(key=lambda a: a['id'])
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('numeric display formatting requires source-bound known-good replay; factory compilation must not discard it')


def reconstruction(previous, release_id, *, minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    disk_budget.validate_reserve(minimum_free_bytes)
    relative = getattr(previous, 'locator', {}).get('sourced_player_name_only_plan_path')
    if not relative:
        return None
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if (plan.get('schema') != SCHEMA or path.resolve() != (previous.package_path.parent / FILENAME).resolve()
            or registry.sha256_file(path) != receipt['original_name_only_plan_sha256']):
        raise ValueError('numeric formatting replay path/hash differs')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited formatting recipe cannot replay an older package')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('numeric formatting replay baseline descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id,
        name_only_plan_path=path, source_release_id=baseline.release_id,
        minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('numeric formatting complete replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode=MODE)
