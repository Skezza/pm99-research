"""Year-only native repair from independently replayed original person entities.

This is biography evidence, NOT opening-club membership clearance. Full names
may differ only by the game's existing accent/case/punctuation normalisation;
initials, surname-only guesses, conflicting DOBs and shared owners are refused.
No recipe birthday, display name, role, skill, portrait or other fact changes.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
import re
import sys

from app.fdi_indexed import IndexedFDIFile
from scripts import audit_compiled_player_birth_dates_v1 as readback
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_number_label_names_v2 as names
from scripts import season_opening_order_repair_v1 as order
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as biographies
from scripts import season_sourced_birth_years_v1 as old

POLICY = 'original-person-entity-full-name-confirmed-DOB-exclusive-year-only-v1'
PREFIX = 'sourced-original-person-birth-years-'
FILENAME = 'sourced-original-person-birth-years.json'
apply = old.apply


def witnesses(document, full_name, birthday):
    wanted = audit.normalise(names.undecorated(full_name))
    matches = [person for batch in document['batches'] for person in batch['people']
               if audit.normalise(person['name']) == wanted]
    if (len(matches) != 1 or matches[0]['birth_date'] != birthday
            or len(names.undecorated(full_name).split()) < 2
            or any(len(word.rstrip('.')) == 1 for word in names.undecorated(full_name).split())):
        return []
    return [dict(source_person=copy.deepcopy(matches[0]),
                 name_policy='full-name-only-existing-game-normalisation-no-initial-expansion',
                 approves_current_club_ownership=False)]


def artifact_id(plan):
    suffix = '-' + plan['transaction_id'] if plan.get('transaction_id') else ''
    return PREFIX + plan['season'] + suffix


def filename(plan):
    return FILENAME.replace('.json', '-' + plan['transaction_id'] + '.json') if plan.get('transaction_id') else FILENAME


def prepare(release, person_document_path, *, transaction_id=None):
    person_document_path = Path(person_document_path)
    source_hash = registry.sha256_file(person_document_path)
    if transaction_id is not None and (not isinstance(transaction_id, str)
            or not re.fullmatch(r'[a-f0-9]{12}', transaction_id) or transaction_id != source_hash[:12]):
        raise ValueError('birthday transaction ID must be the bound biography hash prefix')
    document = pipeline.read_json_file(person_document_path)
    biographies.merge({}, document)  # Independently reparse raw URL/SHA-bound entities.
    for binding in document['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT / binding['path']) != binding['sha256']:
            raise ValueError('original person query input changed')
    package = pipeline.read_json_file(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
    from player_birth_year_guard import patch_native_birth_year_guard
    if patch_native_birth_year_guard(exe)[0] != exe:
        raise ValueError('original-person birthdays need the installed executable guard')
    people = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    owners = order.native_owners(eq)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for failure in readback.inspect(package, jug)['failures']:
        person = people[failure['carrier_id']]
        carrier, club = person['carrier_id'], clubs[person['club_id']]
        birthday = person['facts']['birth_date']
        target = date.fromisoformat(birthday)
        raw = entries[carrier].decode_payload(jug)
        native = audit.native_player(raw, carrier)
        end = native['name_end']
        before = dict(year=int.from_bytes(bytes(b ^ 0x61 for b in raw[end+14:end+16]), 'little'),
                      month=raw[end+13] ^ 0x61, day=raw[end+12] ^ 0x61)
        row = dict(player_id=person['id'], carrier_id=carrier, name=person['name'],
            source_name=names.undecorated(person.get('source_name') or person['name']),
            native_name=native['name'], club_id=club['id'], club_carrier_id=club['carrier_id'],
            birth_date=birthday, before_components=before)
        witness = witnesses(document, row['source_name'], birthday)
        if not witness:
            unresolved.append(dict(row, reason='no unique independently published full-name/DOB; wrong recipe dates and namesakes remain open'))
        elif (club['division'] == 'preserve-existing-mode1-membership' or raw[2:5] != b'\xdd\x63\x61'
                or owners.get(carrier) != {club['carrier_id']}
                or names.literal_name(native['name']) != names.literal_name(person['name'])
                or not 1900 <= before['year'] < 2000 <= target.year
                or (before['month'], before['day']) != (target.month, target.day)):
            unresolved.append(dict(row, reason='outside exact exclusive modern-year-only native scope'))
        else:
            updates.append(dict(row, witnesses=witness))
    for path, original in ((release.game_path / 'DBDAT/JUG98030.FDI', jug),
            (release.game_path / 'DBDAT/EQ98030.FDI', eq), (release.game_path / 'MANAGPRE.EXE', exe)):
        if registry.sha256_file(path) != hashlib.sha256(original).hexdigest():
            raise ValueError('original-person native input changed')
    if (pipeline.read_json_file(release.package_path) != package
            or registry.sha256_file(person_document_path) != source_hash):
        raise ValueError('original-person recipe or biography changed')
    result = dict(schema_version='pm99-original-person-birth-year-repair-v1', policy=POLICY,
        season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path), jug_sha256=hashlib.sha256(jug).hexdigest(),
        eq_sha256=hashlib.sha256(eq).hexdigest(), exe_sha256=hashlib.sha256(exe).hexdigest(),
        original_person_document=dict(path=registry.relative_workspace_path(person_document_path), sha256=source_hash),
        updates=updates, unresolved=unresolved,
        scope='Only two native birth-year bytes; no roster/role/name/skills/asset approval or recipe-date change.')
    if transaction_id is not None:
        result['transaction_id'] = transaction_id
    return result


def verify(release, plan):
    binding = plan['original_person_document']
    path = registry.ROOT / binding['path']
    if (plan.get('policy') != POLICY or registry.sha256_file(path) != binding['sha256']
            or prepare(release, path, transaction_id=plan.get('transaction_id')) != plan):
        raise ValueError('original person/native birth-year plan did not reproduce')


def bind(package, plan):
    result = copy.deepcopy(package)
    identifier = artifact_id(plan)
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('original-person birthday proof layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=filename(plan),
        media_type='application/json', sha256=hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest()))
    result['artifacts'].sort(key=lambda a: a['id'])
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('original-person biography recipe requires source-bound reconstruction; factory compilation must not discard its proof')


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
    if (path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(path) != receipt['birth_year_plan_sha256']):
        raise ValueError('original-person replay source path/hash differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    expected = bind(pipeline.read_json_file(baseline.package_path), plan)
    if expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited biography recipe cannot use exact replay; no edits discarded')
    control = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(control) != dict(season=previous.season, release_id=baseline.release_id,
            package_sha256=registry.sha256_file(baseline.package_path),
            jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('original-person birthday replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, control, release_id=release_id,
        birth_year_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('complete original-person replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-original-person-year-known-good-reconstruction-not-factory-compile')
