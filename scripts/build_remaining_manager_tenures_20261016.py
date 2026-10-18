"""Build admitted remaining/coupled coaches without changing unrelated games.

Only exact parents named by the source admission may be used. This registers
private candidates; runner review and independent verification precede promotion.
"""
import argparse
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_remaining_manager_tenures_20261016 as source
from scripts import build_cached_manager_repairs_20261016 as core

ROOT = source.ROOT
RELEASE = 'sourced-remaining-manager-tenures-20261016-r116a'
REPLAY = 'replayed-remaining-manager-tenures-20261016-r116b'


def wait_for_admission(pid):
    """Wait on the exact owned live source job; never restart its work."""
    deadline = time.monotonic() + 1800
    while True:
        try:
            command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
        except FileNotFoundError:
            break
        if b'scripts.season_remaining_manager_tenures_20261016' not in command:
            raise ValueError('source PID identity changed; inspect rather than waiting on another job')
        if time.monotonic() > deadline:
            raise ValueError('source wait expired; inspect exact live admission before retry')
        time.sleep(5)
    if not (ROOT / 'source-admission-summary.json').is_file():
        raise ValueError('source job stopped without full admission; no games built')


def build(season):
    admission = pipeline.read_json_file(ROOT / 'source-admission-summary.json')
    rows = [r for r in admission['seasons'] if r['season'] == season]
    if len(rows) != 1:
        raise ValueError('season must have exactly one completed source admission')
    row = rows[0]
    path = registry.ROOT / row['source_plan']['path']
    if registry.sha256_file(path) != row['source_plan']['sha256']:
        raise ValueError('admitted source plan changed')
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(season, plan['release_id'])
    current = registry.load_preferred_release(season)
    if current.release_id not in (base.release_id, RELEASE):
        raise ValueError('preferred season moved; preserve intervening changes')
    if current.release_id == base.release_id and current.manifest_sha256 != base.manifest_sha256:
        raise ValueError('preferred parent manifest changed')
    if source.prepare(base) != plan:
        raise ValueError('original sources or native parent no longer reproduce admission')
    if not plan['updates']:
        print(dict(season=season, no_admitted_update=True, not_rebuilt=True), flush=True)
        return
    core.build(season, batch_root=ROOT, release_id=RELEASE, replay_id=REPLAY,
        source_module=source, source_release_id=base.release_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='+')
    parser.add_argument('--wait-for-admission-pid', type=int)
    args = parser.parse_args()
    if args.wait_for_admission_pid is not None:
        wait_for_admission(args.wait_for_admission_pid)
    for season in args.seasons:
        build(season)
