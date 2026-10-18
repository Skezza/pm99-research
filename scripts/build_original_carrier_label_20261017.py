"""Restore one proved original club label, not its separate unresolved squad."""
import shutil
from scripts import season_original_carrier_label_restoration_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_registered_quality_release_v1 as reconstruction
from scripts import capture_stock_replacement_sources_20261010 as cache
from scripts.build_public_fixture_batches_20261017 import share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = source.registry.ROOT / '.local/consolidated-audit-20261009/original-carrier-label-restoration-20261017'
SEASON = '2000-01'
RELEASE = 'sourced-original-carrier-label-20261017-r134a'
REPLAY = 'replayed-original-carrier-label-20261017-r134b'


def external(key):
    path = cache.ROOT / (key + '.html'); receipt = cache.ROOT / (key + '.source.json')
    metadata = source.pipeline.read_json_file(receipt)
    return dict(path=source.registry.relative_workspace_path(path), sha256=source.registry.sha256_file(path),
        source_receipt_path=source.registry.relative_workspace_path(receipt),
        source_receipt_sha256=source.registry.sha256_file(receipt), url=metadata['url'])


def main():
    folder = ROOT / SEASON
    if (folder/'club-plan.json').exists() or source.registry.locator_path(SEASON, RELEASE).exists():
        raise ValueError('existing original-label transaction needs inspection, not regeneration')
    folder.mkdir(parents=True, exist_ok=True)
    base = source.registry.load_preferred_release(SEASON)
    inputs = dict(preallocation=source.bind(source.registry.ROOT / '.local/transfermarkt-opening-plans-current-v1/2000-01/opening-squad-preallocation.json'),
        fixed_registry=source.bind(source.registry.ROOT / 'seasons/2000-01/fixed-carrier-registry.json'),
        opening_equivalence=source.bind(ROOT.parent/'morecambe2000-source-closure-20261017/original-opening-equivalence.json'),
        coach=external('morecambe2000-jim-harvey-original-career'),
        ground=external('morecambe2000-christie-park-original-history'))
    plan = source.prepare(base, [3312], inputs)
    path = folder/'club-plan.json'; retained(path, plan)
    inert = dict(season=SEASON, release_id=base.release_id, package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'], updates=[], unresolved=[])
    retained(folder/'inert.json', inert)
    manager = dict(schema_version='pm99-historical-manager-plan-v1', season=SEASON,
        release_id=base.release_id, package_sha256=plan['package_sha256'], eq_sha256=plan['eq_sha256'],
        ent_sha256=plan['ent_sha256'], updates=[], unresolved=[])
    retained(folder/'manager-plan.json', manager)
    if shutil.disk_usage(source.registry.ROOT).free < 8.15*1024**3:
        raise ValueError('source retained before normal reserve would be threatened')
    publisher.publish(SEASON, folder/'inert.json', release_id=RELEASE, source_release_id=base.release_id,
        club_plan_path=path, manager_plan_path=folder/'manager-plan.json')
    actual = source.registry.load_registered_release(SEASON, RELEASE)
    from scripts.verify_original_carrier_label_20261017 import verify
    retained(folder/'native-byte-proof.json', verify(base, actual, plan))
    result = reconstruction._build_manager_reconstruction(actual, release_id=REPLAY)
    if result is None or not result['complete_game_inventory_identical'] or not result['complete_recipe_identical']:
        raise ValueError('whole original-label SOURCE reconstruction did not succeed')
    rebuilt = source.registry.load_registered_release(SEASON, REPLAY)
    share_verified(actual, rebuilt, folder)
    retained(folder/'complete-SOURCE-replay.json', result)
    retained(folder/'build-summary.json', dict(original_label_game_and_SOURCE_complete=True,
        club_labels_corrected=1, player_or_manager_or_ground_or_asset_changes=0,
        historical_opening_squad_approved=False, native_missing_GK_still_open=True, preferred_changed=False))
    print(dict(actual_club_label_and_SOURCE_complete=True, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
