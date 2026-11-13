"""Archive one old derived review collection, not sources/recipes/native games.

The October4 transfer-review JSONs are historical diagnostic evidence, not
current release bindings. Retain every byte on Pi before any local retirement.
All compiled/registered/consolidated metadata dependencies are checked twice.
"""
from scripts import json_storage_io_v1 as storage_io
from scripts import archive_superseded_2004_probes_20261017 as archive
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    folder=registry.ROOT/'.local/historical-transfer-review-20261004-r1'
    for path in storage_io.glob(folder, '*', recursive=True):
        if path.is_symlink() or storage_io.is_file(path) and path.suffix not in ('.json','.csv') and not path.name.endswith('.json.zst'):
            raise ValueError('cold transfer report collection contains unexpected raw/source/binary files')
    archive.ROOT=registry.ROOT/'.local/cleanup-20261017/cold-transfer-reviews-to-pi'
    archive.SOURCE=registry.ROOT/'.local'
    archive.NAMES=('historical-transfer-review-20261004-r1',)
    archive.REMOTE='/srv/hdd/pm99-archive/evidence/cold-transfer-reviews/20261017/historical-transfer-review-20261004-r1.tar.gz'
    original=archive.no_registered_references
    archive.no_registered_references=lambda: original(extra_roots=(registry.ROOT/'.local/consolidated-audit-20261009',))
    archive.main()
    retained(archive.ROOT/'scope.json',dict(
        scope='Old derived October4 transfer-review JSON/CSV evidence only; no original cached sources, recipes or game files.',
        recovery='Restore the named collection from the verified Pi archive to .local before reopening the old report commands in ALL_26_INDEPENDENT_ROSTER_REVIEW_2026-10-05.md.',
        current26_and_original2015_untouched=True))


if __name__=='__main__':main()
