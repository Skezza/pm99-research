"""Original Accrington owner + Blackpool opening bench, no new scraping."""
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v1 as source
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Aldred2014-original-fixtures-v1'
BASE='sourced-eastleigh-original-opening-20261017-r121a'


def main():
    path=ROOT/'opening-fixture-input-v2.json';plan_path=ROOT/'ownership-plan.json'
    if plan_path.exists():raise ValueError('completed original pair plan must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    retained(path,dict(schema=source.INPUT_SCHEMA,season='2014-15',cases=[
        dict(source_person_id=95076,displaced_carrier=9520,retained_carrier=9580,
            replacement_name='Mark Waddington',replacement_source_person_id=307277,
            previously_retired_frozen_members=[dict(carrier_id=11160,release_id=BASE)])]))
    base=registry.load_registered_release('2014-15',BASE)
    plan=source.prepare(base,path);retained(plan_path,plan)
    row=plan['updates'][0]
    print(dict(source_pair_proved=True,displaced=row['before']['source_name'],retained_carrier=row['retained_carrier_id'],
        replacement=row['replacement']['source_player'],native_writes=0,source_fixture=plan['bindings']['positive_pairs'][0]['original_openings'][0]['date']),flush=True)


if __name__=='__main__':main()
