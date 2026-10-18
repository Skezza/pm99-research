"""Build an approved reserve request, prove byte scope, then replay its SOURCE.

This is orchestration over the existing compiler, not another database writer.
Request JSON carries the season data; no player or club is hardcoded here.
"""
import argparse
import re
import shutil
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_opening_identity_exchange_v1 as source
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.season_within_club_reserve_repair_v1 import native_facts


def reserve_space():
    if shutil.disk_usage(registry.ROOT).free < 8 * 1024 ** 3:
        raise ValueError('8GiB reserve required; no new build/replay started')


def deliver(request_path, release_id, replay_id, evidence_dir):
    if (release_id == replay_id or any(not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,95}', value)
                                      for value in (release_id, replay_id))):
        raise ValueError('distinct lowercase release/replay IDs required')
    request = pipeline.read_json_file(request_path)
    if request['release_id'] in (release_id, replay_id):
        raise ValueError('output IDs must not collide with the immutable source release')
    if request.get('orders'):
        raise ValueError('this reserve-only orchestration preserves all startup orders')
    if (registry.locator_path(request['season'], replay_id).exists()
            and not (evidence_dir / 'complete-SOURCE-replay.json').exists()):
        raise ValueError('unreceipted replay exists; inspect before any new publisher writes')
    existing_receipt = evidence_dir / 'complete-SOURCE-replay.json'
    if existing_receipt.exists():
        receipt = pipeline.read_json_file(existing_receipt)
        if (receipt.get('season') != request['season'] or receipt.get('release_id') != replay_id
                or receipt.get('complete_game_inventory_identical') is not True
                or receipt.get('complete_recipe_identical') is not True):
            raise ValueError('existing SOURCE proof binds another or incomplete replay; no publication')
    base = registry.load_registered_release(request['season'], request['release_id'])
    plan = source.prepare(base, request_path)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    plan_path = evidence_dir / source.filename(plan)
    retained(plan_path, plan)
    inert = evidence_dir / 'inert.json'
    retained(inert, dict(season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]))
    if not registry.locator_path(base.season, release_id).exists():
        reserve_space()
        publisher.publish(base.season, inert, release_id=release_id, source_release_id=base.release_id,
                          profile_assignment_plan_path=plan_path)
    child = registry.load_registered_release(base.season, release_id)
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after = (child.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after_eq = (child.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before, eq, plan) != (after, after_eq) or source.apply(after, after_eq, plan) != (after, after_eq):
        raise ValueError('actual native correction or idempotence differs')
    selected = source.selected_carriers(plan)
    preserve_other_records(before, after, selected)
    old = pipeline.read_json_file(base.package_path)
    new = pipeline.read_json_file(child.package_path)
    if source.bind(old, plan) != new:
        raise ValueError('actual recipe differs from approved request')
    old_players = {p['carrier_id']: p for p in old['players']}
    new_players = {p['carrier_id']: p for p in new['players']}
    if any(new_players[c] != actor for c, actor in old_players.items() if c not in selected):
        raise ValueError('unselected recipe actor changed')
    observed = []
    for carrier in sorted(selected):
        facts = native_facts(after, carrier)
        actor = new_players[carrier]
        if (facts['name'].casefold() != actor['name'].casefold()
                or facts['birth_date'] != actor['facts']['birth_date']
                or facts['position'] != actor['facts']['primary_position']
                or facts['startup_order'] != native_facts(before, carrier)['startup_order']):
            raise ValueError('actual selected identity or preserved order differs')
        observed.append(dict(carrier_id=carrier, **facts))
    expected_photos, _ = delta.no_photo_archive((base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes(), selected)
    if expected_photos != (child.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes():
        raise ValueError('portrait archive differs beyond selected identities')
    loose = {f'DBDAT/MINIFOTO/J96{c:05d}.BMP' for c in selected}
    if any((child.game_path / name).exists() for name in loose):
        raise ValueError('displaced loose portrait remains')
    left = {f['path']: f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
    right = {f['path']: f['sha256'] for f in pipeline.read_json_file(child.inventory_path)['files']}
    allowed = {'DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/MINIFOTO.PKF'} | loose
    if any(left.get(k) != right.get(k) for k in set(left) | set(right) if k not in allowed):
        raise ValueError('unrelated game file changed')
    valid = registry.validate_preferred_release(base.season, release_id=release_id, level='playable')
    if not valid['valid']:
        raise ValueError('actual child failed playable validation')
    proof = dict(schema='pm99-fixed-reserve-actual-build-proof-v1', season=base.season,
        release_id=release_id, source_release_id=base.release_id, selected_carriers=sorted(selected),
        native_new_people=observed, source_plan=source.binding(plan_path),
        all_unselected_actors_exact=True, all_unselected_native_records_exact=True,
        all_original_startup_orders_preserved=True, all_unrelated_game_files_identical=True,
        selected_portrait_clearing_exact=True, actual_native_idempotent=True, playable_validation=valid)
    retained(evidence_dir / 'native-and-unchanged-proof.json', proof)
    replay_path = evidence_dir / 'complete-SOURCE-replay.json'
    if not replay_path.exists():
        if registry.locator_path(base.season, replay_id).exists():
            raise ValueError('unreceipted replay exists; inspect without regeneration')
        reserve_space()
        retained(replay_path, source.reconstruction(child, replay_id))
    else:
        receipt = pipeline.read_json_file(replay_path)
        if (receipt.get('season') != base.season or receipt.get('release_id') != replay_id
                or not receipt.get('complete_game_inventory_identical')
                or not receipt.get('complete_recipe_identical')):
            raise ValueError('existing SOURCE proof binds another replay')
        replay = registry.load_registered_release(base.season, replay_id)
        pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(child.inventory_path))
        if replay.package_path.read_bytes() != child.package_path.read_bytes():
            raise ValueError('existing SOURCE recipe replay differs')
    return dict(season=base.season, release_id=release_id, built=True, SOURCE_replay_verified=True,
                preferred=registry.load_preferred_release(base.season).release_id == release_id,
                runtime_verified=not registry._validate_runtime_attestation(child), changed_carriers=sorted(selected))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--replay-id', required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    print(deliver(args.request, args.release_id, args.replay_id, args.evidence_dir), flush=True)
