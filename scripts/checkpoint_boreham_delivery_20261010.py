"""Close one fixed case only after the complete coupled delivery is verified."""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts import season_boreham_opening_repair_v1 as boreham

AUDIT = registry.ROOT / '.local/consolidated-audit-20261009'


def run():
    prior = AUDIT / 'release-delivery-checklist-v10.json'
    result = copy.deepcopy(pipeline.read_json_file(prior))
    release = registry.load_preferred_release('2017-18')
    if release.release_id != 'sourced-boreham-retained-opening-20261010-r64b':
        raise ValueError('final retained-plus-coupled delivery is not preferred')
    if not registry.validate_preferred_release('2017-18', level='playable')['valid'] or registry._validate_runtime_attestation(release):
        raise ValueError('preferred delivery lacks exact runtime qualification')
    files = ['boreham-triple-complete-native-proof-v1.json',
        'boreham-triple-complete-identity-proof-v1.json', 'boreham-triple-full-rebuild-proof-v1.json',
        'boreham-retained-opening-plan-v1.json', 'boreham-retained-opening-native-proof-v1.json',
        'boreham-retained-opening-full-rebuild-proof-v1.json', 'boreham-complete-final-identity-proof-v1.json',
        'boreham-final-runtime-attestation-v1.json']
    pair_replay = pipeline.read_json_file(AUDIT / files[2])
    retained_replay = pipeline.read_json_file(AUDIT / files[5])
    identity = pipeline.read_json_file(AUDIT / files[6])
    native = pipeline.read_json_file(AUDIT / files[4])
    if not (pair_replay['complete_game_inventory_identical'] and pair_replay['complete_recipe_identical']
            and pair_replay['all_nine_kit_artifacts_freshly_rerendered']
            and retained_replay['complete_game_inventory_identical'] and retained_replay['complete_recipe_identical']
            and identity['introduced_candidate_groups']==0 and identity['young_Ryan_count']==1
            and native['original_xi_readback'] and native['unselected_native_records_exact']):
        raise ValueError('incomplete independent native/reconstruction/identity proofs')
    for label, person, club in [('wrexham','Scott Boden','Wrexham'),
            ('chester','Ross Hannah','Chester'),('guiseley','Frank Mulhern','Guiseley'),
            ('retained-Ryan','Ryan Johnson','Boreham Wood')]:
        filename = ('boreham-triple-'+label+'-live-profile-proof-v1.json'
                    if label != 'retained-Ryan' else 'boreham-retained-Ryan-live-profile-proof-v1.json')
        path = AUDIT / filename; live = pipeline.read_json_file(path)
        if not (live['source_name']==person and live['observed_club']==club
                and live['native_inputs_hash_verified'] and live['kit_pixels']['passed']
                and registry.sha256_file(registry.ROOT/live['screenshot'])==live['screenshot_sha256']):
            raise ValueError('actual named club profile or bitmap input differs')
        files.append(filename)
    case = next(c for c in result['within_club_cases'] if c['id']==boreham.CASE)
    if case['status'] != 'open-source-and-ownership-review':
        raise ValueError('fixed case already counted')
    case.update(status='confirmed-fault-repaired-current-game',delivery=dict(
        release_id=release.release_id,evidence=[binding(AUDIT/name) for name in files],
        actual_team_XI_screen_captured=False,
        scope='False duplicate club3329 retired in complete52-slot Wrexham/Chester/Guiseley transaction. Legitimate young Ryan restored to retained Boreham3304 with missing Bruno/Frank, original XI/bench, two birthdays and Balanta forward role. Three replacement managers and period kit styles/grounds source-bound. Four genuine named profiles and compact kit pixels verified. Other historical facts and portraits are not approved.'))
    old = {b['season']:b for b in result['current_release_bindings']}; current = bindings()
    for row in current:
        labels = {layer['label'] for layer in old[row['season']]['layers']}
        row['layers']=[layer for layer in row['layers'] if layer['label'] in labels]
        if row['season'] != '2017-18' and row != old[row['season']]:
            raise ValueError('unrelated preferred season changed')
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=20,disposed=68,open_real_club_cases=14)
    if len(result['within_club_cases'])!=82 or sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases'])!=14:
        raise ValueError('frozen case denominator drift')
    proof = AUDIT / 'boreham-final-current26-binding-proof-v1.json'
    pipeline.write_canonical_json(proof,dict(utc=datetime.now(UTC).isoformat(),
        changed_season_fresh_runtime_attested='2017-18',unchanged25_exact_bindings=True,
        fresh_all26_sweep=False,current_release_bindings=current))
    result['delivered_evidence'].extend(binding(AUDIT/name) for name in files)
    result['delivered_evidence'].append(binding(proof))
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=current,fresh_runtime_runs_this_checklist=['2017-18'],
        all_required_work_complete=False,next_batch='Barrow2012 source/mapping case plus13 strict Becej/Minerven stock cases. All other original checklist queues still OPEN; original2015 retained.')
    output = AUDIT / 'release-delivery-checklist-v11.json'
    pipeline.write_canonical_json(output,result)
    print(dict(checklist=binding(output),progress=progress),flush=True)


if __name__ == '__main__':
    run()
