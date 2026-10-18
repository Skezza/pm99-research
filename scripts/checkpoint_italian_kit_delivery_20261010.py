"""Append two bounded kit deliveries without resetting any frozen issue count."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts import cascade_compact_kit_v6 as cascade


def run():
    audit = registry.ROOT / '.local/consolidated-audit-20261009'
    root = audit / 'italian-kit-corrections-v1'
    prior = audit / 'release-delivery-checklist-v12.json'
    result = copy.deepcopy(pipeline.read_json_file(prior))
    files = []
    for season, stem in [('2005-06', 'palermo'), ('2006-07', 'atalanta')]:
        release = registry.load_preferred_release(season)
        if (release.release_id != 'sourced-italian-period-kits-20261010-r66c'
                or not registry.validate_preferred_release(season, level='playable')['valid']
                or registry._validate_runtime_attestation(release)):
            raise ValueError('new period kit lacks exact current runtime qualification')
        complete = cascade.installed_contracts(season)
        if complete[223][0]['club'].casefold() != stem:
            raise ValueError('new kit source club differs')
        replay_root = registry.ROOT / '.local/season-visual-replays-v1' / season / 'replayed-italian-period-kits-20261010-r66d'
        proof = pipeline.read_json_file(replay_root / 'replay-proof.json')
        if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
            raise ValueError('new kit game/recipe replay is incomplete')
        native = root / (season + '-v2/candidate/kit-only-native-proof.json')
        if not pipeline.read_json_file(native)['all_game_files_except_three_kit_archives_identical']:
            raise ValueError('new kit modified another native file')
        live_path = root / (stem + '-live-proof-v1.json')
        live = pipeline.read_json_file(live_path)
        if (not live['native_inputs_hash_verified'] or not live['kit_pixels']['passed']
                or registry.sha256_file(registry.ROOT / live['screenshot']) != live['screenshot_sha256']):
            raise ValueError('new kit lacks genuine named-profile pixel proof')
        files.extend([replay_root / 'replay-proof.json', native, live_path,
            root / (season + '-final-attestation.json'),
            root / (season + '-kit-catalogue.json'),
            root / (season + '-v2/delta/complete-kit-receipt.json')])
    old = {row['season']: row for row in result['current_release_bindings']}
    current = bindings()
    for row in current:
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in
                        {layer['label'] for layer in old[row['season']]['layers']}]
        if row['season'] not in ('2005-06', '2006-07') and row != old[row['season']]:
            raise ValueError('unrelated preferred season changed')
        if row['season'] in ('2005-06', '2006-07') and row['package_sha256'] != old[row['season']]['package_sha256']:
            raise ValueError('artwork patch changed the recipe')
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=['2005-06', '2006-07'],
        all_required_work_complete=False,
        next_batch='13 strict stock duplicate/source cases remain. Continue25 source-proven biographic year corrections, number-name identity recovery, positions/opening squads, managers, ratings and global kit/photo visual queues. Original2015 retained.')
    result['delivered_evidence'].extend(binding(path) for path in files)
    item = next(row for row in result['work_items'] if row['id'] == 'kits')
    item['confirmed_target_repairs'] = dict(targets=['Palermo2005/06', 'Atalanta2006/07'],
        all_three_native_icon_sizes_source_bound=True,
        all_unselected_club_bitmaps_preserved=True,
        actual_profile_RIDIESC_pixels_verified=True,
        target_club_TEAM_RATING_or_selection_screens_captured=False,
        global_visual_coverage_complete=False,
        limitations='Period colours/patterns reviewed against original shirt photographs; sponsor logos and fine piping/panels simplified. Not exact-artwork or global historical certification.')
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 13:
        raise ValueError('duplicate denominator drift')
    path = audit / 'release-delivery-checklist-v13.json'
    pipeline.write_canonical_json(path, result)
    print(dict(checklist=binding(path), duplicate_progress=result['within_club_progress'],
        bounded_kit_targets_delivered=2, other24_bindings_unchanged=True), flush=True)


if __name__ == '__main__':
    run()
