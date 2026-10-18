"""Apply one reviewed three-icon patch and replay exact SOURCE, not databases."""
import shutil

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts import season_visual_patch_reconstruction_v1 as replay
from scripts import season_kit_render_bindings_v1 as render
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.capture_genoa_2021_kit_20261016 import ROOT

SEASON = '2021-22'
BASE = 'sourced-arsenal-shirt-numbers-20261016-r112a'
RELEASE = 'sourced-genoa-period-kit-20261016-r113a'
REPLAY = 'replayed-genoa-period-kit-20261016-r113b'


def main():
    base = registry.load_registered_release(SEASON, BASE)
    if registry.load_preferred_release(SEASON).release_id != BASE:
        raise ValueError('preferred baseline changed; inspect before applying')
    measured = pipeline.read_json_file(base.inventory_path)['total_bytes']
    if shutil.disk_usage(ROOT).free < 8 * 1024**3 + 2 * measured + 20 * 1024**2:
        raise ValueError('two bounded games would breach the 8GiB reserve')
    prepared = ROOT / 'prepared-v1'
    if not (ROOT / 'candidate-visual-review.json').exists():
        raise ValueError('review the original source and all rendered icons before build')
    plan = prepared / 'delta/plan.json'
    patch = prepared / 'delta/complete-patch'
    destination = ROOT / 'candidate/game'
    if not registry.locator_path(SEASON, RELEASE).exists():
        if destination.exists():
            raise ValueError('unreceipted candidate exists; inspect rather than recopy')
        art.apply(plan, patch, destination, source_release=base)
        art.publish(SEASON, destination, RELEASE, source_release=base)
    release = registry.load_registered_release(SEASON, RELEASE)
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(release.inventory_path)['files']}
    changed = {k for k in set(left) | set(right) if left.get(k) != right.get(k)}
    if changed != {'DBDAT/' + a for a in render.ARCHIVES}:
        raise ValueError('kit patch changed another game file')
    counts = {}
    for archive in render.ARCHIVES:
        before = render._record_index(base.game_path / 'DBDAT' / archive)
        after = render._record_index(release.game_path / 'DBDAT' / archive)
        if set(before) != set(after):
            raise ValueError('kit patch changed a carrier set')
        carriers = {c for c in before if before[c].raw_bitmap != after[c].raw_bitmap}
        if carriers != {207}:
            raise ValueError('kit patch changed another club icon')
        counts[archive] = len(before) - 1
    if release.package_path.read_bytes() != base.package_path.read_bytes():
        raise ValueError('kit patch changed the source recipe')
    retained(ROOT / 'native-byte-proof.json', dict(season=SEASON, release_id=RELEASE,
        manifest_sha256=release.manifest_sha256, only_changed_files=sorted(changed),
        only_changed_kit_carrier=207, unchanged_records_by_archive=counts,
        every_database_EXE_portrait_and_unselected_game_file_identical=True,
        complete_recipe_identical=True, plan_sha256=registry.sha256_file(plan)))
    if not (ROOT / 'complete-SOURCE-replay.json').exists():
        if registry.locator_path(SEASON, REPLAY).exists():
            raise ValueError('unreceipted kit replay exists; inspect')
        retained(ROOT / 'complete-SOURCE-replay.json', replay.reconstruction(release, REPLAY))
    print(dict(release=RELEASE, actual_game_built=True, all_three_icons_only=True,
        complete_SOURCE_game_and_recipe_exact=True, preferred_unchanged=True), flush=True)


if __name__ == '__main__':
    main()
