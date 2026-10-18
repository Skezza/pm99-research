"""Close one previously delivered repair without conflating two Rob Atkinsons."""
from pathlib import Path
from scripts.reconcile_boreham_eight_frozen_cases_20261017 import ROOT, main, binding
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

WITNESS=ROOT/'luna-closeout-20261017/rob-atkinson-namesake-proof.json'
WITNESS_SHA='a38c7354f1ccd4c99555873031734272b3f96c3005c717257d04e9c94e460d2a'

def validate_namesakes(matches,expected,jug):
    if registry.sha256_file(WITNESS)!=WITNESS_SHA:raise ValueError('reviewed namesake sources changed')
    if {p['carrier_id'] for p in matches}!={9816,11058} or expected['carrier_id']!=11058:
        raise ValueError('namesake evidence cannot waive any other identity collision')
    witness=pipeline.read_json_file(WITNESS);rows=[]
    for key,carrier,person,birthday in (('english_namesake',9816,108814,'1998-07-13'),
            ('guiseley_namesake',11058,38010,'1987-04-29')):
        source=witness[key];path=registry.ROOT/source['source_path']
        if registry.sha256_file(path)!=source['source_sha256'] or source['soccerbase_player_id']!=person:
            raise ValueError('original numeric namesake biography changed')
        biography=original.profile(path.read_bytes(),dict(provider_player_id=person,
            source_player_id='soccerbase:'+str(person)),source['source_url'])
        # The older biography publishes Robert; its already delivered source
        # allocation publishes Rob. This exact pair is not a general alias rule.
        names={9816:{'Rob Atkinson'},11058:{'Rob Atkinson','Robert Atkinson'}}
        actor=next(p for p in matches if p['carrier_id']==carrier)
        native=facts.native_facts(jug,carrier)
        if (biography['name'] not in names[carrier] or biography['birth_date']!=birthday
                or actor['facts']['birth_date']!=birthday or native['birth_date']!=birthday):
            raise ValueError('independent numeric biography/native DOB does not prove different people')
        rows.append(dict(carrier_id=carrier,original_biography=biography,source=binding(path),native=native))
    return dict(witness=binding(WITNESS),people=rows,distinct_numeric_people_and_DOB=True,
        English1998_opening_ownership_not_verified_by_this_identity_proof=True)

def run():
    report=ROOT/'luna-closeout-20261017/single-match-seven-review.json'
    if registry.sha256_file(report)!='fe8675a2349e63e6ec1a42b7dff9ae236218767bbf2a99517926b57a8317fe30':
        raise ValueError('original research changed')
    raw=pipeline.read_json_file(report)
    selected=[r for r in raw['cases'] if r['current_recipe_other_slot']['carrier_id']==11058]
    if len(selected)!=1:raise ValueError('exact Keith Lowe case required')
    row=selected[0];other=row['current_recipe_other_slot'];w=raw['shared_original_sources'][row['original_owner_source_ref']]
    for evidence in (other['source_plan'],other['replacement_raw_profile'],row['original_lineup_identity']['profile']):
        if registry.sha256_file(registry.ROOT/evidence['path'])!=evidence['sha256']:raise ValueError('source changed')
    normalised=ROOT/'luna-closeout-20261017/keith-lowe-lead-normalised-input.json'
    retained(normalised,dict(original_report=binding(report),namesake_report=binding(WITNESS),cases=[dict(
        case_id=row['case_id'],current_global_exact_match=row['current_global_exact_match'],
        current_recipe_other_slot=dict(carrier_id=11058,club_id=other['club_id'],name=other['source_name'],dob=other['dob'],
            raw_profile=other['replacement_raw_profile']['path'],raw_profile_sha256=other['replacement_raw_profile']['sha256'],
            plan=Path(other['source_plan']['path']).name),
        retained_owner_positive_dated_source=dict(club_team_id=w['club_team_id'],match_id=w['match_id'],
            numeric_player_id=row['original_lineup_identity']['numeric_player_id']))]))
    main(report_path=normalised,report_sha=registry.sha256_file(normalised),expected_count=1,
        previous_path=ROOT/'release-delivery-checklist-v111.json',output=ROOT/'release-delivery-checklist-v112.json',
        proof_path=ROOT/'luna-closeout-20261017/keith-lowe-current-disposition.json',namesake_validator=validate_namesakes)

if __name__=='__main__':run()
