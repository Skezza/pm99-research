"""Archive rejected private coach trials; preserve selected safe reuse and parents."""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import archive_rejected_role_trials_20261016 as archive
from scripts import build_cached_manager_repairs_20261016 as prior
from scripts import build_year_bound_manager_repairs_20261016 as current


def targets():
    rows=[];skip=[]
    for season in registry.supported_seasons():
        if season=='2015-16':continue
        decision=pipeline.read_json_file(current.ROOT/season/'source-acceptance-decision.json')
        if decision['reuse_exact_existing_private_plan']:
            skip.append(season)
            continue
        if not decision['deferred']:raise ValueError('cannot retire a trial without an explicit rejected source/owner disposition')
        selection=current.ROOT/season/'selected-delivery.json'
        if selection.exists() and pipeline.read_json_file(selection)['release_id']==prior.RELEASE:
            raise ValueError('a selected exact private coach game cannot be retired')
        rows.append(dict(season=season,release_id=prior.BASE))
    return rows,skip


def main():
    rows,skip=targets()
    archive.ROOT=registry.ROOT/'.local/cleanup-20261016/rejected-manager-trials'
    archive.REMOTE='/srv/hdd/pm99-archive/packages/rejected-manager-trials/20261016'
    archive.RELEASES=(prior.RELEASE,prior.REPLAY)
    archive.DELTA='DBDAT/ENT98030.FDI'
    archive.REASON='Unpublished r109 coach trial rejected by exact-year and retained-owner checks. Preserve all original sources/native proofs/screens; only rejected workspace buffers and private locators retired after Pi member verification. Corrected r110 and exact safe reused r109 games remain local.'
    archive.run(baselines=rows,skip_seasons=skip)


if __name__=='__main__':main()
