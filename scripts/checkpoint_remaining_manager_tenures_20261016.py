"""Promote the remaining-manager batch only with exact game and runtime proof.

Source admission is not delivery. All selected seasons pass independent
readback and original screenshot review before the first preferred change.
"""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_remaining_manager_tenures_20261016 as source
from scripts import build_remaining_manager_tenures_20261016 as batch
from scripts.capture_remaining_manager_tenures_20261016 import tag
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


def verify_original2015():
    """Check the retained actual game, not just an 'untouched' status flag."""
    document=pipeline.read_json_file(registry.ROOT/'data/retained-season-releases-v1.json')
    matches=[r for r in document['releases'] if (r['season'],r['release_id'])==('2015-16','legacy-world-2015-16')]
    if len(matches)!=1:
        raise ValueError('exact original2015 retention missing or ambiguous')
    retained_row=matches[0]
    original=registry.load_registered_release('2015-16','legacy-world-2015-16')
    if (registry.sha256_file(registry.ROOT/retained_row['locator_path'])!=retained_row['locator_sha256']
            or registry.sha256_file(original.inventory_path)!=retained_row['inventory_sha256']):
        raise ValueError('retained original2015 locator or sealed inventory changed')
    pipeline.assert_tree_matches_inventory(original.game_path,pipeline.read_json_file(original.inventory_path))
    path=batch.ROOT/'original2015-retained-inventory-verification.json'
    proof=pipeline.read_json_file(path)
    if proof['original_retention']!=retained_row or not proof['all_original_game_files_verified']:
        raise ValueError('original2015 evidence does not bind the sealed retention')
    return binding(path)


def run():
    previous = batch.ROOT.parent / 'release-delivery-checklist-v54.json'
    output = batch.ROOT.parent / 'release-delivery-checklist-v55.json'
    if output.exists():
        raise ValueError('completed publication must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(previous))
    admission_path = batch.ROOT / 'source-admission-summary.json'
    admission = pipeline.read_json_file(admission_path)
    if admission['original_deferred_cases_admitted'] != 36:
        raise ValueError('all original remaining36 cases must be accounted for')
    admitted = admission['seasons']
    if [r['season'] for r in admitted] != registry.supported_seasons():
        raise ValueError('source admission must cover all26 seasons exactly once')
    originals = {r['season']: r for r in result['current_release_bindings']}
    seasons = [r['season'] for r in admitted if r['corrections']]
    # No publication until every independent native and reviewed runner proof passes.
    rows = [verify(s) for s in seasons]
    if sum(r['canonical_manager_updates'] for r in rows) != admission['admitted_cases']:
        raise ValueError('actual update count differs from source admission')
    selected = {r['season']: r for r in rows}
    for season in registry.supported_seasons():
        actual = registry.load_preferred_release(season); old = originals[season]
        if actual.release_id == old['release_id']:
            if actual.manifest_sha256 != old['manifest_sha256']:
                raise ValueError('preferred parent manifest changed')
        elif season not in selected or (actual.release_id, actual.manifest_sha256) != (
                batch.RELEASE, selected[season]['manifest_sha256']):
            raise ValueError('unexpected preferred change; preserve intervening corrections')
    # Recheck the user's fun backup before any preferred-season mutation.
    original2015_proof=verify_original2015()
    evidence = [original2015_proof]
    for row in rows:
        season = row['season']; root = batch.ROOT / season
        retained(root / 'prepublication-proof.json', row)
        publisher.register_completed_delta(season, batch.RELEASE)
        if not (root / 'final-attestation.json').exists():
            retained(root / 'final-attestation.json', runtime.attest(season=season,
                evidence_dir=registry.ROOT / '.local/runlogs/pm99_runner' / tag(season)))
        valid = registry.validate_preferred_release(season, level='playable')
        if not valid['valid']:
            raise ValueError('preferred game failed playable validation')
        retained(root / 'preferred-playable-validation.json', valid)
        evidence.extend(binding(root / name) for name in ('manager-plan.json', 'native-byte-proof.json',
            'complete-SOURCE-replay.json', 'startup-transport.json', 'startup-visual-review.json',
            'prepublication-proof.json', 'final-attestation.json', 'preferred-playable-validation.json'))
    current = bindings()
    for row in current:
        if row['season'] not in selected and row != originals[row['season']]:
            raise ValueError('unselected preferred binding changed')
    finding = dict(id='remaining-original-August1-managers-and-coupled-owners-v1',
        state='delivered-native-SOURCE-and-runner-verified', seasons=len(seasons),
        original_deferred_cases_delivered=36, original85_now_delivered=85,
        additional_coupled_club_changes=admission['additional_coupled_club_changes'],
        canonical_updates=sum(r['canonical_manager_updates'] for r in rows),
        actual_ENT_records_changed=sum(r['actual_ENT_records_changed'] for r in rows),
        actual_visible_short_names_changed=sum(r['actual_visible_short_names_changed'] for r in rows),
        actual_native_display_names_changed=sum(r['actual_native_display_names_changed'] for r in rows),
        cross_club_cases_closed=0, global_manager_approval=False,
        ambiguous_club_entities_and_missing_timeline_sources_not_approved=True,
        all_player_ratings_tactics_ownership_and_artwork_preserved=True)
    result['additional_confirmed_findings'].append(finding)
    result['delivered_evidence'].extend(evidence + [binding(admission_path)])
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(previous),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=seasons,
        all_required_work_complete=False,
        next_batch='Continue frozen2797 cross-club candidates, dated opening squads/positions, broader manager source/identity gaps including ambiguous club entities, global kit/photo and known-wrong fact QA. Original85 deferred manager cases delivered; no global manager or roster approval.')
    pipeline.write_canonical_json(output, result)
    retained(batch.ROOT / 'final-delivery-summary.json', dict(finding, checklist=binding(output),
        original2015_backup_untouched=True, global_historical_RC=False))
    print(dict(delivered=True, **finding, checklist=binding(output)), flush=True)


if __name__ == '__main__':
    run()
