"""Four exact period-person year repairs; do not choose namesake birthdays.

Only year bytes change. Bloxham's competing Nov1/Nov2 publications are logged,
not resolved by rewriting the supplied target-period recipe day/month.
"""
from scripts import original_namesake_birthday_witness_v1 as witness
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.build_compact_original_person_years_20261010 import main as build

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/remaining-four-native-years-v1'
SOURCE=ROOT.parent/'stock-club-history-v1/remaining-birthday-original-additional-people-v1.json'
BASES={'2023-24':'sourced-original-person-birth-years-20261010-r78a',
       '2024-25':'sourced-original-secondary-facts-20261010-r81a'}
KEYS={
    '2023-24':[(27847,'six-dates-original-morecambe-3697-2023-squad')],
    '2024-25':[(16968,'six-dates-original-crawley-2024-squad'),
               (27009,'six-dates-original-shrewsbury-2024-squad'),
               (9232,'six-dates-original-man-city-2024-squad')],
}


def main():
    ROOT.mkdir(exist_ok=True)
    for season,rows in KEYS.items():
        witnesses=[]
        for carrier,key in rows:
            _,raw,binding=source_rows(key);observed=witness.parse(key,raw)
            witnesses.append(dict(carrier_id=carrier,source_key=key,source_binding=binding,
                name=observed['name'],birth_date=observed['birth_date']))
        document=dict(schema=witness.SCHEMA,witnesses=witnesses)
        path=ROOT/(season+'-independent-period-witnesses.json')
        if path.exists():
            if pipeline.read_json_file(path)!=document:raise ValueError('retained period witnesses differ')
        else:pipeline.write_canonical_json(path,document)
        # Freeze the actual before version. A subsequent preferred promotion
        # must not silently change this completed transaction's source input.
        current=registry.load_registered_release(season,BASES[season])
        case=dict(base=current.release_id,release='sourced-original-secondary-facts-20261011-r93a',
            replay='replayed-original-secondary-facts-20261011-r93b',
            targets={str(carrier):['native_birth_year'] for carrier,_ in rows},count=len(rows))
        build(root=ROOT,cases={season:case},source=SOURCE,identity_document_path=path)


if __name__=='__main__':main()
