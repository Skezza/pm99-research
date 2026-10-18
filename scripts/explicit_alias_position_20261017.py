"""Build/capture/deliver explicit V2 positions; never repeat completed stages."""
import argparse

from scripts import build_exact_position_batch_20261017 as builder
from scripts import capture_exact_position_batch_20261017 as capturer
from scripts import season_exact_primary_position_delta_v2 as source
from scripts import checkpoint_exact_primary_position_v1 as checkpoint
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = builder.registry.ROOT / '.local/consolidated-audit-20261009/alias-primary-positions-20261017'
RELEASE = 'sourced-alias-primary-positions-20261017-r133a'
REPLAY = 'replayed-alias-primary-positions-20261017-r133b'


def tag(season):
    return 'alias_primary_positions_' + season.replace('-', '_') + '_r133a_20261017'


def configure():
    builder.source = source
    builder.ROOT, builder.RELEASE, builder.REPLAY = ROOT, RELEASE, REPLAY
    capturer.tag = tag


def main(args):
    configure()
    folder = ROOT / args.season
    if args.stage == 'build':
        ROOT.mkdir(parents=True, exist_ok=True)
        if (folder / 'position-plan.json').exists() or builder.registry.locator_path(args.season, RELEASE).exists():
            raise ValueError('existing alias-position transaction needs inspection, not regeneration')
        base = builder.registry.load_preferred_release(args.season)
        plan = source.prepare(base, args.carriers)
        path = ROOT / (args.season + '-admitted-plan.json')
        retained(path, plan)
        builder.main(args.season, base.release_id, args.carriers, path)
    elif args.stage == 'capture':
        capturer.main(args.season, 0)
    else:
        spec = builder.pipeline.read_json_file(folder / 'runtime-profile-spec.json')
        actual = builder.registry.load_registered_release(args.season, RELEASE)
        if (spec['season'], spec['release_id'], spec['manifest_sha256']) != (
                args.season, RELEASE, actual.manifest_sha256):
            raise ValueError('alias-position runtime spec binds another native game')
        profiles = [(r['carrier_id'], r['label'], r['search'], r['token']) for r in spec['profiles']]
        previous = ROOT.parent / f'release-delivery-checklist-v{args.previous_version}.json'
        output = ROOT.parent / f'release-delivery-checklist-v{args.previous_version+1}.json'
        checkpoint.run(folder, args.season, RELEASE, REPLAY, previous, output,
                       tag(args.season), profiles, policy=source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('build', 'capture', 'deliver'))
    parser.add_argument('--season', required=True)
    parser.add_argument('--carriers', type=int, nargs='+')
    parser.add_argument('--previous-version', type=int)
    args = parser.parse_args()
    if args.stage == 'build' and not args.carriers:
        parser.error('build requires explicit --carriers')
    if args.stage == 'deliver' and args.previous_version is None:
        parser.error('deliver requires explicit --previous-version')
    main(args)
