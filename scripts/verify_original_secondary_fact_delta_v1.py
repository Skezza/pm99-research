"""Independent actual-byte/fact readback, not merely replay of the writer."""
import copy
from datetime import date
from app.fdi_indexed import IndexedFDIFile
from scripts import season_original_secondary_facts_v1 as layer
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def verify(season, release_id, plan_path, output):
    if output.exists():
        raise ValueError('secondary-fact independent proof is immutable')
    plan = pipeline.read_json_file(plan_path)
    base = registry.load_registered_release(season, plan['release_id'])
    release = registry.load_registered_release(season, release_id)
    layer.verify(base, plan)
    saved = registry.ROOT / release.locator['sourced_profile_assignment_plan_path']
    if pipeline.read_json_file(saved) != plan:
        raise ValueError('compiled secondary-fact source plan differs')
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if len(before) != len(after):
        raise ValueError('secondary-fact native length changed')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed, observed = set(), []
    for row in plan['updates']:
        entry = entries[row['carrier_id']]
        old = entry.decode_payload(before)
        new = entry.decode_payload(after)
        native = layer.original.audit.native_player(old, row['carrier_id'])
        end = native['name_end']
        seen = dict(carrier_id=row['carrier_id'])
        if 'birth_date' in row['fields'] or 'native_birth_year' in row['fields']:
            dob = date(int.from_bytes(bytes(v ^ 0x61 for v in new[end+14:end+16]), 'little'),
                new[end+13] ^ 0x61, new[end+12] ^ 0x61).isoformat()
            if dob != row['birth_date']:
                raise ValueError('actual stored full birthday differs from original entity')
            start = 14 if 'native_birth_year' in row['fields'] else 12
            allowed.update(range(entry.payload_offset+end+start, entry.payload_offset+end+16))
            seen['birth_date'] = dob
        if 'nationality' in row['fields']:
            if new[end+8] ^ 0x61 != row['native_country_code']:
                raise ValueError('actual stored nationality differs from original period source')
            allowed.add(entry.payload_offset+end+8)
            seen['nationality'] = row['nationality']
        observed.append(seen)
    changed = {i for i, (a,b) in enumerate(zip(before, after)) if a != b}
    if not changed <= allowed:
        raise ValueError('secondary-fact delta changed unrelated native bytes')
    before_inventory = pipeline.read_json_file(base.inventory_path)
    after_inventory = pipeline.read_json_file(release.inventory_path)
    def inventory_files(doc):
        return {r['path']: (r['sha256'], r['size']) for r in doc['files']}
    old_files, new_files = inventory_files(before_inventory), inventory_files(after_inventory)
    if set(old_files) != set(new_files) or any(old_files[p] != new_files[p]
            for p in old_files if p != 'DBDAT/JUG98030.FDI'):
        raise ValueError('secondary-fact repair changed other game files')
    pipeline.assert_tree_matches_inventory(release.game_path, after_inventory)
    package = pipeline.read_json_file(release.package_path)
    expected = copy.deepcopy(pipeline.read_json_file(base.package_path))
    people = {p['carrier_id']: p for p in expected['players']}
    for row in plan['updates']:
        player = people[row['carrier_id']]
        if player != row['before_player']:
            raise ValueError('independent secondary-fact recipe preimage differs')
        for field in row['fields']:
            if field == 'native_birth_year':
                continue
            player['facts'][field] = row[field]
        if 'fact_fallbacks' in player:
            player['fact_fallbacks'] = [f for f in player['fact_fallbacks'] if f['field'] not in row['fields']]
    artifact_id = layer.PREFIX + season + '-' + plan['transaction_id']
    additions = [a for a in package['artifacts'] if a['id'] == artifact_id]
    if (len(additions) != 1 or additions[0]['sha256'] != registry.sha256_file(saved)
            or additions[0]['relative_path'] != layer.filename(plan)):
        raise ValueError('independent secondary-fact proof artifact differs')
    without_new_artifact = copy.deepcopy(package)
    without_new_artifact['artifacts'] = [a for a in package['artifacts'] if a['id'] != artifact_id]
    if without_new_artifact != expected:
        raise ValueError('secondary-fact repair changed unrelated recipe facts')
    result = dict(schema_version='pm99-original-secondary-fact-independent-byte-readback-v1',
        season=season, release_id=release_id, source_release_id=base.release_id,
        source_plan_sha256=registry.sha256_file(saved),
        package_sha256=registry.sha256_file(release.package_path), updates=observed,
        native_bytes_changed=len(changed), all_other_native_bytes_identical=True,
        all_other_game_files_identical=True, all_other_recipe_facts_identical=True,
        scope='Selected factual corrections only; no general ownership/roles/ratings/portraits approval')
    pipeline.write_canonical_json(output, result)
    return result
