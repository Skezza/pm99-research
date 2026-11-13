#!/usr/bin/env python3
"""Archive exact retired duplicate-repair cohorts; read-only by default.

Old registrations remain. Replaying archived old versions requires restoring
their exact selected artifacts from the Pi; current versions and live bases stay local.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import json_storage_io_v1 as storage_io
from scripts import archive_retired_season_tests_20261004 as archive
from scripts import season_release_registry_v1 as registry

SOURCE = ROOT / '.local/historical-role-deltas-v1'
PLANS = ROOT / '.local/duplicate-ownership-v3/plans-r11'
ADDITIONAL_ACTIVE_PLANS = (
    ROOT / '.local/duplicate-ownership-v3/plans-r12',
    ROOT / '.local/duplicate-ownership-v3/family-window-proposals-r1',
)
RECEIPT = ROOT / '.local/duplicate-ownership-v3/space-recovery/retired-r23-r31-jug.json'
REMOTE = '/srv/hdd/pm99-archive/packages/retired-duplicate-jug/20261006-r23-r31'
RELEASE = re.compile(r'opening-[a-z0-9.-]+-20261006-r(?:2[3-9]|3[01])a')


def game_root(path,filename):
    return path.parent/'game' if filename=='season-package.json' else path.parents[1]


def eligible(path, protected, pattern=RELEASE,filename='JUG98030.FDI'):
    relative = path.relative_to(SOURCE)
    expected=('season-package.json',) if filename=='season-package.json' else ('game','DBDAT','JUG98030.FDI')
    if (len(relative.parts) != len(expected)+2 or not pattern.fullmatch(relative.parts[1])
            or relative.parts[2:] != expected
            or relative.parts[0] not in registry.supported_seasons()):
        raise ValueError('outside the retired JUG allowlist')
    if path.is_symlink() or storage_io.resolve(path) != path.absolute() or storage_io.stat_result(path).st_nlink != 1:
        raise ValueError('retired JUG is symlinked or shared')
    if storage_io.resolve(path) in protected or archive._active_game(game_root(path,filename)):
        raise ValueError('retired JUG is current, an active plan base, or running')


def protected_files(plan_roots=None,filename='JUG98030.FDI'):
    def selected(release):
        return release.package_path if filename=='season-package.json' else release.game_path/'DBDAT/JUG98030.FDI'
    result = {storage_io.resolve(selected(registry.load_preferred_release(s))) for s in registry.supported_seasons()}
    for plan_root in ((PLANS,*ADDITIONAL_ACTIVE_PLANS) if plan_roots is None else plan_roots):
        for plan_path in storage_io.glob(plan_root, '*/ownership-plan.json'):
            plan = json.loads(storage_io.read_text(plan_path))
            base = registry.load_registered_release(plan['season'], plan['release_id'])
            result.add(storage_io.resolve(selected(base)))
    return result


def run(remove=False,cohort='r23-r31'):
    active_plan_roots=None
    filename='JUG98030.FDI'
    if cohort=='r23-r31':pattern,receipt,remote=RELEASE,RECEIPT,REMOTE
    elif cohort=='r32-r35':
        pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r3[2-5]a')
        receipt=RECEIPT.with_name('retired-r32-r35-jug.json')
        remote='/srv/hdd/pm99-archive/packages/retired-duplicate-jug/20261006-r32-r35'
    elif cohort in ('r32-r38-after-r38','recipes-r23-r38-after-r38'):
        # Earlier baselines are protected until their complete closeout, not
        # forever. Never retire an in-flight native check or its delivery base.
        work=ROOT/'.local/duplicate-ownership-v3'
        for label in ('r36','r37','r38'):
            proof=work/f'closeout-{label}-final/summary.json'
            if not storage_io.is_file(proof) or json.loads(storage_io.read_text(proof)).get('full_release_validation_passed')!=26:
                raise ValueError('complete R36/R37/R38 closeouts required before retiring their baselines')
        active_plan_roots=(work/'capacity-source-plans-r1',work/'capacity-window-proposals-r1')
        if len(list(storage_io.glob(active_plan_roots[0], '*/ownership-plan.json')))!=26:
            raise ValueError('all 26 next-batch baseline plans must exist before retirement')
        if cohort=='r32-r38-after-r38':
            pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r3[2-8]a')
            receipt=RECEIPT.with_name('retired-r32-r38-after-r38-jug.json')
            remote='/srv/hdd/pm99-archive/packages/retired-duplicate-jug/20261006-r32-r38-after-r38'
        else:
            filename='season-package.json'
            pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r(?:2[3-9]|3[0-8])a')
            receipt=RECEIPT.with_name('retired-recipes-r23-r38-after-r38.json')
            remote='/srv/hdd/pm99-archive/packages/retired-duplicate-recipes/20261006-r23-r38-after-r38'
    else:raise ValueError('unknown exact retired release cohort')
    if storage_io.exists(receipt):
        raise ValueError('receipt exists; inspect it instead of overwriting')
    protected = protected_files(active_plan_roots,filename)
    files = []
    retained=[]
    selector='*/opening-*-20261006-r*a/season-package.json' if filename=='season-package.json' else '*/opening-*-20261006-r*a/game/DBDAT/JUG98030.FDI'
    for path in sorted(storage_io.glob(SOURCE, selector)):
        release_dir=path.parent if filename=='season-package.json' else path.parents[2]
        if not pattern.fullmatch(release_dir.name):
            continue
        if storage_io.resolve(path) in protected or archive._active_game(game_root(path,filename)) or storage_io.stat_result(path).st_nlink!=1:
            retained.append(path.relative_to(ROOT).as_posix())
            continue
        eligible(path, protected,pattern,filename)
        stat = storage_io.stat_result(path)
        files.append({'path': path.relative_to(ROOT).as_posix(),
                      'sha256': registry.sha256_file(path), 'size': stat.st_size,
                      'mode': stat.st_mode, 'mtime_ns': stat.st_mtime_ns,
                      'allocated_bytes': stat.st_blocks * 512,
                      'remote_path': remote + '/' + path.relative_to(SOURCE).as_posix()})
    result = {'schema_version': 'pm99-retired-duplicate-jug-archive-v1',
              'host': archive.HOST, 'remote': remote, 'disk_uuid': archive.DISK_UUID,
              'cohort':cohort,'artifact_filename':filename,'protected_files_retained':retained,
              'files': files, 'file_count': len(files),
              'allocated_bytes': sum(f['allocated_bytes'] for f in files),
              'local_removed': False,
              'restore_required_for_archived_old_games': True,
              'current_games_original_2015_sources_and_recipes_preserved': True,
              'closed_older_bases_may_require_archive_restore':active_plan_roots is not None,
              'current_games_original_2015_sources_recipes_and_r36_bases_preserved':active_plan_roots is None}
    if not remove or not files:
        return result
    if archive.remote('findmnt -n -o UUID --target /srv/hdd').strip() != archive.DISK_UUID:
        raise ValueError('Pi disk is not the expected mounted archive disk')
    archive.remote('mkdir -p ' + shlex.quote(remote))
    transport = 'ssh -o BatchMode=yes -o ConnectTimeout=8'
    # rsync --files-from preserves the exact selected relative paths only.
    selected = ''.join(str(Path(f['path']).relative_to(SOURCE.relative_to(ROOT))) + '\n'
                       for f in files)
    archive.command(['rsync', '-ltz', '--compress-level=1', '--files-from=-', '-e', transport,
                     str(SOURCE) + '/', archive.HOST + ':' + remote + '/'], stdin=selected)
    checks = ''.join(f['sha256'] + '  ' + f['remote_path'] + '\n' for f in files)
    archive.remote('sha256sum --check --quiet', stdin=checks)
    protected = protected_files(active_plan_roots,filename)
    for f in files:
        path = ROOT / f['path']
        eligible(path, protected,pattern,filename)
        if registry.sha256_file(path) != f['sha256']:
            raise ValueError('local retired JUG changed during backup')
    result['archive_verified'] = True
    result['verification'] = 'remote SHA256, fresh local SHA256, current/active-base guards'
    archive.save(receipt, result)
    archive.command(['rsync', '-lt', '-e', transport, str(receipt),
                     archive.HOST + ':' + remote + '/receipt.json'])
    archive.remote('sync')
    for f in files:
        path = ROOT / f['path']
        eligible(path, protected_files(active_plan_roots,filename),pattern,filename)
        if registry.sha256_file(path) != f['sha256']:
            raise ValueError('local retired JUG changed before removal')
        storage_io.unlink(path)
        f['local_removed'] = True
        archive.save(receipt, result)
    result['local_removed'] = True
    archive.save(receipt, result)
    archive.command(['rsync', '-lt', '-e', transport, str(receipt),
                     archive.HOST + ':' + remote + '/receipt.json'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-and-remove', action='store_true')
    parser.add_argument('--cohort',choices=('r23-r31','r32-r35','r32-r38-after-r38','recipes-r23-r38-after-r38'),default='r23-r31')
    args = parser.parse_args()
    value = run(args.archive_and_remove,args.cohort)
    print(json.dumps({k: v for k, v in value.items() if k != 'files'}))
