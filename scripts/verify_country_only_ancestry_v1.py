"""Verify private country-only ancestors without making intermediates default.

Read-only: every edge needs its own exact source plan, compiler binding and
complete SOURCE copy. Only the final country's meaning is approved; an old
mapping overridden by a later edge must never become a public default.
"""
from dataclasses import dataclass

from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as v1
from scripts import season_original_country_policy_v2 as v2
from scripts import season_resolved_period_country_v3 as v3


@dataclass(frozen=True)
class Edge:
    release_id: str
    replay_id: str
    root: object


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def validate_scope(plan):
    rows = plan.get('updates', [])
    if (not rows or plan.get('unresolved') != []
            or any(row.get('fields') != ['nationality'] for row in rows)
            or len({row['carrier_id'] for row in rows}) != len(rows)
            or plan.get('targets') != {str(row['carrier_id']): ['nationality'] for row in rows}):
        raise ValueError('country ancestry requires unique, nonempty nationality-only source scope')


def read_country(entry, data, carrier):
    payload = entry.decode_payload(data)  # Container XOR and field XOR are distinct layers.
    native = v1.original.audit.native_player(payload, carrier)
    relative = native['name_end'] + 8
    return payload[relative] ^ 0x61, entry.payload_offset + relative


def walk(actual, base, descriptors):
    if actual.season != base.season or actual.manifest_sha256 == base.manifest_sha256:
        raise ValueError('country ancestry requires a distinct final release in the same season')
    edges = {edge.release_id: edge for edge in descriptors}
    if len(edges) != len(descriptors) or len(edges) > 8:
        raise ValueError('country ancestry descriptors duplicate a release or exceed bounded depth')
    pending, seen, child = [], set(), actual
    while child.manifest_sha256 != base.manifest_sha256:
        if child.release_id in seen or child.release_id not in edges or len(pending) >= 8:
            raise ValueError('country ancestry cycle, missing explicit proof, or excessive depth')
        seen.add(child.release_id)
        edge = edges[child.release_id]
        path = registry.ROOT / child.locator.get('sourced_profile_assignment_plan_path', '')
        plan = pipeline.read_json_file(path)
        policies = {v1.SCHEMA: v1, v2.SCHEMA: v2, v3.SCHEMA: v3}
        if plan.get('schema') not in policies or plan.get('season') != actual.season:
            raise ValueError('country ancestry contains a non-country policy or another season')
        validate_scope(plan)
        if plan.get('release_id') == child.release_id:
            raise ValueError('country ancestry self-parent cycle')
        parent = registry.load_registered_release(actual.season, plan['release_id'])
        pending.append((parent, child, edge, policies[plan['schema']], path, plan))
        child = parent
    return list(reversed(pending))


def verify_edge(parent, child, edge, source, path, plan):
    source.verify(parent, plan)  # Reparse/hash dated raw witnesses; no cached approval.
    if (path.resolve() != (child.package_path.parent / source.filename(plan)).resolve()
            or registry.sha256_file(path) != registry.sha256_file(edge.root / 'country-plan.json')):
        raise ValueError('country ancestry source plan differs from retained build proof')
    replay = registry.load_registered_release(child.season, edge.replay_id)
    if replay.release_id == child.release_id:
        raise ValueError('country ancestry SOURCE replay cannot be the actual release itself')
    plan_sha = registry.sha256_file(path)
    for release in (child, replay):
        saved = registry.ROOT / release.locator.get('sourced_profile_assignment_plan_path', '')
        receipt = pipeline.read_json_file(release.compiler_receipt_path)
        if (receipt.get('compilation_mode') != source.MODE
                or receipt.get('original_profile_assignment_plan_sha256') != plan_sha
                or registry.sha256_file(saved) != plan_sha):
            raise ValueError('country ancestry SOURCE compiler or plan binding differs')
        descriptor = pipeline.read_json_file(release.package_path.parent / 'role-delta-input.json')
        if descriptor != dict(season=parent.season, release_id=parent.release_id,
                package_sha256=registry.sha256_file(parent.package_path),
                jug_sha256=registry.sha256_file(parent.game_path / 'DBDAT/JUG98030.FDI'),
                updates=[], unresolved=[]):
            raise ValueError('country ancestry SOURCE parent descriptor differs')
    replay_proof = pipeline.read_json_file(edge.root / 'complete-SOURCE-replay.json')
    if (replay_proof.get('complete_game_inventory_identical') is not True
            or replay_proof.get('complete_recipe_identical') is not True):
        raise ValueError('country ancestry lacks a complete SOURCE receipt')
    for release in (parent, child, replay):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(child.inventory_path))
    if replay.package_path.read_bytes() != child.package_path.read_bytes():
        raise ValueError('country ancestry full SOURCE recipe differs')
    before = (parent.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (child.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (parent.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before, eq, plan) != (after, eq) or source.apply(after, eq, plan) != (after, eq):
        raise ValueError('country ancestry whole native reconstruction or idempotence differs')
    if source.bind(pipeline.read_json_file(parent.package_path), plan) != pipeline.read_json_file(child.package_path):
        raise ValueError('country ancestry changed unrelated recipe facts')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(parent.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(child.inventory_path)['files']}
    if set(left) != set(right) or any(left[k] != right[k] for k in left if k != 'DBDAT/JUG98030.FDI'):
        raise ValueError('country ancestry changed another game file')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed = set()
    for row in plan['updates']:
        entry = entries[row['carrier_id']]
        country, offset = read_country(entry, after, row['carrier_id'])
        if country != row['native_country_code']:
            raise ValueError('country ancestry independent native country readback differs')
        allowed.add(offset)
    if len(before) != len(after) or any(a != b and i not in allowed for i, (a, b) in enumerate(zip(before, after))):
        raise ValueError('country ancestry changed a non-nationality native byte')
    return dict(parent_release_id=parent.release_id, parent_manifest_sha256=parent.manifest_sha256,
        release_id=child.release_id, manifest_sha256=child.manifest_sha256,
        replay_id=replay.release_id, replay_manifest_sha256=replay.manifest_sha256,
        source_plan=binding(path), retained_plan=binding(edge.root / 'country-plan.json'),
        SOURCE_receipt=binding(edge.root / 'complete-SOURCE-replay.json'),
        compiler_receipt=binding(child.compiler_receipt_path),
        replay_compiler_receipt=binding(replay.compiler_receipt_path), countries=len(plan['updates']))


def verify(actual, base, descriptors):
    steps = walk(actual, base, descriptors)
    effective, origins, proofs = {}, {}, []
    for parent, child, edge, source, path, plan in steps:
        proofs.append(verify_edge(parent, child, edge, source, path, plan))
        for row in plan['updates']:
            effective[row['carrier_id']] = row
            origins[row['carrier_id']] = binding(path)
    # Independent final-vs-public byte scope; latest source country wins. Final
    # semantic labels are checked by the publication gate, never by the old map.
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (actual.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed = set()
    for carrier, row in effective.items():
        entry = entries[carrier]
        country, offset = read_country(entry, after, carrier)
        if country != row['native_country_code']:
            raise ValueError('country ancestry final native country differs from latest source')
        allowed.add(offset)
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    if len(before) != len(after) or not changed <= allowed:
        raise ValueError('country ancestry final game changed unrelated native bytes')
    proof = dict(schema='pm99-verified-country-only-ancestry-v1', season=actual.season,
        base_release_id=base.release_id, base_manifest_sha256=base.manifest_sha256,
        final_release_id=actual.release_id, final_manifest_sha256=actual.manifest_sha256,
        edges=proofs, source_countries=len(effective), native_country_bytes_changed=len(changed),
        intermediate_defaults_published=0, all_other_game_and_recipe_facts_preserved=True)
    return [effective[k] for k in sorted(effective)], origins, proof
