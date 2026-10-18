"""Independent byte/recipe readback for source-backed goalkeeper label deltas."""
import copy
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from scripts import season_sourced_goalkeeper_roles_v1 as source
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def verify(season, release_id, plan_path, output):
    if output.exists():
        raise ValueError('goalkeeper role verification evidence is immutable')
    plan = json.loads(plan_path.read_text())
    base = registry.load_registered_release(season, plan['release_id'])
    release = registry.load_registered_release(season, release_id)
    source.verify(base, plan)
    saved = registry.ROOT / release.locator['historical_role_plan_path']
    if json.loads(saved.read_text()) != plan:
        raise ValueError('compiled goalkeeper source plan differs')
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if len(before) != len(after):
        raise ValueError('role-only delta changed the indexed file length')
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed = set()
    for row in plan['updates']:
        entry = index[row['carrier_id']]
        old = entry.decode_payload(before)
        native = audit.native_player(old, row['carrier_id'])
        end = native['name_end']
        # Independent native-byte expectation: the outer/inner XOR cancels.
        first = entry.payload_offset + end + 2
        if after[first:first+6] != bytes([1, 0, 0, 0, 0, 0]):
            raise ValueError('actual six stored role bytes are not goalkeeper + five unused')
        if native['position'] != 'G' or native['roles'][0] == 0:
            raise ValueError('plan did not repair an actual wrong-label native keeper')
        allowed.update(range(first, first+6))
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    if not changed <= allowed:
        raise ValueError('goalkeeper delta changed other native bytes')
    unchanged = {}
    for name in ('EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF', 'RIDIESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF'):
        digest = registry.sha256_file(release.game_path / 'DBDAT' / name)
        if digest != registry.sha256_file(base.game_path / 'DBDAT' / name):
            raise ValueError('goalkeeper delta changed another native/archive file')
        unchanged[name] = digest
    if registry.sha256_file(release.game_path / 'MANAGPRE.EXE') != registry.sha256_file(base.game_path / 'MANAGPRE.EXE'):
        raise ValueError('goalkeeper delta changed the executable')
    original = json.loads(base.package_path.read_text())
    package = json.loads(release.package_path.read_text())
    expected_people = copy.deepcopy(original['players'])
    updates = {r['player_id']: r for r in plan['updates']}
    for player in expected_people:
        if player['id'] in updates:
            player['facts']['fine_roles'] = [0]
    if package['players'] != expected_people:
        raise ValueError('goalkeeper recipe delta changed unrelated facts or ratings')
    for key in original:
        if key not in ('players', 'artifacts', 'proofs') and package[key] != original[key]:
            raise ValueError('goalkeeper recipe delta changed another collection')
    old_artifacts = [a for a in original['artifacts'] if a['id'] != 'historical-role-plan-' + season]
    new_artifacts = [a for a in package['artifacts'] if a['id'] != 'historical-role-plan-' + season]
    old_proofs = [a for a in original['proofs'] if a['id'] != 'proof-historical-roles-' + season]
    new_proofs = [a for a in package['proofs'] if a['id'] != 'proof-historical-roles-' + season]
    if old_artifacts != new_artifacts or old_proofs != new_proofs:
        raise ValueError('goalkeeper recipe delta changed unrelated evidence')
    result = {'schema_version': 'pm99-sourced-goalkeeper-role-independent-readback-v1',
              'season': season, 'release_id': release_id, 'source_release_id': base.release_id,
              'corrected_goalkeeper_labels': len(plan['updates']), 'native_bytes_changed': len(changed),
              'all_other_native_bytes_identical': True, 'all_other_recipe_facts_ratings_identical': True,
              'unchanged_native_hashes': unchanged, 'executable_unchanged': True,
              'JUG_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
              'package_sha256': registry.sha256_file(release.package_path),
              'source_plan_sha256': registry.sha256_file(saved),
              'source_policy': source.POLICY,
              'scope': 'literal sourced goalkeeper role labels only; not roster/first-XI/skills/portrait/kit clearance'}
    pipeline.write_canonical_json(output, result)
    return result
