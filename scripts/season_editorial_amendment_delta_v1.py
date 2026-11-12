"""Generic, baseline-preserving editorial field amendments over a registered game.

One plan type for every season and every person: the user's workbook cell edits
(rating, broad position, manager name and a few scalar facts) become a byte-scoped
delta over the exact known-good parent release. Nothing is rebuilt from a clean
base; unknown bytes, identities, rosters, tactics, kits, photos and the calendar
stay exactly as the parent had them. Human edits are labelled as such, never as
source evidence. The plan is pure data derived from (parent, request), so
``verify`` simply re-derives it and SOURCE reconstruction is exact.
"""
import collections
import copy
import hashlib
from datetime import date

from app.fdi_indexed import IndexedFDIFile
from app.ent_manager_profiles import parse_indexed_ent_manager_profile, replace_indexed_ent_manager_names
from app.indexed_jug_birth_date import rewrite_indexed_native_birth_dates
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from app.indexed_jug_profile_fields import rewrite_indexed_native_profile_fields
from app.xor import xor_decode, xor_encode
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_quality_only_delta_v1 as quality
from scripts import season_exact_fifa_role_delta_v1 as fifa
from scripts import season_disk_budget_v1 as disk_budget
from scripts import season_editorial_field_policy_v1 as policy
from tools import season_manifest_amendments as amendments

SCHEMA = 'pm99-editorial-field-amendment-delta-v1'
PREFIX = 'editorial-field-amendments-'
SOURCE_PREFIX = 'editorial-amendment-'
MODE = 'known-good-baseline-editorial-field-amendments-v1'
SCOPE = ('Only the declared player rating/broad-position/nationality/DOB/height/weight/shirt bytes (with explicit '
         'dependent fine-role bytes when the broad position changes) and declared ENT manager-name segments; every '
         'other native byte, identity, roster, tactic, kit, photo, calendar and executable byte is the parent\'s.')
# Fine roles that stay coherent with a changed broad position. Existing compatible
# roles keep their order; only when none remain does this fixed editorial default apply.
DEFAULT_FINE_ROLES = {'D': [4, 5], 'M': [9], 'F': [12]}
HEIGHT_RANGE, WEIGHT_RANGE = (50, 250), (40, 140)
_CACHE = collections.OrderedDict()
CACHE_LIMIT = 2          # each entry pins full native images, so keep very few


def _source_fingerprint(base):
    """Everything a derived plan depends on: recipe, the three databases, country table and the birth-year guard flag."""
    game = base.game_path / 'DBDAT'
    return (base.release_id, base.manifest_sha256, registry.sha256_file(base.package_path),
            *(registry.sha256_file(game / n) for n in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'TEXTOS.PKF')),
            bool(base.locator.get('sourced_birth_year_plan_path')))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return packages.canonical_json_bytes(value)


def filename(plan):
    return 'editorial-amendments-' + plan['transaction_id'] + '.json'


def artifact_id(plan):
    return PREFIX + plan['transaction_id']


def source_id(plan):
    return SOURCE_PREFIX + plan['transaction_id']


def make_request(document, changes, *, origin):
    """Reduce workbook amendment rows to the minimal canonical request (full-document SHA stays bound)."""
    rows = [dict(id=c['id'], json_pointer=c['json_pointer'], expected=c['expected'], set=c['set'],
                 reason=c['reason'], evidence=c['evidence']) for c in changes]
    return dict(origin=origin, revision_id=document['revision_id'], season=document['season'],
                amendment_sha256=digest(canonical(document)), changes=rows)


# --- native readers -------------------------------------------------------

def _entries(jug):
    return {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}


def _offsets(payload, carrier):
    native = roster.native_player(payload, carrier)
    end, family = native['name_end'], native['family']
    rating_start = end + 18 if family == 'dd6360' else len(payload) - 16
    return native, end, family, rating_start


def _native_values(payload, carrier):
    native, end, family, rating_start = _offsets(payload, carrier)
    v = lambda offset: payload[offset] ^ 0x61
    try:
        born = date(v(end + 14) | (v(end + 15) << 8), v(end + 13), v(end + 12)).isoformat()
    except ValueError:
        born = None
    return dict(family=family, end=end, position=native['position'], roles=[r for r in native['roles'] if r != 98],
                nationality_code=v(end + 8), birth_date=born, height_cm=v(end + 16), weight_kg=v(end + 17),
                shirt_number=payload[7] ^ 0x61,
                ratings={k: v(rating_start + i) for i, k in enumerate(policy.RATING_KEYS)}, name=native['name'])


def _clean_int(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be a whole number from {low} to {high}')
    return value


def _check_manager_name(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or any(not c.isprintable() for c in value):
        raise ValueError('manager name must be non-empty printable text without surrounding spaces')
    try:
        if len(value.encode('cp1252')) > 120:
            raise ValueError('manager name is too long for the native name segment (120 bytes)')
    except UnicodeEncodeError as exc:
        raise ValueError('manager name has characters the game font/codepage cannot store') from exc
    return value


_PARTICLES = frozenset('de den der di da del della van von ten ter le la el al bin ben dos das do du'.split())
_SUFFIXES = frozenset(('jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv'))


def _short_name(name):
    """The game's short manager name: surname with its particles, ASCII-folded like existing records."""
    import unicodedata
    tokens = [t for t in name.split() if t.lower() not in _SUFFIXES] or name.split()
    start = len(tokens) - 1
    while start > 1 and tokens[start - 1].lower() in _PARTICLES:
        start -= 1
    short = ' '.join(tokens[start:])
    return unicodedata.normalize('NFKD', short).encode('ascii', 'ignore').decode('ascii') or short


def _derive_native_names(old, new_name):
    surname = _short_name(new_name)
    display = surname if old['display_name'] == old['surname'] else new_name
    return dict(display_name=display, surname=surname)


# --- plan derivation ------------------------------------------------------

def _derive(base, request):
    key = (base.season, base.release_id, digest(canonical(request)))
    fingerprint = _source_fingerprint(base)        # re-hashed on every call, so a cache hit can never outlive its preimage
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == fingerprint:
        _CACHE.move_to_end(key)
        return copy.deepcopy(hit[1]), hit[2], hit[3]
    _CACHE.pop(key, None)
    if not isinstance(request, dict) or set(request) != {'origin', 'revision_id', 'season', 'amendment_sha256', 'changes'}:
        raise ValueError('amendment request is malformed')
    if request['season'] != base.season or not request['changes']:
        raise ValueError('amendment request must name this season and at least one change')
    package = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    ent = (base.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    countries = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    entries = _entries(jug)
    by_player, by_manager = {}, {}
    seen = set()
    for change in request['changes']:
        pointer = change['json_pointer']
        kind, index, field = policy.classify(pointer)
        if pointer in seen:
            raise ValueError(f'duplicate amendment target {pointer}')
        seen.add(pointer)
        parent, final = pointer.rsplit('/', 1)
        rows = package['players'] if kind != 'manager-name' else package['managers']
        if index >= len(rows):
            raise ValueError(f'{pointer} does not exist in the parent recipe (stale index)')
        row = rows[index]
        actual = amendments.value_at(package, pointer)
        if actual != change['expected']:
            raise ValueError(f'stale amendment {change["id"]}: the parent recipe now holds {actual!r}, not {change["expected"]!r}')
        if change['set'] == actual:
            raise ValueError(f'amendment {change["id"]} does not change {pointer}')
        target = by_manager if kind == 'manager-name' else by_player
        target.setdefault(index, {})[field] = change
    updates, changed_jug, changed_payloads = [], {}, {}
    for index, edits in sorted(by_player.items()):
        player = package['players'][index]
        facts = player.get('facts', {})
        # Gate each edited field on its own record format; untouched unknown/preserved facts stay exactly as they are.
        for field_name, edit in sorted(edits.items()):
            kind_name = 'player-rating' if field_name in policy.RATING_KEYS else 'player-fact'
            reason = policy.record_reason(kind_name, player, field_name, edit['set'])
            if reason:
                raise ValueError(f'{player.get("name")}: {reason}')
        carrier = player['carrier_id']
        if carrier not in entries:
            raise ValueError(f'{player["name"]}: native carrier {carrier} is absent')
        payload = entries[carrier].decode_payload(jug)
        if payload[2:5].hex() not in ('dd6360', 'dd6361'):
            raise ValueError(f'{player["name"]}: unproved native player family')
        before = _native_values(payload, carrier)
        fields, dependent = [], []
        rating_edits, write = {}, {}
        for field, change in sorted(edits.items()):
            new = change['set']
            pointer = change['json_pointer']
            fields.append(dict(pointer=pointer, field=field, before=change['expected'], after=new))
            if field in policy.RATING_KEYS:
                rating_edits[field] = _clean_int(new, 1, 99, f'{player["name"]} {field}')
                if before['ratings'][field] != change['expected']:
                    raise ValueError(f'{player["name"]}: recipe {field} {change["expected"]} differs from the game\'s {before["ratings"][field]}')
            elif field == 'primary_position':
                if new not in ('D', 'M', 'F') or change['expected'] not in ('D', 'M', 'F'):
                    raise ValueError(f'{player["name"]}: goalkeeper conversions are not supported; use outfield D/M/F only')
                if before['family'] != 'dd6361' or before['position'] != change['expected']:
                    raise ValueError(f'{player["name"]}: broad position is writable only for full dd6361 players that agree with the recipe')
                write['position'] = new
            elif field == 'nationality':
                code = compiler._country_code(new, countries)
                if code == countries['XXX']:
                    raise ValueError(f'{player["name"]}: nationality {new!r} is not representable in this game')
                if compiler._country_code(change['expected'], countries) != before['nationality_code']:
                    raise ValueError(f'{player["name"]}: recipe nationality differs from the game')
                write['nationality'] = code
            elif field == 'birth_date':
                try:
                    born = date.fromisoformat(new)
                except (TypeError, ValueError):
                    raise ValueError(f'{player["name"]}: birth date must be YYYY-MM-DD')
                limit = 2100 if base.locator.get('sourced_birth_year_plan_path') else 1999
                if not 1930 <= born.year <= limit:
                    raise ValueError(f'{player["name"]}: birth year must be 1930-{limit} for this release')
                if before['birth_date'] != change['expected']:
                    raise ValueError(f'{player["name"]}: recipe birth date differs from the game')
                write['birth_date'] = born.isoformat()
            elif field == 'shirt_number':
                _clean_int(new, 1, 99, f'{player["name"]} shirt')
                if before['family'] != 'dd6361' or before['shirt_number'] != change['expected']:
                    raise ValueError(f'{player["name"]}: shirt numbers are writable only for full dd6361 players that agree with the recipe')
                clash = [p['name'] for p in package['players'] if p is not player and p['club_id'] == player['club_id']
                         and p.get('facts', {}).get('shirt_number') == new]
                if clash:
                    raise ValueError(f'{player["name"]}: shirt {new} is already worn by {clash[0]} at this club')
                write['shirt_number'] = new
            elif field in ('height_cm', 'weight_kg'):
                low, high = HEIGHT_RANGE if field == 'height_cm' else WEIGHT_RANGE
                _clean_int(new, low, high, f'{player["name"]} {field}')
                if before[field] != change['expected']:
                    raise ValueError(f'{player["name"]}: recipe {field} differs from the game')
                write[field] = new
        if 'position' in write:
            new_position = write['position']
            old_roles = before['roles']
            recipe_roles = facts.get('fine_roles')
            if recipe_roles != old_roles:
                raise ValueError(f'{player["name"]}: recipe fine roles differ from the game; refusing an incoherent position edit')
            kept = [r for r in old_roles if fifa.compatible(new_position, r)]
            roles = kept or list(DEFAULT_FINE_ROLES[new_position])
            dependent.append(dict(field='fine_roles', before=old_roles, after=roles,
                reason='broad position changed; fine roles must stay compatible (kept compatible roles, else fixed default)'))
            write['roles'] = roles
        updates.append(dict(player_id=player['id'], carrier_id=carrier, person_id=player.get('person_id'), name=player['name'],
            club_id=player['club_id'], recipe_index=index, family=before['family'], fields=fields, dependent_changes=dependent,
            ratings_after={**before['ratings'], **rating_edits} if rating_edits else None, write=write))
    # --- apply with the existing, individually guarded native writers
    candidate = jug
    for row in updates:
        carrier, write = row['carrier_id'], row['write']
        payload = _entries(candidate)[carrier].decode_payload(candidate)
        native_row = {}
        if row['ratings_after']:
            native_row['ratings'] = dict(values=row['ratings_after'])
        if 'nationality' in write:
            native_row['nationality'] = row['fields'][[f['field'] for f in row['fields']].index('nationality')]['after']
        if native_row:
            patched = quality.record_patch(payload, carrier, native_row, countries)
            idx = IndexedFDIFile.from_bytes(candidate)
            candidate = compiler._rebuild_indexed(candidate, idx, {carrier: patched})
        if 'roles' in write:
            candidate, _ = rewrite_indexed_native_roles(candidate, {carrier: write['roles']})
        if 'birth_date' in write:
            before_born = _native_values(payload, carrier)['birth_date']
            candidate, _ = rewrite_indexed_native_birth_dates(candidate, {carrier: dict(
                native_name=_native_values(payload, carrier)['name'], before_birth_date=before_born, birth_date=write['birth_date'])})
        if 'shirt_number' in write:
            current = _native_values(payload, carrier)
            candidate, _ = rewrite_indexed_native_shirt_numbers(candidate, {carrier: dict(
                native_name=current['name'], before_number=current['shirt_number'], number=write['shirt_number'])})
        byte_edits = {k: write[k] for k in ('position', 'height_cm', 'weight_kg') if k in write}
        if byte_edits:
            candidate = _write_profile_bytes(candidate, carrier, byte_edits)
    # --- audit: only declared bytes of declared records differ; record exact bytes in the plan
    old_entries, new_entries = _entries(jug), _entries(candidate)
    if old_entries.keys() != new_entries.keys():
        raise ValueError('player directory changed')
    declared = {row['carrier_id'] for row in updates}
    for carrier in old_entries:
        a, b = old_entries[carrier].decode_payload(jug), new_entries[carrier].decode_payload(candidate)
        if carrier not in declared and a != b:
            raise ValueError(f'unrelated native player {carrier} changed')
    for row in updates:
        a = old_entries[row['carrier_id']].decode_payload(jug)
        b = new_entries[row['carrier_id']].decode_payload(candidate)
        if len(a) != len(b):
            raise ValueError('native player length changed')
        row['native_bytes'] = [dict(index=i, before=x ^ 0x61, after=y ^ 0x61) for i, (x, y) in enumerate(zip(a, b)) if x != y]
        row['native_after'] = {k: v for k, v in _native_values(b, row['carrier_id']).items() if k != 'end'}
        row.pop('write')
    manager_updates, candidate_ent = _derive_managers(base, package, by_manager, ent)
    for row in updates:
        row['ratings_after'] = row['ratings_after'] or None
    plan = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        release_manifest_sha256=base.manifest_sha256, package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=digest(jug), eq_sha256=digest(eq), ent_sha256=digest(ent), request=request,
        updates=updates, manager_updates=manager_updates, scope=SCOPE,
        provenance='human-editorial-amendment-from-local-workbook-not-source-evidence')
    plan['transaction_id'] = digest(canonical(plan))[:24]
    _CACHE[key] = (fingerprint, copy.deepcopy(plan), candidate, candidate_ent)
    while len(_CACHE) > CACHE_LIMIT:
        _CACHE.popitem(last=False)
    return plan, candidate, candidate_ent


def _write_profile_bytes(source, carrier, edits):
    """Delegate native offsets/writes to the canonical editor library."""
    payload = _entries(source)[carrier].decode_payload(source)
    before = _native_values(payload, carrier)
    fields = {}
    for field, value in edits.items():
        old = before[field]
        if field == 'position':
            old, value = compiler.POSITION[old], compiler.POSITION[value]
        fields[field] = dict(before=old, after=value)
    candidate, _ = rewrite_indexed_native_profile_fields(source, {
        carrier: dict(native_name=before['name'], fields=fields)})
    return candidate


def _derive_managers(base, package, by_manager, ent):
    rows, replacements = [], {}
    if not by_manager:
        return rows, ent
    index = IndexedFDIFile.from_bytes(ent)
    entries = {e.record_id: e for e in index.entries}
    for idx, edits in sorted(by_manager.items()):
        manager = package['managers'][idx]
        change = edits['name']
        reason = policy.record_reason('manager-name', manager, 'name')
        if reason:
            raise ValueError(f'{manager.get("name")}: {reason}')
        new = _check_manager_name(change['set'])
        carrier = manager['carrier_id']
        if carrier not in entries:
            raise ValueError(f'manager carrier {carrier} is absent from ENT')
        raw = xor_encode(entries[carrier].decode_payload(ent))
        profile = parse_indexed_ent_manager_profile(raw, record_id=carrier)
        old = dict(display_name=profile.display_name, surname=profile.surname)
        if old != manager['native_names']:
            raise ValueError(f'{manager["name"]}: recipe native names differ from the game ENT record')
        names = _derive_native_names(old, new)
        if profile.format == 'surname_only':
            names = dict(display_name=names['surname'], surname=names['surname'])
        updated = replace_indexed_ent_manager_names(raw, record_id=carrier, expected_surname=old['surname'],
            expected_display_name=old['display_name'], surname=names['surname'], display_name=names['display_name'])
        replacements[carrier] = xor_decode(updated)
        rows.append(dict(manager_id=manager['id'], carrier_id=carrier, recipe_index=idx, pointer=change['json_pointer'],
            before_name=manager['name'], after_name=new, before_native_names=old, after_native_names=names,
            native_format=profile.format))
    candidate = compiler._rebuild_indexed(ent, index, replacements)
    after = {e.record_id: e for e in IndexedFDIFile.from_bytes(candidate).entries}
    if after.keys() != entries.keys() or any(after[i].decode_payload(candidate) != e.decode_payload(ent)
                                              for i, e in entries.items() if i not in replacements):
        raise ValueError('unrelated ENT record changed')
    return rows, candidate


def prepare(base, request):
    plan, _jug, _ent = _derive(base, request)
    return plan


def verify(base, plan):
    if plan.get('schema') != SCHEMA or canonical(prepare(base, plan['request'])) != canonical(plan):
        raise ValueError('editorial amendment sources/preimage no longer reproduce')


def bind(package, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    if registry.sha256_file(base.package_path) != plan['package_sha256'] or pipeline.read_json_file(base.package_path) != package:
        raise ValueError('editorial amendment recipe preimage differs')
    result = copy.deepcopy(package)
    players = {p['id']: p for p in result['players']}
    aid, sid = artifact_id(plan), source_id(plan)
    for row in plan['updates']:
        player = players[row['player_id']]
        for field in row['fields']:
            name = field['field']
            if name in policy.RATING_KEYS:
                if player['ratings']['values'][name] != field['before']:
                    raise ValueError('editorial rating preimage differs')
                player['ratings']['values'][name] = field['after']
            else:
                if player['facts'][name] != field['before']:
                    raise ValueError('editorial fact preimage differs')
                player['facts'][name] = field['after']
                player['fact_fallbacks'] = [f for f in player.get('fact_fallbacks', []) if f['field'] != name]
                if not player['fact_fallbacks']:
                    player.pop('fact_fallbacks')
        for dep in row['dependent_changes']:
            if player['facts']['fine_roles'] != dep['before']:
                raise ValueError('editorial fine-role preimage differs')
            player['facts']['fine_roles'] = list(dep['after'])
            player['fact_fallbacks'] = [f for f in player.get('fact_fallbacks', []) if f['field'] != 'fine_roles']
            if not player['fact_fallbacks']:
                player.pop('fact_fallbacks')
        if any(f['field'] in policy.RATING_KEYS for f in row['fields']):
            player['ratings']['provenance'] = dict(method='human-editorial-amendment-v1',
                proof_grade='reviewed-editorial', source_ids=[sid])
    managers = {m['id']: m for m in result['managers']}
    for row in plan['manager_updates']:
        manager = managers[row['manager_id']]
        if manager['name'] != row['before_name'] or manager['native_names'] != row['before_native_names']:
            raise ValueError('editorial manager preimage differs')
        manager['name'] = row['after_name']
        manager['native_names'] = dict(row['after_native_names'])
    result['artifacts'].append(dict(id=aid, kind='season-input', relative_path=filename(plan),
        sha256=digest(canonical(plan)), media_type='application/json'))
    result['sources'].append(dict(id=sid, title='Human editorial amendment from the local workbook (not source evidence)',
        proof_grade='reviewed-editorial', evidence_artifact_id=aid))
    result['artifacts'].sort(key=lambda a: a['id'])
    result['sources'].sort(key=lambda s: s['id'])
    packages.validate_package(result)
    return result


def _checked_against(base, plan):
    return _checked(base, plan)


def _checked(base, plan, jug=None, ent=None):
    original_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_ent = (base.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    if digest(original_jug) != plan['jug_sha256'] or digest(original_ent) != plan['ent_sha256']:
        raise ValueError('editorial native preimage differs')
    rebuilt, candidate_jug, candidate_ent = _derive(base, plan['request'])
    if canonical(rebuilt) != canonical(plan):
        raise ValueError('editorial amendment plan no longer reproduces from its request')
    return original_jug, candidate_jug, original_ent, candidate_ent


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original, candidate, _, _ = _checked(base, plan)
    if digest((base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()) != plan['eq_sha256'] or digest(eq) != plan['eq_sha256']:
        raise ValueError('editorial EQ preimage differs')
    if jug not in (original, candidate):
        raise ValueError('editorial amendment requires exact whole native pre/postimage')
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    preserve_other_records(original, candidate, {r['carrier_id'] for r in plan['updates']})
    return candidate, eq


def apply_ent(ent, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    _, _, original, candidate = _checked(base, plan)
    if ent not in (original, candidate):
        raise ValueError('editorial amendment requires exact whole ENT pre/postimage')
    return candidate


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('editorial-amendment recipe requires exact source-bound reconstruction over its parent game')


def reconstruction(previous, release_id, *, minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    """Deterministically rebuild ``previous`` from its parent release and its saved plan, or return None."""
    disk_budget.validate_reserve(minimum_free_bytes)
    path = previous.locator.get('sourced_profile_assignment_plan_path')
    if not path:
        return None
    path = registry.ROOT / path
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    package = pipeline.read_json_file(previous.package_path)
    artifact = next(a for a in package['artifacts'] if a['id'] == artifact_id(plan))
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve() or registry.sha256_file(path) != artifact['sha256']:
        raise ValueError('editorial amendment SOURCE artifact differs')
    if bind(pipeline.read_json_file(base.package_path), plan) != package:
        raise ValueError('editorial SOURCE would discard recipe edits')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != inert_descriptor(base, plan):
        raise ValueError('editorial SOURCE input is not the exact inert descriptor')
    for r in (base, previous):
        pipeline.assert_tree_matches_inventory(r.game_path, pipeline.read_json_file(r.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path, minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != package:
        raise ValueError('editorial SOURCE recipe differs')
    return dict(season=previous.season, release_id=release_id, complete_game_inventory_identical=True,
                complete_recipe_identical=True, compilation_mode='source-bound-editorial-amendment-reconstruction-not-factory-compile')


def inert_descriptor(base, plan):
    return dict(season=base.season, release_id=base.release_id, package_sha256=plan['package_sha256'],
                jug_sha256=plan['jug_sha256'], updates=[], unresolved=[])
