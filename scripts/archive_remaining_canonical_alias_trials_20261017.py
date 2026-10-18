"""Retire six inactive September experiments only after verified Pi backup."""
from scripts import archive_superseded_2004_probes_20261017 as archive


def main():
    archive.ROOT=archive.registry.ROOT/'.local/cleanup-20261017/remaining-canonical-alias-trials-to-pi'
    archive.SOURCE=archive.registry.ROOT/'.local'
    archive.NAMES=('season-canonical-alias-candidate-v1','season-canonical-alias-roster-candidate-v1',
        'season-canonical-alias-roster-carrier1001-candidate-v1','season-canonical-alias-roster-carrier12-candidate-v1',
        'season-canonical-alias-roster-carrier1303-candidate-v1','season-canonical-alias-workspace-v1')
    archive.REMOTE='/srv/hdd/pm99-archive/research/canonical-alias-probes/20261017/remaining-six-September-alias-trials.tar.gz'
    archive.main()


if __name__=='__main__':main()
