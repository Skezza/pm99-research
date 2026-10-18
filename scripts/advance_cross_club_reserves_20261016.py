"""Deliver one evidenced frozen cross-club case, without replaying old seasons."""
import os
import shutil

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cross_club_reserve_repair_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.season_art_transaction_v1 import atomic_bytes

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/cross-club-reserves-20261016-v1'
SEASON = '2000-01'
RELEASE = 'sourced-cross-club-reserves-20261016-r106a'
REPLAY = 'replayed-cross-club-reserves-20261016-r106b'
SOURCES = (
    ('cross-club-2000-kanchelskis-original-20261016', 'Andrei_Kanchelskis'),
    ('cross-club-2000-wright-phillips-original-20261016', 'Shaun_Wright-Phillips'),
)


def materialise_cache(root=ROOT):
    """Reuse just-acquired originals, retaining the full acquisition receipts."""
    cache = root / 'source-cache'
    inputs = []
    for key, slug in SOURCES:
        path, raw, binding = source_rows(key)
        receipt = path.with_suffix('.source.json')
        metadata = pipeline.read_json_file(receipt)
        url = 'https://en.wikipedia.org/wiki/' + slug
        if metadata['url'] != url:
            raise ValueError('cross-club biography URL differs from its explicit source')
        target = cache / 'wiki' / (slug + '.html')
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError('retained cross-club biography bytes changed')
        else:
            atomic_bytes(target, raw)
        retained(target.with_name(target.name + '.source.json'), dict(url=url, sha256=binding['sha256']))
        inputs.append(dict(binding, receipt_path=registry.relative_workspace_path(receipt),
            receipt_sha256=registry.sha256_file(receipt)))
    path, raw, binding = source_rows('cross-club-2000-wright-phillips-soccerbase-original-20261016')
    receipt = path.with_suffix('.source.json')
    url = 'https://www.soccerbase.com/players/player.sd?player_id=14892&season_id=130'
    if pipeline.read_json_file(receipt)['url'] != url:
        raise ValueError('secondary biography URL differs')
    target = cache / 'player/14892.html'
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('retained secondary biography bytes changed')
    if not target.exists():
        atomic_bytes(target, raw)
    retained(target.with_name(target.name + '.source.json'), dict(url=url, sha256=binding['sha256']))
    inputs.append(dict(binding, receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt)))
    retained(root / 'complete-source-acquisition-bindings.json', inputs)
    return cache


def main(*, root=ROOT, release_id=RELEASE, replay_id=REPLAY, output_review=None):
    ROOT, RELEASE, REPLAY = root, release_id, replay_id
    ROOT.mkdir(parents=True, exist_ok=True)
    pin = ROOT / 'baseline.json'
    if not pin.exists():
        base = registry.load_preferred_release(SEASON)
        retained(pin, dict(season=SEASON, release_id=base.release_id,
            manifest_sha256=base.manifest_sha256,
            all26_preferred={s: registry.load_preferred_release(s).release_id for s in registry.supported_seasons()}))
    baseline = pipeline.read_json_file(pin)
    base = registry.load_registered_release(SEASON, baseline['release_id'])
    if base.manifest_sha256 != baseline['manifest_sha256']:
        raise ValueError('cross-club baseline manifest changed')
    if registry.load_preferred_release(SEASON).release_id not in (base.release_id, RELEASE):
        raise ValueError('another worker advanced this season outside the owned batch')
    if shutil.disk_usage(ROOT).free < 8.3 * 1024**3:
        raise ValueError('cross-club build refuses to threaten the 8GiB free-space reserve')
    cache = materialise_cache(ROOT)
    plan = source.make_plan(base, 9171, 2774, 'Shaun Wright-Phillips',
        'Shaun_Wright-Phillips', 'Andrei_Kanchelskis', cache, secondary_biography_id=14892,
        output_review=output_review)
    folder = ROOT / SEASON
    folder.mkdir(exist_ok=True)
    path = folder / 'ownership-plan.json'
    retained(path, plan)
    source.verify_plan(base, pipeline.read_json_file(path))
    descriptor = folder / 'inert.json'
    retained(descriptor, dict(season=SEASON, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    if not registry.locator_path(SEASON, RELEASE).exists():
        publisher.publish(SEASON, descriptor, release_id=RELEASE, source_release_id=base.release_id,
            ownership_plan_path=path)
    proof = ROOT / 'native-byte-proof.json'
    if not proof.exists():
        verify_native_batch(ROOT, RELEASE, proof, seasons=[SEASON])
    actual = registry.load_registered_release(SEASON, RELEASE)
    replay_proof = ROOT / 'complete-SOURCE-replay.json'
    if not replay_proof.exists():
        if registry.locator_path(SEASON, REPLAY).exists():
            raise ValueError('unreceipted SOURCE replay exists; inspect rather than rerun')
        source.reconstruction(actual, REPLAY)
        rebuilt = registry.load_registered_release(SEASON, REPLAY)
        pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(actual.inventory_path))
        if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(actual.package_path):
            raise ValueError('cross-club complete SOURCE recipe replay differs')
        retained(replay_proof, dict(season=SEASON, release_id=RELEASE, replay_release_id=REPLAY,
            entire_game_inventory_identical=True, entire_recipe_identical=True,
            native_proof_sha256=registry.sha256_file(proof), ownership_plan_sha256=registry.sha256_file(path)))
        for original, target in ((actual.package_path, rebuilt.package_path),
                (actual.game_path / 'DBDAT/JUG98030.FDI', rebuilt.game_path / 'DBDAT/JUG98030.FDI')):
            if registry.sha256_file(original) != registry.sha256_file(target):
                raise ValueError('newly owned replay bytes differ before content sharing')
            if original.stat().st_ino != target.stat().st_ino:
                temporary = target.with_name(target.name + '.verified-link')
                if temporary.exists():
                    raise ValueError('unreceipted sharing temporary exists')
                os.link(original, temporary)
                os.replace(temporary, target)
    print(dict(season=SEASON, release_id=RELEASE, built=True, SOURCE_exact=True,
        preferred_unchanged=True, runner_review_pending=True), flush=True)


if __name__ == '__main__':
    main()
