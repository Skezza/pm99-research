"""Publish Japan only after literal final-game nationality and digit checks."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_takano_period_country_20261017 as build
from scripts.capture_takano_period_country_20261017 import TAG,PROFILE
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def bind(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def check_alias_scope(scope,current):
    def projected(rows):
        return sorted((r['season'],r['release_id'],r['manifest_sha256']) for r in rows)
    if (len(scope['bindings'])!=26 or len({r['season'] for r in scope['bindings']})!=26
            or projected(scope['bindings'])!=projected(current) or len(scope['matches'])!=1
            or (scope['matches'][0]['season'],scope['matches'][0]['layer'],scope['matches'][0]['carrier_id'])
                !=(build.SEASON,'main',10992)):
        raise ValueError('all26 exact published-alias cascade scope differs; inspect other occurrences before publication')


def main(previous_version):
    old_path=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed Takano country publication must not repeat')
    previous=pipeline.read_json_file(old_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('Takano previous checkpoint differs from actual preferred games')
    scope_path=build.ROOT/'all26-Takano-alias-scope-v91.json'
    scope=pipeline.read_json_file(scope_path)
    check_alias_scope(scope,initial)
    base=registry.load_preferred_release(build.SEASON)
    if base.release_id!=build.BASE:raise ValueError('country baseline advanced; preserve intervening fixes')
    actual=registry.load_registered_release(build.SEASON,build.RELEASE)
    plan=pipeline.read_json_file(build.ROOT/'country-plan.json');build.source.verify(base,plan)
    retained(build.ROOT/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    rebuilt=registry.load_registered_release(build.SEASON,build.REPLAY)
    proof=pipeline.read_json_file(build.ROOT/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
        raise ValueError('Takano full SOURCE proof incomplete')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Takano full SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport=pipeline.read_json_file(build.ROOT/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(build.ROOT/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!='2000-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('Takano final actual game startup not independently approved')
    digits(build.ROOT,build.SEASON,build.RELEASE,[PROFILE]);verify_profiles(build.ROOT,build.SEASON,build.RELEASE,[PROFILE])
    review=pipeline.read_json_file(build.ROOT/'takano_japan-profile-visual-review.json')
    if (review.get('observed_nationality')!='JAPAN' or review.get('observed_position')!='MIDFIELDER'
            or review['observed_club']!='Morecambe' or review['observed_age']!=24):
        raise ValueError('literal final original Takano Japan/MIDFIELDER/retained age observation differs')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('preferred game changed during Takano prepublication')
    publisher.register_completed_delta(build.SEASON,build.RELEASE)
    retained(build.ROOT/'final-attestation.json',runtime.attest(season=build.SEASON,evidence_dir=evidence))
    playable=registry.validate_preferred_release(build.SEASON,level='playable')
    if not playable['valid']:raise ValueError('Takano final preferred game failed playable gate')
    retained(build.ROOT/'preferred-playable-validation.json',playable)
    current=bindings()
    if [r for r in current if r['season']!=build.SEASON]!=[r for r in initial if r['season']!=build.SEASON]:
        raise ValueError('Takano country publication changed another season')
    result=copy.deepcopy(previous)
    for finding in result['additional_confirmed_findings']:
        if finding['id']=='Takano2000-inherited-England-fallback-and-secondary-birthday-disagreement':
            finding.update(state='country-JPN-delivered-native-SOURCE-runner-verified-birthday-choice-still-explicitly-disputed',
                current_nationality_in_runner='JAPAN',country_evidence=bind(build.ROOT/'takano_japan-profile-visual-review.json'))
    names=['country-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'independent-prepublication-native-proof.json','final-attestation.json','preferred-playable-validation.json']
    names += ['takano_japan'+s for s in ('-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup,bind(scope_path)]+[bind(build.ROOT/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[build.SEASON],all_required_work_complete=False,
        next_batch='Continue frozen2789 cross-club cases and source/native club-identity candidate adjudications; preserve declared spelling aliases. Remaining opening positions/managers/known facts/assets/final regression unchanged. Takano optional DOB conflict remains disclosed, not a native/recipe mismatch.')
    pipeline.write_canonical_json(output,result)
    retained(build.ROOT/'final-delivery-summary.json',dict(checklist=bind(output),country_corrections_delivered=1,
        native_byte_changes=1,opening_squad_and_all_birthdays_preserved=True,unchanged_other25_preferred_bindings=True,
        original2015_backup_verified=True,cross_club_cases_closed=0,global_historical_RC=False))
    print(dict(Takano_Japan_delivered=True,global_historical_RC=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-version',type=int,required=True)
    main(parser.parse_args().previous_version)
