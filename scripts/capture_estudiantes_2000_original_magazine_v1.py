"""Bounded capture of the original CONMEBOL magazine, not scraped summaries."""
from datetime import UTC,datetime
from urllib.request import Request,urlopen
import shutil
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes

URL='https://www.spfcpedia.com.br/ebooks/2021-05-08_revista-conmebol_066.pdf'
ROOT=registry.ROOT/'.local/consolidated-audit-20261009/stock-club-history-v1'


def capture():
    path=ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf'
    receipt=path.with_suffix('.source.json')
    if path.exists():
        previous=pipeline.read_json_file(receipt)
        if previous['url']!=URL or previous['sha256']!=registry.sha256_file(path):
            raise ValueError('retained original magazine differs')
        return path
    if shutil.disk_usage(ROOT).free<8*1024**3+32*1024**2:
        raise ValueError('capture would cross8GiB reserve')
    with urlopen(Request(URL,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as response:
        if response.geturl()!=URL:raise ValueError('magazine redirected to another source')
        raw=response.read(32*1024**2+1)
    if not raw.startswith(b'%PDF-') or len(raw)>32*1024**2:
        raise ValueError('original magazine is not PDF or exceeds32MiB bound')
    atomic_bytes(path,raw)
    pipeline.write_canonical_json(receipt,dict(url=URL,sha256=registry.sha256_file(path),
        bytes=len(raw),utc=datetime.now(UTC).isoformat(),
        provider='Original CONMEBOL magazine66 publicly archived by SPFCpedia',
        historical_XI_verified=False,native_writes=0,
        scope='Original bytes only; locate and inspect the dated match pages before roster use.'))
    return path


if __name__=='__main__':print(capture(),flush=True)
