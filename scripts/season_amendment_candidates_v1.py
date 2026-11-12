"""Light registry of workbook-built editorial candidates (no heavy imports; shared by CLI and workbook)."""
import json
import os
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDS_ROOT = ROOT / '.local/season-amendment-builds-v1'
SCHEMA = 'pm99-editorial-candidates-v1'


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(_canonical(value))
    os.replace(temporary, path)


def list_candidates(season, builds_root=None):
    path = Path(builds_root or BUILDS_ROOT) / season / 'candidates.json'
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding='utf-8'))['candidates']


def record_candidate(season, entry, builds_root=None):
    root = Path(builds_root or BUILDS_ROOT)
    rows = [r for r in list_candidates(season, root) if r['release_id'] != entry['release_id']] + [entry]
    write_json(root / season / 'candidates.json', dict(schema=SCHEMA, season=season,
                                                         candidates=sorted(rows, key=lambda r: r['release_id'])))


def play_command(season, release_id):
    return shlex.join(['./pm99-season', 'play', season, '--release-id', release_id])
