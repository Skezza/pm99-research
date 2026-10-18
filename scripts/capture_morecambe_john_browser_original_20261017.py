"""Retain an ordinary browser-rendered original profile, never bypass access."""
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import tempfile

from bs4 import BeautifulSoup
from scripts import capture_stock_replacement_sources_20261010 as capture
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

KEY = 'morecambe2000-john-11v11-browser-rendered-original-v2'
URL = 'https://www.11v11.com/players/john-norman-9941/'
BROWSER = Path('/home/joe/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell')


def main():
    body = capture.ROOT / (KEY + '.html')
    receipt = capture.ROOT / (KEY + '.source.json')
    if receipt.exists() or body.exists():
        raise ValueError('existing browser source needs inspection, not repeated acquisition')
    row = dict(url=URL, utc=datetime.now(UTC).isoformat(), native_writes=0,
        transport='ordinary-local-Chromium-dump-dom',
        content_form='browser-rendered-publisher-DOM-not-original-network-bytes',
        target_identity_approved=False)
    try:
        with tempfile.TemporaryDirectory(prefix='pm99-john-public-browser-') as profile:
            result = subprocess.run([str(BROWSER), '--headless', '--no-sandbox',
                '--disable-gpu', '--disable-background-networking', '--disable-extensions',
                '--disk-cache-size=1', '--media-cache-size=1', '--user-data-dir=' + profile,
                '--dump-dom', '--timeout=22000', '--virtual-time-budget=2000', URL],
                capture_output=True, check=True, timeout=30)
        if not 1000 < len(result.stdout) <= 2 * 1024**2:
            raise ValueError('ordinary original profile DOM absent or unexpectedly large')
        page = BeautifulSoup(result.stdout, 'lxml')
        if [h.get_text(' ', strip=True) for h in page.select('h1')] != ['John Norman']:
            raise ValueError('ordinary browser returned an access page or another profile; no challenge bypass attempted')
        text = page.get_text(' ', strip=True)
        if not all(token in text for token in ('26 June 1971', 'Morecambe', '01 Mar 2000', '30 Jun 2002')):
            raise ValueError('complete original numerical person/date/club interval not present')
        atomic_bytes(body, result.stdout)
        row.update(status='original-browser-DOM-captured', bytes=len(result.stdout),
            sha256=capture.registry.sha256_file(body))
    except Exception as exc:
        row.update(status='source-acquisition-gap', reason=str(exc))
    retained(receipt, row)
    print(dict(key=KEY, status=row['status'], reason=row.get('reason')), flush=True)


if __name__ == '__main__':
    main()
