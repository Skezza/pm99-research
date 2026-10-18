#!/usr/bin/env python3
"""Archive regenerable Windows files of the old upscale test Wine prefix.

Keep the test game's database, prefix registry and all home-directory symlinks.
No links are followed. Refuse any Wine process or current release reference.
The existing archive transport checks every original file on the mounted Pi,
checksum-rsync and fresh local inventory before deleting this exact child.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import archive_retired_season_tests_20261004 as transport
from scripts import season_release_registry_v1 as registry

PREFIX = ROOT / '.local/pm99-upscale-poc-stable-v2/wineprefix-enhanced'
SOURCE = PREFIX / 'drive_c/windows'


def guard(path):
    if path != SOURCE or any(p.is_symlink() for p in (PREFIX, PREFIX / 'drive_c', SOURCE)):
        raise ValueError('not the exact retired upscale Windows child')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / 'cmdline').read_bytes().split(b'\0')
            executable = Path(cmd[0].decode()).name.lower() if cmd and cmd[0] else ''
            if executable.startswith(('wine', 'wineserver')):
                raise ValueError('a Wine process is running; keep every local prefix')
        except (OSError, UnicodeDecodeError):
            pass
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        if release.game_path.resolve().is_relative_to(PREFIX.resolve()):
            raise ValueError('current game uses the retired test prefix')
        documents = [json.dumps(release.locator)]
        documents += [p.read_text() for p in (release.package_path, release.release_manifest_path,
            release.compiler_receipt_path, release.build_chain_path)]
        if any('wineprefix-enhanced' in text for text in documents):
            raise ValueError('current recipe or rebuild input references the test prefix')
    if transport._active_game(PREFIX):
        raise ValueError('retired prefix is active')


def run(apply=False):
    transport.WORKSPACE = PREFIX / 'drive_c'
    transport.TARGETS = ('windows',)
    transport.RECEIPTS = ROOT / '.local/duplicate-ownership-v3/space-recovery/retired-upscale-enhanced-windows'
    transport.REMOTE = '/srv/hdd/pm99-archive/packages/retired-upscale-enhanced-windows/20261006'
    transport.REMOTE_RECEIPTS = '/srv/hdd/pm99-archive/receipts/retired-upscale-enhanced-windows-20261006'
    original_guard = transport.guard
    def checked(path):
        original_guard(path)
        guard(path)
    transport.guard = checked
    try:
        result = transport.archive('windows', apply)
    finally:
        transport.guard = original_guard
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    args = parser.parse_args()
    run(args.archive_and_remove)
