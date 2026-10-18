"""Use an existing admitted position plan, then capture the actual new game."""
import argparse
from pathlib import Path

from scripts import explicit_alias_position_20261017 as batch


def main(path):
    batch.configure()
    plan = batch.builder.pipeline.read_json_file(path)
    if plan['schema'] != batch.source.SCHEMA:
        raise ValueError('requires the exact independently source-admitted V2 plan')
    base = batch.builder.registry.load_preferred_release(plan['season'])
    if (base.release_id != plan['release_id']
            or batch.builder.registry.sha256_file(base.package_path) != plan['package_sha256']):
        raise ValueError('admitted position baseline advanced; do not discard later fixes')
    batch.builder.main(plan['season'], base.release_id, plan['targets'], path)
    batch.capturer.main(plan['season'], 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admitted-plan', required=True, type=Path)
    main(parser.parse_args().admitted_plan)
