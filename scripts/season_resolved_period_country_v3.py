"""Country-only corrective transaction over an existing good/private build.

Rederive the original typed annual plan, then independently resolve its country
conflicts. Never reuse current nationality, regenerate a season or touch roles,
skills, ownership, coaches, images or other native bytes.
"""
import copy
from datetime import date
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from scripts import season_original_country_policy_v2 as v2
from scripts import season_original_secondary_facts_v1 as v1
from scripts import season_period_country_resolution_v3 as resolver
from scripts import season_package_v2 as packages

pipeline, registry = v2.pipeline, v2.registry
compiler, original = v2.compiler, v2.original
SCHEMA = 'pm99-resolved-original-period-country-only-v3'
MODE = 'known-good-baseline-resolved-original-period-country-only-v3'
PREFIX = 'sourced-resolved-period-country-v3-'
digest = v2.digest


def filename(plan):
    return 'resolved-period-country-v3-' + plan['transaction_id'] + '.json'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def prepare(base, original_plan_path, targets):
    if (not targets or any(not str(k).isdigit() or int(k) < 1 or v != ['nationality'] for k, v in targets.items())
            or len({int(k) for k in targets}) != len(targets)):
        raise ValueError('explicit unique country-only target carriers required')
    targets = {str(int(k)): v for k, v in targets.items()}
    path = Path(original_plan_path)
    annual_plan = pipeline.read_json_file(path)
    policies = {v1.SCHEMA: v1, v2.SCHEMA: v2}
    if annual_plan.get('schema') not in policies or annual_plan.get('season') != base.season:
        raise ValueError('resolved country requires an original typed same-season annual plan')
    annual_base = registry.load_registered_release(base.season, annual_plan['release_id'])
    policies[annual_plan['schema']].verify(annual_base, annual_plan)
    originals = {r['carrier_id']: r for r in annual_plan['updates']}
    if len(originals) != len(annual_plan['updates']) or not {int(k) for k in targets} <= set(originals):
        raise ValueError('resolved country targets absent or duplicated in original source plan')
    package = pipeline.read_json_file(base.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = original.order.native_owners(eq)
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    fifa_sha = registry.sha256_file(resolver.fifa.fifa.identity.old.FIFA)
    index = resolver.fifa.load(fifa_sha)
    updates, unresolved = [], []
    for key in sorted(targets, key=int):
        carrier = int(key)
        source_row, player = originals[carrier], players[carrier]
        raw = entries[carrier].decode_payload(jug)
        native = original.audit.native_player(raw, carrier)
        end = native['name_end']
        birthday = date(int.from_bytes(bytes(v ^ 0x61 for v in raw[end+14:end+16]), 'little'),
            raw[end+13] ^ 0x61, raw[end+12] ^ 0x61).isoformat()
        if (player.get('policy') == 'preserve-existing-mode1'
                or owners.get(carrier) != {clubs[player['club_id']]['carrier_id']}
                or birthday != player['facts'].get('birth_date')
                or birthday != source_row['source_person']['birth_date']
                or player['name'] != source_row['before_player']['name']
                or player.get('source_name') != source_row['before_player'].get('source_name')
                or original.names.literal_name(native['name']) != original.names.literal_name(player['name'])):
            unresolved.append(dict(carrier_id=carrier, reason='original country actor/current native identity differs'))
            continue
        try:
            resolution = resolver.resolve(source_row, base.season, index=index, file_sha=fifa_sha)
            code, label = v2.native_country(resolution['nationality'], codes)
        except ValueError as exc:
            unresolved.append(dict(carrier_id=carrier, reason=str(exc)))
            continue
        if raw[end+8] ^ 0x61 == code and player['facts']['nationality'] == resolution['nationality']:
            unresolved.append(dict(carrier_id=carrier, reason='already resolved in actual native and recipe'))
            continue
        row = copy.deepcopy(source_row)
        row.update(before_player=copy.deepcopy(player), native_name=native['name'],
            before_nationality_code=raw[end+8] ^ 0x61, fields=['nationality'],
            nationality=resolution['nationality'], native_country_code=code, native_label=label,
            country_resolution_input=copy.deepcopy(source_row), country_resolution=resolution,
            representability='proven-native-capacity-XXX' if label == 'XXX' else 'native-country-label')
        updates.append(row)
    result = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=digest(jug), eq_sha256=digest(eq),
        original_annual_plan=binding(path), targets=targets, updates=updates, unresolved=unresolved,
        implementation_inputs=[binding(Path(m.__file__)) for m in (resolver, resolver.cgo,
            resolver.passport, resolver.fifa)] + [binding(Path(__file__))],
        scope='Only selected country bytes/recipe nationality/fallback declarations/source artifact; all other facts and files unchanged. Source choices are single game flags, not exclusive citizenship claims.')
    result['transaction_id'] = digest(packages.canonical_json_bytes(result))[:24]
    return result


def verify(base, plan):
    source = plan['original_annual_plan']
    path = registry.ROOT / source['path']
    if (plan.get('schema') != SCHEMA or registry.sha256_file(path) != source['sha256']
            or prepare(base, path, plan['targets']) != plan):
        raise ValueError('resolved original country source/native transaction does not reproduce')


def verify_row_resolution(row, season, *, index, file_sha):
    if (row.get('country_resolution_input') is None
            or resolver.resolve(row['country_resolution_input'], season, index=index, file_sha=file_sha) != row.get('country_resolution')
            or row['country_resolution']['nationality'] != row['nationality']):
        raise ValueError('resolved country independent source choice changed')
    return row['country_resolution']


def bind(package, plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('resolved country recipe schema differs')
    result = copy.deepcopy(package)
    for row in plan['updates']:
        players = [p for p in result['players'] if p['carrier_id'] == row['carrier_id']]
        if players != [row['before_player']]:
            raise ValueError('resolved country exact recipe preimage differs')
        players[0]['facts']['nationality'] = row['nationality']
        if 'fact_fallbacks' in players[0]:
            players[0]['fact_fallbacks'] = [f for f in players[0]['fact_fallbacks'] if f['field'] != 'nationality']
    result['artifacts'].append(dict(id=PREFIX+plan['transaction_id'], kind='season-input',
        relative_path=filename(plan), sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('resolved country native schema differs')
    return v2.apply(jug, eq, dict(plan, schema=v2.SCHEMA))


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('resolved country recipe requires exact SOURCE reconstruction')


def reconstruction(previous, release_id):
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if (receipt.get('compilation_mode') != MODE
            or path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(path) != receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('resolved country original artifact/compiler binding differs')
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('resolved country SOURCE would discard recipe edits')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=base.season, release_id=base.release_id,
            package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]):
        raise ValueError('resolved country SOURCE parent differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('resolved country whole SOURCE recipe differs')
    return dict(season=previous.season, complete_game_inventory_identical=True, complete_recipe_identical=True)
