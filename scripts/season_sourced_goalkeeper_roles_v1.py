"""Correct copied outfield role labels for independently sourced goalkeepers.

A literal G source maps to PM99 role zero; no outfield side inference. Reuse
completed raw reparses only when every capture binding and raw hash still
matches. Skip shared carriers and preserved/uncertain identities.
"""
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_opening_order_repair_v1 as order

POLICY = 'original-target-squad-full-name-DOB-literal-G-to-PM99-role-zero-v1'
CONSISTENCY_POLICY = 'declared-and-native-G-preserved-fine-role-to-keeper-zero-v1'


def declared_keeper_target(player, native):
    """Synchronise an existing G declaration, without claiming new history."""
    facts = player['facts']
    return (player.get('policy') != 'preserve-existing-mode1'
            and facts.get('primary_position') == 'G'
            and facts.get('fine_roles') == {'policy': 'preserve-existing-mode1'}
            and native['position'] == 'G'
            and audit.normalise(native['name']) == audit.normalise(player['name']))


def prepare_position_consistency(release):
    """Replace inherited outfield roles only where recipe and game say G.

    This is deterministic compilation consistency, not independent evidence
    that the current person's historical position or roster ownership is right.
    Explicit fine-role declarations and whole-person fallbacks stay closed.
    """
    raw = release.package_path.read_bytes()
    package = json.loads(raw)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for player in package['players']:
        if (player.get('policy') == 'preserve-existing-mode1'
                or player['facts'].get('primary_position') != 'G'
                or player['facts'].get('fine_roles') != {'policy': 'preserve-existing-mode1'}):
            continue
        carrier = player['carrier_id']
        try:
            decoded = entries[carrier].decode_payload(jug)
            _, roles = read_indexed_native_roles(decoded, carrier)
            if roles[0] == 0:
                continue
            native = audit.native_player(decoded, carrier)
        except (KeyError, ValueError) as exc:
            unresolved.append({'carrier_id': carrier, 'reason': str(exc)})
            continue
        if not declared_keeper_target(player, native):
            unresolved.append({'carrier_id': carrier, 'reason': 'recipe/native identity or broad G disagrees'})
            continue
        updates.append({'player_id': player['id'], 'carrier_id': carrier,
            'name': player['name'], 'birth_date': player['facts'].get('birth_date'),
            'fine_roles': [0], 'provenance': {'method': CONSISTENCY_POLICY,
                'declared_primary_position': 'G', 'native_primary_position': 'G',
                'native_before_roles': roles,
                'limit': 'Existing declared/native G synchronisation only; no new historical identity, ownership, biography or ability approval'}})
    if (registry.sha256_file(release.package_path) != hashlib.sha256(raw).hexdigest()
            or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != hashlib.sha256(jug).hexdigest()):
        raise ValueError('goalkeeper consistency inputs changed during planning')
    return {'schema_version': 'pm99-historical-role-plan-v1', 'season': release.season,
        'release_id': release.release_id, 'package_sha256': hashlib.sha256(raw).hexdigest(),
        'jug_sha256': hashlib.sha256(jug).hexdigest(), 'policy': CONSISTENCY_POLICY,
        'proof_grade': 'reviewed-editorial',
        'updates': updates, 'unresolved': unresolved,
        'summary': {'declared_keeper_role_corrections': len(updates),
                    'native_identity_or_position_conflicts': len(unresolved)}}


def original_keeper(capture, name, birthday):
    rows = [p for p in capture['players'] if audit.normalise(p['name']) == audit.normalise(name)]
    if len(rows) != 1 or (rows[0]['birth_date'], rows[0]['position']) != (birthday, 'G'):
        return None
    return rows[0]


def prepare(release, reparse_report):
    report_raw = reparse_report.read_bytes()
    report_hash = hashlib.sha256(report_raw).hexdigest()
    report = json.loads(report_raw)
    captures, bindings = audit.load_sources(release.season)
    checker = audit.SourceVerifier(release.season, previous=report, source_bindings=bindings)
    by_club = defaultdict(list)
    for capture in captures:
        by_club[(audit.source_group(capture['country_catalog']), audit.normalise(capture['club_name']))].append(capture)
    package_raw = release.package_path.read_bytes()
    package_hash = hashlib.sha256(package_raw).hexdigest()
    package = json.loads(package_raw)
    clubs = {c['id']: c for c in package['clubs']}
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = order.native_owners(eq)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for player in package['players']:
        if (player.get('policy') == 'preserve-existing-mode1'
                or player['facts']['primary_position'] != 'G'
                or not isinstance(player['facts'].get('birth_date'), str)):
            continue
        carrier, club = player['carrier_id'], clubs[player['club_id']]
        name, birthday = player.get('source_name') or player['name'], player['facts']['birth_date']
        evidence = []
        for alias in audit.club_names(audit.club_group(club), club['name'], club.get('full_name', '')):
            for capture in by_club.get((audit.club_group(club), alias), []):
                source = original_keeper(capture, name, birthday)
                if source is None:
                    continue
                proof = checker.verify(capture)
                if proof['status'] == 'raw-source-reparsed':
                    evidence.append({'capture': capture, 'raw_proof': proof, 'source_player': source})
        if not evidence:
            continue
        if owners.get(carrier) != {club['carrier_id']}:
            unresolved.append({'carrier_id': carrier, 'name': name, 'reason': 'shared or mismatched actual native ownership'})
            continue
        try:
            decoded = index[carrier].decode_payload(jug)
            native = audit.native_player(decoded, carrier)
            end, before = read_indexed_native_roles(decoded, carrier)
            born = date(int.from_bytes(bytes(v ^ 0x61 for v in decoded[end+14:end+16]), 'little'),
                        decoded[end+13] ^ 0x61, decoded[end+12] ^ 0x61).isoformat()
        except (KeyError, ValueError) as exc:
            unresolved.append({'carrier_id': carrier, 'name': name,
                               'reason': 'native identity/role/date unreadable; no write', 'detail': str(exc)})
            continue
        if (audit.normalise(native['name']) != audit.normalise(player['name'])
                or native['position'] != 'G' or born != birthday):
            unresolved.append({'carrier_id': carrier, 'name': name, 'reason': 'native full display/DOB/primary position disagreement'})
            continue
        if before[0] == 0:
            continue
        updates.append({'player_id': player['id'], 'carrier_id': carrier, 'name': player['name'],
                        'birth_date': birthday, 'fine_roles': [0],
                        'provenance': {'method': POLICY, 'source_name': name,
                                       'source_position': 'G', 'native_before_roles': before,
                                       'club_id': club['id'], 'club_carrier_id': club['carrier_id'],
                                       'evidence': evidence,
                                       'limit': 'literal goalkeeper role only; no new ownership/first-XI/ability/photo claim'}})
    # Recheck the exact bytes consumed, not hashes taken only after the reads.
    if (registry.sha256_file(release.package_path) != package_hash
            or registry.sha256_file(reparse_report) != report_hash
            or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != hashlib.sha256(jug).hexdigest()
            or registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI') != hashlib.sha256(eq).hexdigest()
            or audit.load_sources(release.season)[1] != bindings):
        raise ValueError('source or native inputs changed during keeper role planning')
    for row in updates:
        for evidence in row['provenance']['evidence']:
            proof = evidence['raw_proof']
            if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
                raise ValueError('used original keeper source changed during planning')
    return {'schema_version': 'pm99-historical-role-plan-v1', 'season': release.season,
            'release_id': release.release_id, 'package_sha256': package_hash,
            'jug_sha256': hashlib.sha256(jug).hexdigest(),
            'eq_sha256': hashlib.sha256(eq).hexdigest(),
            'policy': POLICY, 'original_reparse_report': {'path': registry.relative_workspace_path(reparse_report),
                                                       'sha256': report_hash},
            'source_bindings': bindings, 'updates': updates, 'unresolved': unresolved,
            'summary': {'goalkeeper_role_corrections': len(updates), 'shared_or_native_conflicts': len(unresolved)}}


def verify(release, plan):
    if plan.get('policy') == CONSISTENCY_POLICY:
        expected = prepare_position_consistency(release)
        # Retain reproducibility for the initial, uninstalled pilot receipt.
        # New plans explicitly distinguish derived consistency from history.
        if 'proof_grade' not in plan:
            expected.pop('proof_grade')
        if expected != plan:
            raise ValueError('declared goalkeeper consistency plan does not reproduce')
        return
    binding = plan['original_reparse_report']
    path = registry.ROOT / binding['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != binding['sha256'] or prepare(release, path) != plan:
        raise ValueError('sourced goalkeeper role plan does not independently reproduce')


def reconstruction(previous, release_id, *, minimum_free_bytes=None):
    """Replay this exact role-only child, never an inherited keeper ancestor."""
    from scripts import season_pipeline_v2 as pipeline
    from scripts import publish_historical_role_delta_v1 as publisher
    from app.indexed_jug_roles import rewrite_indexed_native_roles

    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != 'known-good-baseline-role-only-delta':
        return None
    relative = previous.locator.get('historical_role_plan_path')
    if not relative:
        raise ValueError('role-only SOURCE requires its saved plan')
    path = registry.ROOT / relative
    registry.relative_workspace_path(path)
    plan = pipeline.read_json_file(path)
    if plan.get('policy') not in (POLICY, CONSISTENCY_POLICY):
        return None
    if (not plan.get('updates') or plan.get('unresolved')
            or receipt.get('plan_sha256') != registry.sha256_file(path)):
        raise ValueError('keeper SOURCE plan is changed, empty or unresolved')
    base = registry.load_registered_release(previous.season, plan['release_id'])
    expected_parent = (registry.canonical_document_sha256(base.package_path),
        registry.sha256_file(base.compiler_receipt_path), registry.sha256_file(base.build_chain_path))
    actual_parent = tuple(receipt.get(key) for key in ('source_season_package_sha256',
        'source_compiler_receipt_sha256', 'source_build_chain_sha256'))
    if actual_parent != expected_parent:
        raise ValueError('keeper SOURCE receipt does not bind the exact immutable parent')
    verify(base, plan)
    if publisher.updated_package(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited keeper recipe cannot be silently reconstructed')
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    expected, _ = rewrite_indexed_native_roles(before,
        {row['carrier_id']: row['fine_roles'] for row in plan['updates']})
    if expected != (previous.game_path / 'DBDAT/JUG98030.FDI').read_bytes():
        raise ValueError('keeper SOURCE current native bytes differ from its exact plan')
    inventories = [pipeline.read_json_file(item.inventory_path) for item in (base, previous)]
    left, right = [{row['path']: row['sha256'] for row in inv['files']} for inv in inventories]
    if set(left) != set(right) or any(left[key] != right[key] for key in left if key != 'DBDAT/JUG98030.FDI'):
        raise ValueError('keeper SOURCE changed another game file')
    pipeline.assert_tree_matches_inventory(previous.game_path, inventories[1])
    options = {} if minimum_free_bytes is None else {'minimum_free_bytes': minimum_free_bytes}
    publisher.publish(previous.season, path, release_id=release_id,
                      source_release_id=base.release_id, **options)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, inventories[1])
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('keeper SOURCE complete recipe replay differs')
    if not registry.validate_preferred_release(previous.season, release_id=release_id, level='playable')['valid']:
        raise ValueError('keeper SOURCE output failed playable validation')
    return dict(season=previous.season, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        clean_machine_parent_reconstruction=False,
        compilation_mode='source-bound-keeper-role-only-reconstruction')
