"""Repair year-only serializer omissions from original period biographies.

An immutable DOB can be witnessed in another season, but an exact full name
must have one unanimous birthday across every captured original. Conflicting
people, incorrect recipe dates, aliases, and shared/native mode1 carriers stop.
No recipe fact, name, role, rating or asset changes in this narrow layer.
"""
import copy
from datetime import date
import hashlib
import sys

from app.fdi_indexed import IndexedFDIFile
from scripts import audit_compiled_player_birth_dates_v1 as readback
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_number_label_names_v2 as names
from scripts import season_opening_order_repair_v1 as order
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_sourced_birth_years_v1 as old

POLICY = 'original-cross-period-exact-full-name-unanimous-literal-DOB-year-only-v1'
PREFIX = 'sourced-cross-period-birth-years-'
FILENAME = 'sourced-cross-period-birth-years.json'
apply = old.apply


def prepare(release):
    package = pipeline.read_json_file(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
    from player_birth_year_guard import patch_native_birth_year_guard
    if patch_native_birth_year_guard(exe)[0] != exe:
        raise ValueError('cross-period birthdays need the installed executable guard')
    failures = readback.inspect(package, jug)['failures']
    people = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    wanted = {names.literal_name(names.undecorated(people[f['carrier_id']]['name'])) for f in failures}
    by_name, evidence, source_bindings = {}, {}, []
    for season in registry.supported_seasons():
        captures, bindings = audit.load_sources(season)
        checker = audit.SourceVerifier(season, source_bindings=bindings)
        source_bindings.append(dict(season=season, bindings=bindings))
        for capture in captures:
            matches = [p for p in capture['players'] if names.literal_name(names.undecorated(p['name'])) in wanted]
            if not matches:
                continue
            proof = checker.verify(capture)
            if proof['status'] != 'raw-source-reparsed':
                continue
            key = hashlib.sha256(pipeline.canonical_json_bytes(dict(season=season, capture=capture))).hexdigest()
            evidence[key] = dict(source_season=season, capture=capture, raw_proof=proof)
            for person in matches:
                name = names.literal_name(names.undecorated(person['name']))
                by_name.setdefault(name, []).append(dict(evidence_key=key, source_player=person,
                    exact_name_rows_in_capture=sum(names.literal_name(names.undecorated(p['name'])) == name
                        for p in capture['players']), approves_current_club_ownership=False))
    owners = order.native_owners(eq)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for failure in failures:
        person = people[failure['carrier_id']]
        carrier, club = person['carrier_id'], clubs[person['club_id']]
        target = date.fromisoformat(person['facts']['birth_date'])
        raw = entries[carrier].decode_payload(jug)
        native = audit.native_player(raw, carrier)
        end = native['name_end']
        before = dict(year=int.from_bytes(bytes(b ^ 0x61 for b in raw[end+14:end+16]), 'little'),
            month=raw[end+13] ^ 0x61, day=raw[end+12] ^ 0x61)
        row = dict(player_id=person['id'], carrier_id=carrier, name=person['name'],
            source_name=names.undecorated(person['name']), native_name=native['name'],
            club_id=club['id'], club_carrier_id=club['carrier_id'],
            birth_date=target.isoformat(), before_components=before)
        witnesses = by_name.get(names.literal_name(row['source_name']), [])
        dates = {w['source_player'].get('birth_date') for w in witnesses
            if isinstance(w['source_player'].get('birth_date'), str)}
        if (dates != {target.isoformat()} or any(w['exact_name_rows_in_capture'] != 1 for w in witnesses)
                or not witnesses):
            unresolved.append(dict(row, reason='no unanimous exact original biography; wrong recipe/aliases stay open'))
        elif (club['division'] == 'preserve-existing-mode1-membership' or raw[2:5] != b'\xdd\x63\x61'
                or owners.get(carrier) != {club['carrier_id']}
                or names.literal_name(native['name']) != names.literal_name(person['name'])
                or not 1900 <= before['year'] < 2000 <= target.year
                or (before['month'], before['day']) != (target.month, target.day)):
            unresolved.append(dict(row, reason='outside exact exclusive modern-year-only native scope'))
        else:
            updates.append(dict(row, witnesses=[w for w in witnesses
                if w['source_player'].get('birth_date') == target.isoformat()]))
    for path, original in ((release.game_path / 'DBDAT/JUG98030.FDI', jug),
            (release.game_path / 'DBDAT/EQ98030.FDI', eq), (release.game_path / 'MANAGPRE.EXE', exe)):
        if registry.sha256_file(path) != hashlib.sha256(original).hexdigest():
            raise ValueError('cross-period original native input changed')
    if pipeline.read_json_file(release.package_path) != package:
        raise ValueError('cross-period recipe input changed')
    for source in source_bindings:
        if audit.load_sources(source['season'])[1] != source['bindings']:
            raise ValueError('cross-period original capture set changed')
    for item in evidence.values():
        proof = item['raw_proof']
        if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
            raise ValueError('cross-period original biography bytes changed')
    return dict(schema_version='pm99-sourced-cross-period-birth-year-repair-v1', policy=POLICY,
        season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), jug_sha256=hashlib.sha256(jug).hexdigest(),
        eq_sha256=hashlib.sha256(eq).hexdigest(), exe_sha256=hashlib.sha256(exe).hexdigest(),
        source_bindings=source_bindings, evidence=evidence, updates=updates, unresolved=unresolved,
        scope='Two native birth-year bytes only; original cross-period DOB biography is not current roster/name/role/ratings/photo approval')


def verify(release, plan):
    if plan.get('policy') != POLICY or prepare(release) != plan:
        raise ValueError('cross-period original biography/native plan did not reproduce')


def bind(package, plan):
    result = copy.deepcopy(package)
    identifier = PREFIX + plan['season']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('cross-period birthday proof layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=FILENAME,
        media_type='application/json', sha256=hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest()))
    result['artifacts'].sort(key=lambda a: a['id'])
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('cross-period biography recipe requires source-bound reconstruction; factory compilation must not discard its proof')


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
    if path.resolve() != (previous.package_path.parent / FILENAME).resolve() or registry.sha256_file(path) != receipt['birth_year_plan_sha256']:
        raise ValueError('cross-period birthday replay source path/hash differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited cross-period recipe cannot use exact replay; no edits discarded')
    control = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(control) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('cross-period birthday replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, control, release_id=release_id,
        birth_year_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('complete cross-period replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-cross-period-biographic-year-known-good-reconstruction-not-factory-compile')
