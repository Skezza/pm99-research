"""Promote only after actual six-player runner proof and unchanged-season checks."""
import copy
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_city_2024_opening_exchange_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.build_city_opening_exchange_20261011 import ROOT,SEASON,BASE,RELEASE,moved_skill_proof
from scripts.capture_city_opening_exchange_20261011 import PROFILES,TAG


def run():
    prior=ROOT.parent/'release-delivery-checklist-v39.json'
    output=ROOT.parent/'release-delivery-checklist-v40.json'
    if output.exists():raise ValueError('completed City checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior))
    old={r['season']:r for r in result['current_release_bindings']}
    release=registry.load_registered_release(SEASON,RELEASE)
    base=registry.load_registered_release(SEASON,BASE)
    plan=pipeline.read_json_file(ROOT/'opening-exchange-plan.json');source.verify(base,plan)
    moved_skill_proof()
    native=pipeline.read_json_file(ROOT/'native-byte-proof.json')
    if (native['changed_carriers']!=[16,8564,9244,9245,9250,19441]
            or native['package_sha256']!=registry.sha256_file(release.package_path)
            or native['jug_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
            or native['plan_sha256']!=registry.sha256_file(ROOT/'opening-exchange-plan.json')
            or not all(native[k] for k in ('exact_native_reproduction_from_sources','idempotent',
                'ten_visible_skills_verified','exact_portrait_directory_reproduction','preserved_first_XI_and_native_orders'))):
        raise ValueError('City native proof is stale/incomplete')
    replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('City complete source replay incomplete')
    visual=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(ROOT/'startup-transport.json')
    if (visual['observed_team']!='Stoke City' or visual['observed_date']!='2024-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256):
        raise ValueError('City actual normal startup unproved')
    package=pipeline.read_json_file(release.package_path)
    players={p['carrier_id']:p for p in package['players']};clubs={c['id']:c for c in package['clubs']}
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
                or not proof['kit_pixels']['passed']):raise ValueError('six City actual ownership profiles incomplete')
    before=pipeline.read_json_file(base.package_path)
    selected=set(native['changed_carriers'])
    if [p for p in package['players'] if p['carrier_id'] not in selected]!=[p for p in before['players'] if p['carrier_id'] not in selected]:
        raise ValueError('unrelated recipe people changed')
    for row in plan['exchanges']:
        if players[row['destination_carrier']]['ratings']['values']!=row['moved_before']['ratings']['values']:
            raise ValueError('moved person abilities changed')
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    if registry.load_preferred_release(SEASON).release_id not in (BASE,RELEASE):raise ValueError('City preferred baseline changed')
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
    attestation=runtime.attest(season=SEASON,evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/TAG)
    pipeline.write_canonical_json(ROOT/'final-attestation.json',attestation)
    for row in plan['exchanges']:
        result['additional_confirmed_findings'].append(dict(id='City2024-late-entry-'+str(row['city_carrier']),season=SEASON,
            state='repaired-and-runtime-verified',moved_person=row['moved_before']['source_name'],
            opening_owner=clubs[players[row['destination_carrier']]['club_id']]['name'],
            city_replacement=players[row['city_carrier']]['source_name'],
            original38_denominator_unchanged=True,source_plan=binding(ROOT/'opening-exchange-plan.json')))
    names=['opening-exchange-plan.json','native-byte-proof.json','moved-people-native-skill-preservation.json','complete-SOURCE-replay.json',
        'startup-visual-review.json','startup-transport.json','final-attestation.json']
    names.extend(label+suffix for _,label,_,_ in PROFILES for suffix in
        ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=checked_bindings(),
        fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='City2024 three confirmed late entries and their opening club ownership delivered. Woking paired ownership/source fit and broader cross-club/role/manager/rating/visual queues remain open. Original38 denominator and 2015 fun backup preserved.')
    pipeline.write_canonical_json(output,result)
    print(dict(checklist=binding(output),city_late_entries_repaired=3,actual_profiles_verified=6,
        remaining25_preferred_unchanged=True,all_required_work_complete=False),flush=True)


if __name__=='__main__':run()
