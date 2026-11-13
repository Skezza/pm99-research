"""Shared exclusions for local research JSON; game/control data stays plain."""
from pathlib import Path

SKIP_DIRS = {'game', 'games', 'wine-prefix', '.git', 'node_modules', '__pycache__',
             'DBDAT', 'SIMULDAT', 'SFX', 'CURSORES', 'MINIFOTO'}
EXCLUDED_ROOTS = {'season-release-registry-v1', 'season-workspace-v1', 'season-play-sessions-v1',
                  'season-editorial-amendments-v1', 'season-amendment-builds-v1',
                  'json-compression-pilot-20261113', 'json-storage-rollout-20261113'}

def excluded(relative):
    parts=Path(relative).parts
    return (len(parts)<3 or parts[0]!='.local' or parts[1] in EXCLUDED_ROOTS
            or parts[1].startswith(('cleanup','claude','qa-','json-storage'))
            or Path(relative).name in {'current.json','working.json','candidates.json','locator.json'}
            or Path(relative).name.endswith('-current.json')
            or bool(SKIP_DIRS.intersection(parts)))

