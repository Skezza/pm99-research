"""Move the unregistered cold1990 preview to verified recoverable Pi storage."""
import argparse
from scripts import archive_superseded_2004_probes_20261017 as archive
from scripts.capture_shinnie_country_20261017 import wait_owned


def main(previous_pid):
    wait_owned(previous_pid,'scripts.hertha2001_cohort_label_20261017')
    root=archive.registry.ROOT/'.local/consolidated-audit-20261009'
    summary=archive.pipeline.read_json_file(root/'hertha2001-cohort-label-20261017/final-delivery-summary.json')
    checkpoint=root/'release-delivery-checklist-v97.json'
    if summary['checklist']['sha256']!=archive.registry.sha256_file(checkpoint):
        raise ValueError('label publication did not finish; preserve prototype before archive')
    archive.ROOT=archive.registry.ROOT/'.local/cleanup-20261017/cold-1990-preview-to-pi'
    archive.SOURCE=archive.registry.ROOT/'.local';archive.NAMES=('season-1990-91',)
    archive.REMOTE='/srv/hdd/pm99-archive/research/season-previews/20261017/unregistered-1990-91-simple-preview.tar.gz'
    archive.main()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--previous-pid',type=int,required=True)
    main(parser.parse_args().previous_pid)
