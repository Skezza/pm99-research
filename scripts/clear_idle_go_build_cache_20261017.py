"""Clear only the verified Go build cache, not source or downloaded modules."""
from datetime import UTC, datetime
import argparse
from pathlib import Path
import shutil
import subprocess
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

TARGET=Path('/home/joe/.cache/go-build')
GO=Path('/home/joe/.local/go/bin/go')
OUT=registry.ROOT/'.local/cleanup-20261017/go-compiler-cache/completed.json'

def run(*, record_completed_recovery=False):
    if OUT.exists():raise ValueError('completed cache cleanup must not repeat')
    actual=subprocess.check_output([str(GO),'env','GOCACHE'],text=True).strip()
    if actual!=str(TARGET) or TARGET.is_symlink() or TARGET.resolve()!=TARGET or not TARGET.is_dir():
        raise ValueError('expected exact ordinary compiler cache required')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:
            if (process/'exe').resolve().is_relative_to(TARGET):raise ValueError('cached executable running')
            for fd in (process/'fd').iterdir():
                if fd.resolve().is_relative_to(TARGET):raise ValueError('compiler cache currently in use')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    catalog=registry.sha256_file(registry.CATALOG_PATH);before=shutil.disk_usage(registry.ROOT).free
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if record_completed_recovery:
        # First command succeeded, but its receipt parent was missing. Never
        # repeat the cleanup just to repair bookkeeping or invent its free delta.
        remaining=sum(p.stat().st_size for p in TARGET.rglob('*') if p.is_file())
        proof=registry.ROOT/'.local/consolidated-audit-20261009/Barnet2018-native-delivery-v1/final-all26-v110.json'
        from scripts import season_pipeline_v2 as pipeline
        if remaining>1024*1024 or pipeline.read_json_file(proof)['catalog_sha256']!=catalog:
            raise ValueError('cache not already cleared or preferred games changed')
    else:
        retained(OUT.parent/'preflight.json',dict(utc=datetime.now(UTC).isoformat(),before_free_bytes=before,
            catalog_sha256=catalog,target=str(TARGET)))
        subprocess.run([str(GO),'clean','-cache'],check=True)
    if catalog!=registry.sha256_file(registry.CATALOG_PATH):raise ValueError('preferred catalog advanced')
    after=shutil.disk_usage(registry.ROOT).free
    retained(OUT,dict(utc=datetime.now(UTC).isoformat(),machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',target=str(TARGET),
        command=[str(GO),'clean','-cache'],before_free_bytes=None if record_completed_recovery else before,after_free_bytes=after,
        recovered_bytes=None if record_completed_recovery else after-before,preferred_catalog_sha256=catalog,
        recovered_receipt_without_repeating_cleanup=record_completed_recovery,
        previous_cache_du_observation='3.5 GiB; exact recovered byte delta unavailable for receipt-recovery path',
        scope='Regenerable Go compiler cache only; no source, downloaded modules, PM99 games or evidence.',
        recovery='Go automatically recompiles missing cache entries on the next build; no unique data removed.',
        archived=False,archive_unnecessary_reason='Downloadable/rebuildable compiler cache, not unique project data.'))
    print(dict(regenerable_Go_cache_cleared=True,recovered_bytes=None if record_completed_recovery else after-before,
        available_bytes=after,cleanup_not_repeated=record_completed_recovery),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-completed-recovery',action='store_true')
    run(record_completed_recovery=parser.parse_args().record_completed_recovery)
