"""Bind acquired independent country witnesses and inventory held CGO proposals."""
from scripts import season_cgo_disambiguation_v1 as country
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_stock_replacement_sources_20261010 import ROOT as CACHE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=country.CATALOG.parent


def main():
    if country.CATALOG.exists():raise ValueError('existing independent Congo catalogue must not be overwritten')
    ROOT.mkdir(parents=True,exist_ok=True)
    people=[]
    for id,name,born,slug,key in (
        (29016,'Christopher Samba','1984-03-28','Christopher_Samba','cgo-samba-original-country-witness'),
        (130756,'Giannelli Imbula','1992-09-12','Giannelli_Imbula','cgo-imbula-original-country-witness')):
        path=CACHE/(key+'.html');receipt=CACHE/(key+'.source.json')
        metadata=pipeline.read_json_file(receipt)
        if metadata.get('status')!='original-captured' or metadata['sha256']!=registry.sha256_file(path):
            raise ValueError('independent Congo witness not actually captured')
        people.append(dict(source_player_id=id,name=name,birth_date=born,wikipedia_slug=slug,
            source=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path),
                receipt_path=registry.relative_workspace_path(receipt),receipt_sha256=registry.sha256_file(receipt))))
    retained(country.CATALOG,dict(schema=country.SCHEMA,people=people,
        provider_CGO_requires_independent_interpretation=True,native_writes=0))
    rows=[]
    for folder in sorted((ROOT.parent/'country-policy-v2-cohort-20261017').iterdir()):
        plan_path=folder/'country-plan.json'
        if not plan_path.is_file():continue
        plan=pipeline.read_json_file(plan_path)
        for actor in plan['updates']:
            if actor['nationality']!='CGO':continue
            try:
                proof=country.verify(actor,plan['season'])
                result=dict(status='independently-disambiguated-for-target-year',proof=proof)
            except ValueError as exc:
                result=dict(status='held-no-country-publication-approved',reason=str(exc))
            rows.append(dict(season=plan['season'],carrier_id=actor['carrier_id'],name=actor['before_player']['name'],
                country_plan=dict(path=registry.relative_workspace_path(plan_path),sha256=registry.sha256_file(plan_path)),**result))
    # The SAME vendor token has a dated Republic-of-Congo witness for Samba,
    # but a dated DR-Congo witness for Imbula in2019. It is not an ISO guarantee.
    imbula=next(p for p in people if p['source_player_id']==130756)
    independent=country.parse((registry.ROOT/imbula['source']['path']).read_bytes(),imbula['name'],imbula['birth_date'],'2019-20')
    if independent['country']!='COD':raise ValueError('independent vendor ambiguity counterexample changed')
    retained(ROOT/'pending-country-admission.json',dict(rows=rows,native_writes=0,preferred_writes=0,
        CGO_not_a_provider_safe_ISO_token=True,Imbula2019_independent_country=independent,
        Imbula2016_country_not_established_by_future_caps=True,
        next='Use exact-year independent source country evidence in a new immutable policy. Do not publish held V2 CGO games. Non-CGO corrections remain separately deliverable.'))
    print(dict(CGO_rows=len(rows),held=sum(r['status'].startswith('held') for r in rows),
        independent_target_year_admitted=sum(r['status'].startswith('independently') for r in rows),native_writes=0),flush=True)


if __name__=='__main__':main()
