"""Deliver admitted exact period-country defaults to affected private games.

Two bounded script workers. Existing ownership/position corrections are explicit
parents, never overwritten. Source refusals remain separate; no country default
is guessed and unsupported countries are left as declared gaps.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import shutil

from scripts import discover_original_country_defaults_20261017 as discovery
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_original_secondary_fact_delta_v1 import verify
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = discovery.ROOT.parent/'original-country-default-delivery-20261017-v1'
RELEASE = 'sourced-original-period-country-defaults-20261017-r127a'
REPLAY = 'replayed-original-period-country-defaults-20261017-r127b'
OVERRIDES = {'2021-22':'sourced-shinnie-exact-midfield-20261017-r126a',
    '2024-25':'sourced-public-original-fixture-reserves-20261017-r124a',
    '2025-26':'sourced-frozen-original-fixture-reserves-20261017-r123a'}


def guard_candidate(actor,candidate):
    original_name=source.original.names.undecorated(actor.get('source_name') or actor['name'])
    candidate_name=source.original.names.undecorated(candidate['name'])
    # Discovery stores the exact game display, while source_name can contain
    # a non-decomposing letter such as Ł. Do not transliterate/fuzzy-match it.
    # Exact unchanged display+DOB is allowed ONLY with the subsequent original
    # source-person ID check after the typed raw-source adapter admits it.
    if ((source.original.audit.normalise(original_name)!=source.original.audit.normalise(candidate_name)
            and actor['name']!=candidate['name'])
            or actor['facts']['birth_date']!=candidate['birth_date']):
        raise ValueError('an intervening identity repair changes country target; do not write another person')


def guard_source_person(row,candidate):
    if (row['source_person']['source_player_id']!=candidate['source_person_id']
            or row['source_person']['birth_date']!=candidate['birth_date']
            or row['nationality']!=candidate['source_country']):
        raise ValueError('country discovery and original admitted numeric person/DOB/country disagree')


def build_one(row,*,prepared_admission=None):
    season=row['season'];folder=ROOT/season;folder.mkdir(parents=True,exist_ok=True)
    if registry.locator_path(season,RELEASE).exists() or (folder/'country-plan.json').exists():
        raise ValueError('existing country plan/game needs inspection, not regeneration')
    base=registry.load_registered_release(season,OVERRIDES.get(season,row['release_id']))
    actors={p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
    targets={};already=[]
    for candidate in row['candidates']:
        actor=actors[candidate['carrier_id']]
        guard_candidate(actor,candidate)
        if actor['facts']['nationality']==candidate['source_country']:
            already.append(candidate['carrier_id']);continue
        if actor['facts']['nationality']!=candidate['before_country']:
            raise ValueError('country preimage advanced; do not discard another correction')
        targets[str(candidate['carrier_id'])]=['nationality']
    if not targets:
        return dict(season=season,status='all-source-candidates-already-corrected',already=already)
    if prepared_admission is None:
        admission=source.prepare(base,discovery.PEOPLE,targets)
    else:
        admission=prepared_admission
        if ((admission['season'],admission['release_id'],admission['targets'])!=(season,base.release_id,targets)
                or admission['package_sha256']!=registry.sha256_file(base.package_path)
                or admission['jug_sha256']!=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI')
                or admission['eq_sha256']!=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI')
                or admission['exe_sha256']!=registry.sha256_file(base.game_path/'MANAGPRE.EXE')
                or admission['original_person_document']['sha256']!=registry.sha256_file(discovery.PEOPLE)):
            raise ValueError('retained country admission binds changed targets or source/native preimages')
    retained(folder/'source-admission.json',admission)
    refused={str(r['carrier_id']) for r in admission['unresolved']}
    accepted={k:v for k,v in targets.items() if k not in refused}
    if not accepted:
        result=dict(season=season,status='no-exact-supported-country-admitted',refused=admission['unresolved'],native_writes=0)
        retained(folder/'source-gap.json',result);return result
    if prepared_admission is not None:
        from scripts.project_admitted_country_plan_v1 import project
        plan=project(admission,accepted)
    else:
        plan=source.prepare(base,discovery.PEOPLE,accepted) if refused else admission
    if plan['unresolved'] or len(plan['updates'])!=len(accepted):
        raise ValueError('accepted exact country batch did not reproduce')
    candidates={r['carrier_id']:r for r in row['candidates']}
    for admitted in plan['updates']:
        guard_source_person(admitted,candidates[admitted['carrier_id']])
    path=folder/'country-plan.json';retained(path,plan)
    descriptor=folder/'inert.json'
    retained(descriptor,dict(season=season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free<8.15*1024**3:
        raise ValueError('retained country source plan paused before unchanged8GiB reserve')
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    verify(season,RELEASE,path,folder/'native-byte-proof.json')
    actual=registry.load_registered_release(season,RELEASE)
    replay=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(season,REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(actual.inventory_path))
    if rebuilt.package_path.read_bytes()!=actual.package_path.read_bytes():
        raise ValueError('exact country full SOURCE recipe differs')
    share_verified(actual,rebuilt,folder)
    retained(folder/'complete-SOURCE-replay.json',replay)
    result=dict(season=season,status='actual-native-and-whole-SOURCE-complete',
        corrected_countries=len(plan['updates']),source_parent=base.release_id,
        already_corrected=already,refused=admission['unresolved'],preferred_changed=False,
        ownership_role_skill_tactics_manager_and_assets_preserved=True,runtime_pending=True,cross_club_cases_closed=0)
    retained(folder/'build-summary.json',result);print(result,flush=True);return result


def main():
    if ROOT.exists():
        raise ValueError('existing country batch needs per-season inspection, never blind rerun')
    cleanup=registry.ROOT/'.local/cleanup-20261017/shared-completed-role-SOURCE-copies/completed.json'
    if not cleanup.exists():
        raise ValueError('verified disk sharing must finish before country batch allocation')
    ROOT.mkdir()
    document=pipeline.read_json_file(discovery.ROOT/'discovery.json')
    rows=[r for r in document['seasons'] if r['candidates']]
    retained(ROOT/'batch-input.json',dict(discovery_path=registry.relative_workspace_path(discovery.ROOT/'discovery.json'),
        discovery_sha256=registry.sha256_file(discovery.ROOT/'discovery.json'),rows=rows,parent_overrides=OVERRIDES,
        cleanup_ledger_sha256=registry.sha256_file(cleanup),preferred_writes=0))
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(build_one,row):row['season'] for row in rows}
        for future in as_completed(jobs):
            season=jobs[future]
            try:
                result=future.result()
            except Exception as exc:
                result=dict(season=season,status='stopped-inspect-partial-state',
                    error=type(exc).__name__+': '+str(exc),automatic_rerun=False)
                retained(ROOT/season/'build-failure.json',result);print(result,flush=True)
            results.append(result)
    retained(ROOT/'batch-summary.json',dict(utc=datetime.now(UTC).isoformat(),rows=results,
        preferred_changed=False,unaffected_seasons_regenerated=0,cross_club_cases_closed=0,
        original2015_untouched=True,global_historical_RC=False))


if __name__=='__main__':
    main()
