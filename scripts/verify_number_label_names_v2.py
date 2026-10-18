"""Read original versus actual renamed records independently of the writer."""
from datetime import date

from app.editor_actions import _indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile
from scripts import season_number_label_names_v2 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.audit_compiled_player_birth_dates_v1 import inspect
from scripts import probe_dd6361_skill_patch as skills


def verify(season, release_id, plan_path, output):
    if output.exists():
        raise ValueError('numeric-label independent evidence is immutable')
    plan = pipeline.read_json_file(plan_path)
    base = registry.load_registered_release(season, plan['release_id'])
    release = registry.load_registered_release(season, release_id)
    source.verify(base, plan)
    saved = registry.ROOT / release.locator['sourced_player_name_only_plan_path']
    if pipeline.read_json_file(saved) != plan:
        raise ValueError('published numeric-label plan differs')
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    old_index, new_index = IndexedFDIFile.from_bytes(before), IndexedFDIFile.from_bytes(after)
    old_entries, new_entries = {e.record_id: e for e in old_index.entries}, {e.record_id: e for e in new_index.entries}
    selected = {r['carrier_id']: r for r in plan['updates']}
    if len(selected) != len(plan['updates']) or not selected or len(before) != len(after) or set(old_entries) != set(new_entries):
        raise ValueError('numeric-label empty/duplicate updates or changed native directory')
    allowed = set()
    for carrier, entry in old_entries.items():
        new_entry = new_entries[carrier]
        if (entry.payload_offset, entry.payload_length) != (new_entry.payload_offset, new_entry.payload_length):
            raise ValueError('numeric-label carrier directory changed')
        old, new = entry.decode_payload(before), new_entry.decode_payload(after)
        if carrier not in selected:
            if old != new:
                raise ValueError('numeric-label unrelated native player changed')
            continue
        row = selected[carrier]
        a, b = _indexed_variable_name_runtime_segments(old), _indexed_variable_name_runtime_segments(new)
        if a != b:
            raise ValueError('numeric-label string widths or footer cursor shifted')
        if old[:a['full_len_offset']] != new[:b['full_len_offset']]:
            raise ValueError('numeric-label changed existing surname/header component')
        actual_name = source.audit.native_player(new, carrier)['name']
        if source.literal_name(actual_name) != source.literal_name(row['display_name']):
            raise ValueError('numeric-label actual full-name string differs')
        old_suffix = bytearray(old[a['full_name_end']:])
        if row['repair_birth_year']:
            old_suffix[14:16] = bytes(value ^ 0x61 for value in date.fromisoformat(row['birth_date']).year.to_bytes(2, 'little'))
        new_end = b['full_name_end']
        if bytes(old_suffix) != new[new_end:new_end+len(old_suffix)] or any(value != 0x61 for value in new[new_end+len(old_suffix):]):
            raise ValueError('numeric-label changed an undeclared native suffix field/tail')
        allowed.update(range(entry.payload_offset, entry.payload_offset+entry.payload_length))
    if any(a != b and n not in allowed for n, (a, b) in enumerate(zip(before, after))):
        raise ValueError('numeric-label changed a byte outside declared carriers')
    old_package, package = pipeline.read_json_file(base.package_path), pipeline.read_json_file(release.package_path)
    reconstructed = dict(package, players=[dict(p) for p in package['players']],
        artifacts=[a for a in package['artifacts'] if a['id'] != source.PREFIX+season])
    people = {p['carrier_id']: p for p in reconstructed['players']}
    for carrier, row in selected.items():
        person = people[carrier]
        if person['name'] != row['display_name'] or person['source_name'] != row['source_name']:
            raise ValueError('numeric-label recipe strings differ')
        person['name'], person['source_name'] = row['before_player']['name'], row['before_player']['source_name']
    if reconstructed != old_package:
        raise ValueError('numeric-label modified another recipe fact/record/evidence')
    before_inventory = pipeline.read_json_file(base.inventory_path)
    after_inventory = pipeline.read_json_file(release.inventory_path)
    pipeline.assert_tree_matches_inventory(base.game_path, before_inventory)
    pipeline.assert_tree_matches_inventory(release.game_path, after_inventory)
    # Native and visual assets are all protected, not only a short known-file list.
    old_files = {r['path']: r['sha256'] for r in before_inventory['files']}
    new_files = {r['path']: r['sha256'] for r in after_inventory['files']}
    if {k: v for k, v in old_files.items() if k != 'DBDAT/JUG98030.FDI'} != {k: v for k, v in new_files.items() if k != 'DBDAT/JUG98030.FDI'}:
        raise ValueError('numeric-label changed another game file/asset')
    first, last = inspect(old_package, before), inspect(package, after)
    repaired = sum(row['repair_birth_year'] for row in selected.values())
    if first['failure_count']-last['failure_count'] != repaired:
        raise ValueError('numeric-label literal birthday reduction differs from declared repairs')
    old_stats = skills.build_dd6361_pid_stats_index(player_file=base.game_path / 'DBDAT/JUG98030.FDI')
    new_stats = skills.build_dd6361_pid_stats_index(player_file=release.game_path / 'DBDAT/JUG98030.FDI')
    if set(old_stats) != set(new_stats) or any(any(old_stats[pid][key] != new_stats[pid][key]
            for key in ('mapped10', 'decoded18', 'role_ratings5', 'unknown_byte16_candidate')) for pid in old_stats):
        raise ValueError('numeric-label global visible skill/role-rating semantics changed')
    result = dict(season=season, release_id=release_id, source_release_id=base.release_id,
        original_name_strings_repaired=len(selected), birth_years_repaired=repaired,
        before_birthday_disagreements=first['failure_count'], after_birthday_disagreements=last['failure_count'],
        original_surname_components_preserved=True, all_other_native_suffix_bytes_identical=True,
        all_biographic_stat_ids_preserved=True, all_visible_skills_and_role_ratings_identical=True,
        biographic_stat_records_checked=len(old_stats),
        all_other_game_files_identical=True, all_other_recipe_facts_identical=True,
        package_sha256=registry.sha256_file(release.package_path), source_plan_sha256=registry.sha256_file(saved),
        scope='Independent exact name/year delta, not opening-roster ownership, surname correction or portrait approval')
    pipeline.write_canonical_json(output, result)
    return result
