"""Source-bound Maccabi fine roles with exact native masks and SOURCE replay."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_opening_order_repair_v1 as ownership

SCHEMA = 'pm99-source-bound-maccabi-role-r129-v1'
POLICY = 'source-bound-Maccabi-Tal-Ben-Haim-fine-role-only-projection-v1'
MODE = 'known-good-baseline-source-bound-maccabi-fine-roles-v1'
RELEASE_ID = 'sourced-original-country-policy-cohort-20261017-r129a'
PLAN_SHA256 = '20d32091386d73fe0712fa16cc51a3c549b58128f7c6c20269ae6d773873ede7'
SOURCE_BINDINGS = {
    'official_maccabi_archive': ('.local/consolidated-audit-20261009/official-namesake-sources/maccabi-player-archive.html', 'ec5768d46c7776cd15297c55e98348a6d14693d85f6be0300380409b23ab0540', 'https://www.maccabi-tlv.co.il/en/team/page/52/'),
    'official_plzen_match': ('.local/consolidated-audit-20261009/official-namesake-sources/plzen-maccabi-20150805.html', '04d6974b651ef92a57ad41518aff1773fef98c4f63b79c2970ac8fb82eb3e546', 'https://www.fcviktoria.cz/zapas.asp?id=2879'),
    'sofifa_legacy': ('.local/external-sources/sofifa-fifa16/male_players_legacy.csv', '13389f463935d257e92811eebbd50405df1a982aa45233a63d1ce075daca133e', 'https://sofifa.com/'),
    'name_case': ('.local/consolidated-audit-20261009/maccabi-name-delivery/name-only-plan.json', '9df45c1262ebaa3b488baf5b906d22073093c2d9a76bbfbf60c1cc223dbb0e5d', None),
    'v132_scope': ('.local/consolidated-audit-20261009/release-delivery-checklist-v132.json', '663bd84c29097f9a416cb349889e2e4787fa51f482cbe9d787d024c5b0df8f08', None),
    'role_map': ('scripts/season_historical_role_plan_v1.py', '27d1c59b281dce774fefb17bbc041643ec42f3e6976e801b6fbeca82431cb25f', None),
    'compatible_guard': ('scripts/season_exact_fifa_role_delta_v1.py', '19d84ab0a49629703c42711b2806b97a2b0ba6fa70f780e317322e565fd12920', None),
}
EXPECTED = {2027: [4, 1, 2], 32232: [10]}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def filename(plan):
    if plan.get('schema') != SCHEMA or plan.get('policy') != POLICY:
        raise ValueError('unsupported Maccabi role source plan')
    return 'role-plan.json'


def _source_check(plan):
    bindings = {row['id']: row for row in plan['source_bindings']}
    if set(bindings) != set(SOURCE_BINDINGS):
        raise ValueError('Maccabi source binding set changed')
    for source_id, (relative, expected_sha, url) in SOURCE_BINDINGS.items():
        expected = {'id': source_id, 'path': relative, 'sha256': expected_sha, 'url': url}
        actual = bindings[source_id]
        if actual != expected or _sha(registry.ROOT / relative) != expected_sha:
            raise ValueError('Maccabi raw source binding changed: ' + source_id)
    csv_path = registry.ROOT / SOURCE_BINDINGS['sofifa_legacy'][0]
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    wanted = {
        ('141001', '15'): ('Tal Ben Haim', '1982-03-31', '2014-09-18', 'CB, RB, LB'),
        ('206316', '18'): ('Tal Ben Chaim', '1989-08-05', '2017-09-18', 'LW, LM'),
    }
    for key, values in wanted.items():
        matches = [row for row in rows if (row['player_id'], row['fifa_version']) == key]
        if len(matches) != 1:
            raise ValueError('Maccabi exact FIFA corroboration row is ambiguous or missing')
        row = matches[0]
        if tuple(row[k] for k in ('long_name', 'dob', 'fifa_update_date', 'player_positions')) != values:
            raise ValueError('Maccabi exact FIFA corroboration row changed')
    archive = (registry.ROOT / SOURCE_BINDINGS['official_maccabi_archive'][0]).read_bytes()
    text = ' '.join(audit.BeautifulSoup(archive, 'lxml').get_text(' ', strip=True).split())
    if ('The central defender was an integral part' not in text or
            'On June 3, 2015 Ben Haim signed a two year contract with Maccabi Tel Aviv' not in text or
            'The talented winger added four more league goals' not in text):
        raise ValueError('dated official Maccabi identity/role text changed')
    match = (registry.ROOT / SOURCE_BINDINGS['official_plzen_match'][0]).read_bytes()
    if b'Ben Haim I' not in match or b'Ben Haim II' not in match:
        raise ValueError('dated Plzen lineup no longer distinguishes namesakes')
    names = pipeline.read_json_file(registry.ROOT / SOURCE_BINDINGS['name_case'][0])
    witness = names.get('source_witness', {})
    witnessed = {row.get('carrier_id'): row for row in witness.get('players', [])}
    if (names.get('schema') != 'pm99-original-Maccabi-2015-name-only-layer-v1'
            or names.get('season') != '2015-16'
            or witness.get('candidate_id') != 'b10350da555981b028b52ac7a6dbd80efdf015b388c9d6f8ac45a17da200db41'
            or witness.get('duplicate_suspicion_cleared') is not True
            or witness.get('native_writes') != 0
            or set(witnessed) != {2027, 32232}
            or (witnessed[2027].get('source_name'), witnessed[2027].get('native', {}).get('birth_date')) != ('Ben-Haim, Tal', '1982-03-31')
            or (witnessed[32232].get('source_name'), witnessed[32232].get('native', {}).get('birth_date')) != ('Ben-Haim, Tal', '1989-08-05')
            or witness.get('witness', {}).get('date') != '2015-08-05'
            or witness.get('witness', {}).get('exact_birthdays_independently_verified') is not False):
        raise ValueError('dated Maccabi namesake/source witness no longer binds the two exact native identities')


def verify(base, plan):
    if (plan.get('schema'), plan.get('policy'), plan.get('season'), plan.get('release_id')) != (
            SCHEMA, POLICY, '2015-16', RELEASE_ID):
        raise ValueError('unsupported Maccabi role policy/parent')
    if base.season != '2015-16' or base.release_id != RELEASE_ID:
        raise ValueError('Maccabi role adapter is bound only to r129')
    if hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest() != PLAN_SHA256:
        raise ValueError('Maccabi typed source plan differs from the reviewed immutable plan')
    if (_sha(base.package_path), _sha(base.game_path / 'DBDAT/JUG98030.FDI')) != (
            plan['package_sha256'], plan['jug_sha256']):
        raise ValueError('Maccabi preferred-parent package/JUG changed')
    _source_check(plan)
    package = pipeline.read_json_file(base.package_path)
    people = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = ownership.native_owners(eq)
    raw = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(raw).entries}
    rows = {r['carrier_id']: r for r in plan['updates']}
    from scripts import season_exact_fifa_role_delta_v1 as role_compatibility
    if set(rows) != set(EXPECTED):
        raise ValueError('Maccabi role actor set changed')
    for carrier, wanted in EXPECTED.items():
        row, actor = rows[carrier], people.get(carrier)
        if actor is None or (row['player_id'], row['name'], row['birth_date']) != (
                actor['id'], actor['name'], actor['facts'].get('birth_date')):
            raise ValueError('Maccabi recipe identity or DOB changed')
        if (actor['club_id'] != 'club-2101' or clubs[actor['club_id']]['carrier_id'] != 2101
                or owners.get(carrier) != {2101}):
            raise ValueError('Maccabi native ownership is not exclusively club 2101')
        if actor['facts'].get('fine_roles') != {'policy': 'preserve-existing-mode1'}:
            raise ValueError('Maccabi role fallback changed')
        native = audit.native_player(entries[carrier].decode_payload(raw), carrier)
        if (native['name'], native['position'], native['roles']) != (
                row['before_native_name'], row['before_native_position'], row['before_native_roles']):
            raise ValueError('Maccabi native identity/position/role preimage changed')
        if row['fine_roles'] != wanted or not all(
                role_compatibility.compatible(native['position'], role) for role in wanted):
            raise ValueError('Maccabi exact role projection/primary-class compatibility changed')
    # Rebind from immutable original plan with the existing canonical role publisher.
    from scripts import publish_historical_role_delta_v1 as publisher
    if publisher.updated_package(package, plan) != bind(package, plan):
        raise ValueError('existing role publisher does not reproduce bound source recipe')


def bind(package, plan):
    if plan.get('schema') != SCHEMA or plan.get('policy') != POLICY:
        raise ValueError('Maccabi bind requires typed exact policy')
    from scripts import publish_historical_role_delta_v1 as publisher
    result = publisher.updated_package(package, plan)
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release('2015-16', RELEASE_ID)
    verify(base, plan)
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if jug not in (original, rewrite_indexed_native_roles(original, EXPECTED)[0]) or eq != original_eq:
        raise ValueError('Maccabi SOURCE accepts only exact JUG pre/postimage and unchanged EQ')
    patched, _ = rewrite_indexed_native_roles(original, EXPECTED)
    if rewrite_indexed_native_roles(patched, EXPECTED) != (patched, []):
        raise ValueError('Maccabi role writer is not idempotent')
    changed = {i for i, (a, b) in enumerate(zip(original, patched)) if a != b}
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(original).entries}
    allowed = set()
    for carrier, roles in EXPECTED.items():
        payload = entries[carrier].decode_payload(original)
        end, old = read_indexed_native_roles(payload, carrier)
        if old != next(r['before_native_roles'] for r in plan['updates'] if r['carrier_id'] == carrier):
            raise ValueError('Maccabi role slots changed after verify')
        after = roles + [98] * (6 - len(roles))
        for slot, (before, target) in enumerate(zip(old, after)):
            if before != target:
                allowed.add(entries[carrier].payload_offset + end + 2 + slot)
    if changed != allowed or len(changed) != 6:
        raise ValueError('Maccabi adapter changed bytes outside six fine-role slots')
    return patched, eq


def reconstruction(previous, release_id):
    # A later unrelated child can inherit this profile-assignment locator.
    # Read the child's own compiler receipt first so that inherited evidence
    # never makes this adapter claim a transaction it did not compile.
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    locator = previous.locator or {}
    relative = locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    if plan.get('policy') != POLICY:
        raise ValueError('typed Maccabi plan has unexpected policy')
    if (not isinstance(receipt.get('original_profile_assignment_plan_sha256'), str)
            or registry.sha256_file(path) != receipt['original_profile_assignment_plan_sha256']):
        raise ValueError('Maccabi compiler receipt does not bind its source plan')
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    package = pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path), plan) != package:
        raise ValueError('Maccabi role SOURCE would lose unrelated recipe edits')
    artifact = next((a for a in package['artifacts'] if a['id'] == 'historical-role-plan-2015-16'), None)
    if (artifact is None or path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest() != artifact['sha256']):
        raise ValueError('Maccabi role source artifact path/hash differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    descriptor_path = previous.package_path.parent / 'role-delta-input.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    wanted = dict(season='2015-16', release_id=RELEASE_ID,
                  package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'],
                  updates=[], unresolved=[])
    if descriptor != wanted:
        raise ValueError('Maccabi replay descriptor is not exact inert parent pin')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        source_release_id=RELEASE_ID, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != package:
        raise ValueError('Maccabi SOURCE replay changed the complete recipe')
    return dict(season='2015-16', release_id=release_id,
                complete_game_inventory_identical=True, complete_recipe_identical=True)

