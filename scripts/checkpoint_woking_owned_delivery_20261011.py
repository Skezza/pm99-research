"""Promote the paired ownership fix only after actual runner verification."""
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
from scripts.build_woking_owned_opening_20261011 import ROOT,SEASON,BASE,RELEASE
from scripts.capture_woking_owned_opening_20261011 import PROFILES,TAG


def run():
    prior=ROOT.parent/'release-delivery-checklist-v40.json'
    output=ROOT.parent/'release-delivery-checklist-v41.json'
    if output.exists():raise ValueError('completed Woking checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior));old={r['season']:r for r in result['current_release_bindings']}
    release=registry.load_registered_release(SEASON,RELEASE)
    native=pipeline.read_json_file(ROOT/'native-byte-proof.json')
    if (native['changed_carriers']!=list(range(11141,11157))+[33060]
            or native['package_sha256']!=registry.sha256_file(release.package_path)
            or native['plan_sha256']!=registry.sha256_file(ROOT/'opening-ownership-plan.json')
            or len(native['all_ten_native_skills_preserved_for'])!=10
            or not all(native[k] for k in ('exact_native_reproduction_from_sources','idempotent',
                'Oxford_roster_count_and_XI_preserved','original_first_XI_retained','exact_portrait_clear'))):
        raise ValueError('Woking actual native proof incomplete/stale')
    replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('Woking complete source replay incomplete')
    coach=pipeline.read_json_file(ROOT/'manager-native-ownership-proof.json')
    if (coach['native_owner']!=[dict(carrier_id=3321,club_name='Woking')]
            or coach['display_name']!='Cockerill' or coach['canonical_name']!='Glenn Cockerill'
            or coach['actual_EQ_sha256']!=registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI')
            or coach['actual_ENT_sha256']!=registry.sha256_file(release.game_path/'DBDAT/ENT98030.FDI')):
        raise ValueError('actual sourced manager name/ownership unproved')
    visual=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(ROOT/'startup-transport.json')
    if (visual['observed_team']!='Stoke City' or visual['observed_date']!='2003-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256):
        raise ValueError('actual normal season startup unproved')
    package=pipeline.read_json_file(release.package_path);players={p['carrier_id']:p for p in package['players']}
    clubs={c['id']:c for c in package['clubs']}
    for carrier,label,_,_ in PROFILES:
        visual=pipeline.read_json_file(ROOT/(label+'-profile-visual-review.json'));check_visual(visual)
        proof=pipeline.read_json_file(ROOT/(label+'-native-runtime-proof.json'))
        if (visual['observed_native_name']!=players[carrier]['name']
                or visual['observed_club']!=clubs[players[carrier]['club_id']]['name']
                or visual['observed_skills']!=players[carrier]['ratings']['values']
                or proof['screenshot_sha256']!=visual['screenshot_sha256']
                or proof['visual_review_sha256']!=registry.sha256_file(ROOT/(label+'-profile-visual-review.json'))
                or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
                or not proof['native_inputs_hash_verified'] or not proof['ten_visible_skills_verified']
                or not proof['kit_pixels']['passed']):raise ValueError('paired actual ownership profiles incomplete')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    if registry.load_preferred_release(SEASON).release_id not in (BASE,RELEASE):raise ValueError('preferred baseline changed')
    def checked_bindings():
        current=bindings()
        for row in current:
            row['layers']=[l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
            if row['season']!=SEASON and row!=old[row['season']]:raise ValueError('an unselected season changed')
        return current
    checked_bindings()
    readbacks=pipeline.read_json_file(ROOT.parent/'current-literal-birthdays-20261010-v13.json')['seasons']
    readbacks=[audit(SEASON,RELEASE) if row['season']==SEASON else row for row in readbacks]
    validate_frozen_birthdays(result,readbacks,[],pipeline.read_json_file(ROOT.parent/'current-literal-birthdays-20261010-v1.json'),
        expected_delivered=246,expected_remaining=1)
    publisher.register_completed_delta(SEASON,RELEASE)
    pipeline.write_canonical_json(ROOT/'final-attestation.json',runtime.attest(season=SEASON,
        evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/TAG))
    result['additional_confirmed_findings'].append(dict(id='Woking2003-owned-opening-paired-Oxford',season=SEASON,
        state='repaired-and-runtime-verified',source_plan=binding(ROOT/'opening-ownership-plan.json'),
        Woking_label_manager_full_XI_and_capacity_squad_corrected=True,Oxford_Louis_replaced_with_positive_Winters=True,
        original38_denominator_unchanged=True))
    names=['opening-ownership-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'opening-squad-native-readback.json','current-literal-birthdays-readback.json',
        'louis-first-row-capture-REJECTED.json','manager-native-ownership-proof.json','implementation-receipt-v2.json',
        'startup-visual-review.json','startup-transport.json','final-attestation.json']
    names.extend(label+suffix for _,label,_,_ in PROFILES for suffix in
        ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=checked_bindings(),fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Bounded City2024 late-entry/ownership and Woking2003 paired ownership milestone delivered in actual games and runner verified. Broader source/role/rating/manager/visual queues remain separate; not global historical approval. Original38 and 2015 fun backup preserved.')
    pipeline.write_canonical_json(output,result)
    print(dict(checklist=binding(output),paired_ownership_delivered=True,actual_profiles_verified=3,
        other25_preferred_unchanged=True,all_required_work_complete=False),flush=True)


if __name__=='__main__':run()
