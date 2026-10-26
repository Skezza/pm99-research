"""Annual source-only correction of an inherited broad-position byte.

This adapter accepts an exact FootballSquads full-name/DOB row and changes one
native broad-position byte plus that one recipe fact. It never recalculates or
rewrites fine roles, the adjacent +10 byte, ownership, or other native fields.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from app.xor import xor_encode
from scripts import season_exact_primary_position_delta_v2 as writer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_disk_budget_v1 as disk_budget
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as common
from scripts.capture_footballsquads_season import _read_club_file
from scripts.season_within_club_reserve_repair_v1 import native_facts

KIND = 'annual-literal-broad-position-only'
POLICY = 'exact-annual-fullname-dob-source-position-preserve-compatible-fine-role-v1'
PREFIX = 'annual-literal-broad-position-'
SCOPE = ('Only the selected source annual primary_position recipe field and one native broad-position byte at '
         'the existing name_end+11 writer offset. Preserve adjacent +10, fine_roles, DOB, country, identity, '
         'skills, owner, EQ/order, tactics, manager, photos, kit, and all unrelated bytes.')


def _sha(path: Path) -> str:
    return registry.sha256_file(path)


def filename(plan: dict) -> str:
    if plan.get('kind') != KIND:
        raise ValueError('unsupported annual literal broad-position plan')
    return PREFIX + plan['transaction_id'] + '.json'


def artifact_id(plan: dict) -> str:
    return PREFIX + plan['transaction_id']


def _root_file(binding: dict) -> Path:
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('exact path and content SHA binding required')
    relative = Path(binding['path'])
    if '..' in relative.parts:
        raise ValueError('annual source binding may not traverse parent directories')
    cursor = registry.ROOT
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('annual source binding may not traverse symlinks')
    path = registry.ROOT / relative
    if (relative.is_absolute() or path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(registry.ROOT.resolve())
            or _sha(path) != binding['sha256']):
        raise ValueError('annual source binding is absent, symlinked, escaping, or changed')
    return path


def _read_input(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(registry.ROOT.resolve()):
        raise ValueError('annual position request must be a retained in-workspace file')
    request = pipeline.read_json_file(path)
    if (request.get('schema') != 'pm99-annual-literal-broad-position-input-v1'
            or request.get('kind') != KIND or not isinstance(request.get('changes'), list)
            or not request['changes']):
        raise ValueError('annual source request schema/kind/changes differ')
    return request


def _parse_annual(case: dict) -> tuple[dict, dict]:
    dataset_path = _root_file(case['dataset'])
    body_path = _root_file({k: case['source_body'][k] for k in ('path', 'sha256')})
    dataset = pipeline.read_json_file(dataset_path)
    season_label = f"{case['season'][:4]}/{case['season'][-2:]}"
    if (dataset.get('schema_version') != 'pm99-footballsquads-season-capture-v1'
            or dataset.get('season', {}).get('label') != season_label
            or dataset.get('source', {}).get('repository') != 'https://github.com/footballcsv/cache.footballsquads'):
        raise ValueError('captured annual source dataset/season provenance differs')
    source_matches = [club for club in dataset['clubs']
        if club.get('source_path') == case['source_body']['source_path']
        and club.get('source_sha256') == case['source_body']['sha256']]
    if len(source_matches) != 1 or source_matches[0].get('club_name') != case['source_club']:
        raise ValueError('raw source path/hash must identify exactly the selected annual club')
    expected_row = case['source_row']
    dataset_rows = [row for row in source_matches[0]['players']
        if row.get('name') == case['full_name'] and row.get('birth_date') == case['birth_date']]
    if (len(dataset_rows) != 1 or any(dataset_rows[0].get(k) != expected_row.get(k)
            for k in ('name', 'birth_date', 'position', 'shirt_number'))
            or dataset_rows[0].get('position') not in {'D', 'M', 'F', 'G'}):
        raise ValueError('source-club cohort must contain exactly one full-name/DOB row with the asserted position')

    # Reparse the original club body using the existing FootballSquads parser.
    # The captured JSON is a cross-check, not a substitute for its raw row.
    parsed = _read_club_file(body_path, root=registry.ROOT / '.local/external-sources/cache.footballsquads',
        season_start=int(case['season'][:4]), season_label=season_label)
    if (parsed.get('source_path') != case['source_body']['source_path']
            or parsed.get('source_sha256') != case['source_body']['sha256']
            or parsed.get('club_name') != case['source_club']):
        raise ValueError('original annual source body reparses to another club or source identity')
    raw_rows = [row for row in parsed['players']
        if row.get('name') == case['full_name'] and row.get('birth_date') == case['birth_date']]
    if (len(raw_rows) != 1 or any(raw_rows[0].get(k) != expected_row.get(k)
            for k in ('name', 'birth_date', 'position', 'shirt_number'))):
        raise ValueError('raw annual club file must uniquely repeat the exact selected full-name/DOB/position row')
    if case['annual_position'] != expected_row['position']:
        raise ValueError('annual literal position differs from the source row')
    return dataset_rows[0], raw_rows[0]


def prepare(base, input_path) -> dict:
    input_path = Path(input_path)
    if not input_path.is_absolute():
        input_path = registry.ROOT / input_path
    request = _read_input(input_path)
    matches = [case for case in request['changes']
        if case.get('season') == base.season and case.get('release_id') == base.release_id]
    if len(matches) != 1:
        raise ValueError('request must select exactly one matching exact registered parent')
    case = matches[0]
    if (case['release_manifest_sha256'] != base.manifest_sha256
            or _sha(base.package_path) != case['package_sha256']):
        raise ValueError('registered release or exact recipe pin differs')
    jug_path, eq_path = base.game_path / 'DBDAT/JUG98030.FDI', base.game_path / 'DBDAT/EQ98030.FDI'
    jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
    if _sha(jug_path) != case['jug_sha256'] or _sha(eq_path) != case['eq_sha256']:
        raise ValueError('native parent JUG/EQ pin differs')
    annual_row, raw_row = _parse_annual(case)
    package = pipeline.read_json_file(base.package_path)
    actors = [row for row in package['players'] if row.get('carrier_id') == case['carrier_id']]
    if len(actors) != 1:
        raise ValueError('selected carrier is not unique in the exact parent package')
    actor = actors[0]
    clubs = [club for club in package['clubs'] if club.get('id') == actor.get('club_id')]
    if (len(clubs) != 1 or clubs[0].get('carrier_id') != case['club_carrier_id']
            or actor.get('club_id') != case['actor_club_id']
            or actor.get('person_id') != case['actor_person_id']
            or actor.get('source_name') != case['full_name']
            or actor.get('facts', {}).get('birth_date') != case['birth_date']
            or actor.get('facts', {}).get('primary_position') != case['native_before_position']
            or actor.get('facts', {}).get('fine_roles') != case['recipe_fine_roles_preserved']):
        raise ValueError('source full-name/DOB does not bind exact recipe actor, club, broad-role or fine-role preimage')

    if (roster.normalise(clubs[0]['name']) != roster.normalise(case['source_club'])
            or roster.source_group(case['source_body']['source_path'].split('/')[0])
               != roster.club_group(clubs[0])):
        raise ValueError('annual source club/country does not identify the native owner')

    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(jug).entries}
    entry = entries.get(case['carrier_id'])
    if entry is None:
        raise ValueError('native player carrier is absent')
    payload = entry.decode_payload(jug)
    if payload[2:5].hex() != 'dd6361':
        raise ValueError('literal +11 broad-position repair is proven only for dd6361 actors')
    observed = roster.native_player(payload, case['carrier_id'])
    native_role_end, native_fine_roles = read_indexed_native_roles(payload, case['carrier_id'])
    facts = native_facts(jug, case['carrier_id'])
    owners = ownership.native_owners(eq).get(case['carrier_id'])
    if (roster.normalise(observed['name']) != roster.normalise(case['full_name'])
            or facts['birth_date'] != case['birth_date']
            or observed['position'] != case['native_before_position']
            or native_fine_roles != case['native_fine_roles_preserved']
            or owners != {case['club_carrier_id']}):
        raise ValueError('native full name/DOB/broad role and exclusive EQ owner do not agree')
    end = observed['name_end']
    target_offset = entry.payload_offset + end + 11
    adjacent_offset = entry.payload_offset + end + 10
    if target_offset != case['primary_visible_byte_offset'] or jug[target_offset] != case['native_before_byte']:
        raise ValueError('selected writer offset or original broad-position byte differs')
    target_position = annual_row['position']
    target_byte = xor_encode(bytes([compiler.POSITION[target_position] ^ 0x61]))[0]
    if target_byte != case['native_after_byte'] or jug[target_offset] == target_byte:
        raise ValueError('annual source value does not map to the exact expected visible native byte')
    if not writer.fifa.compatible(target_position, case['native_fine_roles_preserved'][0]):
        raise ValueError('preserved fine role is not compatible with the annual source broad position')
    before_native = copy.deepcopy(observed)
    native_role_candidates = [role for role in native_fine_roles if role != 98]
    writer_plan = {'schema': writer.SCHEMA, 'season': base.season, 'release_id': base.release_id,
        'jug_sha256': _sha(jug_path), 'eq_sha256': _sha(eq_path),
        'updates': [{'carrier_id': case['carrier_id'], 'before_native': before_native,
            'primary_position': target_position, 'fine_roles': native_role_candidates}]}
    masks = [{'file': 'DBDAT/JUG98030.FDI', 'record_offset': end + 11,
        'file_offset': target_offset, 'before': jug[target_offset], 'after': target_byte}]
    plan = {'schema': common.SCHEMA, 'kind': KIND, 'policy': POLICY,
        'season': base.season, 'release_id': base.release_id,
        'source_input': {'path': registry.relative_workspace_path(input_path), 'sha256': _sha(input_path)},
        'case_id': case['case_id'], 'carrier_id': case['carrier_id'],
        'package_sha256': _sha(base.package_path), 'jug_sha256': _sha(jug_path), 'eq_sha256': _sha(eq_path),
        'dataset': copy.deepcopy(case['dataset']), 'source_body': copy.deepcopy(case['source_body']),
        'source_row': copy.deepcopy(annual_row), 'raw_source_row': copy.deepcopy(raw_row),
        'full_name': case['full_name'], 'birth_date': case['birth_date'],
        'expected_owner': case['club_carrier_id'], 'before': copy.deepcopy(actor),
        'field_mask': ['primary_position'], 'values': {'primary_position': target_position},
        'fine_roles_preserved': copy.deepcopy(case['recipe_fine_roles_preserved']),
        'native_fine_roles_preserved': copy.deepcopy(case['native_fine_roles_preserved']),
        'native_before': before_native, 'native_masks': masks,
        'adjacent_byte': {'file': 'DBDAT/JUG98030.FDI', 'file_offset': adjacent_offset,
            'before': jug[adjacent_offset], 'after': jug[adjacent_offset]},
        'writer_plan': writer_plan, 'scope': SCOPE,
        'updates': [{'carrier_id': case['carrier_id'], 'field_mask': ['primary_position'],
                     'values': {'primary_position': target_position}}]}
    plan['transaction_id'] = hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest()[:24]
    return plan


def verify(base, plan):
    if plan.get('schema') != common.SCHEMA or plan.get('kind') != KIND:
        raise ValueError('annual literal broad-position plan schema differs')
    path = _root_file(plan['source_input'])
    if prepare(base, path) != plan:
        raise ValueError('annual raw-source/full-identity/native parent did not reproduce the plan')


def validate_mask(plan):
    if (plan.get('schema') != common.SCHEMA or plan.get('kind') != KIND
            or plan.get('policy') != POLICY or plan.get('field_mask') != ['primary_position']
            or set(plan.get('values', {})) != {'primary_position'}
            or len(plan.get('native_masks', [])) != 1):
        raise ValueError('annual broad-position-only mask required')
    mask = plan['native_masks'][0]
    if (mask.get('file') != 'DBDAT/JUG98030.FDI'
            or mask.get('file_offset') != plan['adjacent_byte']['file_offset'] + 1
            or mask.get('before') == mask.get('after')
            or plan['adjacent_byte'].get('after') != plan['adjacent_byte'].get('before')
            or set(plan['values']) != {'primary_position'}
            or plan['values']['primary_position'] != plan['source_row'].get('position')
            or plan['fine_roles_preserved'] != plan['before']['facts'].get('fine_roles')
            or [role for role in plan['native_fine_roles_preserved'] if role != 98]
                != plan['writer_plan']['updates'][0].get('fine_roles')):
        raise ValueError('mask is broader than exact +11 byte and source-position recipe field')
    if plan.get('writer_plan', {}).get('updates', [{}])[0].get('fine_roles') != [
            role for role in plan['native_fine_roles_preserved'] if role != 98]:
        raise ValueError('native writer bridge must preserve the existing fine-role list exactly')


def bind(package, plan):
    validate_mask(plan)
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    if (pipeline.read_json_file(base.package_path) != package
            or _sha(base.package_path) != plan['package_sha256']):
        raise ValueError('exact annual source recipe parent required')
    result = copy.deepcopy(package)
    actors = [actor for actor in result['players'] if actor.get('carrier_id') == plan['carrier_id']]
    if len(actors) != 1 or actors[0] != plan['before']:
        raise ValueError('exact selected actor recipe preimage differs')
    actors[0]['facts']['primary_position'] = plan['values']['primary_position']
    result['artifacts'].append({'id': artifact_id(plan), 'kind': 'season-input',
        'relative_path': filename(plan), 'sha256': hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest(),
        'media_type': 'application/json'})
    result['proofs'].append({'id': 'proof-' + artifact_id(plan), 'grade': 'source-receipt',
        'artifact_id': artifact_id(plan), 'covers': ['exact-annual-full-name-DOB-broad-position-source-fact']})
    result['artifacts'].sort(key=lambda row: row['id'])
    result['proofs'].sort(key=lambda row: row['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    validate_mask(plan)
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    after, after_eq = writer.apply(jug, eq, plan['writer_plan'])
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
    expected = [plan['native_masks'][0]['file_offset']]
    adjacent = plan['adjacent_byte']['file_offset']
    if (changed != expected or after_eq != eq
            or after[adjacent] != before[adjacent]
            or after[expected[0]] != plan['native_masks'][0]['after']):
        raise ValueError('writer changed anything except the single broad-position byte')
    return after, after_eq


def reject_factory_recipe(package):
    if any(item.get('id', '').startswith(PREFIX) for item in package.get('artifacts', [])):
        raise ValueError('annual literal broad-position recipe requires exact retained SOURCE replay')


def reconstruction(previous, release_id, *, minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    disk_budget.validate_reserve(minimum_free_bytes)
    relative = getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    plan_path = registry.ROOT / relative
    plan = pipeline.read_json_file(plan_path)
    if plan.get('kind') != KIND:
        return None
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if (receipt.get('compilation_mode') != common.MODE
            or plan_path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or _sha(plan_path) != receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('annual broad-position SOURCE receipt/plan binding differs')
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('annual broad-position SOURCE would discard recipe edits')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = {'season': base.season, 'release_id': base.release_id,
        'package_sha256': plan['package_sha256'], 'jug_sha256': plan['jug_sha256'],
        'updates': [], 'unresolved': []}
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('annual broad-position SOURCE descriptor differs from exact parent')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=plan_path,
        minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('annual broad-position SOURCE full recipe differs')
    return {'season': previous.season, 'complete_game_inventory_identical': True,
        'complete_recipe_identical': True}
