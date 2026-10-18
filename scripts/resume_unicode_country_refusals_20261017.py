"""Resume only two inspected pre-plan refusals; never rerun completed games."""
from scripts import build_original_country_defaults_20261017 as build
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    inputs=pipeline.read_json_file(build.ROOT/'batch-input.json')
    for season in ('2022-23','2023-24'):
        folder=build.ROOT/season
        failure=folder/'build-failure.json'
        old=pipeline.read_json_file(failure)
        if old.get('error')!='ValueError: an intervening identity repair changes country target; do not write another person':
            raise ValueError('country recovery requires the exact inspected pre-plan refusal')
        if (folder/'country-plan.json').exists() or registry.locator_path(season,build.RELEASE).exists():
            raise ValueError('country recovery refuses existing plan/native release; inspect partial state')
        row=next(r for r in inputs['rows'] if r['season']==season)
        retained(folder/'unicode-guard-recovery-input.json',dict(
            original_failure=dict(path=registry.relative_workspace_path(failure),sha256=registry.sha256_file(failure)),
            cause='Exact game display differs from canonical source_name only in existing Polish Ł; no identity repair occurred.',
            policy='Exact unchanged display+DOB, then independently rederived original numeric source-person/DOB/country equality.',
            plan_or_native_build_existed=False,unaffected_games_regenerated=0))
        admission=folder/'source-admission.json'
        # Any retained admission is a candidate, not a trusted write approval.
        # Native publisher still independently reparses and compares the exact
        # selected plan before writing. Never repeat an existing game.
        result=build.build_one(row,prepared_admission=pipeline.read_json_file(admission) if admission.exists() else None)
        retained(folder/'unicode-guard-recovery-result.json',result)


if __name__=='__main__':main()
