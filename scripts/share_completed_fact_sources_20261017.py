"""Free duplicate SOURCE storage; preserve every file and recovery path.

Only older, nonpreferred registered fact-correction replays r79..r99. Whole
game inventories and recipe bytes must agree before and after exact sharing.
"""
from datetime import UTC,datetime
from pathlib import Path
import re
import shutil
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.archive_completed_arsenal_replays_20261016 import assert_equal_games,active
from scripts.share_verified_r70_source_copies_20261016 import share_identical
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/cleanup-20261017/shared-completed-fact-SOURCE-copies'


def main():
    if (ROOT/'completed.json').exists():raise ValueError('completed sharing must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True)
    catalog=registry.sha256_file(registry.CATALOG_PATH);free=shutil.disk_usage(registry.ROOT).free
    targets=[]
    for season in registry.supported_seasons():
        folder=registry.locator_path(season,'unused').parent.parent
        for path in sorted(folder.glob('replayed-*/locator.json')):
            rid=path.parent.name;match=re.search(r'-r([0-9]+)b$',rid)
            if match is None or not 79<=int(match[1])<=99:continue
            actual_id=rid.replace('replayed-','sourced-',1)[:-1]+'a'
            if not registry.locator_path(season,actual_id).exists():continue
            base=registry.load_registered_release(season,actual_id);replay=registry.load_registered_release(season,rid)
            if (replay.game_path!=registry.ROOT/'.local/historical-role-deltas-v1'/season/rid/'game'
                    or registry.load_preferred_release(season).release_id in (actual_id,rid)
                    or active(base.game_path.parent) or active(replay.game_path.parent)):
                raise ValueError('unsafe/active/preferred old SOURCE sharing scope')
            pairs=((base.package_path,replay.package_path),
                (base.game_path/'DBDAT/JUG98030.FDI',replay.game_path/'DBDAT/JUG98030.FDI'))
            if all(a.stat().st_ino==b.stat().st_ino for a,b in pairs):continue
            targets.append((season,actual_id,rid,base,replay,pairs))
    retained(ROOT/'analysis.json',dict(utc=datetime.now(UTC).isoformat(),catalog_sha256=catalog,
        targets=[dict(season=s,actual_release=a,replay_release=r) for s,a,r,*_ in targets],
        before_free_bytes=free,removed_paths=[]))
    rows=[]
    for season,actual_id,rid,base,replay,pairs in targets:
        ledger=ROOT/(season+'-'+rid+'.json')
        if ledger.exists():raise ValueError('partial sharing ledger exists; inspect instead of repeating')
        assert_equal_games(base,replay)
        shared=[share_identical(a,b) for a,b in pairs]
        assert_equal_games(base,replay)
        if registry.sha256_file(registry.CATALOG_PATH)!=catalog:raise ValueError('preferred catalog advanced during sharing; inspect retained ledger')
        retained(ledger,dict(season=season,actual_release=actual_id,replay_release=rid,shared_files=shared,
            complete_games_and_recipes_equal_before_and_after=True,removed_paths=[],
            recovery='All original and replay files remain byte-identical at the same paths. Future immutable-file edits must use atomic replacement, never in-place writes.'))
        rows.append(dict(path=registry.relative_workspace_path(ledger),sha256=registry.sha256_file(ledger)))
        print(dict(season=season,replay=rid,former_unique_allocated_bytes=sum(r['former_unique_allocated_bytes'] for r in shared)),flush=True)
    retained(ROOT/'completed.json',dict(utc=datetime.now(UTC).isoformat(),rows=rows,
        before_free_bytes=free,after_free_bytes=shutil.disk_usage(registry.ROOT).free,
        preferred_catalog_sha256=catalog,current26_unchanged=True,removed_paths=[],
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))


if __name__=='__main__':main()
