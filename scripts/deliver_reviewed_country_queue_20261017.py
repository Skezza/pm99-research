"""Finish two ROOT-reviewed country deliveries serially, then check all26.

No build, capture or visual approval is performed. These original frames were
already inspected. Each publication still runs the complete guarded native,
SOURCE, literal review, exact digit, asset, default-binding and backup gates.
"""
import argparse
from pathlib import Path
import time

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import deliver_original_country_defaults_20261017 as initial
from scripts import deliver_country_policy_v2_cohort_20261017 as cohort
from scripts import verify_checkpoint_all26_v1 as all26
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/reviewed-country-delivery-queue-20261017'


def main(previous_pid):
    if ROOT.exists():
        raise ValueError('existing reviewed delivery queue needs inspection; never blind rerun')
    ROOT.mkdir()
    root=ROOT.parent;prior=root/'release-delivery-checklist-v74.json'
    predecessor=initial.ROOT/'2012-13/final-delivery-summary.json'
    retained(ROOT/'input.json',dict(previous_controller_pid=previous_pid,previous_checklist=str(prior),
        tasks=[dict(season='2014-15',release_id=initial.RELEASE,previous_version=74),
               dict(season='2009-10',release_id=cohort.build.RELEASE,previous_version=75)],
        automatic_visual_approval=False,unaffected_regeneration=False))
    while not (prior.exists() and predecessor.exists()):
        try:command=Path(f'/proc/{previous_pid}/cmdline').read_bytes()
        except FileNotFoundError as exc:
            raise ValueError('2012 publication stopped without final checkpoint; inspect before continuing') from exc
        if b'scripts.deliver_original_country_defaults_20261017' not in command or b'2012-13' not in command:
            raise ValueError('queued country predecessor PID identity changed')
        time.sleep(10)
    if pipeline.read_json_file(predecessor)['checklist']['sha256']!=registry.sha256_file(prior):
        raise ValueError('queued predecessor receipt binds another checklist')
    tasks=[('2014-15',initial,74),('2009-10',cohort,75)]
    for season,module,version in tasks:
        folder=module.ROOT/season if module is initial else cohort.build.ROOT/season
        spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
        for name in ['startup-visual-review.json']+[r['label']+'-profile-visual-review.json' for r in spec['profiles']]:
            review=pipeline.read_json_file(folder/name)
            if review.get('reviewer')!='ROOT' or not review.get('original_frame_visually_inspected'):
                raise ValueError('queued delivery lacks prior ROOT original-image inspection')
        module.main(season,version)
        summary=folder/'final-delivery-summary.json'
        saved=pipeline.read_json_file(summary)
        checkpoint=root/f'release-delivery-checklist-v{version+1}.json'
        if saved['checklist']['sha256']!=registry.sha256_file(checkpoint):
            raise ValueError('queued final delivery summary differs from exact checkpoint')
        retained(ROOT/f'{season}-completed.json',dict(checklist=saved['checklist'],
            summary=dict(path=registry.relative_workspace_path(summary),sha256=registry.sha256_file(summary)),
            countries_delivered=saved['countries_delivered']))
    check=all26.verify(root/'release-delivery-checklist-v76.json',ROOT/'postpublication-all26-v76.json')
    retained(ROOT/'completed.json',dict(checklist=check['checklist'],all26_actual_bindings_exact=True,
        original_frames_reused=True,automatic_visual_approval=False,unaffected_regenerated_seasons=0,
        global_historical_RC=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-pid',type=int,required=True)
    main(parser.parse_args().previous_pid)
