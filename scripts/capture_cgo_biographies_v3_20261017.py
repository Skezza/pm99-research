"""Acquire one original biography per Congo identity, not per season.

Name and DOB validation happens in the resolver before use. A downloaded page
is not approval of a historical country; no game or preferred release changes.
"""
from urllib.parse import quote
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_stock_replacement_sources_20261010 as acquire
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/cgo-biographies-v3-20261017'


def main():
    if (ROOT/'catalog.json').exists():raise ValueError('completed Congo biography collection must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    people={}
    for path in sorted((ROOT.parent/'country-policy-v2-cohort-20261017').glob('*/country-plan.json')):
        for row in pipeline.read_json_file(path)['updates']:
            if row['nationality']!='CGO':continue
            person=row['source_person'];id=person['source_player_id']
            if id in people and people[id]!=person:raise ValueError('same original person ID has contradictory biography')
            people[id]=person
    requests=[];records=[]
    for id,person in sorted(people.items()):
        key={29016:'cgo-samba-original-country-witness',130756:'cgo-imbula-original-country-witness'}.get(id,'cgo-person-'+str(id)+'-original-wikipedia')
        url='https://en.wikipedia.org/wiki/'+quote(person['name'].replace(' ','_'))
        requests.append((key,url));records.append(dict(source_player_id=id,source_person=person,key=key,url=url))
    retained(ROOT/'input.json',dict(rows=records,one_request_per_person=True,native_writes=0))
    acquire.main(extra_sources=requests,only_extra=True,transport='curl')
    for row in records:
        path=acquire.ROOT/(row['key']+'.html');receipt=acquire.ROOT/(row['key']+'.source.json')
        metadata=pipeline.read_json_file(receipt);row['status']=metadata['status']
        row['source']=dict(path=registry.relative_workspace_path(path),sha256=metadata.get('sha256'),
            receipt_path=registry.relative_workspace_path(receipt),receipt_sha256=registry.sha256_file(receipt),url=row['url'])
    retained(ROOT/'catalog.json',dict(rows=records,native_writes=0,download_does_not_approve_historical_country=True))
    print(dict(original_people=len(records),captured=sum(r['status']=='original-captured' for r in records)),flush=True)


if __name__=='__main__':main()
