"""Capture selected coach candidates as the exact owned builder finishes them."""
import argparse
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_year_bound_manager_repairs_20261016 import ROOT
from scripts.capture_year_bound_manager_repairs_20261016 import main as capture


def await_selected(season,build_pid):
    root=ROOT/season;deadline=time.monotonic()+14400
    while not (root/'selected-delivery.json').exists():
        proc=Path('/proc')/str(build_pid)/'cmdline'
        if not proc.exists() or b'scripts.build_year_bound_manager_repairs_20261016' not in proc.read_bytes():
            raise ValueError('owned year-bound manager builder stopped; inspect outcome, do not restart blindly')
        if time.monotonic()>deadline:raise ValueError('bounded owned manager build wait expired')
        time.sleep(10)
    selected=pipeline.read_json_file(root/'selected-delivery.json')
    evidence=registry.ROOT/selected['evidence_root']
    if not (evidence/'complete-SOURCE-replay.json').exists():
        raise ValueError('selection was written before the exact full SOURCE proof')


def main(build_pid,start_season=None):
    seasons=registry.supported_seasons()
    if start_season is not None:
        if start_season not in seasons:raise ValueError('unsupported capture resume season')
        seasons=seasons[seasons.index(start_season):]
    for season in seasons:
        if season=='2015-16':continue
        await_selected(season,build_pid)
        capture([season])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manager-build-pid',type=int,required=True)
    parser.add_argument('--start-season',choices=registry.supported_seasons())
    args=parser.parse_args()
    main(args.manager_build_pid,args.start_season)
