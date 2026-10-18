"""Record the two Mfuyi source decisions, explicitly not a native delivery."""
from scripts import season_cgo_redirect_country_witness_v1 as witness
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root=witness.old.CATALOG.parent
    path=root/'mfuyi-original-country-link-review.json'
    if path.exists():raise ValueError('completed original country redirect review must not repeat')
    rows=[]
    for season,carrier in [('2011-12',12506),('2012-13',8023)]:
        plan_path=root.parent/'country-policy-v2-cohort-20261017'/season/'country-plan.json'
        plan=witness.old.pipeline.read_json_file(plan_path)
        row=next(r for r in plan['updates'] if r['carrier_id']==carrier)
        proof=witness.verify(row,season)
        rows.append(dict(season=season,carrier_id=carrier,source_person=row['source_person'],
            original_annual_country='CGO',resolved_country='COD',independent_source_proof=proof,
            source_plan=dict(path=witness.old.registry.relative_workspace_path(plan_path),
                sha256=witness.old.registry.sha256_file(plan_path))))
    retained(path,dict(rows=rows,native_writes=0,preferred_writes=0,
        diagnosis='Retained biography links Congo_DR_national_football_team, an independently captured canonical COD redirect. Missing alias support, not missing historical data.',
        frozen_V3_source_policy_unchanged=True,native_and_recipe_correction_still_required=True))
    print(dict(source_country_meanings_resolved=2,actual_game_fixes_delivered=0),flush=True)


if __name__=='__main__':main()
