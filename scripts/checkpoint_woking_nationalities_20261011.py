"""Promote only actual byte-proven nationalities with inspected runner profiles."""
import copy
from datetime import UTC,datetime
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_quality_only_delta_v1 as delta,season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster,publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.capture_woking_nationalities_20261011 import ROOT,RELEASE,TAG,PROFILES
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from app.fdi_indexed import IndexedFDIFile

def run():
    prior=ROOT.parent/'release-delivery-checklist-v41.json';output=ROOT.parent/'release-delivery-checklist-v42.json'
    if output.exists():raise ValueError('completed nationality checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior));old={r['season']:r for r in result['current_release_bindings']}
    release=registry.load_registered_release('2003-04',RELEASE);plan=pipeline.read_json_file(ROOT/'quality-plan.json')
    baseline=registry.load_registered_release('2003-04',plan['release_id']);delta.verify(baseline,plan)
    if [r['carrier_id'] for r in plan['updates']]!=list(range(11141,11157)):raise ValueError('not all sixteen Woking nationalities')
    proof=pipeline.read_json_file(ROOT/'native-byte-proof.json');replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if (proof['skills_changed'] or not proof['exact_native_reproduction'] or not proof['idempotent']
            or proof['actual_manifest_sha256']!=release.manifest_sha256
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):raise ValueError('nationality actual/replay proof invalid')
    original=(baseline.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(baseline.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    actual=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if delta.apply(original,eq,plan)!=(actual,eq):raise ValueError('actual native file differs from source country plan')
    index=IndexedFDIFile.from_bytes(actual);entries={e.record_id:e for e in index.entries}
    readback=[]
    for row in plan['updates']:
        raw=entries[row['carrier_id']].decode_payload(actual);end=roster.native_player(raw,row['carrier_id'])['name_end']
        country=raw[end+8]^0x61
        if country!=row['native_country_code']:raise ValueError('actual native nationality wrong')
        readback.append(dict(carrier_id=row['carrier_id'],name=row['before']['name'],country=row['nationality'],native_code=country))
    pipeline.write_canonical_json(ROOT/'sixteen-native-nationalities.json',dict(players=readback,XXX_remaining=0))
    expected=dict(louis='DOMINICA',bayes='ENGLAND',nade='FRANCE')
    for carrier,label,token in PROFILES:
        check_visual(pipeline.read_json_file(ROOT/(label+'-profile-visual-review.json')),nationality=expected[label])
    verify_profiles(ROOT,'2003-04',RELEASE,[(carrier,label,'',token) for carrier,label,token in PROFILES])
    visual=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(ROOT/'startup-transport.json')
    if (visual['observed_team']!='Stoke City' or visual['observed_date']!='2003-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256 or transport['exit_code']!=0):raise ValueError('startup unproved')
    def checked():
        current=bindings()
        for row in current:
            row['layers']=[l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
            if row['season']!='2003-04' and row!=old[row['season']]:raise ValueError('unselected season changed')
        return current
    checked();publisher.register_completed_delta('2003-04',RELEASE)
    pipeline.write_canonical_json(ROOT/'final-attestation.json',runtime.attest(season='2003-04',
        evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/TAG))
    result['additional_confirmed_findings'].append(dict(id='Woking2003-sixteen-source-nationalities',season='2003-04',
        state='repaired-and-runtime-verified',source_plan=binding(ROOT/'quality-plan.json'),players=16,XXX_remaining=0,
        biographies_not_claims_of_2003_international_caps=True,identities_skills_and_all_other_native_bytes_unchanged=True))
    names=['quality-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','sixteen-native-nationalities.json',
        'startup-transport.json','startup-visual-review.json','final-attestation.json']
    names.extend(label+suffix for _,label,_ in PROFILES for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=checked(),
        fresh_runtime_runs_this_checklist=['2003-04'],all_required_work_complete=False,
        next_batch='Woking16 nationalities actually delivered and runtime verified; all26 rating-only calibrations underway, not globally historically approved.')
    pipeline.write_canonical_json(output,result);print(dict(checklist=binding(output),Woking_XXX_remaining=0,actual_profiles_verified=3),flush=True)

if __name__=='__main__':run()
