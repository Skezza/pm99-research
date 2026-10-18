#!/usr/bin/env python3
"""Validate or launch one preferred post-1999 playable season candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
REQUIRED = registry.REQUIRED_GAME_FILES
ORIGINAL_RELEASE = "legacy-world-2015-16"


def load_original_release():
    retained = json.loads((ROOT / 'data/retained-season-releases-v1.json').read_text())
    rows = [row for row in retained['releases']
            if (row['season'], row['release_id']) == ('2015-16', ORIGINAL_RELEASE)]
    if len(rows) != 1:
        raise ValueError('original backup is not uniquely recorded in the retention ledger')
    row = rows[0]
    path = registry.locator_path('2015-16', ORIGINAL_RELEASE)
    if (registry.relative_workspace_path(path) != row['locator_path'] or
            registry.sha256_file(path) != row['locator_sha256']):
        raise ValueError('original backup locator differs from the retention ledger')
    release = registry.load_registered_release('2015-16', ORIGINAL_RELEASE)
    if registry.sha256_file(release.inventory_path) != row['inventory_sha256']:
        raise ValueError('original backup inventory differs from the retention ledger')
    return release


def original_session_game(release):
    """Use a normal copy, never mutable hardlinks into the original backup."""
    from scripts.season_playtest_variant_v1 import _copy_game_tree
    target = ROOT / '.local/season-play-sessions-v1/2015-16-original/game'
    if not target.exists():
        inventory = pipeline.read_json_file(release.inventory_path)
        pipeline.assert_tree_matches_inventory(release.game_path, inventory)
        _copy_game_tree(release.game_path, target)
        pipeline.assert_tree_matches_inventory(target, inventory)
    elif target.is_symlink() or not target.is_dir():
        raise ValueError('original play session is not a safe directory')
    for name, digest in release.locator['required_file_hashes'].items():
        path = target / name
        if not path.is_file() or registry.sha256_file(path) != digest:
            raise ValueError('original play session database/assets changed: ' + name)
        if path.stat().st_ino == (release.game_path / name).stat().st_ino:
            raise ValueError('original play session must not share writable backup inodes')
    return target

# Transitional compatibility for older orchestration helpers.  The mapping is
# derived from the authoritative release catalogue instead of maintaining a
# second hard-coded season/revision table.
class _PreferredRevisions(Mapping[str, str]):
    """Read legacy revision bindings only when an old helper requests them.

    Importing pure QA/capture code must not require 26 installed games. Actual
    lookup still fails closed when local registration is absent or invalid.
    The first requested snapshot remains stable for the process, like the old
    eager dictionary, without its import-time local-data dependency.
    """

    @cached_property
    def _snapshot(self) -> dict[str, str]:
        result = {}
        for season in registry.supported_seasons():
            if season == "2015-16":
                continue
            revision = registry.load_preferred_release(season).revision
            if revision is not None:
                result[season] = revision
        return result

    def __getitem__(self, key: str) -> str:
        return self._snapshot[key]

    def __iter__(self):
        return iter(self._snapshot)

    def __len__(self) -> int:
        return len(self._snapshot)


REVISIONS = _PreferredRevisions()


def game_path(season: str) -> Path:
    return registry.load_preferred_release(season).game_path


def validate(season: str, *, level: str = "playable") -> dict[str, object]:
    return registry.validate_preferred_release(season, level=level)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="YYYY-YY or all with --check")
    parser.add_argument("--check", action="store_true", help="validate the registered release without launching")
    parser.add_argument("--level", choices=("playable", "release"), default="release")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--original", action="store_true",
                        help="play the retained original 2015/16 in a separate writable session")
    args = parser.parse_args()
    if args.original and args.season != '2015-16':
        parser.error('--original is only available for 2015-16')
    seasons = registry.supported_seasons() if args.season == "all" else [args.season]
    if any(not re.fullmatch(r"20\d{2}-\d{2}", season) for season in seasons):
        parser.error("season must be YYYY-YY or all")
    check_level = args.level if args.check or args.season == "all" else "playable"
    if not args.original and not args.check and not args.print_command and args.season != "all":
        from scripts.season_visual_patch_v1 import ensure_playable_patch
        try:
            patch_result = ensure_playable_patch(args.season)
        except (OSError, ValueError) as exc:
            parser.error("could not apply the retained portrait fix safely: " + str(exc))
        if patch_result and patch_result.get("status") != "already-applied":
            print("Applied the retained portrait corrections; the original release is unchanged.", file=sys.stderr)
    if args.original:
        release = load_original_release()
        # This historic backup predates canonical release/runtime attestations.
        # Do not present it as a modern QA pass; verify its saved full inventory.
        result = registry.validate_preferred_release(args.season, level='playable', release_id=ORIGINAL_RELEASE)
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        results = [result]
    else:
        results = [validate(season, level=check_level) for season in sorted(seasons)]
    if args.check or args.season == "all":
        print(json.dumps({"valid": all(row["valid"] for row in results), "seasons": results}, indent=2, sort_keys=True))
        return 0 if all(row["valid"] for row in results) else 1
    result = results[0]
    if not result["valid"]:
        parser.error("candidate is incomplete: " + ", ".join(result["missing"]))
    if args.original and args.print_command:
        print(shlex.join([str(ROOT / 'pm99-season'), 'play', args.season, '--original']))
        return 0
    game = (original_session_game(release) if args.original else game_path(args.season)).resolve()
    command = ["wine", "./MANAGPRE.EXE"]
    if args.print_command:
        print(f"cd {shlex.quote(str(game))} && {shlex.join(command)}")
        return 0
    os.chdir(game)
    os.execvp(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
