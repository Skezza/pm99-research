"""Remove two unused downloadable executable versions, not running tools."""
import fcntl
import shutil
from datetime import UTC, datetime
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = Path('/home/joe/.codex/packages/standalone')
TARGETS = ('0.159.3-x86_64-unknown-linux-musl', '0.160.0-x86_64-unknown-linux-musl')
RECEIPT = registry.ROOT / '.local/cleanup-20261016/unused-tool-versions.json'


def running():
    executables = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            executables.append((process / 'exe').readlink())
        except FileNotFoundError:
            continue
        except PermissionError:
            # Other users/root cannot be running these private user packages.
            continue
    return executables


def main(*, targets=TARGETS, receipt=RECEIPT):
    allowed = {'0.159.3-x86_64-unknown-linux-musl','0.160.0-x86_64-unknown-linux-musl',
        '0.160.1-x86_64-unknown-linux-musl',
        '0.161.0-x86_64-unknown-linux-musl', '0.162.0-x86_64-unknown-linux-musl'}
    if not targets or not set(targets) <= allowed:
        raise ValueError('cleanup accepts only the explicitly reviewed old executable versions')
    TARGETS, RECEIPT = tuple(targets), receipt
    if RECEIPT.exists():
        raise ValueError('completed executable-cache cleanup must not repeat')
    with (ROOT / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = (ROOT / 'current').resolve()
        rollback = ROOT / 'releases/0.162.1-x86_64-unknown-linux-musl'
        if not current.is_dir() or not rollback.is_dir():
            raise ValueError('current and rollback versions must remain available')
        targets = [ROOT / 'releases' / name for name in TARGETS]
        for path in targets:
            if (not path.is_dir() or path.is_symlink() or path.resolve() != path
                    or current.is_relative_to(path) or rollback.is_relative_to(path)
                    or any(executable.is_relative_to(path) for executable in running())):
                raise ValueError('selected old executable version is unsafe or active')
        catalog = registry.sha256_file(registry.CATALOG_PATH)
        proof = dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
            source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
            removed_paths=[str(p) for p in targets], retained_current=str(current),
            retained_rollback=str(rollback), retained_running=[str(p) for p in running() if 'codex' in str(p)],
            before_free_bytes=shutil.disk_usage(registry.ROOT).free, catalog_sha256=catalog,
            recovery='Re-download the recorded executable versions if needed; only installed software binaries/resources are removed, not sessions, configuration, credentials, projects or source data.')
        retained(RECEIPT.with_name(RECEIPT.stem+'-before-removal.json'), proof)
        for path in targets:
            if any(executable.is_relative_to(path) for executable in running()):
                raise ValueError('selected version became active before removal')
            shutil.rmtree(path)
        if registry.sha256_file(registry.CATALOG_PATH) != catalog:
            raise ValueError('preferred PM99 catalog changed during cleanup')
        proof['after_free_bytes'] = shutil.disk_usage(registry.ROOT).free
        retained(RECEIPT, proof)
        print(dict(removed_unused_versions=list(TARGETS),
            bytes_recovered=proof['after_free_bytes'] - proof['before_free_bytes'],
            running_current_rollback_and_all_PM99_games_preserved=True), flush=True)


if __name__ == '__main__':
    main()
