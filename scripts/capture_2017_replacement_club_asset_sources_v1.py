"""Retain original dated sources for the unregistered 2017 club transaction."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.capture_ntf_historical_carrier_squads_v1 import Cache
from scripts import season_pipeline_v2 as pipeline

SOURCES = {
    'guiseley-2017-opener.html': 'https://chadwickmedia.wordpress.com/2017/08/07/guiseley-afc-v-ebbsfleet-united/',
    'guiseley-2017-opener-95.jpg': 'https://chadwickmedia.wordpress.com/wp-content/uploads/2017/08/95.jpg',
    'wrexham-kit-history.html': 'https://www.historicalkits.co.uk/Wrexham/Wrexham.htm',
    'wrexham-2017-home.gif': 'https://www.historicalkits.co.uk/Wrexham/images/wrexham_2017-2018-1st.gif',
    'chester-2017-home-shirt.html': 'https://www.oldfootballshirts.com/en/teams/c/chester-fc/old-chester-fc-football-shirt-s89353.html',
    'chester-2017-home-match.html': 'https://www.wrexhamafcarchive.co.uk/matchdetails.php?id=169',
}


def capture():
    root = ROOT / '.local/consolidated-audit-20261009/boreham-retirement-pair-assets-v1/source-cache'
    def one(item):
        name, url = item
        cache = Cache(root, offline=False, delay=1, stop_on_http_block=True)
        try:
            cache.get(url, name)
            return {'status': 'captured', **cache.used[0]}
        except Exception as exc:
            return {'status': 'gap', 'url': url, 'cache_path': name, 'reason': str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(one, SOURCES.items()))
    output = root / 'replacement-2017-source-captures-v1.json'
    if output.exists():
        raise ValueError('capture receipt is immutable')
    pipeline.write_canonical_json(output, {'sources': rows, 'native_writes': 0})
    for row in rows:
        print(row, flush=True)


if __name__ == '__main__':
    capture()
