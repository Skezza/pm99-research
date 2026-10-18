"""Build the proved donor-role fix, starting with the actual City/Rangers game."""
import argparse
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_donor_keeper_role_delta_v1 as source
from scripts.advance_exact_fifa_roles_20261015 import build
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_cross_club_reviewed_reserve_20261016 import RELEASE as CITY_PARENT

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/donor-role-safety-20261016-v1'
RELEASE='sourced-donor-role-safety-20261016-r108a'
REPLAY='replayed-donor-role-safety-20261016-r108b'


def main(seasons, *, prepare_only=False):
    ROOT.mkdir(parents=True,exist_ok=True)
    pin=ROOT/'baseline.json'
    if not pin.exists():
        preferred={s:registry.load_preferred_release(s).release_id for s in registry.supported_seasons()}
        retained(ROOT/'preferred-before-batch.json',preferred)
        retained(pin,[dict(season=s,release_id=CITY_PARENT if s=='2000-01' else preferred[s])
            for s in registry.supported_seasons()])
    for season in seasons:
        if prepare_only:
            folder=ROOT/season;folder.mkdir(parents=True,exist_ok=True)
            path=folder/'role-plan.json'
            baseline=next(r for r in pipeline.read_json_file(pin) if r['season']==season)
            base=registry.load_registered_release(season,baseline['release_id'])
            if path.exists():
                existing=pipeline.read_json_file(path)
                if (existing['release_id'],existing['package_sha256'],existing['jug_sha256'])!=(
                        base.release_id,registry.sha256_file(base.package_path),
                        registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI')):
                    raise ValueError('prepared donor plan baseline changed')
                print(dict(season=season,reused_exact_prepared_plan=True),flush=True)
                continue
            plan=source.prepare(base);retained(path,plan)
            print(dict(season=season,role_corrections=sum(r['fine_roles'] is not None for r in plan['updates']),
                nationality_declarations=sum(r['nationality'] is not None for r in plan['updates']),
                native_writes=0),flush=True)
            continue
        build(season,batch_root=ROOT,release_id=RELEASE,replay_id=REPLAY,source_module=source,
            require_preferred=season!='2000-01',allow_declared_country_bytes=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='*',default=['2000-01'])
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    main(registry.supported_seasons() if args.seasons==['all'] else args.seasons,prepare_only=args.prepare_only)
