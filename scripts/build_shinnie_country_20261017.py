"""Repair the newly observed Shinnie country using the existing typed layer.

Reuses original cached people and exact-DOB target-season annuals. The separate
broad-position conflict remains explicit; nationality evidence is not a role
or opening-squad approval. No new source scraping or unaffected-season rebuild.
"""
import shutil

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_original_secondary_fact_delta_v1 import verify
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/shinnie-native-facts-20261017-v1'
SEASON = '2021-22'
BASE = 'sourced-frozen-original-fixture-reserves-20261017-r123a'
RELEASE = 'sourced-shinnie-original-country-20261017-r125a'
REPLAY = 'replayed-shinnie-original-country-20261017-r125b'


def main():
    folder = ROOT / 'country-delivery'
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'complete-SOURCE-replay.json').exists():
        raise ValueError('completed country game exists; inspect rather than regenerate')
    if registry.locator_path(SEASON, RELEASE).exists():
        raise ValueError('partial existing country game requires inspection')
    base = registry.load_registered_release(SEASON, BASE)
    if registry.load_preferred_release(SEASON).manifest_sha256 != base.manifest_sha256:
        raise ValueError('current default advanced; do not discard intervening changes')
    plan = source.prepare(base, registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json',
                          {'9718': ['nationality']})
    if plan['unresolved'] or len(plan['updates']) != 1 or plan['updates'][0]['nationality'] != 'SCO':
        raise ValueError('one original-source Scottish country correction required')
    plan_path = folder / 'country-plan.json'
    retained(plan_path, plan)
    inert = folder / 'inert.json'
    retained(inert, dict(season=SEASON, release_id=BASE, package_sha256=plan['package_sha256'],
                         jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    if shutil.disk_usage(registry.ROOT).free < 8.15 * 1024**3:
        raise ValueError('stop before unchanged8GiB reserve; retained source plan needs no rerun')
    publisher.publish(SEASON, inert, release_id=RELEASE, source_release_id=BASE,
                      profile_assignment_plan_path=plan_path)
    verify(SEASON, RELEASE, plan_path, folder / 'native-byte-proof.json')
    actual = registry.load_registered_release(SEASON, RELEASE)
    replay = source.reconstruction(actual, REPLAY)
    rebuilt = registry.load_registered_release(SEASON, REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes() != rebuilt.package_path.read_bytes():
        raise ValueError('complete country SOURCE recipe differs')
    share_verified(actual, rebuilt, folder)
    retained(folder / 'complete-SOURCE-replay.json', replay)
    retained(folder / 'build-summary.json', dict(season=SEASON, release_id=RELEASE, native_country='SCO',
        actual_game_and_whole_SOURCE_verified=True, preferred_changed=False, runtime_pending=True,
        known_broad_position_conflict_remains=True, cross_club_cases_closed=0))
    print(dict(actual_country_game_built=True, complete_SOURCE=True, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
