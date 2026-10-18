"""Capture an actually SOURCE-complete corrected country game, never approve."""
import argparse

from scripts import build_resolved_period_country_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture, wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):
    return 'resolved_period_country_' + season.replace('-', '_') + '_r130a_20261017'


def main(season, builder_pid, target_carrier=None):
    folder = build.ROOT / season
    if (folder / 'runtime-profile-spec.json').exists():
        raise ValueError('existing corrected country capture requires inspection, not restart')
    if builder_pid:
        wait_owned(builder_pid, 'scripts.build_resolved_period_country_20261017')
    if not (folder / 'complete-SOURCE-replay.json').exists():
        raise ValueError('corrected country builder has no complete SOURCE proof')
    actual = build.source.registry.load_registered_release(season, build.RELEASE)
    plan = build.source.pipeline.read_json_file(folder / 'country-plan.json')
    choices = [r for r in plan['updates'] if target_carrier is None or r['carrier_id'] == target_carrier]
    if not choices or target_carrier is not None and len(choices) != 1:
        raise ValueError('explicit country profile carrier is not uniquely changed in this game')
    selected = choices[0]
    carrier = selected['carrier_id']
    actor = selected['before_player']
    search = build.source.original.names.undecorated(actor.get('source_name') or actor['name'])
    profile = dict(carrier_id=carrier, label='country_' + str(carrier), search=search,
        token=search.split()[-1], expected_native_name=actor['name'],
        expected_country=selected['nationality'], expected_native_country_label=selected['native_label'])
    retained(folder / 'runtime-profile-spec.json', dict(season=season, release_id=build.RELEASE,
        manifest_sha256=actual.manifest_sha256, profiles=[profile], visual_approval=False))
    capture(0, 0, folder=folder, release_id=build.RELEASE, run_tag=tag(season), season=season, profile=profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--builder-pid', type=int, default=0)
    parser.add_argument('--target-carrier', type=int)
    args = parser.parse_args()
    main(args.season, args.builder_pid, args.target_carrier)
