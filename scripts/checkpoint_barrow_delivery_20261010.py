"""Close the one fixed Barrow case without changing the82-case denominator."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts import season_barrow_opening_repair_v1 as source

AUDIT = registry.ROOT / '.local/consolidated-audit-20261009'


def run():
    prior = AUDIT/'release-delivery-checklist-v11.json'
    result = copy.deepcopy(pipeline.read_json_file(prior))
    release = registry.load_preferred_release('2012-13')
    if release.release_id != 'sourced-barrow-retained-label-manager-20261010-r65e':
        raise ValueError('correct final Barrow delivery is not preferred')
    if (not registry.validate_preferred_release(release.season,level='playable')['valid']
            or registry._validate_runtime_attestation(release)):
        raise ValueError('preferred delivery lacks exact runtime qualification')
    files = ['barrow-wrexham-complete-native-proof-v1.json',
        'barrow-wrexham-complete-identity-proof-v1.json','barrow-wrexham-full-rebuild-proof-v1.json',
        'barrow-retained-opening-plan-v2.json','barrow-retained-opening-full-rebuild-proof-v2.json',
        'barrow-retained-club-plan-v2.json','barrow-retained-manager-plan-v2.json',
        'barrow-retained-label-manager-full-rebuild-proof-v2.json',
        'barrow-complete-final-native-identity-proof-v2.json','barrow-final-runtime-attestation-v1.json']
    for name in [files[2],files[4],files[7]]:
        proof = pipeline.read_json_file(AUDIT/name)
        if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
            raise ValueError('whole game/recipe reconstruction incomplete')
    native = pipeline.read_json_file(AUDIT/files[8])
    if not (native['original_xi_readback'] and native['original_published_bench_readback']
            and native['unselected_native_records_exact'] and native['dated_Bayliss_exclusive_native_owner']
            and native['stale_portraits_cleared'] and native['young_Rowe_count']==1
            and native['introduced_candidate_groups']==0
            and native['package_sha256']==registry.sha256_file(release.package_path)):
        raise ValueError('independent combined native/identity proof incomplete')
    for name, person, club in [('barrow-wrexham-morrell-live-proof-v1.json','Andy Morrell','Wrexham'),
            ('barrow-retained-mukendi-live-proof-v1.json','Vinny Mukendi','Barrow')]:
        live = pipeline.read_json_file(AUDIT/name)
        if not (live['source_name']==person and live['observed_club']==club
                and live['native_inputs_hash_verified'] and live['kit_pixels']['passed']
                and registry.sha256_file(registry.ROOT/live['screenshot'])==live['screenshot_sha256']):
            raise ValueError('named original club profile/bitmap inputs differ')
        files.append(name)
    case = next(c for c in result['within_club_cases'] if c['id']==source.CASE)
    if case['status']!='open-source-and-ownership-review':
        raise ValueError('fixed Barrow case already counted')
    case.update(status='confirmed-fault-repaired-current-game',delivery=dict(release_id=release.release_id,
        evidence=[binding(AUDIT/name) for name in files],actual_team_XI_screen_captured=False,
        scope='Retire false Barrow3312 into original Wrexham18/dated Morrell/period kit/ground. Restore four original substitutes in retained actual Barrow3325, including distinct1990 keeper Pearson; legitimate young Rowe1992 remains, late older copy removed. Original XI/five bench order and Skelton midfield role restored; actual retained label and dated Bayliss822 corrected separately. Two genuine named club profiles/compact bitmap inputs and fresh normal Stoke startup proved. Existing retained reserve ownership, source name/role conflicts and kit/ground historical design remain explicit queues; no overall historical approval.'))
    old = {b['season']:b for b in result['current_release_bindings']}; current = bindings()
    for row in current:
        scope = {layer['label'] for layer in old[row['season']]['layers']}
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in scope]
        if row['season']!='2012-13' and row!=old[row['season']]:
            raise ValueError('unrelated preferred season changed')
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=21,disposed=69,open_real_club_cases=13)
    if len(result['within_club_cases'])!=82 or sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases'])!=13:
        raise ValueError('fixed case denominator drift')
    path = AUDIT/'barrow-final-current26-binding-proof-v1.json'
    pipeline.write_canonical_json(path,dict(utc=datetime.now(UTC).isoformat(),
        changed_season_fresh_runtime_attested='2012-13',unchanged25_exact_bindings=True,
        fresh_all26_sweep=False,current_release_bindings=current))
    result['delivered_evidence'].extend(binding(AUDIT/name) for name in files)
    result['delivered_evidence'].append(binding(path))
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=current,fresh_runtime_runs_this_checklist=['2012-13'],
        all_required_work_complete=False,
        next_batch='13 strict Becej/Minerven stock source cases remain. Continue original other checklist queues; Barrow retained reserves/name/role/kit/ground gaps explicit. Original2015 retained.')
    output = AUDIT/'release-delivery-checklist-v12.json'
    pipeline.write_canonical_json(output,result)
    print(dict(checklist=binding(output),progress=progress),flush=True)


if __name__=='__main__':
    run()
