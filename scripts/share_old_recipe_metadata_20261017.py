"""Deduplicate identical old nonpreferred recipe inputs, with every path kept.

Only first-level JSON metadata in registered historical role releases <=r116;
no game, image, current default, original2015, locator or source bytes change.
"""
from collections import defaultdict
from datetime import UTC, datetime
import re
import shutil

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.share_verified_r70_source_copies_20261016 import share_identical
from scripts.archive_rejected_role_trials_20261016 import active
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT/'.local/cleanup-20261017/shared-old-recipe-metadata'


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/'analysis.json').exists():
        raise ValueError('existing metadata sharing run needs inspection, not repetition')
    catalog=registry.sha256_file(registry.CATALOG_PATH)
    groups=defaultdict(list)
    for season in registry.supported_seasons():
        preferred=registry.load_preferred_release(season).release_id
        for path in (registry.locator_path(season,'unused').parent.parent).glob('*/locator.json'):
            rid=path.parent.name;version=re.search(r'-r([0-9]+)[ab]$',rid)
            if version is None or not 58<=int(version[1])<=116 or rid==preferred:
                continue
            release=registry.load_registered_release(season,rid)
            workspace=release.package_path.parent
            if workspace!=registry.ROOT/'.local/historical-role-deltas-v1'/season/rid or active(workspace):
                continue
            for item in workspace.glob('*.json'):
                if item.is_symlink() or not item.is_file() or item.stat().st_size<65536:
                    continue
                groups[(item.name,item.stat().st_size,registry.sha256_file(item))].append(item)
    targets=[]
    for key,paths in groups.items():
        unique={p.stat().st_ino:p for p in sorted(paths)}
        if len(unique)<2:
            continue
        paths=list(unique.values());original=paths[0]
        targets.extend((original,p) for p in paths[1:] if p.stat().st_nlink==1)
    retained(ROOT/'analysis.json',dict(utc=datetime.now(UTC).isoformat(),catalog_sha256=catalog,
        pairs=[dict(original=registry.relative_workspace_path(a),duplicate=registry.relative_workspace_path(b),
                    sha256=registry.sha256_file(a),bytes=b.stat().st_size) for a,b in targets],
        removed_paths=[],current_preferred_metadata_not_targeted=True))
    before=shutil.disk_usage(registry.ROOT).free
    rows=[]
    for number,(a,b) in enumerate(targets):
        row=share_identical(a,b)
        rows.append(row)
        retained(ROOT/f'shared-{number:04d}.json',row)
    if registry.sha256_file(registry.CATALOG_PATH)!=catalog:
        raise ValueError('catalog advanced; preserve partial ledger and inspect')
    retained(ROOT/'completed.json',dict(utc=datetime.now(UTC).isoformat(),rows=rows,
        recovered_unique_allocated_bytes=sum(r['former_unique_allocated_bytes'] for r in rows),
        before_free_bytes=before,after_free_bytes=shutil.disk_usage(registry.ROOT).free,
        catalog_sha256=catalog,removed_paths=[],all_original_metadata_hashes_and_paths_retained=True,
        immutable_updates_require_atomic_replacement=True,machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))
    print(dict(shared_files=len(rows),recovered_bytes=sum(r['former_unique_allocated_bytes'] for r in rows),
               removed_paths=0),flush=True)


if __name__=='__main__':
    main()
