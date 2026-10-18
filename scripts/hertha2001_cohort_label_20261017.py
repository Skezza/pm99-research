"""Reuse the annual-label build/capture/delivery workflow for sourced2001."""
import argparse
from scripts import build_hertha_cohort_label_20261017 as build
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=build.source.registry.ROOT/'.local/consolidated-audit-20261009/hertha2001-cohort-label-20261017'
RELEASE='sourced-hertha2001-cohort-label-20261017-r140a'
REPLAY='replayed-hertha2001-cohort-label-20261017-r140b'
TAG='hertha2001_cohort_label_r140a_20261017'
PROFILE=(12468,'hertha_preetz','Preetz','Preetz')


def configure():
    admitted=build.source.pipeline.read_json_file(ROOT/'source-admitted-club-plan.json')
    build.ROOT,build.SEASON,build.BASE,build.RELEASE,build.REPLAY=(ROOT,'2001-02',admitted['release_id'],RELEASE,REPLAY)
    build.inputs=lambda: admitted['source_inputs']
    return admitted


def main(args):
    admitted=configure()
    if args.stage=='build':
        base=build.source.registry.load_preferred_release('2001-02')
        if base.release_id!=build.BASE:raise ValueError('source-admitted Hertha2001 parent advanced')
        build.source.verify(base,admitted)
        build.main()
    elif args.stage=='capture':
        path=ROOT/'runtime-profile-spec.json'
        if path.exists():raise ValueError('existing Hertha2001 capture must be inspected, not restarted')
        wait_owned(args.previous_runner_pid,'scripts.capture_haladas2000_opening_keeper_20261017')
        if not (ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('Hertha2001 complete SOURCE required')
        actual=build.source.registry.load_registered_release('2001-02',RELEASE)
        carrier,label,search,token=PROFILE;profile=dict(carrier_id=carrier,label=label,search=search,token=token)
        retained(path,dict(season='2001-02',release_id=RELEASE,manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False))
        capture(0,0,folder=ROOT,release_id=RELEASE,run_tag=TAG,season='2001-02',profile=profile)
    else:
        from scripts import deliver_hertha_cohort_label_20261017 as delivery
        delivery.TAG,delivery.PROFILE=TAG,PROFILE
        if args.previous_version is None:raise ValueError('latest --previous-version required')
        delivery.main(args.previous_version)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=['build','capture','deliver'])
    parser.add_argument('--previous-version',type=int);parser.add_argument('--previous-runner-pid',type=int,default=0)
    main(parser.parse_args())
