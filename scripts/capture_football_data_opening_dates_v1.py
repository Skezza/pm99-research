#!/usr/bin/env python3
"""Capture bounded original season results; no recipe/native game changes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_football_data_opening_dates_v1 as dates
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes


def capture(season, code, cache):
    url = 'https://www.football-data.co.uk/mmz4281/' + season[2:4] + season[-2:] + '/' + code + '.csv'
    dates.validate_url(url, season, code)
    key = hashlib.sha256(url.encode()).hexdigest()
    path, receipt = cache / (key + '.csv'), cache / (key + '.source.json')
    if path.exists():
        raw = path.read_bytes()
        original = json.loads(receipt.read_text())
        dates.validate_url(original['response_url'], season, code)
        if original['requested_url'] != url or original['sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('original league result URL/hash changed')
        reused = True
    else:
        if receipt.exists():
            raise ValueError('original result receipt lacks its CSV')
        with urlopen(Request(url, headers={'User-Agent': 'PM99 historical football research'}), timeout=25) as response:
            response_url = response.geturl()
            dates.validate_url(response_url, season, code)
            raw = response.read(2 * 1024 * 1024 + 1)
        if not 1000 <= len(raw) <= 2 * 1024 * 1024:
            raise ValueError('original league results are truncated or oversized')
        original = {'requested_url': url, 'response_url': response_url, 'sha256': hashlib.sha256(raw).hexdigest()}
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, original)
        time.sleep(1)
        reused = False
    matches = dates.parse(raw, season, code)
    return {'season': season, 'competition': code, 'matches': len(matches),
        'clubs': len({r[k] for r in matches for k in ('home', 'away')}),
        'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path),
        'receipt_path': registry.relative_workspace_path(receipt), 'original_urls': original,
        'reused': reused, 'source_scope': 'first played league dates only; no player ownership or XI approval'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--competition', choices=sorted(dates.CODES), required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.season, args.competition, args.cache)), flush=True)
