"""Build an explicit country correction over an existing release, never promote."""
import argparse

from scripts import build_original_country_policy_v2_20261017 as exporter
from scripts import season_resolved_period_country_v3 as source

ROOT = source.registry.ROOT / '.local/consolidated-audit-20261009/resolved-period-country-v3-20261017'
RELEASE = 'sourced-resolved-period-country-20261017-r130a'
REPLAY = 'replayed-resolved-period-country-20261017-r130b'


def main(season, parent, original_plan, carriers):
    exporter.source = source
    exporter.ROOT, exporter.RELEASE, exporter.REPLAY = ROOT, RELEASE, REPLAY
    exporter.PEOPLE = original_plan
    exporter.build(season, parent, carriers)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--source-release', required=True)
    parser.add_argument('--original-plan', type=source.Path, required=True)
    parser.add_argument('--target-carriers', type=int, nargs='+', required=True)
    args = parser.parse_args()
    main(args.season, args.source_release, args.original_plan, args.target_carriers)
