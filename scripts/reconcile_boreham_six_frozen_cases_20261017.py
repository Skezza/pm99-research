"""Normalise five proved candidates; keep the sixth namesake review pending.

Jimmy Dunne is deliberately excluded: unique identity is not correct ownership.
"""
from scripts.reconcile_boreham_eight_frozen_cases_20261017 import ROOT, main, binding
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def run():
    report=ROOT/'luna-closeout-20261017/single-match-seven-review.json'
    if registry.sha256_file(report)!='fe8675a2349e63e6ec1a42b7dff9ae236218767bbf2a99517926b57a8317fe30':
        raise ValueError('reviewed original report changed')
    raw=pipeline.read_json_file(report);rows=[]
    jimmy='a4003189b0b9eff91be12edd137f76d3d1e4627d56eaade807cb1d9ebb6a4ee7'
    for row in raw['cases']:
        if row['case_id']==jimmy:continue
        other=row['current_recipe_other_slot'];plan=other['source_plan'];profile=other['replacement_raw_profile']
        # Rob Atkinson1987/1998 needs positive independent namesake evidence.
        # Its failure in the first six-case native gate must not block five
        # separately proved cases, nor silently close the sixth.
        if other['carrier_id']==11058:continue
        for evidence in (plan,profile,row['original_lineup_identity']['profile']):
            if registry.sha256_file(registry.ROOT/evidence['path'])!=evidence['sha256']:
                raise ValueError('original evidence body changed')
        witness=raw['shared_original_sources'][row['original_owner_source_ref']]
        rows.append(dict(case_id=row['case_id'],current_global_exact_match=row['current_global_exact_match'],
            current_recipe_other_slot=dict(carrier_id=other['carrier_id'],club_id=other['club_id'],
                name=other['source_name'],dob=other['dob'],raw_profile=profile['path'],
                raw_profile_sha256=profile['sha256'],plan=__import__('pathlib').Path(plan['path']).name),
            retained_owner_positive_dated_source=dict(club_team_id=witness['club_team_id'],
                match_id=witness['match_id'],numeric_player_id=row['original_lineup_identity']['numeric_player_id'])))
    if len(rows)!=5 or len(raw['cases'])!=7:raise ValueError('exact five plus two pending required')
    normalised=ROOT/'luna-closeout-20261017/five-lead-normalised-input.json'
    retained(normalised,dict(original_report=binding(report),cases=rows,Jimmy_Dunne_open_confirmed_wrong_owner=True,
        Keith_Lowe_case_open_pending_Atkinson_namesake_sources=True))
    main(report_path=normalised,report_sha=registry.sha256_file(normalised),expected_count=5,
        previous_path=ROOT/'release-delivery-checklist-v110.json',output=ROOT/'release-delivery-checklist-v111.json',
        proof_path=ROOT/'luna-closeout-20261017/boreham-five-current-dispositions.json')

if __name__=='__main__':run()
