"""Recover ONLY this turn's unpromoted rejected r100 trial buffers.

Keep verified compressed unique game/recipe/metadata recovery copies, all source
plans/screenshots/receipts, and every original preferred playable season.
"""
import hashlib
import shutil
import subprocess
import tarfile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/rating-calibration-v1'

def run():
    baselines=pipeline.read_json_file(ROOT/'pinned-baselines.json');archive_root=ROOT/'rejected-recovery';archive_root.mkdir(exist_ok=True)
    processes=subprocess.check_output(['ps','-eo','args'],text=True)
    ledger=[]
    for b in baselines:
        season=b['season'];baseline=registry.load_registered_release(season,b['release_id'])
        if registry.load_preferred_release(season).release_id!=baseline.release_id:raise ValueError('current playable baseline changed; no retirement')
        for prefix,suffix in [('sourced','r100a'),('replayed','r100b')]:
            rid=prefix+'-rating-calibration-20261011-'+season+'-'+suffix
            workspace=registry.ROOT/'.local/historical-role-deltas-v1'/season/rid
            if not workspace.exists():continue
            if workspace.is_symlink() or workspace.resolve()!=workspace.absolute():raise ValueError('unsafe rejected workspace')
            if str(workspace) in processes:raise ValueError('rejected workspace still in use; wait for existing transport, never kill host lock')
            locator=registry.locator_path(season,rid)
            archive=archive_root/(season+'-'+suffix+'.tar.gz');receipt=archive_root/(season+'-'+suffix+'-receipt.json')
            files=[p for p in workspace.rglob('*') if p.is_file() and not p.is_relative_to(workspace/'game')]
            jug=workspace/'game/DBDAT/JUG98030.FDI'
            if jug.exists():files.append(jug)
            items=[(p,p.relative_to(workspace).as_posix()) for p in files]
            if locator.exists():items.append((locator,'registered-locator.json'))
            expected={name:registry.sha256_file(path) for path,name in items}
            if not archive.exists():
                with tarfile.open(archive,'w:gz',dereference=True) as stream:
                    for path,name in items:stream.add(path,arcname=name,recursive=False)
            with tarfile.open(archive,'r:gz') as stream:
                members={member.name:member for member in stream.getmembers()}
                if set(members)!=set(expected):raise ValueError('rejected recovery member set differs')
                for name,digest in expected.items():
                    content=stream.extractfile(members[name])
                    if content is None or hashlib.file_digest(content,'sha256').hexdigest()!=digest:raise ValueError('rejected archive member hash differs')
            # No arbitrary files from the game are discarded: all except JUG
            # MUST still be exact immutable baseline bytes (normally hardlinks).
            base_inventory=pipeline.read_json_file(baseline.inventory_path)
            for row in base_inventory['files']:
                if row['path']=='DBDAT/JUG98030.FDI':continue
                target=workspace/'game'/row['path']
                if not target.exists() or registry.sha256_file(target)!=row['sha256']:raise ValueError('rejected game contains unique non-JUG changes')
            retained(receipt,dict(season=season,rejected_release=rid,baseline=b['release_id'],
                workspace=registry.relative_workspace_path(workspace),archive=registry.relative_workspace_path(archive),
                archive_sha256=registry.sha256_file(archive),archived_member_hashes=expected,
                all_other_game_bytes_recoverable_from_exact_unchanged_baseline=True,
                reason='Rejected before promotion: unknown foreign XI treated as bench; known-star calibration regression',
                existing_playable_games_untouched=True))
            if locator.exists():locator.unlink()
            shutil.rmtree(workspace)
            ledger.append(dict(receipt=registry.relative_workspace_path(receipt),archive=registry.relative_workspace_path(archive),
                deleted_rejected_buffer=registry.relative_workspace_path(workspace),recoverable=True))
    # Include any already safely archived/retired rows from a prior bounded
    # pass that stopped at a still-active transport.
    ledger=[]
    for path in sorted(archive_root.glob('*-receipt.json')):
        receipt=pipeline.read_json_file(path)
        if (registry.ROOT/receipt['workspace']).exists():continue
        archive=registry.ROOT/receipt['archive']
        if registry.sha256_file(archive)!=receipt['archive_sha256']:raise ValueError('retained recovery archive differs')
        ledger.append(dict(receipt=registry.relative_workspace_path(path),archive=receipt['archive'],
            deleted_rejected_buffer=receipt['workspace'],recoverable=True))
    retained(ROOT/'rejected-trial-retirement-ledger.json',ledger)
    print(dict(rejected_buffers_retired=len(ledger),all_current26_games_preserved=True,archived_and_hash_verified=True),flush=True)

if __name__=='__main__':run()
