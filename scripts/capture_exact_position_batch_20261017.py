"""Capture the actual position-only game and every changed player's profile."""
import argparse

from scripts import build_exact_position_batch_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):return 'explicit_primary_positions_'+season.replace('-','_')+'_r132a_20261017'


def main(season,builder_pid):
    folder=build.ROOT/season
    if (folder/'runtime-profile-spec.json').exists():raise ValueError('existing position capture needs inspection, not restart')
    if builder_pid:wait_owned(builder_pid,'scripts.build_exact_position_batch_20261017')
    if not (folder/'complete-SOURCE-replay.json').exists():raise ValueError('actual position SOURCE incomplete')
    release=build.registry.load_registered_release(season,build.RELEASE)
    plan=build.pipeline.read_json_file(folder/'position-plan.json')
    profiles=[]
    for row in plan['updates']:
        name=build.source.fifa.names(row['before_player'])
        full=min(name,key=lambda n:(n.startswith('#'),len(n),n)) if name else row['before_player']['name']
        # The original display can contain a literal number label. Search
        # retains the person's full lexical name; no initial expansion.
        from scripts.season_number_label_names_v2 import undecorated
        full=undecorated(full)
        profiles.append(dict(carrier_id=row['carrier_id'],label='position_'+str(row['carrier_id']),
            search=full,token=full.split()[-1]))
    retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
        manifest_sha256=release.manifest_sha256,profiles=profiles,visual_approval=False))
    for index,profile in enumerate(profiles):
        capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,
                profile=profile,capture_startup=index==0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True);parser.add_argument('--builder-pid',type=int,default=0)
    args=parser.parse_args();main(args.season,args.builder_pid)
