"""Source-proven birth years are biography, not opening-club ownership.

An exact original full-name/DOB witness from another club can establish the
same immutable birthday. It does NOT approve the current roster membership.
Ambiguous names/dates, number-prefixed names and shared native owners stop.
"""
import copy
from datetime import date
import hashlib
import sys

from app.fdi_indexed import IndexedFDIFile
from scripts import audit_compiled_player_birth_dates_v1 as readback
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_opening_order_repair_v1 as order
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_sourced_birth_years_v1 as old

POLICY = 'original-exact-full-name-unanimous-DOB-biography-not-club-ownership-v1'
PREFIX = 'sourced-biographic-birth-years-'
FILENAME = 'sourced-biographic-birth-years.json'
apply = old.apply


def unique_date_witnesses(captures, name, birthday):
    candidates = []
    dates = set()
    for capture in captures:
        matches = [p for p in capture.get('players', []) if audit.normalise(p['name']) == audit.normalise(name)]
        if len(matches) > 1:
            return []
        for person in matches:
            value = person.get('birth_date')
            if isinstance(value, str):
                dates.add(value)
                if value == birthday:
                    candidates.append((capture, person))
    return candidates if dates == {birthday} else []


def prepare(release):
    sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
    from player_birth_year_guard import patch_native_birth_year_guard
    exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    if patch_native_birth_year_guard(exe)[0] != exe:
        raise ValueError('modern birthdays need the already verified executable guard')
    package = pipeline.read_json_file(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = order.native_owners(eq)
    people = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    captures, bindings = audit.load_sources(release.season)
    checker = audit.SourceVerifier(release.season, source_bindings=bindings)
    updates, unresolved, evidence = [], [], {}
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    for failure in readback.inspect(package, jug)['failures']:
        person = people[failure['carrier_id']]
        club = clubs[person['club_id']]
        birthday = person['facts'].get('birth_date')
        target = date.fromisoformat(birthday)
        if target.year < 2000 or club['division'] == 'preserve-existing-mode1-membership':
            continue
        carrier = person['carrier_id']
        name = person.get('source_name') or person['name']
        native = audit.native_player(entries[carrier].decode_payload(jug), carrier)
        payload = entries[carrier].decode_payload(jug)
        end = native['name_end']
        before = dict(year=int.from_bytes(bytes(v ^ 0x61 for v in payload[end+14:end+16]), 'little'),
            month=payload[end+13] ^ 0x61, day=payload[end+12] ^ 0x61)
        row = dict(player_id=person['id'], carrier_id=carrier, name=person['name'],
            source_name=name, native_name=native['name'], club_id=club['id'],
            club_carrier_id=club['carrier_id'], birth_date=birthday, before_components=before)
        if (name.startswith('#') or payload[2:5] != b'\xdd\x63\x61'
                or owners.get(carrier) != {club['carrier_id']}
                or audit.normalise(native['name']) != audit.normalise(person['name'])
                or not 1900 <= before['year'] < 2000
                or (before['month'], before['day']) != (target.month, target.day)):
            unresolved.append(dict(row, reason='outside exact-exclusive-name-year-only biography scope'))
            continue
        witnesses = []
        for capture, source in unique_date_witnesses(captures, name, birthday):
            proof = checker.verify(capture)
            if proof['status'] != 'raw-source-reparsed':
                continue
            key = hashlib.sha256(pipeline.canonical_json_bytes(capture)).hexdigest()
            evidence[key] = dict(capture=capture, raw_proof=proof)
            witnesses.append(dict(evidence_key=key, source_player=source,
                biography_source_club=capture['club_name'], approves_current_club_ownership=False))
        if not witnesses:
            unresolved.append(dict(row, reason='no unambiguous independently reparsed exact full-name/DOB'))
        else:
            updates.append(dict(row, witnesses=witnesses))
    for path, raw in [(release.game_path / 'MANAGPRE.EXE', exe),
            (release.game_path / 'DBDAT/JUG98030.FDI', jug), (release.game_path / 'DBDAT/EQ98030.FDI', eq)]:
        if registry.sha256_file(path) != hashlib.sha256(raw).hexdigest():
            raise ValueError('biographic plan native input changed')
    if pipeline.read_json_file(release.package_path) != package or audit.load_sources(release.season)[1] != bindings:
        raise ValueError('biographic plan source/recipe input changed')
    for item in evidence.values():
        proof = item['raw_proof']
        if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
            raise ValueError('original birthday source changed during planning')
    return dict(schema_version='pm99-sourced-biographic-birth-year-repair-v1', policy=POLICY,
        season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        jug_sha256=hashlib.sha256(jug).hexdigest(), eq_sha256=hashlib.sha256(eq).hexdigest(),
        exe_sha256=hashlib.sha256(exe).hexdigest(), source_bindings=bindings,
        evidence=evidence, updates=updates, unresolved=unresolved,
        scope='Two native year bytes only. Original biography evidence does not approve current roster ownership, names, roles, ratings, portraits or other facts.')


def verify(release, plan):
    if plan.get('policy') != POLICY or prepare(release) != plan:
        raise ValueError('original biographic birth-year plan did not reproduce')


def bind(package, plan):
    result = copy.deepcopy(package)
    identifier = PREFIX + plan['season']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('biographic birthday layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=FILENAME,
        media_type='application/json', sha256=hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest()))
    result['artifacts'].sort(key=lambda a: a['id'])
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('biographic year recipe requires source-bound pm99-season build reconstruction; factory compilation must not silently discard its original-source proof')


def reconstruction(previous, release_id):
    path = getattr(previous, 'locator', {}).get('sourced_birth_year_plan_path')
    if not path:
        return None
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != 'known-good-baseline-original-sourced-modern-birth-year-delta':
        return None
    path = registry.ROOT / path
    plan = pipeline.read_json_file(path)
    if plan.get('policy') != POLICY:
        return None
    if (path.resolve() != (previous.package_path.parent / FILENAME).resolve()
            or registry.sha256_file(path) != receipt['birth_year_plan_sha256']):
        raise ValueError('biographic replay source path/hash differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts import season_package_v2 as packages
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if packages.canonical_json_bytes(expected) != packages.canonical_json_bytes(pipeline.read_json_file(previous.package_path)):
        raise ValueError('edited biographic recipe cannot use exact replay; no edits discarded')
    control = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(control) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('biographic replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, control, release_id=release_id,
        birth_year_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(expected):
        raise ValueError('complete biographic replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-biographic-year-known-good-reconstruction-not-factory-compile')
