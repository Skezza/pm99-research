"""Capture bounded original period-shirt evidence; never change a game."""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

OUTPUT = registry.ROOT / '.local/consolidated-audit-20261009/italian-kit-corrections-v1/source-cache'
SOURCES = {
    'palermo-2005': ('https://www.mondorosanero.it/palermo200506.HTM',
        ['stagione%202005-06/palermo06%20corini%20vs.%20Juventus.JPG',
         'stagione%202005-06/Corini%20vs.Juventus%20picture.jpg']),
    'atalanta-2006': ('https://www.le7sorelle.it/en/products/maglia-home-atalanta-asics-ml-2006-2007',
        ['//www.le7sorelle.it/cdn/shop/files/asics-maglia-home-atalanta-asics-ml-20062007-50115-home.jpg?v=1762979712&width=640']),
}


def capture(url, path):
    receipt = path.with_name(path.name + '.source.json')
    if path.exists():
        if pipeline.read_json_file(receipt) != dict(url=url, sha256=registry.sha256_file(path)):
            raise ValueError('retained original capture differs')
        return
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if len(response.content) > 8 * 1024**2:
        raise ValueError('source exceeds bounded capture budget')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    pipeline.write_canonical_json(receipt, dict(url=url, sha256=registry.sha256_file(path)))


def main():
    for name, (url, images) in SOURCES.items():
        page = OUTPUT / (name + '.html')
        capture(url, page)
        soup = BeautifulSoup(page.read_bytes(), 'html.parser')
        actual = {urljoin(url, image.get('src', '')) for image in soup.find_all('img')}
        for number, src in enumerate(images, 1):
            source = urljoin(url, src)
            if source not in actual:
                raise ValueError('original period page does not link selected photograph')
            capture(source, OUTPUT / f'{name}-{number}.jpg')
        print(dict(source=name, captured=True, reviewed=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
