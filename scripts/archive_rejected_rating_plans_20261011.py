"""Compress this turn's26 rejected v2 plans, keeping exact recovery hashes."""
import hashlib
import tarfile
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.archive_rejected_rating_trial_20261011 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def main():
    targets=[ROOT/row['season']/'quality-plan.json' for row in pipeline.read_json_file(ROOT/'pinned-baselines.json')]
    if any(not path.is_file() or path.is_symlink() for path in targets):raise ValueError('exact26 rejected plans required')
    for path in targets:
        plan=pipeline.read_json_file(path)
        if plan['kind']!='season-rating-calibration':raise ValueError('not a rejected v2 plan')
        if registry.load_preferred_release(plan['season']).release_id!=plan['release_id']:raise ValueError('preferred baseline changed')
    archive=ROOT/'rejected-recovery/rejected26-source-plans.tar.gz'
    expected={path.relative_to(ROOT).as_posix():registry.sha256_file(path) for path in targets}
    if not archive.exists():
        with tarfile.open(archive,'w:gz') as stream:
            for path in targets:stream.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
    with tarfile.open(archive,'r:gz') as stream:
        members=stream.getmembers()
        if {m.name for m in members}!=set(expected):raise ValueError('rejected source archive members differ')
        for member in members:
            if hashlib.file_digest(stream.extractfile(member),'sha256').hexdigest()!=expected[member.name]:raise ValueError('rejected source archive hash differs')
    retained(ROOT/'rejected-source-plan-archive-ledger.json',dict(archive=registry.relative_workspace_path(archive),
        archive_sha256=registry.sha256_file(archive),source_member_sha256=expected,
        reason='Rejected v2, superseded by v3; no preferred game ever used these plans',recoverable=True))
    for path in targets:path.unlink()
    print(dict(rejected_plans_archived=26,hash_verified=True,all_actual_playable_games_preserved=True),flush=True)

if __name__=='__main__':main()
