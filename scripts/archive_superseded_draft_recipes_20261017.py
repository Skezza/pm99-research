"""Move one superseded September draft collection to Pi after dependency checks."""
import argparse
from pathlib import Path
import time

from scripts import archive_superseded_2004_probes_20261017 as archive
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main(wait_pid):
    while wait_pid:
        try:
            command = Path(f'/proc/{wait_pid}/cmdline').read_bytes()
        except FileNotFoundError:
            break
        if not command:
            break
        if b'scripts.explicit_alias_position_20261017' not in command or b'deliver' not in command:
            raise ValueError('expected publisher PID changed identity')
        time.sleep(10)
    source = registry.ROOT / '.local/season-draft-replay-v2'
    files = [p for p in source.rglob('*') if p.is_file()]
    if len(files) != 51 or any(p.suffix != '.json' or p.is_symlink() for p in files):
        raise ValueError('superseded draft scope differs from inspected 51 JSON files')
    archive.ROOT = registry.ROOT / '.local/cleanup-20261017/superseded-draft-recipes-to-pi'
    archive.SOURCE = registry.ROOT / '.local'
    archive.NAMES = ('season-draft-replay-v2',)
    archive.REMOTE = '/srv/hdd/pm99-archive/research/superseded-draft-recipes/20261017/season-draft-replay-v2.tar.gz'
    original = archive.no_registered_references
    archive.no_registered_references = lambda: original(extra_roots=(
        registry.ROOT / '.local/consolidated-audit-20261009',))
    archive.main()
    retained(archive.ROOT / 'scope.json', dict(
        scope='51 superseded September draft recipe/build-audit JSONs, not current season recipes or original sources.',
        recovery='Restore season-draft-replay-v2 under .local from the verified Pi archive before reopening old draft-only research.',
        current26_and_original2015_untouched=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-publisher-pid', type=int, default=0)
    main(parser.parse_args().wait_publisher_pid)
