"""Capture only photographs explicitly linked by retained 2004 retrospectives.

No image transformations or source approval. Original bytes/URL receipts stay
local, with bounded downloads and without refetching an existing photograph.
"""
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.prepare_ofk_2004_source_allocation_v1 import original, AUDIT
from scripts.season_art_transaction_v1 import atomic_bytes

SOURCES = {
    'ofk-2004-intertoto-official-retrospective': [
        'https://ofkbeograd.com/wp-content/uploads/2024/07/1A_0038.jpg'],
    'ofk-2004-intertoto-mondo-retrospective': [
        'https://static2.mondo.rs/api/v3/images/592/1184/1412983?ts=2024-07-27T23:08:14',
        'https://static2.mondo.rs/api/v3/images/592/1184/1412912?ts=2024-07-27T16:19:48',
        'https://static2.mondo.rs/api/v3/images/592/1184/1413143?ts=2024-07-27T23:40:28'],
}


def main(*, sources=None, directory=None):
    for key, images in (SOURCES if sources is None else sources).items():
        raw, binding = original(key)
        page = BeautifulSoup(raw, 'html.parser')
        links = {i.get('src') for i in page.find_all('img')} | {
            i.get('content') for i in page.select('meta[property="og:image"]')}
        for n, url in enumerate(images, 1):
            if url not in links:
                raise ValueError('selected photograph is absent from the retained original period article')
            path = (AUDIT / 'ofk-2004-kit-originals' if directory is None else directory) / f'{key}-{n}.jpg'
            receipt = path.with_name(path.name + '.source.json')
            if path.exists():
                if pipeline.read_json_file(receipt) != dict(url=url, sha256=registry.sha256_file(path)):
                    raise ValueError('retained photograph URL/hash changed')
                continue
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                if response.geturl() != url: raise ValueError('original photograph redirected')
                payload = response.read(2 * 1024**2 + 1)
            if len(payload) > 2 * 1024**2: raise ValueError('photograph exceeds bounded source budget')
            if not payload.startswith((b'\xff\xd8', b'\x89PNG')):
                raise ValueError('original photograph is not a JPEG/PNG')
            atomic_bytes(path, payload)
            pipeline.write_canonical_json(receipt, dict(url=url, sha256=registry.sha256_file(path)))
            print(dict(source=key, image=n, captured=True, reviewed=False), flush=True)


if __name__ == '__main__': main()
