"""Independent exact readback of a club-name-only restoration."""
import json
from scripts import season_original_carrier_label_restoration_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher


def verify(base, actual, plan):
    policy = source
    from scripts import season_original_carrier_label_restoration_v2 as exact_page
    if plan.get('schema_version') == exact_page.SCHEMA:
        policy = exact_page
    policy.verify(base, plan)
    before = (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    after = (actual.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    expected, changes = source.labels.rewrite_club_labels(before, plan['updates'])
    if expected != after or len(changes) != len(plan['updates']):
        raise ValueError('club label native delta differs from exact bound scope')
    old = source.IndexedFDIFile.from_bytes(before); new = source.IndexedFDIFile.from_bytes(after)
    entries = {e.record_id:e for e in old.entries}; targets = {r['carrier_id'] for r in plan['updates']}
    if {e.record_id for e in new.entries} != set(entries):
        raise ValueError('club restoration changed indexed directory membership')
    for entry in new.entries:
        a = entries[entry.record_id].decode_payload(before); b = entry.decode_payload(after)
        if entry.record_id in targets:
            if source.labels.prefix_parts(a)[2] != source.labels.prefix_parts(b)[2]:
                raise ValueError('restored club changed ground, manager, roster or opaque bytes')
        elif a != b:
            raise ValueError('restored club changed another native team')
    left = {r['path']:r['sha256'] for r in source.pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']:r['sha256'] for r in source.pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left) != set(right) or any(left[k] != right[k] for k in left if k != 'DBDAT/EQ98030.FDI'):
        raise ValueError('club label edit changed a player, coach, executable or image file')
    inert = dict(season=base.season, release_id=base.release_id, package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'], updates=[], unresolved=[])
    manager = dict(schema_version='pm99-historical-manager-plan-v1', season=base.season,
        release_id=base.release_id, package_sha256=plan['package_sha256'], eq_sha256=plan['eq_sha256'],
        ent_sha256=plan['ent_sha256'], updates=[], unresolved=[])
    if publisher.updated_package(source.pipeline.read_json_file(base.package_path), inert,
            manager_plan=manager, club_plan=plan) != source.pipeline.read_json_file(actual.package_path):
        raise ValueError('club restoration recipe changed outside exact labels/provenance')
    return dict(source_native_original_registry_and_dated_coach_ground_verified=True,
        current_manifest_sha256=actual.manifest_sha256,
        changed_clubs=json.loads(source.pipeline.canonical_json_bytes(changes)),
        all_players_coaches_grounds_rosters_tactics_EXE_and_assets_preserved=True,
        missing_keeper_secondary_facts_and_complete_opening_squad_still_open=True)
