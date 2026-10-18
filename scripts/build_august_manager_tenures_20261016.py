"""Build admitted August1 manager changes on exact current v53 parents."""
import argparse
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_august_manager_tenures_20261016 as source
from scripts import build_cached_manager_repairs_20261016 as build_core

ROOT = source.ROOT
RELEASE = 'sourced-august-manager-tenures-20261016-r115a'
REPLAY = 'replayed-august-manager-tenures-20261016-r115b'


def build(season):
    path = ROOT / season / 'manager-plan.json'
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(season, plan['release_id'])
    if source.prepare(base) != plan:
        raise ValueError('admitted original sources or exact parent recipe changed')
    current = registry.load_preferred_release(season)
    if current.release_id not in (base.release_id, RELEASE):
        raise ValueError('preferred season moved to another parent; do not discard intervening changes')
    if current.release_id == base.release_id and current.manifest_sha256 != base.manifest_sha256:
        raise ValueError('parent manifest changed')
    if not plan['updates']:
        print(dict(season=season, no_admitted_update=True, not_rebuilt=True), flush=True)
        return
    build_core.build(season, batch_root=ROOT, release_id=RELEASE, replay_id=REPLAY,
        source_module=source, source_release_id=base.release_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='+')
    for season in parser.parse_args().seasons:
        build(season)
