"""Count one frozen stock-club repair only after complete source/runtime proof.

Reusable final checkpoint: independently checks native/identity/replay evidence,
an actual corrected-player frame, final-bound normal startup and unchanged
issue IDs/other seasons. It does not regenerate or waive historical sources.
"""
import copy
import re
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit


def native_height_display_inches(height_cm):
    """Match MANAGPRE's two _ftol conversions, not nearest-inch rounding.

    Observed at 0x4c26a0: feet=trunc(cm*0.03280839895013123), then
    inches=trunc((cm-feet*30.48)*0.39370078740157477).
    Research and the actual 197cm profile are bound in the height note.
    """
    if type(height_cm) is not int or not 150 <= height_cm <= 250:
        raise ValueError('invalid native centimetre height')
    feet=int(height_cm*0.03280839895013123)
    inches=int((height_cm-feet*30.48)*0.39370078740157477)
    return feet*12+inches


def verify_profile_review(review, profile, player, year, countries, *, native_height_cm=None):
    from scripts import prepare_duplicate_whole_club_native_v1 as native
    height=re.fullmatch(r'(\d) ft (\d{1,2}) in',review.get('observed_height',''))
    source_height = player['facts']['height_cm']
    if type(source_height) is int:
        if native_height_cm is not None and native_height_cm != source_height:
            raise ValueError('native height differs from published source height')
        expected_height = source_height
    elif source_height == {'policy': 'preserve-existing-mode1'}:
        if type(native_height_cm) is not int:
            raise ValueError('declared fallback height requires actual native readback')
        expected_height = native_height_cm
    else:
        raise ValueError('unsupported source height or undeclared fallback')
    expected_inches=native_height_display_inches(expected_height)
    if (review.get('observed_native_name','').casefold()!=player['name'].casefold()
            or review.get('observed_club')!=profile['club']
            or review.get('observed_skills')!=player['ratings']['values']
            or review.get('observed_age')!=year-int(player['facts']['birth_date'][:4])
            or height is None or int(height[1])*12+int(height[2])!=expected_inches
            or countries.get(review.get('observed_nationality'))!=native.delta.compiler._country_code(player['facts']['nationality'],dict(countries))):
        raise ValueError('original-frame review differs from source-bound native name/skills/age/height/country')
    return True


def run(*, prior, output, season, release_id, case_id, candidate, replay_path,
        profile_path, review_path, visual_path, evidence_dir, attestation_path,
        observed_date, player_carrier, scope):
    if output.exists():
        raise ValueError('completed checkpoint must not be repeated')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    release=registry.load_registered_release(season,release_id)
    native_path=release.package_path.parent/'independent-native.json'
    identity_path=release.package_path.parent/'independent-identity.json'
    receipt_path=release.package_path.parent/'candidate-receipt.json'
    from scripts import season_foreign_fixed_roster_delta_v1 as foreign
    plan_path=release.package_path.parent/foreign.FILENAME
    plan=pipeline.read_json_file(plan_path)
    foreign.verify_plan(plan)
    native,identity,receipt,replay=(pipeline.read_json_file(p) for p in [native_path,identity_path,receipt_path,replay_path])
    if plan['source_adapter'] in (foreign.BORAC_2003_ADAPTER,foreign.HAJDUK_2002_ADAPTER,foreign.MONAGAS_2003_ADAPTER,foreign.MONAGAS_2002_ADAPTER,foreign.SARTID_2000_ADAPTER,foreign.ESTUDIANTES_2000_ADAPTER,foreign.MLADOST_2001_ADAPTER):
        # This adapter permits explicitly unavailable height/weight facts.
        # Re-read all18 actual fields and prove their seed-slot preservation;
        # do not let a plausible screenshot certify an invented source value.
        import tempfile
        from pathlib import Path
        from scripts import verify_ofk_2004_private_native_v1 as readback
        with tempfile.TemporaryDirectory(prefix='pm99-borac-final-native-') as temporary:
            current_native = readback.verify(release.package_path.parent, Path(temporary) / 'proof.json',
                proposal_path=registry.ROOT / plan['original_proposal']['path'], source_bound_game=True)
        if current_native != native:
            raise ValueError('strict declared-fallback native readback differs from retained proof')
    if (not native['source_bound_complete_game'] or not native['source_allocation_replayed']
            or not native['all_selected_native_ownership_exclusive'] or not native['source_people_unique']
            or len(native['players'])!=plan['fixed_slots'] or not native['unrelated_native_records_byte_identical']
            or native['package_sha256']!=registry.sha256_file(release.package_path)
            or native['source_candidate_receipt_sha256']!=registry.sha256_file(receipt_path)
            or identity['candidate_receipt_sha256']!=registry.sha256_file(receipt_path)
            or identity['package_sha256']!=native['package_sha256']
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared'] or not identity['unselected_recipe_people_clubs_managers_identical']
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
            or receipt['game_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']
            or receipt['plan_sha256']!=registry.sha256_file(plan_path) or plan['season']!=season):
        raise ValueError('complete source/native/identity/reconstruction proof incomplete')
    private_receipt=candidate/'candidate-receipt.json'
    if pipeline.read_json_file(private_receipt)['game_inventory_fingerprint']!=receipt['game_inventory_fingerprint']:
        raise ValueError('actual profile candidate differs from final published game')
    profile,review=(pipeline.read_json_file(p) for p in [profile_path,review_path])
    package=pipeline.read_json_file(release.package_path)
    player=next(p for p in package['players'] if p['carrier_id']==player_carrier)
    from scripts import prepare_duplicate_whole_club_native_v1 as native_tools
    countries=native_tools.delta.compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    from app.editor_actions import _read_native_dd6360_fields
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entry = next(e for e in native_tools.IndexedFDIFile.from_bytes(jug).entries if e.record_id == player_carrier)
    raw = entry.decode_payload(jug)
    if raw[2:5] != bytes.fromhex('dd6360'):
        raise ValueError('compact foreign checkpoint cannot decode an extended player record')
    actual = native_tools.source.roster.native_player(raw, player_carrier)
    fields = _read_native_dd6360_fields(raw, actual['name_end'])
    verify_profile_review(review,profile,player,package['season']['start_year'],countries,
        native_height_cm=fields['height_cm'])
    if (profile['player_carrier_id']!=player_carrier or profile['club']!=plan['kit_source_catalogue']['rows'][0]['club_name']
            or not profile['native_inputs_hash_verified'] or not profile['kit_pixels']['passed']
            or profile['candidate_receipt_sha256']!=registry.sha256_file(private_receipt)
            or profile['screenshot_sha256']!=review['screenshot_sha256']
            or registry.sha256_file(registry.ROOT/profile['screenshot'])!=profile['screenshot_sha256']
            or not review.get('all_ten_visible_skills_inspected') or not review.get('nationality_height_age_inspected')):
        raise ValueError('original corrected-player membership/skills/facts/kit frame not inspected')
    visual=pipeline.read_json_file(visual_path)
    summary=pipeline.read_json_file(evidence_dir/'summary.json')
    if (visual['observed_team']!='Stoke City' or visual['observed_date']!=observed_date
            or not visual['original_frame_visually_inspected']
            or registry.sha256_file(registry.ROOT/visual['screenshot'])!=visual['screenshot_sha256']
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or not summary['success'] or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):
        raise ValueError('fresh final-bound original normal startup proof incomplete')
    birthday=audit(season,release_id)
    # Compare against this transaction's exact known-good baseline, not an
    # obsolete snapshot that predates later delivered birthday repairs.
    previous=audit(season,receipt['baseline_release_id'])
    if birthday['failures']!=previous['failures']:
        raise ValueError('transaction changed frozen birthday issue accounting')
    old={r['season']:r for r in result['current_release_bindings']}
    if registry.load_preferred_release(season).release_id not in (release_id,receipt['baseline_release_id']):
        raise ValueError('another worker changed preferred season baseline')

    def checked_bindings():
        current=bindings()
        for row in current:
            labels={layer['label'] for layer in old[row['season']]['layers']}
            row['layers']=[layer for layer in row['layers'] if layer['label'] in labels]
            if row['season']!=season and row!=old[row['season']]:
                raise ValueError('an unselected preferred season changed')
        return current

    checked_bindings()
    case=next(c for c in result['within_club_cases'] if c['id']==case_id)
    if case['status']!='open-source-and-ownership-review' or case['season']!=season:
        raise ValueError('case already counted or wrong season')
    old_count=sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases'])
    progress=result['within_club_progress']
    if old_count!=progress['open_real_club_cases'] or len(result['within_club_cases'])!=82:
        raise ValueError('frozen duplicate accounting inconsistent before promotion')
    register_completed_delta(season,release_id)
    attestation=runtime.attest(season=season,evidence_dir=evidence_dir)
    if attestation_path.exists():
        if pipeline.read_json_file(attestation_path)!=attestation:
            raise ValueError('retained attestation changed')
    else:
        pipeline.write_canonical_json(attestation_path,attestation)
    files=[native_path,identity_path,receipt_path,release.package_path.parent/'foreign-fixed-roster.json',
        replay_path,profile_path,review_path,visual_path,attestation_path]
    case.update(status='confirmed-fault-repaired-current-game',delivery=dict(release_id=release_id,
        evidence=[binding(p) for p in files],actual_team_XI_screen_captured=False,scope=scope))
    progress.update(confirmed_faults_repaired=progress['confirmed_faults_repaired']+1,
        disposed=progress['disposed']+1,open_real_club_cases=old_count-1)
    if sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases'])!=old_count-1:
        raise ValueError('frozen duplicate identities drifted')
    result['delivered_evidence'].extend(binding(p) for p in files)
    birthday_remaining=next(w['current_remaining_native_recipe_disagreements'] for w in result['work_items'] if w['id']=='birthdays')
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=checked_bindings(),fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch=f'{old_count-1} real stock cases remain; {birthday_remaining} frozen birthday disagreements and original cross-club, roles, managers, ratings and global visual checklist still open.')
    pipeline.write_canonical_json(output,result)
    return dict(checklist=binding(output),within_club_progress=progress,other25_preferred_bindings_unchanged=True,all_required_work_complete=False)
