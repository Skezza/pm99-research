"""Build verified coach candidates alongside the live owned role builder."""
import argparse
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as source
from scripts.build_cached_manager_repairs_20261016 import build, ROOT
from scripts.build_donor_role_safety_20261016 import ROOT as ROLE_ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main(build_pid):
    for season in registry.supported_seasons():
        report=pipeline.read_json_file(source.REVIEWS/season/'opening-review.json')
        if report['bindings']['opening_capture_path'] is None:
            if season!='2015-16':raise ValueError('unexpected absent original capture')
            root=ROOT/season;root.mkdir(parents=True,exist_ok=True)
            retained(root/'separate-legacy-source-layout-required.json',dict(season=season,
                native_writes=0,game_not_rebuilt=True,manager_approval=False,
                reason='legacy2015 needs separate original-source replay; no generic capture binding'))
            continue
        deadline=time.monotonic()+14400
        while not (ROLE_ROOT/season/'complete-SOURCE-replay.json').exists():
            proc=Path('/proc')/str(build_pid)/'cmdline'
            if not proc.exists() or b'scripts.build_donor_role_safety_20261016' not in proc.read_bytes():
                raise ValueError('own parent builder stopped; inspect its terminal state')
            if time.monotonic()>deadline:raise ValueError('bounded own parent build wait expired')
            time.sleep(10)
        build(season)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role-build-pid',type=int,required=True)
    main(parser.parse_args().role_build_pid)
