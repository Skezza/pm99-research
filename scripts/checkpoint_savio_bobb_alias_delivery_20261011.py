"""Close one additional alias defect; never inflate the frozen38 denominator."""
import copy
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts import season_within_club_reserve_repair_v1 as source
from scripts.build_savio_bobb_alias_reserve_20261011 import ROOT,SEASON,BASE,RELEASE


def check_bobb_visual(visual,values):
    check_visual(visual)
    if (visual.get('observed_native_name')!='Oscar Bobb' or visual.get('observed_club')!='Manchester City'
            or visual.get('observed_age')!=21 or visual.get('expected_age')!=21
            or visual.get('observed_nationality')!='NORWAY'
            or not visual.get('visible_skills_match_compiled_replacement')
            or visual.get('observed_skills')!=values):raise ValueError('actual replacement facts/10 authored skills not inspected')


def run():
    prior=ROOT.parent/'release-delivery-checklist-v38.json'
    output=ROOT.parent/'release-delivery-checklist-v39.json'
    if output.exists():raise ValueError('completed alias checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    old={row['season']:row for row in result['current_release_bindings']}
    release=registry.load_registered_release(SEASON,RELEASE)
    base=registry.load_registered_release(SEASON,BASE)
    plan=pipeline.read_json_file(ROOT/SEASON/'ownership-plan.json')
    source.verify_plan(base,plan)
    proof=pipeline.read_json_file(ROOT/'native-byte-proof.json')
    row=proof['seasons'][0]
    if (len(proof['seasons'])!=1 or proof['players']!=1 or row['season']!=SEASON
            or row['package_sha256']!=registry.sha256_file(release.package_path)
            or row['ownership_plan_sha256']!=registry.sha256_file(ROOT/SEASON/'ownership-plan.json')
            or row['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
            or not row['exact_native_reproduction_from_source_release'] or not row['idempotent']
            or row['all_unrelated_player_records']!='byte-identical'
            or row['all_unrelated_clubs_tactics_managers']!='byte-identical'
            or not row['exact_portrait_directory_reproduction']):raise ValueError('alias native proof incomplete/stale')
    for key in (k for k in proof if k.endswith('_path')):
        sha=key.removesuffix('_path')+'_sha256'
        if sha in proof and registry.sha256_file(registry.ROOT/proof[key])!=proof[sha]:raise ValueError('frozen alias checker differs')
    replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:raise ValueError('alias complete SOURCE replay differs')
    visual=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(ROOT/'startup-transport.json')
    if (visual['observed_team']!='Stoke City' or visual['observed_date']!='2024-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256):raise ValueError('final alias startup unproved')
    visual=pipeline.read_json_file(ROOT/'bobb-profile-visual-review.json')
    bobb=next(p for p in pipeline.read_json_file(release.package_path)['players'] if p['carrier_id']==9246)
    check_bobb_visual(visual,bobb['ratings']['values'])
    profile=pipeline.read_json_file(ROOT/'bobb-native-runtime-proof.json')
    kit=pipeline.read_json_file(ROOT/'bobb-kit-runtime-proof.json')
    transport=pipeline.read_json_file(ROOT/'bobb-profile-transport.json')
    if (profile['carrier_id']!=9246 or not profile['native_inputs_hash_verified']
            or profile['screenshot_sha256']!=visual['screenshot_sha256']
            or kit['screenshot_sha256']!=visual['screenshot_sha256'] or not kit['kit_pixels']['passed']
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256):raise ValueError('actual Bobb/kit inputs unproved')
    package=pipeline.read_json_file(release.package_path);before=pipeline.read_json_file(base.package_path)
    old_files={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    new_files={r['path']:r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    allowed={'DBDAT/JUG98030.FDI','DBDAT/MINIFOTO.PKF','DBDAT/MINIFOTO/J9609246.BMP'}
    if any(old_files.get(k)!=new_files.get(k) for k in set(old_files)|set(new_files) if k not in allowed):
        raise ValueError('alias delta changed an unrelated game file')
    selected=[p for p in package['players'] if p['club_id']=='english-club-313' and p['facts'].get('birth_date')=='2004-04-10']
    if len(selected)!=1 or selected[0]['carrier_id']!=9232 or selected[0]['facts']['nationality']!='BRA':raise ValueError('Savio alias copy not uniquely resolved')
    if next(p for p in package['players'] if p['carrier_id']==9232)!=next(p for p in before['players'] if p['carrier_id']==9232):raise ValueError('retained starter changed')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    if registry.load_preferred_release(SEASON).release_id not in (BASE,RELEASE):raise ValueError('alias baseline changed')
    def checked_bindings():
        current=bindings()
        for row in current:
            row['layers']=[l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
            if row['season']!=SEASON and row!=old[row['season']]:raise ValueError('unselected season changed')
        return current
    checked_bindings()
    # Reuse unchanged25 byte-bound date readbacks; independently audit only the changed game.
    readbacks=pipeline.read_json_file(ROOT.parent/'current-literal-birthdays-20261010-v13.json')['seasons']
    readbacks=[audit(SEASON,RELEASE) if r['season']==SEASON else r for r in readbacks]
    validate_frozen_birthdays(result,readbacks,[],pipeline.read_json_file(ROOT.parent/'current-literal-birthdays-20261010-v1.json'),
        expected_delivered=246,expected_remaining=1)
    publisher.register_completed_delta(SEASON,RELEASE)
    attestation=runtime.attest(season=SEASON,evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner/savio_bobb_2024_r96a_20261011')
    pipeline.write_canonical_json(ROOT/'final-attestation.json',attestation)
    finding=dict(id='savio-savinho-2024-confirmed-alias-duplicate',season=SEASON,
        state='repaired-and-runtime-verified',retained_carrier=9232,replaced_carrier=9246,replacement='Oscar Bobb',
        original38_denominator_unchanged=True,source_plan=binding(ROOT/SEASON/'ownership-plan.json'),
        correction_evidence=binding(ROOT/'bobb-profile-visual-review.json'))
    result['additional_confirmed_findings'].append(finding)
    country=ROOT.parent/'savio-original-country-v1'
    result['additional_confirmed_findings'].append(dict(id='savio-2024-nationality-eng-instead-of-bra',season=SEASON,
        state='repaired-and-runtime-verified',carrier_id=9232,corrected_observed='BRAZIL',
        source_plan=binding(country/'2024-25-plan.json'),correction_evidence=binding(country/'savio_verified-profile-visual-review.json')))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in ('native-byte-proof.json','complete-SOURCE-replay.json',
        'startup-visual-review.json','startup-transport.json','bobb-profile-visual-review.json','bobb-profile-transport.json',
        'bobb-native-runtime-proof.json','bobb-kit-runtime-proof.json','final-attestation.json'))
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=checked_bindings(),
        fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Original38 duplicate cases closed; additional Savio alias repaired. FortuneOnoh exact birthday conflict and frozen cross-club/role/manager/rating/visual queues remain open. No global historical certification.')
    pipeline.write_canonical_json(output,result)
    print(dict(checklist=binding(output),additional_alias_fault_repaired=1,original38_closed=True,
        literal_birthdays_repaired=246,literal_birthdays_remaining=1,all_required_work_complete=False),flush=True)


if __name__=='__main__':run()
