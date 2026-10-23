"""Exact readback of a source-verified club-label and manager-name delta."""
import json
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_club_label_plan_v1 as labels
from scripts import publish_historical_role_delta_v1 as publisher


def verify(base, actual, plan, *, policy):
    policy.verify(base, plan)
    manager = plan['manager_plan']
    policy.verify_manager_pair(plan, manager)
    if len(plan['updates']) != 1 or len(manager['updates']) != 1:
        raise ValueError('one explicitly paired club and manager required')
    club, coach = plan['updates'][0], manager['updates'][0]
    if club['carrier_id'] != coach['club_carrier_id']:
        raise ValueError('manager correction belongs to another club')
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    expected_eq, changes = labels.rewrite_club_labels(eq, plan['updates'])
    if (actual.game_path / 'DBDAT/EQ98030.FDI').read_bytes() != expected_eq:
        raise ValueError('actual club-label bytes differ')
    ent = (base.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    index = IndexedFDIFile.from_bytes(ent)
    entries = {e.record_id: e for e in index.entries}
    carrier = coach['carrier_id']
    replacement = publisher._patch_ent_name(entries[carrier].decode_payload(ent), carrier, coach['native_after'])
    expected_ent = publisher._rebuild_indexed(ent, index, {carrier: replacement})
    if (actual.game_path / 'DBDAT/ENT98030.FDI').read_bytes() != expected_ent:
        raise ValueError('actual manager bytes differ from the exact one-name rewrite')
    holders, names = publisher._manager_graph(eq_path=actual.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=actual.game_path / 'DBDAT/ENT98030.FDI')
    if names.get(carrier) != coach['native_after'] or [c['carrier_id'] for c in holders.get(carrier, [])] != [club['carrier_id']]:
        raise ValueError('actual native manager name/exclusive owner differs')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    changed = sorted(k for k in left.keys() & right.keys() if left[k] != right[k])
    if left.keys() != right.keys() or changed != ['DBDAT/ENT98030.FDI', 'DBDAT/EQ98030.FDI']:
        raise ValueError('coupled name correction changed another file or inventory path')
    descriptor = dict(season=base.season, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[])
    expected_package = publisher.updated_package(pipeline.read_json_file(base.package_path),
        descriptor, manager_plan=manager, club_plan=plan)
    if expected_package != pipeline.read_json_file(actual.package_path):
        raise ValueError('coupled recipe differs outside exact source-backed fields')
    return dict(season=base.season, parent_release_id=base.release_id, release_id=actual.release_id,
        manifest_sha256=actual.manifest_sha256, club_carrier_id=club['carrier_id'],
        club_after=club['after'], manager_carrier_id=carrier, manager_after=coach['after'],
        native_manager_after=coach['native_after'], changed_files=changed,
        all_players_dates_countries_roles_orders_skills_tactics_assets_EXE_exact=True,
        exact_recipe_binding=True, native_manager_exclusive_owner_verified=True,
        native_club_changes=json.loads(pipeline.canonical_json_bytes(changes)),
        global_historical_RC=False)
