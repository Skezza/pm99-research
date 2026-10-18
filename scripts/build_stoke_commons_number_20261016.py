"""Complete the sourced alias reserve with one byte, not a squad regeneration."""
import os
import shutil
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_stoke_commons_number_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Stoke-Commons-shirt-delivery-v1'
SEASON = '2001-02'
RELEASE = 'sourced-stoke-commons-number-20261016-r118a'
REPLAY = 'replayed-stoke-commons-number-20261016-r118b'


def main():
    if (ROOT / 'complete-SOURCE-replay.json').exists():
        raise ValueError('completed single-byte game must not repeat')
    if shutil.disk_usage(registry.ROOT).free < 8.3 * 1024**3:
        raise ValueError('shirt correction refuses to threaten8GiB reserve')
    base = registry.load_registered_release(SEASON, source.BASE)
    plan = source.prepare(base)
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / source.FILENAME; retained(path, plan)
    descriptor = ROOT / 'inert.json'
    retained(descriptor, dict(season=SEASON, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    if not registry.locator_path(SEASON, RELEASE).exists():
        publisher.publish(SEASON, descriptor, release_id=RELEASE, source_release_id=base.release_id,
            profile_assignment_plan_path=path)
    actual = registry.load_registered_release(SEASON, RELEASE)
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    native = (actual.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(original, eq, plan) != (native, eq) or source.apply(native, eq, plan) != (native, eq):
        raise ValueError('actual single shirt-byte reproduction/idempotence failed')
    diffs = [i for i,(a,b) in enumerate(zip(original,native)) if a != b]
    if len(original) != len(native) or len(diffs) != 1 or plan['native_byte_changes'] != 1:
        raise ValueError('actual change is not exactly one native byte')
    old = {r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    new = {r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(old) != set(new) or any(old[k] != new[k] for k in old if k != 'DBDAT/JUG98030.FDI'):
        raise ValueError('shirt correction changed another game file')
    if source.bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(actual.package_path):
        raise ValueError('entire shirt recipe does not reproduce')
    retained(ROOT / 'native-byte-proof.json', dict(season=SEASON, release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256, source_plan_sha256=registry.sha256_file(path),
        exact_native_byte_changes=1, allowed_offsets=diffs, all_other_game_files_identical=True,
        all_other_player_facts_ratings_roles_tactics_managers_and_artwork_identical=True,
        independently_reproduced=True, idempotent=True, shirt_before=5, shirt_after=24))
    if registry.locator_path(SEASON, REPLAY).exists():
        raise ValueError('unreceipted shirt SOURCE copy exists; inspect rather than rerun')
    replay = source.reconstruction(actual, REPLAY)
    retained(ROOT / 'complete-SOURCE-replay.json', dict(replay, source_release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256, preferred_unchanged=True))
    rebuilt = registry.load_registered_release(SEASON, REPLAY)
    for a,b in ((actual.package_path,rebuilt.package_path),
            (actual.game_path/'DBDAT/JUG98030.FDI',rebuilt.game_path/'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a) != registry.sha256_file(b):
            raise ValueError('new shirt SOURCE bytes differ before verified content sharing')
        if a.stat().st_ino != b.stat().st_ino:
            temporary = b.with_name(b.name+'.verified-link')
            if temporary.exists(): raise ValueError('unreceipted sharing temporary')
            os.link(a,temporary);os.replace(temporary,b)
    print(dict(actual_game_built=True, native_byte_changes=1, shirt_number=24,
        full_SOURCE_replay=True, preferred_unchanged=True, runner_pending=True), flush=True)


if __name__ == '__main__':
    main()
