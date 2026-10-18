"""Resume exact source plans and explicitly separate the legacy2015 layout.

The source helper is already pinned by a real candidate. Keep it immutable;
this orchestration handles the known absent legacy capture-path field only.
"""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as source
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/cached-manager-source-repairs-20261016-v1'


def main():
    summaries=[];separate=[]
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        report=pipeline.read_json_file(source.REVIEWS/season/'opening-review.json')
        if report['bindings']['opening_capture_path'] is None:
            if season!='2015-16':raise ValueError('unexpected missing historical source capture')
            separate.append(dict(season=season,release_id=release.release_id,
                reason='legacy2015 review has no generic opening-capture binding; separate saved-source replay required',
                source_unavailable_on_internet_claimed=False,manager_approval=False))
            continue
        path=ROOT/'source-plans'/season/(release.release_id+'.json')
        reused=path.exists()
        if reused:
            plan=pipeline.read_json_file(path)
            if plan['package_sha256']!=registry.sha256_file(release.package_path):
                raise ValueError('prepared source plan no longer binds actual immutable recipe')
        else:
            plan=source.prepare(release);path.parent.mkdir(parents=True,exist_ok=True);retained(path,plan)
        summaries.append(dict(season=season,**plan['summary'],
            source_plan=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))))
        print(dict(season=season,reused_completed_source_plan=reused,**plan['summary'],native_writes=0),flush=True)
    retained(ROOT/'source-preparation-summary.json',dict(seasons=summaries,separate_layout=separate,
        source_qualified_corrections=sum(r['corrections'] for r in summaries),
        native_writes=0,not_a_global_manager_quality_approval=True))


if __name__=='__main__':main()
