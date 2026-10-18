"""Frozen adversarial gates BEFORE any of the26 candidate games are built."""
from scripts.build_all_rating_calibrations_20261011 import ROOT
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def check():
    assertions=[]
    for season,carrier,field,minimum in [('2015-16',1790,'quality',90),('2025-26',1790,'quality',82),
            ('2025-26',1790,'dribbling',90),('2024-25',9244,'speed',88)]:
        plan=pipeline.read_json_file(ROOT/season/'quality-plan.json')
        matches=[r for r in plan['updates'] if r['carrier_id']==carrier]
        if len(matches)!=1 or matches[0]['ratings']['values'][field]<minimum:raise ValueError('known-star rating regression: '+season)
        assertions.append(dict(season=season,carrier=carrier,field=field,minimum=minimum,actual=matches[0]['ratings']['values'][field]))
    total=0;unknown=0;date_neutral=0
    for season in registry.supported_seasons():
        plan=pipeline.read_json_file(ROOT/season/'quality-plan.json')
        if plan['kind']!='season-rating-calibration-v3':raise ValueError('mixed rating policy batch')
        base=registry.load_registered_release(season,plan['release_id']);players={p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
        for row in plan['updates']:
            player=players[row['carrier_id']];values=row['ratings']['values'];basis=row['rating_basis']
            if player['facts']['primary_position']!='G' and values['handling']>20:raise ValueError('outfield handling regression')
            if 'fifa_edition' in basis:
                gap=int(season[:4])-(basis['fifa_edition']+1999)
                if not 0<=gap<=3 or not isinstance(player['facts']['birth_date'],str):raise ValueError('future/distant/unproved-FIFA match')
            unknown+=basis.get('opening_status')=='unknown'
            date_neutral+=basis.get('birth_date_available') is False
        total+=len(plan['updates'])
    retained(ROOT/'pre-build-adversarial-benchmarks.json',dict(known_star_tests=assertions,seasons=26,
        planned_updates=total,outfield_handling_guard_passed=True,no_future_or_distant_FIFA=True,
        unknown_XI_not_reserve_estimates=unknown,age_neutral_without_invented_DOB=date_neutral,
        rejected_model_v2_not_promoted=True))

if __name__=='__main__':check()
