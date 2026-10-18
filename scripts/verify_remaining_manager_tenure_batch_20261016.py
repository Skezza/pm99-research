"""Independently read exact manager games after original runner review."""
import argparse
from scripts import season_remaining_manager_tenures_20261016 as source
from scripts import checkpoint_remaining_manager_tenures_20261016 as checkpoint
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main(seasons):
    for season in seasons:
        root = source.ROOT / season
        path = root / 'independent-delivery-readback.json'
        if path.exists():
            saved = pipeline.read_json_file(path)
            actual = registry.load_registered_release(season, checkpoint.batch.RELEASE)
            if (saved['manifest_sha256'] != actual.manifest_sha256
                    or saved['source_plan']['sha256'] != registry.sha256_file(root / 'manager-plan.json')
                    or saved['startup_screenshot_sha256'] != registry.sha256_file(registry.ROOT / saved['startup_screenshot'])):
                raise ValueError('existing readback no longer binds exact immutable game and original screenshot')
            print(dict(season=season, existing_exact_readback_retained=True), flush=True)
            continue
        verified = checkpoint.verify(season)
        retained(path, verified)
        print(dict(season=season, independent_native_source_runtime_readback=True,
            canonical_manager_updates=verified['canonical_manager_updates']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='+')
    main(parser.parse_args().seasons)
