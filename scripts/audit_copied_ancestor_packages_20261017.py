"""Measure duplicate copied ancestor JSONs; read-only, no links/deletions.

The existing SOURCE sharing covers the current recipe/JUG/MINIFOTO, but may
leave identical inherited English source-package copies in every workspace.
Scope only two years initially; never walk native game/ trees.
"""
from collections import Counter, defaultdict
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/cleanup-20261017/duplicated-ancestor-packages'


def main():
    output=ROOT/'two-season-readonly-audit.json'
    if output.exists():raise ValueError('completed metadata storage audit must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[];hashed={}
    for season in ('2016-17','2017-18'):
        folder=registry.ROOT/'.local/historical-role-deltas-v1'/season
        for workspace in sorted(folder.iterdir()):
            if not workspace.is_dir() or workspace.is_symlink():continue
            path=workspace/'english-season-package.json'
            if not path.is_file() or path.is_symlink():continue
            info=path.stat();inode=(info.st_dev,info.st_ino)
            if inode not in hashed:hashed[inode]=registry.sha256_file(path)
            after=path.stat()
            if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise ValueError('ancestor package changed during read-only storage audit')
            rows.append(dict(path=registry.relative_workspace_path(path),season=season,sha256=hashed[inode],
                device=info.st_dev,inode=info.st_ino,size=info.st_size,allocated=info.st_blocks*512,
                links=info.st_nlink,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,mtime_ns=info.st_mtime_ns))
    groups=defaultdict(list)
    for row in rows:
        groups[(row['sha256'],row['size'],row['mode'],row['uid'],row['gid'],row['mtime_ns'])].append(row)
    candidates=[];recoverable=0
    for key,items in groups.items():
        inodes=Counter((r['device'],r['inode']) for r in items)
        unique={ (r['device'],r['inode']):r for r in items }
        if len(unique)<2:continue
        canonical=max(unique,key=lambda i:(unique[i]['links'],unique[i]['path']))
        eligible=[i for i in unique if i!=canonical and unique[i]['links']==inodes[i]]
        amount=sum(unique[i]['allocated'] for i in eligible)
        recoverable+=amount
        candidates.append(dict(sha256=key[0],canonical_candidate=unique[canonical]['path'],
            copied_paths=[r['path'] for r in items],distinct_inodes=len(unique),
            allocated_bytes_potentially_recoverable=amount,
            metadata_identical=True))
    retained(output,dict(rows=rows,groups=candidates,potential_allocated_bytes=recoverable,
        scope='Exact copied ancestor english-season-package.json in2016/2017 workspaces ONLY.',
        files_changed=0,hardlinks_created=0,deleted_paths=[],
        caution='Audit only. Require locator/source-role checks, inactive-writer checks and fresh hashes before any sharing. Never treat merely same-sized JSON as identical.'))
    print(dict(files_measured=len(rows),distinct_inode_hashes=len(hashed),duplicate_groups=len(candidates),
        potential_allocated_bytes=recoverable,files_changed=0),flush=True)


if __name__=='__main__':main()
