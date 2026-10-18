"""Promote only after actual source/native/SOURCE and original runtime proof."""
import copy
from datetime import UTC,datetime
from scripts import season_source_verified_player_changes_v1 as changes
from scripts.publish_confirmed_country_changes_20261017 import ROOT,FOLDER,RELEASE,REPLAY
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.consolidated_season_discovery_v1 import bindings
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime

TAG='profile_countries_2013_14_r145a_20261017'


def main():
    output=ROOT/'release-delivery-checklist-v114.json'
    if output.exists():raise ValueError('completed checkpoint must not repeat')
    prior=ROOT/'release-delivery-checklist-v113.json'
    result=copy.deepcopy(changes.pipeline.read_json_file(prior))
    assert result['remaining_cross_club_cases']==2762 and len(result['cross_club_dispositions'])==47
    actual=changes.registry.load_registered_release('2013-14',RELEASE)
    replay=changes.registry.load_registered_release('2013-14',REPLAY)
    native=changes.pipeline.read_json_file(FOLDER/'independent-native-recipe-proof.json')
    source=changes.pipeline.read_json_file(FOLDER/'complete-SOURCE-replay.json')
    assert native['actual_manifest_sha256']==actual.manifest_sha256
    assert native['native_changed_bytes']==5 and native['parent_inventory_unchanged']
    assert native['all_other_game_files_identical'] and native['all_other_recipe_data_identical']
    assert source['complete_game_inventory_identical'] and source['complete_recipe_identical']
    assert actual.package_path.read_bytes()==replay.package_path.read_bytes()
    startup=changes.pipeline.read_json_file(FOLDER/'startup-visual-review.json')
    check_visual(startup)
    assert startup['observed_team']=='Stoke City' and startup['observed_date']=='2013-08-01'
    assert startup['release_manifest_sha256']==actual.manifest_sha256
    visual=changes.pipeline.read_json_file(FOLDER/'moses-profile-visual-review.json')
    check_visual(visual,nationality='ENGLAND')
    assert visual['observed_native_name']=='Tunji MOSES' and visual['observed_club']=='Hyde'
    transport=changes.pipeline.read_json_file(FOLDER/'moses-profile-transport.json')
    assert transport['exit_code']==0 and transport['release_manifest_sha256']==actual.manifest_sha256
    evidence=changes.registry.ROOT/transport['evidence']
    summaries=list(evidence.rglob('summary.json'));assert len(summaries)==1
    profile_root=summaries[0].parent
    summary=changes.pipeline.read_json_file(summaries[0])
    assert summary['success'] and not summary.get('wine_debugger_detected')
    assert summary['player_profile']['expected_name_token_satisfied']
    assert changes.registry.sha256_file(profile_root/'input-provenance.json')==changes.registry.sha256_file(actual.compiler_receipt_path)
    hashes={line.split()[1]:line.split()[0] for line in (profile_root/'dbdat_override.sha256').read_text().splitlines() if line and not line.startswith('#')}
    for name in ('JUG98030.FDI','EQ98030.FDI','ENT98030.FDI'):
        assert hashes['DBDAT/'+name]==changes.registry.sha256_file(actual.game_path/'DBDAT'/name)
    assert changes.registry.sha256_file(profile_root/'screens'/summary['player_profile']['screenshot'].split('/')[-1])==visual['screenshot_sha256']
    old={r['season']:r for r in result['current_release_bindings']}
    before=bindings()
    assert before==result['current_release_bindings']
    backup=verify_original2015()
    publisher.register_completed_delta('2013-14',RELEASE)
    after=bindings()
    assert all(row==old[row['season']] for row in after if row['season']!='2013-14')
    assert next(row for row in after if row['season']=='2013-14')['release_id']==RELEASE
    attestation=runtime.attest(season='2013-14',evidence_dir=changes.registry.ROOT/'.local/runlogs/pm99_runner'/TAG)
    changes.pipeline.write_canonical_json(FOLDER/'final-attestation.json',attestation)
    valid=changes.registry.validate_preferred_release('2013-14',level='playable')
    assert valid['valid']
    changes.pipeline.write_canonical_json(FOLDER/'preferred-playable-validation.json',valid)
    follow=next(r for r in result['new_required_followups'] if r['id']=='Hyde2013-original-profile-country-omissions')
    assert len(follow['cases'])==5 and {r['carrier_id'] for r in follow['cases']}=={r['carrier_id'] for r in native['observations']}
    follow.update(status='delivered-native-SOURCE-and-runner-verified',delivery=changes.binding(FOLDER/'independent-native-recipe-proof.json'))
    for row in follow['cases']:row.update(delivered=True,delivered_release=RELEASE,delivered_country='ENG')
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=changes.binding(prior),
        current_release_bindings=after,fresh_runtime_runs_this_checklist=['2013-14'],all_required_work_complete=False,
        next_batch='Atomic Barrow2017 opening squad plus Accrington wrong-owner correction using shared source-bound roster path; remaining candidates still require review.')
    result['delivered_evidence'].append(backup)
    result['delivered_evidence'].extend(changes.binding(FOLDER/name) for name in (
        'independent-native-recipe-proof.json','complete-SOURCE-replay.json','startup-visual-review.json',
        'startup-transport.json','moses-profile-visual-review.json','moses-profile-transport.json',
        'final-attestation.json','preferred-playable-validation.json'))
    changes.pipeline.write_canonical_json(output,result)
    print(dict(checklist=str(output),actual_country_corrections=5,duplicate_dispositions_unchanged=47,
               remaining_cross_club_candidates=2762,complete=False),flush=True)


if __name__=='__main__':main()
