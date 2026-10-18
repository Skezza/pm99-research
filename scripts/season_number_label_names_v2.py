"""Bounded current-release numeric-label/name repairs with original biographies.

This is not the old clean-compile name repair. Retain all native suffix bytes,
except a separately declared source-proven modern birth-year omission, and keep
every non-target player, database, portrait, kit and recipe fact unchanged.
"""
import copy
from datetime import date
import hashlib
import re
import unicodedata

from app.editor_actions import _indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_opening_order_repair_v1 as order
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

SCHEMA = 'pm99-original-biographic-numeric-label-fixed-display-window-delta-v3'
PREFIX = 'sourced-original-number-labels-v3-'
FILENAME = 'sourced-original-number-labels-v3.json'
NUMBER = re.compile(r'^#\s*\d{1,3}\s+')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def literal_name(value):
    return unicodedata.normalize('NFC', ' '.join(value.split())).casefold()


def undecorated(value):
    return NUMBER.sub('', value).strip()


def renamed_payload(raw, row):
    before = audit.native_player(raw, row['carrier_id'])
    if before['name'] != row['before_native_name'] or raw[2:5] != b'\xdd\x63\x61':
        raise ValueError('number-label exact native name/family differs')
    if not NUMBER.match(before['name']) or literal_name(undecorated(before['name'])) != literal_name(row['display_name']):
        raise ValueError('numeric-label target changes the actual person name')
    # Keep BOTH string lengths and every suffix/footer cursor fixed. Appending
    # zero padding at the record end is UNSAFE for dd6361: the stat trailer is
    # relative to the following biography boundary. Use harmless trailing
    # ASCII spaces inside the existing full-display window instead.
    segments = _indexed_variable_name_runtime_segments(raw)
    start, end = segments['full_name_start'], segments['full_name_end']
    original = raw[start:end].decode('cp1252')
    cleaned = undecorated(original).encode('cp1252')
    removed = end - start - len(cleaned)
    if not 0 < removed <= 8 or literal_name(cleaned.decode('cp1252')) != literal_name(row['display_name']):
        raise ValueError('numeric-label removal is not the exact bounded original full-name prefix')
    result = bytearray(raw)
    result[start:end] = cleaned + b' ' * removed
    renamed = bytes(result)
    after = audit.native_player(renamed, row['carrier_id'])
    old_end, new_end = before['name_end'], after['name_end']
    if raw[old_end:] != renamed[new_end:]:
        raise ValueError('numeric-label name writer changed a native suffix')
    if literal_name(after['name']) != literal_name(row['display_name']):
        raise ValueError('numeric-label full name did not round-trip')
    if old_end != new_end or raw[:start] != renamed[:start]:
        raise ValueError('numeric-label repair changed a string/header/footer cursor')
    metadata = dict(original_surname_component_preserved=True, old_name_end=old_end,
        new_name_end=new_end, old_payload_length=len(raw), new_payload_length=len(renamed),
        payload_length_delta=0, name_end_delta=0, full_display_padding='trailing-ASCII-space-inside-original-window',
        removed_prefix_bytes=removed, scope='Full display text only; surname/lengths/footer cursors fixed')
    result = bytearray(renamed)
    if row['repair_birth_year']:
        born = date.fromisoformat(row['birth_date'])
        old_year = int.from_bytes(bytes(b ^ 0x61 for b in raw[old_end+14:old_end+16]), 'little')
        if not 1900 <= old_year < 2000 <= born.year or old_year != row['before_birth_year']:
            raise ValueError('numeric-label year repair is not the declared modern-year omission')
        if (result[new_end+12] ^ 0x61, result[new_end+13] ^ 0x61) != (born.day, born.month):
            raise ValueError('numeric-label biography would change day/month')
        result[new_end+14:new_end+16] = bytes(b ^ 0x61 for b in born.year.to_bytes(2, 'little'))
    if len(result) != len(raw):
        raise ValueError('numeric-label repair resized the carrier')
    return bytes(result), metadata


def prepare(release):
    package = pipeline.read_json_file(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = order.native_owners(eq)
    clubs = {c['id']: c for c in package['clubs']}
    captures, bindings = audit.load_sources(release.season)
    checker = audit.SourceVerifier(release.season, source_bindings=bindings)
    by_name = {}
    for capture in captures:
        for person in capture['players']:
            by_name.setdefault(literal_name(undecorated(person['name'])), []).append((capture, person))
    updates, unresolved, evidence = [], [], {}
    for person in package['players']:
        if not NUMBER.match(person['name']):
            continue
        carrier, club = person['carrier_id'], clubs[person['club_id']]
        label = dict(carrier_id=carrier, name=person['name'])
        birthday = person['facts'].get('birth_date')
        if (club['division'] == 'preserve-existing-mode1-membership' or not isinstance(birthday, str)
                or owners.get(carrier) != {club['carrier_id']}):
            unresolved.append(dict(label, reason='outside exclusive literal-biography mode0 scope'))
            continue
        target = undecorated(person['name'])
        candidates = by_name.get(literal_name(target), [])
        known_dates = {p.get('birth_date') for _, p in candidates if isinstance(p.get('birth_date'), str)}
        # Different biographies and multiple same-name rows in one original
        # source are not disambiguated by a numeric heading or a name guess.
        capture_counts = {}
        for capture, _ in candidates:
            key = digest(pipeline.canonical_json_bytes(capture))
            capture_counts[key] = capture_counts.get(key, 0) + 1
        if known_dates != {birthday} or any(n != 1 for n in capture_counts.values()):
            unresolved.append(dict(label, reason='missing or ambiguous original exact-name/DOB biography'))
            continue
        witnesses = []
        for capture, source in candidates:
            if source.get('birth_date') != birthday:
                continue
            proof = checker.verify(capture)
            if proof['status'] != 'raw-source-reparsed':
                continue
            key = digest(pipeline.canonical_json_bytes(capture))
            evidence[key] = dict(capture=capture, raw_proof=proof)
            witnesses.append(dict(evidence_key=key, source_player=source,
                original_raw_name=source['name'], approves_current_club_ownership=False))
        if not witnesses:
            unresolved.append(dict(label, reason='original exact-name/DOB raw source did not reparse'))
            continue
        raw = entries[carrier].decode_payload(jug)
        native = audit.native_player(raw, carrier)
        end, born = native['name_end'], date.fromisoformat(birthday)
        old_year = int.from_bytes(bytes(b ^ 0x61 for b in raw[end+14:end+16]), 'little')
        if (raw[2:5] != b'\xdd\x63\x61' or literal_name(native['name']) != literal_name(person['name'])
                or (raw[end+12] ^ 0x61, raw[end+13] ^ 0x61) != (born.day, born.month)
                or (old_year != born.year and not (1900 <= old_year < 2000 <= born.year))):
            unresolved.append(dict(label, reason='native biography/name is outside bounded suffix/year scope'))
            continue
        row = dict(carrier_id=carrier, player_id=person['id'], before_player=copy.deepcopy(person),
            before_native_name=native['name'], display_name=target, source_name=undecorated(witnesses[0]['original_raw_name']),
            birth_date=birthday, before_birth_year=old_year, repair_birth_year=old_year != born.year,
            witnesses=witnesses, before_payload_sha256=digest(raw))
        changed, metadata = renamed_payload(raw, row)
        row.update(after_payload_sha256=digest(changed), name_metadata=metadata)
        updates.append(row)
    if any(row['repair_birth_year'] for row in updates):
        import sys
        sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
        from player_birth_year_guard import patch_native_birth_year_guard
        exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
        if patch_native_birth_year_guard(exe)[0] != exe:
            raise ValueError('source-proven modern birthday needs the installed executable guard')
    if (pipeline.read_json_file(release.package_path) != package
            or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != digest(jug)
            or registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI') != digest(eq)
            or audit.load_sources(release.season)[1] != bindings):
        raise ValueError('numeric-label source/native inputs changed while planning')
    for item in evidence.values():
        proof = item['raw_proof']
        if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
            raise ValueError('numeric-label original raw source changed while planning')
    return dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), jug_sha256=digest(jug), eq_sha256=digest(eq),
        exe_sha256=registry.sha256_file(release.game_path / 'MANAGPRE.EXE'), source_bindings=bindings,
        updates=updates, unresolved=unresolved, evidence=evidence,
        scope='Source-proven numeric-name label removal plus explicitly declared native year-only omissions. Recipe facts, suffix roles/skills, other native records, clubs/managers/tactics, EXE and images unchanged. Biography is not opening-roster ownership approval.')


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release) != plan:
        raise ValueError('numeric-label original identity/native plan did not reproduce')


def apply(jug, plan):
    if plan.get('schema') != SCHEMA or not plan.get('updates'):
        raise ValueError('numeric-label empty or wrong-schema plan')
    index = IndexedFDIFile.from_bytes(jug)
    entries = {e.record_id: e for e in index.entries}
    replacements = {}
    seen = set()
    for row in plan['updates']:
        carrier = row['carrier_id']
        if carrier in seen:
            raise ValueError('repeated numeric-label carrier')
        seen.add(carrier)
        raw = entries[carrier].decode_payload(jug)
        if digest(raw) == row['after_payload_sha256']:
            continue
        if digest(raw) != row['before_payload_sha256']:
            raise ValueError('numeric-label native preimage differs')
        changed, metadata = renamed_payload(raw, row)
        if digest(changed) != row['after_payload_sha256'] or metadata != row['name_metadata']:
            raise ValueError('numeric-label native postimage differs')
        replacements[carrier] = changed
    if replacements and digest(jug) != plan['jug_sha256']:
        raise ValueError('numeric-label whole native baseline differs')
    result = compiler._rebuild_indexed(jug, index, replacements) if replacements else jug
    allowed = set()
    for carrier in replacements:
        entry = entries[carrier]
        allowed.update(range(entry.payload_offset, entry.payload_offset + entry.payload_length))
    if len(result) != len(jug) or any(a != b and n not in allowed for n, (a, b) in enumerate(zip(jug, result))):
        raise ValueError('numeric-label delta changed another record/directory')
    return result


def bind(package, plan):
    result = copy.deepcopy(package)
    people = {p['id']: p for p in result['players']}
    for row in plan['updates']:
        person = people[row['player_id']]
        if person != row['before_player']:
            raise ValueError('numeric-label recipe person preimage differs')
        person['name'], person['source_name'] = row['display_name'], row['source_name']
    identifier = PREFIX + plan['season']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('numeric-label recipe layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=FILENAME,
        media_type='application/json', sha256=digest(pipeline.canonical_json_bytes(plan))))
    result['artifacts'].sort(key=lambda a: a['id'])
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith('sourced-original-number-labels-') for a in package.get('artifacts', [])):
        raise ValueError('numeric-label identity recipe requires source-bound known-good replay; factory compilation must not discard it')


def reconstruction(previous, release_id):
    relative = getattr(previous, 'locator', {}).get('sourced_player_name_only_plan_path')
    if not relative:
        return None
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != 'known-good-baseline-original-numeric-label-name-year-delta':
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if (plan.get('schema') != SCHEMA or path.resolve() != (previous.package_path.parent / FILENAME).resolve()
            or registry.sha256_file(path) != receipt['original_name_only_plan_sha256']):
        raise ValueError('numeric-label replay source path/hash differs')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited numeric-label recipe cannot use exact replay; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('numeric-label replay baseline descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id,
        name_only_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('numeric-label complete replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-original-numeric-label-known-good-reconstruction-not-factory-compile')
