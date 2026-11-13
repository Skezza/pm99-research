"""Light registry of workbook-built editorial candidates (no heavy imports; shared by CLI and workbook)."""
try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import json
import os
import shlex
from pathlib import Path

ROOT = storage_io.resolve(Path(__file__)).parents[1]
BUILDS_ROOT = ROOT / '.local/season-amendment-builds-v1'
SCHEMA = 'pm99-editorial-candidates-v1'


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    storage_io.write_bytes(temporary, _canonical(value))
    storage_io.replace_file(temporary, path)


def list_candidates(season, builds_root=None):
    path = Path(builds_root or BUILDS_ROOT) / season / 'candidates.json'
    if not storage_io.is_file(path):
        return []
    return json.loads(storage_io.read_text(path, encoding='utf-8'))['candidates']


def record_candidate(season, entry, builds_root=None):
    root = Path(builds_root or BUILDS_ROOT)
    rows = [r for r in list_candidates(season, root) if r['release_id'] != entry['release_id']] + [entry]
    write_json(root / season / 'candidates.json', dict(schema=SCHEMA, season=season,
                                                         candidates=sorted(rows, key=lambda r: r['release_id'])))


def play_command(season, release_id):
    return shlex.join(['./pm99-season', 'play', season, '--release-id', release_id])
