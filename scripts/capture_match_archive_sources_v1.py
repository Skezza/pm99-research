#!/usr/bin/env python3
"""Capture bounded original 11v11 schedule/match/profile pages with receipts.

One ordinary public request per second, no challenge solving or retries.
These are original research inputs, not approved lineups or identity bridges.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def validate_url(url):
    value = urlparse(url)
    if (value.scheme != 'https' or value.netloc != 'www.11v11.com'
            or value.query or value.fragment or value.username or value.password
            or not value.path.startswith(('/teams/', '/matches/', '/players/'))):
        raise ValueError('only exact original public 11v11 archive URLs are supported')


def capture(url, cache):
    validate_url(url)
    key = hashlib.sha256(url.encode()).hexdigest()
    path, receipt = cache / (key + '.html'), cache / (key + '.source.json')
    if path.exists():
        raw = path.read_bytes()
        if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('original match archive URL/hash receipt changed')
        reused = True
    else:
        if receipt.exists():
            raise ValueError('original archive receipt exists but its source page is missing')
        with urlopen(Request(url, headers={'User-Agent': 'PM99 historical football research',
                'Accept-Language': 'en-GB'}), timeout=25) as response:
            if response.geturl() != url:
                raise ValueError('archive redirected to a different original identity')
            raw = response.read(2 * 1024 * 1024 + 1)
        sample = raw[:100000].decode('utf-8', errors='replace').casefold()
        if (not 1000 <= len(raw) <= 2 * 1024 * 1024 or '<h1' not in sample
                or any(marker in sample for marker in ('cf-chl-', 'just a moment...', 'captcha'))):
            raise ValueError('original archive is truncated, oversized or an access challenge')
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
        time.sleep(1)
        reused = False
    return {'url': url, 'path': registry.relative_workspace_path(path),
        'sha256': registry.sha256_file(path), 'receipt_path': registry.relative_workspace_path(receipt),
        'bytes': len(raw), 'reused': reused, 'approved_opening_source': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', action='append', required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    for url in args.url:
        print(json.dumps(capture(url, args.cache)), flush=True)
