"""Archive six exact unregistered September aliases, after the live publication.

Full archive member SHA/size verification on the existing Pi volume, unchanged
local-source rehash, full registry/SOURCE references and inactive target checks
precede deletion. Current releases and required source caches are out of scope.
"""
import argparse
from pathlib import Path
import time
from scripts import archive_superseded_2004_probes_20261017 as archive
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline


def main(previous_pid):
    root=registry.ROOT/'.local/consolidated-audit-20261009'
    summary=root/'country-policy-v2-cohort-20261017/2010-11/final-delivery-summary.json'
    checkpoint=root/'release-delivery-checklist-v78.json'
    while not (summary.exists() and checkpoint.exists()):
        try:command=Path(f'/proc/{previous_pid}/cmdline').read_bytes()
        except FileNotFoundError as exc:
            raise ValueError('country publication stopped without final proof; inspect before archive') from exc
        if b'scripts.deliver_country_policy_v2_cohort_20261017' not in command or b'2010-11' not in command:
            raise ValueError('country predecessor PID identity changed')
        time.sleep(10)
    if pipeline.read_json_file(summary)['checklist']['sha256']!=registry.sha256_file(checkpoint):
        raise ValueError('country predecessor summary/checkpoint differ')
    archive.ROOT=registry.ROOT/'.local/cleanup-20261017/superseded-canonical-alias-probes-to-pi'
    archive.SOURCE=registry.ROOT/'.local'
    archive.NAMES=tuple('season-canonical-alias-roster-carrier'+str(n)+'-candidate-v1'
        for n in (1251,1252,1256,1260,11,10))
    archive.REMOTE='/srv/hdd/pm99-archive/research/canonical-alias-probes/20261017/six-unregistered-September-alias-probes.tar.gz'
    archive.main()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-pid',type=int,required=True)
    main(parser.parse_args().previous_pid)
