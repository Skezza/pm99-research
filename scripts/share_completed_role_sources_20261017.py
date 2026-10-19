"""Share old equal role SOURCE copies, retaining every original/recovery path."""
from datetime import UTC, datetime
import re
import shutil

from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts.archive_completed_arsenal_replays_20261016 import assert_equal_games, active
from scripts.share_verified_r70_source_copies_20261016 import share_identical
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT/'.local/cleanup-20261017/shared-completed-role-SOURCE-copies'


def main(*, min_revision=100, max_revision=116, selected_replays=None):
    if (type(min_revision) is not int or type(max_revision) is not int
            or not 1 <= min_revision <= max_revision):
        raise ValueError('explicit bounded completed revision range required')
    if selected_replays is not None:
        selected_replays = frozenset(selected_replays)
        if not selected_replays or any(not isinstance(row, tuple) or len(row) != 2
                                       for row in selected_replays):
            raise ValueError('explicit nonempty season/replay pairs required')
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT/'completed.json').exists():
        raise ValueError('completed sharing must not repeat')
    catalog = registry.sha256_file(registry.CATALOG_PATH)
    before = shutil.disk_usage(registry.ROOT).free
    targets = []
    selected_found = set()
    for season in registry.supported_seasons():
        folder = registry.locator_path(season,'unused').parent.parent
        for path in sorted(folder.glob('replayed-*/locator.json')):
            rid=path.parent.name;match=re.search(r'-r([0-9]+)b$',rid)
            if match is None or not min_revision<=int(match[1])<=max_revision:
                continue
            if selected_replays is not None and (season, rid) not in selected_replays:
                continue
            selected_found.add((season, rid))
            actual_id=rid.replace('replayed-','sourced-',1)[:-1]+'a'
            if not registry.locator_path(season,actual_id).exists():
                if selected_replays is not None:
                    raise ValueError('explicit replay has no registered actual counterpart')
                continue
            if registry.load_preferred_release(season).release_id in (actual_id,rid):
                if selected_replays is not None:
                    raise ValueError('explicit replay or actual counterpart is preferred')
                continue
            base=registry.load_registered_release(season,actual_id)
            replay=registry.load_registered_release(season,rid)
            if (replay.game_path!=registry.ROOT/'.local/historical-role-deltas-v1'/season/rid/'game'
                    or active(base.game_path.parent) or active(replay.game_path.parent)):
                raise ValueError('unexpected or active old role SOURCE scope')
            pairs=((base.package_path,replay.package_path),
                (base.game_path/'DBDAT/JUG98030.FDI',replay.game_path/'DBDAT/JUG98030.FDI'))
            if all(a.stat().st_ino==b.stat().st_ino for a,b in pairs):
                if selected_replays is not None:
                    raise ValueError('explicit replay files already shared; reuse prior ledger instead')
                continue
            targets.append((season,actual_id,rid,base,replay,pairs))
    if selected_replays is not None and selected_found != selected_replays:
        raise ValueError('one or more explicitly selected replay registrations absent or out of range')
    retained(ROOT/'analysis.json',dict(utc=datetime.now(UTC).isoformat(),catalog_sha256=catalog,
        revision_range=[min_revision,max_revision],
        selected_replays=sorted(selected_replays) if selected_replays is not None else None,
        targets=[dict(season=s,actual_release=a,replay_release=r) for s,a,r,*_ in targets],removed_paths=[]))
    rows=[]
    for season,actual_id,rid,base,replay,pairs in targets:
        ledger=ROOT/(season+'-'+rid+'.json')
        if ledger.exists():
            raise ValueError('partial sharing ledger exists; inspect instead of repeating')
        assert_equal_games(base,replay)
        shared=[share_identical(a,b) for a,b in pairs]
        assert_equal_games(base,replay)
        if registry.sha256_file(registry.CATALOG_PATH)!=catalog:
            raise ValueError('catalog advanced; preserve ledger and inspect')
        retained(ledger,dict(season=season,actual_release=actual_id,replay_release=rid,
            shared_files=shared,complete_games_and_recipes_equal_before_and_after=True,removed_paths=[],
            policy='All bytes/paths/recovery data retained; future writes use atomic replacement, never in-place changes.'))
        rows.append(dict(path=registry.relative_workspace_path(ledger),sha256=registry.sha256_file(ledger)))
        print(dict(season=season,replay=rid,
            recovered_allocated_bytes=sum(r['former_unique_allocated_bytes'] for r in shared)),flush=True)
    retained(ROOT/'completed.json',dict(utc=datetime.now(UTC).isoformat(),rows=rows,before_free_bytes=before,
        after_free_bytes=shutil.disk_usage(registry.ROOT).free,catalog_sha256=catalog,current26_unchanged=True,
        removed_paths=[],machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))


if __name__=='__main__':
    main()
