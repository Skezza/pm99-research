"""Retain bounded original-linked photographs; no image or kit approval."""
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes

SOURCES = {
    'borac-2003-original-opening-club-news': 'https://partizan.net/news/images/borac0803.jpg',
    'borac-2003-original-opening-photographs-retrospective':
        'https://crnobelanostalgija.com/wp-content/uploads/2023/02/izvestaj-Partizan-Borac-C-6-1.jpg',
}


def capture():
    for key, url in SOURCES.items():
        _, raw, binding = source_rows(key)
        metadata = pipeline.read_json_file(ROOT / (key + '.source.json'))
        links = {urljoin(metadata['url'], img.get('src', ''))
                 for img in BeautifulSoup(raw, 'html.parser').select('img[src]')}
        if url not in links:
            raise ValueError('selected photograph is absent from retained original article')
        path = ROOT.parent / 'borac-2003-period-originals' / (key + '.jpg')
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = path.with_name(path.name + '.source.json')
        if receipt.exists() and not path.exists():
            retained = pipeline.read_json_file(receipt)
            if retained.get('status') != 'source-acquisition-gap' or retained.get('url') != url or retained.get('source_binding') != binding:
                raise ValueError('retained photograph gap receipt changed')
            continue
        if path.exists():
            if pipeline.read_json_file(receipt) != dict(url=url, sha256=registry.sha256_file(path), source_binding=binding):
                raise ValueError('retained original photograph or article binding changed')
            continue
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                if response.geturl() != url:
                    raise ValueError('selected original photograph redirected')
                raw = response.read(2 * 1024 ** 2 + 1)
            if len(raw) > 2 * 1024 ** 2 or not raw.startswith(b'\xff\xd8'):
                raise ValueError('original photograph exceeds bound or is not JPEG')
        except Exception as exc:
            pipeline.write_canonical_json(receipt, dict(url=url, status='source-acquisition-gap',
                reason=str(exc), source_binding=binding, visually_approved=False))
            print(dict(source=key, status='source-acquisition-gap'), flush=True)
            continue
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, dict(url=url, sha256=registry.sha256_file(path), source_binding=binding))
        print(dict(source=key, captured=True, visually_approved=False), flush=True)


if __name__ == '__main__':
    capture()
