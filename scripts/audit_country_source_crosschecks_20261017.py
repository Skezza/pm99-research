"""Audit all prepared country corrections against exact historical FIFA data."""
from scripts import season_country_fifa_crosscheck_v1 as cross
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/country-source-crosschecks-20261017'


def main():
    output=ROOT/'audit.json'
    if output.exists():raise ValueError('completed country crosscheck must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    sha=registry.sha256_file(cross.fifa.identity.old.FIFA);index=cross.load(sha)
    rows=[]
    for namespace in ('original-country-default-delivery-20261017-v1','country-policy-v2-cohort-20261017'):
        for folder in sorted((ROOT.parent/namespace).iterdir()):
            path=folder/'country-plan.json'
            if not path.is_file():continue
            plan=pipeline.read_json_file(path)
            for actor in plan['updates']:
                result=cross.check(actor,plan['season'],index=index,file_sha=sha)
                rows.append(dict(namespace=namespace,season=plan['season'],carrier_id=actor['carrier_id'],
                    name=actor['before_player']['name'],plan=dict(path=registry.relative_workspace_path(path),
                    sha256=registry.sha256_file(path)),**result))
    report=dict(rows=rows,contradictions=[r for r in rows if r['status']=='contradiction-requires-resolution'],
        native_writes=0,recipe_writes=0,preferred_writes=0,source_country_not_blindly_approved=True)
    retained(output,report)
    print(dict(country_proposals_checked=len(rows),exact_FIFA_contradictions=len(report['contradictions']),native_writes=0),flush=True)


if __name__=='__main__':main()
