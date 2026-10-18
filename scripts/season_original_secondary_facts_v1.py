"""Narrow original-source birthday/default and nationality corrections.

No roster, skills, roles, current-club facts or portraits are authorised. Full
namesakes are refused. A full DOB may replace ONLY an explicit deterministic
recipe default; nationality and compact year repairs require an exact-DOB
original period squad row. Year repairs never alter recipe facts.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
import sys

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import season_original_person_birth_years_v1 as original
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_2015_english92_release import _country_code
from scripts import season_package_compiler_v2 as compiler

SCHEMA = 'pm99-original-entity-explicit-secondary-fact-delta-v1'
PREFIX = 'sourced-original-secondary-facts-'
MODE = 'known-good-baseline-original-secondary-fact-delta'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return 'original-secondary-facts-' + plan['transaction_id'] + '.json'


def prepare(release, person_document_path, targets, *, identity_document_path=None):
    path = Path(person_document_path)
    source_sha = registry.sha256_file(path)
    doc = pipeline.read_json_file(path)
    original.biographies.merge({}, doc)
    for binding in doc['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT / binding['path']) != binding['sha256']:
            raise ValueError('secondary-fact original person query changed')
    if not targets or any(not str(k).isdigit() or not v or set(v) - {'birth_date', 'nationality', 'native_birth_year'}
            or len(v) != len(set(v)) or ('native_birth_year' in v and len(v) != 1)
            for k, v in targets.items()):
        raise ValueError('explicit unique birthday/nationality target fields required')
    if len(targets) != len(set(int(k) for k in targets)) or any(int(k) < 1 for k in targets):
        raise ValueError('duplicate target carrier aliases')
    targets = {str(int(k)): sorted(v) for k, v in targets.items()}
    identity_binding, independent_namesakes = None, {}
    if identity_document_path is not None:
        from scripts.original_namesake_birthday_witness_v1 import load
        identity_path = Path(identity_document_path)
        identity_binding = dict(path=registry.relative_workspace_path(identity_path),
            sha256=registry.sha256_file(identity_path))
        independent_namesakes = load(identity_path)
        allowed_country=lambda k,v: (v==['nationality'] and independent_namesakes.get(int(k),{}).get('exact_period_nationality')=='BRA'
            and independent_namesakes[int(k)].get('single_name_alias_verified')
            and independent_namesakes[int(k)].get('source_period')==release.season)
        if set(independent_namesakes) != {int(k) for k in targets} or any(v not in (['birth_date'],['native_birth_year']) and not allowed_country(k,v) for k,v in targets.items()):
            raise ValueError('explicit independent biography scope must match birthday-only targets')
    package = pipeline.read_json_file(release.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
    from player_birth_year_guard import patch_native_birth_year_guard
    if patch_native_birth_year_guard(exe)[0] != exe:
        raise ValueError('secondary-fact correction needs installed executable date guard')
    owners = original.order.native_owners(eq)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    codes = compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
    sources, source_bindings = original.audit.load_sources(release.season)
    verifier = original.audit.SourceVerifier(release.season)
    persons = [p for b in doc['batches'] for p in b['people']]
    updates, unresolved = [], []
    for key, fields in sorted(targets.items(), key=lambda item: int(item[0])):
        carrier = int(key)
        player = players[carrier]
        club = clubs[player['club_id']]
        raw = entries[carrier].decode_payload(jug)
        native = original.audit.native_player(raw, carrier)
        name = original.names.undecorated(player.get('source_name') or player['name'])
        candidates = [p for p in persons if original.audit.normalise(p['name']) == original.audit.normalise(name)]
        identity_witness = independent_namesakes.get(carrier)
        if identity_witness is not None:
            if (original.audit.normalise(identity_witness['name']) != original.audit.normalise(name)
                    or original.audit.normalise(identity_witness['historical_club']) != original.audit.normalise(club['name'])):
                raise ValueError('independent namesake biography names another recipe player')
            candidates = [p for p in candidates if p['birth_date'] == identity_witness['birth_date']]
        if (len(candidates) != 1 or (len(name.split()) < 2 and not (identity_witness or {}).get('single_name_alias_verified'))
                or any(len(word.rstrip('.')) == 1 for word in name.split())
                or owners.get(carrier) != {club['carrier_id']}
                or player.get('policy') == 'preserve-existing-mode1'
                or original.names.literal_name(native['name']) != original.names.literal_name(player['name'])):
            unresolved.append(dict(carrier_id=carrier, reason='ambiguous full name, whole-record fallback or non-exclusive native ownership'))
            continue
        person = candidates[0]
        end = native['name_end']
        before_dob = date(int.from_bytes(bytes(b ^ 0x61 for b in raw[end+14:end+16]), 'little'),
            raw[end+13] ^ 0x61, raw[end+12] ^ 0x61).isoformat()
        row = dict(carrier_id=carrier, native_name=native['name'], before_player=copy.deepcopy(player),
            before_birth_date=before_dob, source_person=copy.deepcopy(person), fields=fields,
            before_nationality_code=raw[end+8] ^ 0x61)
        accepted = True
        if identity_witness is not None:
            period_evidence = []
            direct_period=(identity_witness.get('source_period')==release.season
                           and isinstance(identity_witness.get('period_person_source_id'),int))
            if direct_period:
                if identity_witness['period_person_source_id']!=person['source_player_id']:
                    raise ValueError('exact original period person ID differs from selected biography')
                period_evidence.append(dict(original_player=dict(name=identity_witness['name'],
                    birth_date=identity_witness['birth_date'],source_player_id=identity_witness['period_person_source_id']),
                    raw_proof=dict(status='raw-source-reparsed',local_path=identity_witness['original_binding']['path'],
                        source_sha256=identity_witness['original_binding']['sha256']),
                    source_period=identity_witness['source_period']))
            for source in sources:
                if (original.audit.source_group(source['country_catalog']) != original.audit.club_group(club)
                        or original.audit.normalise(source['club_name']) != original.audit.normalise(club['name'])):
                    continue
                matching = [p for p in source['players']
                    if original.audit.normalise(p['name']) == original.audit.normalise(name)]
                if not matching:
                    continue
                proof = verifier.verify(source)
                if proof['status'] != 'raw-source-reparsed' or len(matching) != 1:
                    accepted = False
                    continue
                if matching[0].get('birth_date') not in (None, identity_witness['birth_date']):
                    accepted = False
                period_evidence.append(dict(original_player=matching[0], raw_proof=proof))
            if not period_evidence:
                accepted = False
            row['independent_namesake_resolution'] = dict(biography=identity_witness,
                original_same_season_club_rows=period_evidence,
                policy='unique API full-name/DOB agreeing with an independently reparsed biography and exact original season-club name; no youngest/current-club selection')
        if 'native_birth_year' in fields:
            target = date.fromisoformat(person['birth_date'])
            before = date.fromisoformat(before_dob)
            if (person['birth_date'] != player['facts']['birth_date']
                    or raw[2:5] not in (b'\xdd\x63\x60', b'\xdd\x63\x61')
                    or not 1900 <= before.year < 2000 <= target.year
                    or (before.month, before.day) != (target.month, target.day)
                    or any(f['field'] == 'birth_date' for f in player.get('fact_fallbacks', []))):
                accepted = False
            evidence, dates = [], set()
            if identity_witness is not None and direct_period:
                evidence=copy.deepcopy(period_evidence)
                dates={identity_witness['birth_date']}
            for source in ([] if identity_witness is not None and direct_period else sources):
                matching = [p for p in source['players']
                    if original.audit.normalise(p['name']) == original.audit.normalise(name)]
                if not matching:
                    continue
                proof = verifier.verify(source)
                if proof['status'] != 'raw-source-reparsed':
                    continue
                if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
                    raise ValueError('compact birthday original period bytes changed')
                dates.update(p.get('birth_date') for p in matching)
                if len(matching) != 1:
                    accepted = False
                evidence.append(dict(source_club=source['club_name'], original_players=matching,
                    raw_proof=proof, approves_current_club_ownership=False))
            if dates != {target.isoformat()} or not evidence:
                accepted = False
            row.update(birth_date=target.isoformat(), birth_year_evidence=evidence)
        if 'birth_date' in fields:
            fallbacks = [f for f in player.get('fact_fallbacks', []) if f['field'] == 'birth_date']
            opening = date(int(release.season[:4]), 8, 1)
            born = date.fromisoformat(person['birth_date'])
            age = (opening - born).days / 365.2425
            if (len(fallbacks) != 1 or fallbacks[0].get('method') != 'deterministic-default'
                    or fallbacks[0].get('value') != player['facts']['birth_date']
                    or player['facts']['birth_date'] != '2000-07-01' or not 14 <= age <= 50):
                accepted = False
            row['birth_date'] = person['birth_date']
        if 'nationality' in fields:
            evidence, values = [], set()
            if person['birth_date'] != player['facts']['birth_date'] or before_dob != person['birth_date']:
                accepted = False
            direct_country=(identity_witness is not None and direct_period
                and identity_witness.get('exact_period_nationality')=='BRA')
            if direct_country:
                values.add('BRA')
                evidence=copy.deepcopy(period_evidence)
            for source in ([] if direct_country else sources):
                matching = [p for p in source['players']
                    if original.audit.normalise(p['name']) == original.audit.normalise(name)
                    and p.get('birth_date') == person['birth_date']]
                if not matching:
                    continue
                proof = verifier.verify(source)
                if proof['status'] != 'raw-source-reparsed' or len(matching) != 1:
                    accepted = False
                    continue
                labels = matching[0].get('nationalities') or [matching[0].get('nationality')]
                values.update(facts.country(label) for label in labels)
                evidence.append(dict(source_club=source['club_name'], original_player=matching[0], raw_proof=proof,
                    approves_current_club_ownership=False))
            if len(values) != 1 or None in values or not evidence:
                accepted = False
            else:
                code = next(iter(values))
                native_code = _country_code(code, codes)
                if native_code == codes['XXX'] or native_code == row['before_nationality_code']:
                    accepted = False
                row.update(nationality=code, native_country_code=native_code, nationality_evidence=evidence)
        if accepted:
            updates.append(row)
        else:
            unresolved.append(dict(carrier_id=carrier, reason='not an explicit supported default or unique exact-DOB period nationality source'))
    for p, raw in ((release.game_path / 'DBDAT/JUG98030.FDI', jug),
            (release.game_path / 'DBDAT/EQ98030.FDI', eq), (release.game_path / 'MANAGPRE.EXE', exe)):
        if registry.sha256_file(p) != digest(raw):
            raise ValueError('secondary-fact native input changed')
    if pipeline.read_json_file(release.package_path) != package or registry.sha256_file(path) != source_sha:
        raise ValueError('secondary-fact recipe or entity document changed')
    transaction_inputs = dict(people=source_sha, targets=targets)
    if identity_binding is not None:
        if registry.sha256_file(identity_path) != identity_binding['sha256']:
            raise ValueError('independent namesake biography document changed')
        transaction_inputs['independent_namesake_biographies'] = identity_binding
    transaction = digest(pipeline.canonical_json_bytes(transaction_inputs))[:12]
    result = dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(package)),
        jug_sha256=digest(jug), eq_sha256=digest(eq), exe_sha256=digest(exe),
        original_person_document=dict(path=registry.relative_workspace_path(path), sha256=source_sha),
        targets=targets, transaction_id=transaction, period_source_bindings=source_bindings,
        updates=updates, unresolved=unresolved,
        scope='Only selected exact birthdays/one-byte nationalities and corresponding recipe facts/default declarations; no ownership, roles, skills, heights, weights, portraits or other file approval.')
    if any('native_birth_year' in r['fields'] for r in updates):
        result['scope'] += ' Explicit native_birth_year targets change only two native year bytes and no recipe facts.'
    if identity_binding is not None:
        result['independent_namesake_biography_document'] = identity_binding
    return result


def verify(release, plan):
    binding = plan['original_person_document']
    path = registry.ROOT / binding['path']
    identity = plan.get('independent_namesake_biography_document')
    kwargs = {}
    if identity is not None:
        identity_path = registry.ROOT / identity['path']
        if registry.sha256_file(identity_path) != identity['sha256']:
            raise ValueError('independent namesake biography document changed')
        kwargs['identity_document_path'] = identity_path
    if (plan.get('schema') != SCHEMA or registry.sha256_file(path) != binding['sha256']
            or prepare(release, path, plan['targets'], **kwargs) != plan):
        raise ValueError('original secondary-fact source/native plan did not reproduce')


def apply(jug, eq, plan):
    if plan.get('schema') != SCHEMA or digest(eq) != plan['eq_sha256']:
        raise ValueError('secondary-fact schema or whole-club preimage differs')
    baseline = registry.load_registered_release(plan['season'], plan['release_id'])
    before = (baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before) != plan['jug_sha256'] or not plan['updates']:
        raise ValueError('secondary-fact immutable baseline changed or empty update')
    dates = {r['carrier_id']: r for r in plan['updates']
        if 'birth_date' in r['fields'] or 'native_birth_year' in r['fields']}
    for row in dates.values():
        if 'native_birth_year' in row['fields']:
            old, new = date.fromisoformat(row['before_birth_date']), date.fromisoformat(row['birth_date'])
            if (row['fields'] != ['native_birth_year']
                    or (old.month, old.day) != (new.month, new.day)
                    or row['birth_date'] != row['before_player']['facts']['birth_date']):
                raise ValueError('native year-only scope cannot alter day, month or recipe birthday')
    countries = {r['carrier_id']: r['native_country_code'] for r in plan['updates'] if 'nationality' in r['fields']}
    if len({r['carrier_id'] for r in plan['updates']}) != len(plan['updates']):
        raise ValueError('duplicate secondary-fact carriers')
    after, _ = rewrite_indexed_native_birth_dates(before, dates)
    after, _ = rewrite_indexed_native_nationalities(after, countries)
    if jug not in (before, after):
        raise ValueError('secondary-fact whole native preimage/postimage differs')
    return after, eq


def bind(package, plan):
    if plan.get('schema') != SCHEMA or digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('secondary-fact whole recipe preimage differs')
    result = copy.deepcopy(package)
    seen = set()
    for row in plan['updates']:
        actual = [p for p in result['players'] if p['carrier_id'] == row['carrier_id']]
        if actual != [row['before_player']] or row['carrier_id'] in seen:
            raise ValueError('secondary-fact exact recipe person preimage differs')
        seen.add(row['carrier_id'])
        for field in row['fields']:
            if field == 'native_birth_year':
                continue
            actual[0]['facts'][field] = row['birth_date'] if field == 'birth_date' else row['nationality']
        if 'fact_fallbacks' in actual[0]:
            actual[0]['fact_fallbacks'] = [f for f in actual[0]['fact_fallbacks'] if f['field'] not in row['fields']]
    identifier = PREFIX + plan['season'] + '-' + plan['transaction_id']
    if any(a['id'] == identifier for a in result['artifacts']):
        raise ValueError('secondary-fact proof layer already exists')
    result['artifacts'].append(dict(id=identifier, kind='season-input', relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('original secondary-fact recipe requires SOURCE reconstruction; factory compile must not discard its proof')


def reconstruction(previous, release_id):
    locator = getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path')
    if not locator:
        return None
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    path = registry.ROOT / locator
    plan = pipeline.read_json_file(path)
    if (plan.get('schema') != SCHEMA or path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(path) != receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('secondary-fact replay source binding differs')
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    expected = bind(pipeline.read_json_file(base.package_path), plan)
    if expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited secondary-fact recipe cannot use exact replay; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=previous.season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]):
        raise ValueError('secondary-fact replay descriptor differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=base.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('complete secondary-fact replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=base.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode='source-bound-original-secondary-facts-known-good-reconstruction-not-factory-compile')
