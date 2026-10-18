"""Record a source-bound delivery without changing the frozen case baseline."""
import copy
from datetime import UTC, datetime
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.attest_registered_season_runtime_v1 import attest
from scripts.consolidated_season_discovery_v1 import bindings, write_new
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding

AUDIT = registry.ROOT / '.local/consolidated-audit-20261009'
CASE = '2c01311314826e92f838732f4049bdbb8a1f3f3dab539de196dd43de8bfed553'


def run():
    previous = AUDIT / 'release-delivery-checklist-v9.json'
    result = copy.deepcopy(pipeline.read_json_file(previous))
    release = registry.load_preferred_release('2002-03')
    if release.release_id != 'sourced-stevenage-opening-manager-20261010-r63b':
        raise ValueError('current delivery binding changed')
    native = pipeline.read_json_file(AUDIT / 'stevenage-2002-opening-native-proof-v1.json')
    replay = pipeline.read_json_file(AUDIT / 'stevenage-2002-opening-rebuild-proof-v1.json')
    manager = pipeline.read_json_file(AUDIT / 'stevenage-2002-opening-manager-native-proof-v1.json')
    manager_replay = pipeline.read_json_file(AUDIT / 'stevenage-2002-opening-manager-rebuild-proof-v1.json')
    live = pipeline.read_json_file(AUDIT / 'stevenage-2002-opening-live-Sigere-proof-v1.json')
    if not (native['visible_Midson_count'] == 1 and native['all_other_native_records_identical']
            and replay['complete_game_inventory_identical'] and replay['complete_recipe_identical']
            and manager_replay['complete_game_inventory_identical']
            and manager['all_players_clubs_tactics_photos_kits_exe_identical']
            and manager['other_native_manager_records_identical']
            and live['all_uploaded_hashes_verified'] and live['visual_inspected']):
        raise ValueError('incomplete source/native/reconstruction/runtime evidence')
    for key in ('screenshot', 'summary'):
        b = live[key]
        if registry.sha256_file(registry.ROOT / b['path']) != b['sha256']:
            raise ValueError('live evidence changed')
    runtime = attest(season='2002-03', evidence_dir=registry.ROOT /
        '.local/runlogs/pm99_runner/stevenage_r63b_stoke_lineup_20261010')
    runtime_path = AUDIT / 'stevenage-2002-opening-manager-runtime-attestation-v1.json'
    if runtime_path.exists():
        if pipeline.read_json_file(runtime_path) != runtime:
            raise ValueError('prior runtime receipt changed')
    else:
        write_new(runtime_path, runtime)
    old = {r['season']: r for r in result['current_release_bindings']}
    current = bindings()
    # Earlier checkpoints pinned the main recipe only. Compare precisely that
    # recorded scope; do not mistake a newly enumerated English layer for a
    # changed game. Record the extra existing layer separately below.
    additional_layers = []
    for row in current:
        declared = {layer['label'] for layer in old[row['season']]['layers']}
        additional_layers.extend(dict(season=row['season'], **layer)
            for layer in row['layers'] if layer['label'] not in declared)
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in declared]
    for row in current:
        if row['season'] != '2002-03' and row != old[row['season']]:
            raise ValueError('unrelated preferred season changed')
    evidence = [AUDIT / ('stevenage-2002-' + suffix + '-v1.json') for suffix in (
        'opening-repair-plan', 'opening-native-proof', 'opening-rebuild-proof',
        'opening-live-Sigere-proof', 'retained-August-reserve-source-proof',
        'opening-manager-plan', 'opening-manager-native-proof', 'opening-manager-rebuild-proof')]
    evidence.append(runtime_path)
    case = next(c for c in result['within_club_cases'] if c['id'] == CASE)
    if case['status'] != 'open-source-and-ownership-review':
        raise ValueError('case already counted')
    case.update(status='confirmed-fault-repaired-current-game', delivery=dict(
        release_id=release.release_id, evidence=[binding(p) for p in evidence],
        actual_team_XI_screen_captured=False,
        scope='Eight sourced opening people replace legacy identities; one Midson remains. Original XI/bench orders, three birthdays and conservative primary roles repaired. Dated Wayne Turner manager separately delivered; other facts/assets not historically approved.'))
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=19, disposed=67, open_real_club_cases=15)
    if len(result['within_club_cases']) != 82 or sum(
            c['status'] == 'open-source-and-ownership-review'
            for c in result['within_club_cases']) != 15:
        raise ValueError('frozen baseline drift')
    proof_path = AUDIT / 'stevenage-2002-current26-binding-proof-v1.json'
    write_new(proof_path, dict(utc=datetime.now(UTC).isoformat(),
        changed_season_fresh_runtime_attested='2002-03', fresh_all26_sweep=False,
        unchanged25_exact_bindings=True, current_release_bindings=current,
        additional_existing_layers_not_previously_enumerated=additional_layers))
    result['delivered_evidence'].extend(binding(p) for p in evidence + [proof_path])
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(previous),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=['2002-03'],
        all_required_work_complete=False,
        next_batch='15 real cases: Boreham2017 source-provider identity conflict and missing original starters; Barrow2012 paired club mapping; 13 Becej/Minerven stock source gaps without a waiver. Other original required queues remain OPEN.')
    output = AUDIT / 'release-delivery-checklist-v10.json'
    write_new(output, result)
    print(dict(checklist=binding(output), progress=progress))


if __name__ == '__main__':
    run()
