"""Deliver49 admitted August1 coaches only after21 exact-game runtime reviews.

All85 originally deferred cases remain accounted for:49 delivered,36 open.
No unrelated historical roster or source-coverage queue is silently closed.
"""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_august_manager_tenures_20261016 as source
from scripts import build_august_manager_tenures_20261016 as batch
from scripts.capture_august_manager_tenures_20261016 import tag
from scripts import checkpoint_cached_managers_20261016 as core
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def verify(season):
    plan = pipeline.read_json_file(batch.ROOT / season / 'manager-plan.json')
    return core.verify(season, evidence_root=batch.ROOT / season, release_id=batch.RELEASE,
        source_module=source, run_tag=tag(season), source_release_id=plan['release_id'])


def run():
    previous = batch.ROOT.parent / 'release-delivery-checklist-v53.json'
    output = batch.ROOT.parent / 'release-delivery-checklist-v54.json'
    if output.exists():
        raise ValueError('completed manager publication must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(previous))
    admission = pipeline.read_json_file(batch.ROOT / 'source-admission-summary.json')
    if (admission['original_receipt_backed_candidates'], admission['admitted'], admission['unresolved']) != (53, 49, 4):
        raise ValueError('frozen original manager admission counts changed')
    seasons = [r['season'] for r in admission['seasons'] if r['corrections']]
    if len(seasons) != 21:
        raise ValueError('only exact21 admitted seasons may be selected')
    originals = {r['season']: r for r in result['current_release_bindings']}
    rows = [verify(s) for s in seasons]
    if sum(r['canonical_manager_updates'] for r in rows) != 49:
        raise ValueError('actual verified canonical manager count differs from admission')
    selected = {r['season']: r for r in rows}
    for season in registry.supported_seasons():
        actual = registry.load_preferred_release(season); old = originals[season]
        if actual.release_id == old['release_id']:
            if actual.manifest_sha256 != old['manifest_sha256']:
                raise ValueError('preferred parent manifest changed')
        elif season not in selected or (actual.release_id, actual.manifest_sha256) != (
                batch.RELEASE, selected[season]['manifest_sha256']):
            raise ValueError('unexpected preferred change; preserve intervening corrections')
    evidence = []
    for row in rows:
        season = row['season']; root = batch.ROOT / season
        retained(root / 'prepublication-proof.json', row)
        publisher.register_completed_delta(season, batch.RELEASE)
        if not (root / 'final-attestation.json').exists():
            retained(root / 'final-attestation.json', runtime.attest(season=season,
                evidence_dir=registry.ROOT / '.local/runlogs/pm99_runner' / tag(season)))
        valid = registry.validate_preferred_release(season, level='playable')
        if not valid['valid']:
            raise ValueError('actual preferred manager game failed playable validation')
        retained(root / 'preferred-playable-validation.json', valid)
        evidence.extend(binding(root / n) for n in ('manager-plan.json', 'native-byte-proof.json',
            'complete-SOURCE-replay.json', 'startup-transport.json', 'startup-visual-review.json',
            'prepublication-proof.json', 'final-attestation.json', 'preferred-playable-validation.json'))
    current = bindings()
    for row in current:
        if row['season'] not in selected and row != originals[row['season']]:
            raise ValueError('unselected preferred binding changed')
    finding = dict(id='original-August1-manager-tenures-v1', state='delivered-native-SOURCE-and-runner-verified',
        seasons=21, originally_deferred=85, original_receipt_backed_candidates=53,
        canonical_updates=49, actual_visible_short_names_changed=sum(r['actual_visible_short_names_changed'] for r in rows),
        actual_native_display_names_changed=sum(r['actual_native_display_names_changed'] for r in rows),
        deferred_remaining=36, identical_full_name_people_still_deferred=4,
        global_manager_approval=False, legacy2015_unchanged=True, cross_club_cases_closed=0,
        all_player_ratings_tactics_ownership_and_artwork_preserved=True)
    result['additional_confirmed_findings'].append(finding)
    result['delivered_evidence'].extend(evidence + [binding(batch.ROOT / 'source-admission-summary.json')])
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(previous),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=seasons,
        all_required_work_complete=False,
        next_batch='Continue frozen2797 cross-club candidates, dated opening squads/positions,36 deferred coaches including four distinct-person Phil Parkinson admissions, older manager proof gaps/legacy2015, global kit/photo and known-wrong fact QA. Preserve all birthday/rating/roster/artwork fixes.')
    pipeline.write_canonical_json(output, result)
    retained(batch.ROOT / 'final-delivery-summary.json', dict(finding, checklist=binding(output),
        unselected5_preferred_unchanged=True, original2015_backup_untouched=True, global_historical_RC=False))
    print(dict(delivered=True, **finding, checklist=binding(output)), flush=True)


if __name__ == '__main__':
    run()
