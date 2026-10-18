"""Repair inherited goalkeeper donor roles, without changing broad positions.

Mechanical compatibility, not global historical-position certification. Only
an authored, native-matching outfielder with an explicitly inherited GK-only
role and an original goalkeeper donor qualifies. Detailed sourced roles and
whole-record fallbacks remain untouched. A separately parsed exact biography
can additionally resolve a known role/country defect; no club-country defaults.
"""
import copy
import hashlib
from functools import lru_cache
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts.audit_inherited_goalkeeper_roles_20261016 import selected
from scripts.finalize_season_release_v1 import DEFAULT_BASE
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA = 'pm99-source-bound-donor-GK-role-and-known-country-delta-v1'
PREFIX = 'source-bound-donor-gk-role-'
MODE = 'known-good-baseline-source-bound-donor-GK-role-safety-v1'
KNOWN_KEY = 'cross-club-2000-kanchelskis-original-20261016'
KNOWN_URL = 'https://en.wikipedia.org/wiki/Andrei_Kanchelskis'


def digest(value):
    return hashlib.sha256(packages.canonical_json_bytes(value)).hexdigest()


def filename(plan):
    return 'donor-role-country-' + plan['transaction_id'] + '.json'


@lru_cache(maxsize=2)
def factory_people(file_sha):
    path = DEFAULT_BASE / 'DBDAT/JUG98030.FDI'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != file_sha:
        raise ValueError('factory donor source changed')
    result = {}
    for entry in IndexedFDIFile.from_bytes(data).entries:
        raw = entry.decode_payload(data)
        if raw[2:5] not in (bytes.fromhex('dd6360'), bytes.fromhex('dd6361')):
            continue
        result[entry.record_id] = roster.native_player(raw, entry.record_id)
    return result


def known_biography(raw):
    page = BeautifulSoup(raw, 'lxml')
    if [h.get_text(' ',strip=True) for h in page.select('h1')] != ['Andrei Kanchelskis']:
        raise ValueError('known role/country article identifies another person')
    boxes = [b for b in page.select('table.infobox') if b.select('.bday')]
    if len(boxes) != 1 or [b.get_text(strip=True) for b in boxes[0].select('.bday')] != ['1969-01-23']:
        raise ValueError('known role/country biography needs its one literal DOB')
    if not any('Kanchelskis usually played as a right-winger throughout his career' in p.get_text(' ',strip=True)
            for p in page.select('p')):
        raise ValueError('known biography does not positively establish the career right-wing role')
    international, rows = False, []
    for tr in boxes[0].select('tr'):
        headings = tr.select('th.infobox-header')
        if headings:
            international = headings[0].get_text(' ',strip=True) == 'International career'
            continue
        if international:
            cells = tr.find_all(['th','td'], recursive=False)
            if len(cells) >= 2:
                rows.append([cells[0].get_text(' ',strip=True), cells[1].get_text(' ',strip=True)])
    if rows.count(['1992–1998','Russia']) != 1 or rows[-1:] != [['1992–1998','Russia']]:
        raise ValueError('known nationality lacks its dated final pre-season Russia representation')
    return dict(name='Andrei Kanchelskis', birth_date='1969-01-23', nationality='RUS',
        role_by_existing_broad_position={'M':6,'F':11},
        role_grade='reviewed-editorial-native-RM/RW-mapping-of-literal-career-right-wing-witness',
        country_basis='Literal1992–1998 Russia representation, final international career row; no birthplace/current-club default.',
        exact_target_match_role_claimed=False)


def prepare(base):
    package = pipeline.read_json_file(base.package_path)
    data = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
    factory_path = DEFAULT_BASE / 'DBDAT/JUG98030.FDI'
    factory_sha = registry.sha256_file(factory_path)
    factory = factory_people(factory_sha)
    countries = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    known_path, known_raw, known_binding = source_rows(KNOWN_KEY)
    receipt = known_path.with_suffix('.source.json')
    if pipeline.read_json_file(receipt)['url'] != KNOWN_URL:
        raise ValueError('known role/country source URL differs')
    known = known_biography(known_raw)
    updates = []
    for label, layer, _ in layers.package_layers(base):
        for player in layer['players']:
            carrier = player['carrier_id']
            if carrier not in factory or carrier not in index:
                continue
            raw = index[carrier].decode_payload(data)
            native = roster.native_player(raw, carrier)
            end, roles = read_indexed_native_roles(raw, carrier)
            safety = selected(player, native, roles, factory[carrier])
            named = (roster.normalise(player.get('source_name') or player['name']) == 'andreikanchelskis'
                and player['facts'].get('birth_date') == known['birth_date']
                and player.get('policy') != 'preserve-existing-mode1'
                and native['position'] == player['facts'].get('primary_position')
                and native['position'] in ('M','F')
                and roster.normalise(player['name']) == roster.normalise(native['name']))
            if not safety and not named:
                continue
            if label != 'main':
                raise ValueError('donor-role safety must not silently skip a separately stored English-layer candidate')
            role_after = ({'D':4,'M':9,'F':12}[native['position']] if safety else None)
            if named and [r for r in roles if r != 98] == [0]:
                role_after = known['role_by_existing_broad_position'][native['position']]
            country_after = None
            if named:
                birthday = (f"{int.from_bytes(bytes(v^0x61 for v in raw[end+14:end+16]),'little'):04d}-"
                    f"{raw[end+13]^0x61:02d}-{raw[end+12]^0x61:02d}")
                if birthday != known['birth_date']:
                    raise ValueError('known nationality actor has a different native birthday')
                wanted = compiler._country_code(known['nationality'], dict(countries))
                if wanted == countries['XXX']:
                    raise ValueError('known nationality is unsupported by this native country table')
                if player['facts'].get('nationality') != known['nationality'] or (raw[end+8]^0x61) != wanted:
                    country_after = known['nationality']
            if role_after is None and country_after is None:
                continue
            updates.append(dict(layer=label,carrier_id=carrier,player_id=player['id'],name=player['name'],
                before_player_sha256=digest(player),before_record_sha256=hashlib.sha256(raw).hexdigest(),
                before_native_roles=roles,before_native_country_code=raw[end+8]^0x61,
                primary_position=native['position'],donor_name=factory[carrier]['name'],
                donor_broad_position=factory[carrier]['position'],
                fine_roles=[role_after] if role_after is not None else None,
                nationality=country_after,known_biography_applies=named,
                role_basis=('literal-career-right-wing-mapped-to-existing-native-broad-class' if named and role_after is not None
                    else 'conservative-central-role-only-to-remove-inherited-GK-donor-not-historical-specialism-proof')
                    if role_after is not None else None))
    paths = [Path(__file__), registry.ROOT / 'scripts/audit_inherited_goalkeeper_roles_20261016.py',
        registry.ROOT / 'upstream/pm99-skezmod-db-editor/app/indexed_jug_roles.py',
        registry.ROOT / 'upstream/pm99-skezmod-db-editor/app/indexed_jug_nationality.py']
    doc = dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=hashlib.sha256(data).hexdigest(),
        factory_JUG_sha256=factory_sha,known_biography=known,
        source_bindings=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p)) for p in paths]
            + [dict(known_binding,url=KNOWN_URL,receipt_path=registry.relative_workspace_path(receipt),
                receipt_sha256=registry.sha256_file(receipt))],
        updates=updates,
        scope='Only selected six detailed-role bytes and explicitly known nationality byte; existing broad classes, every skill, identity/DOB, clubs/ownership/orders/tactics/managers/assets/EXE stay exact. Conservative fallback roles are reviewed editorial, not independently proved historical specialisms.')
    doc['transaction_id'] = digest(doc)[:24]
    return doc


def verify(base, plan):
    if plan.get('schema') != SCHEMA or packages.canonical_json_bytes(prepare(base)) != packages.canonical_json_bytes(plan):
        raise ValueError('donor-role source/native preimages or known-country evidence changed')


def bind(package, plan):
    result = copy.deepcopy(package)
    players = {p['carrier_id']:p for p in result['players']}
    for row in plan['updates']:
        player = players[row['carrier_id']]
        if digest(player) != row['before_player_sha256']:
            raise ValueError('donor-role player preimage differs')
        fields = set()
        if row['fine_roles'] is not None:
            player['facts']['fine_roles'] = list(row['fine_roles']); fields.add('fine_roles')
        if row['nationality'] is not None:
            player['facts']['nationality'] = row['nationality']; fields.add('nationality')
        if 'fact_fallbacks' in player:
            player['fact_fallbacks'] = [f for f in player['fact_fallbacks'] if f['field'] not in fields]
    aid = PREFIX + plan['transaction_id']
    result['artifacts'].append(dict(id=aid,kind='season-input',relative_path=filename(plan),
        sha256=digest(plan),media_type='application/json'))
    result['proofs'].append(dict(id='proof-'+aid,grade='reviewed-editorial',artifact_id=aid,
        covers=['native-outfield-versus-inherited-GK-donor-role-compatibility-not-historical-specialism',
            'explicit-full-name-DOB-known-biography-country-where-declared']))
    for key in ('artifacts','proofs'):
        result[key].sort(key=lambda r:r['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if (hashlib.sha256(original).hexdigest() != plan['jug_sha256']
            or eq != (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()):
        raise ValueError('donor-role exact native preimage/EQ changed')
    roles = {r['carrier_id']:r['fine_roles'] for r in plan['updates'] if r['fine_roles'] is not None}
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    nations = {r['carrier_id']:compiler._country_code(r['nationality'],dict(codes))
        for r in plan['updates'] if r['nationality'] is not None}
    if len({r['carrier_id'] for r in plan['updates']}) != len(plan['updates']):
        raise ValueError('ambiguous donor-role carrier')
    actual, _ = rewrite_indexed_native_roles(original, roles)
    actual, _ = rewrite_indexed_native_nationalities(actual, nations)
    if jug not in (original, actual):
        raise ValueError('donor-role requires the exact whole native preimage or postimage')
    return actual, eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('donor-role recipe requires exact source-bound reconstruction, not factory recompilation')


def reconstruction(previous, release_id):
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base = registry.load_registered_release(previous.season,plan['release_id'])
    verify(base,plan)
    package = pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan) != package:
        raise ValueError('donor-role SOURCE would discard recipe edits')
    artifact = next(a for a in package['artifacts'] if a['id']==PREFIX+plan['transaction_id'])
    if path.resolve() != (previous.package_path.parent/filename(plan)).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('donor-role SOURCE artifact path/hash differs')
    descriptor = previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('donor-role SOURCE descriptor differs')
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:
        raise ValueError('donor-role SOURCE full recipe differs')
    return dict(season=previous.season,release_id=release_id,
        complete_game_inventory_identical=True,complete_recipe_identical=True)
