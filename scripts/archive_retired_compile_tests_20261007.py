"""Archive five unregistered September compile tests, then optionally remove them.

Reuse all-file SHA256 archive verification. Keep every build receipt, source,
current release, original 2015 game and any referenced recovery input.
"""
import argparse
import json
from functools import lru_cache
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as transport
from scripts import archive_superseded_ingress_games_20261004 as ingress
from scripts import season_release_registry_v1 as registry

NAMES = (
    '2007-08-canonical-compile-20260908-r1-game',
    '2007-08-canonical-compile-20260908-r2-game',
    '2007-08-alias-canonical-compile-20260908-r1-game',
    '2008-09-canonical-compile-20260907-r1-game',
    '2008-09-canonical-compile-20260907-r2-game',
)

@lru_cache(maxsize=128)
def references(path, mtime_ns, size):
    return tuple(ingress.nested_strings(json.loads(path.read_text())))

def check_references(source):
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        documents = [release.locator]
        for path in (release.package_path, release.release_manifest_path,
                     release.compiler_receipt_path, release.build_chain_path):
            stat = path.stat()
            documents.append(list(references(path, stat.st_mtime_ns, stat.st_size)))
        # Literal directory name catches absolute and workspace-relative paths.
        if any(source.name in value for document in documents
               for value in ingress.nested_strings(document)):
            raise ValueError('current release/rebuild input references this old test')

def run(apply=False):
    transport.TARGETS = NAMES
    transport.RECEIPTS = ROOT / '.local/cleanup-20261007/retired-compile-tests'
    transport.REMOTE = '/srv/hdd/pm99-archive/packages/retired-compile-tests/20261007'
    transport.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/retired-compile-tests-20261007'
    original_guard = transport.guard
    def guard(source):
        original_guard(source)
        check_references(source)
    transport.guard = guard
    try:
        rows = []
        for name in NAMES:
            print(json.dumps({'name': name, 'stage': 'checking-and-archiving'}), flush=True)
            row = transport.archive(name, apply)
            rows.append(row)
            print(json.dumps(row), flush=True)
            if apply:
                transport.save(transport.RECEIPTS / 'summary.json', {'results': rows})
        return rows
    finally:
        transport.guard = original_guard

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    run(parser.parse_args().archive_and_remove)
