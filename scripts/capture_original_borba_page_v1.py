"""Retain a bounded original newspaper scan linked by its public page form.

OCR can misspell names; inspect the original scan before expanding a published
short label. No invented source body, authentication or native writes.
"""
import re
import shutil
from datetime import date
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def original_download_url(raw):
    """Reject generated navigation pages outside the actual newspaper issue."""
    page=BeautifulSoup(raw,'html.parser')
    forms=page.select('form#download-jpg')
    if len(forms)!=1 or forms[0].get('method')!='post':
        raise ValueError('original public JPG form missing or ambiguous')
    url=forms[0].get('action','')
    match=re.fullmatch(r'https://pretraziva\.rs/download/borba--(\d{4}-\d{2}-\d{2})--(\d{1,2})\.jpg',url)
    if not match:
        raise ValueError('unexpected original newspaper download endpoint')
    issue=date.fromisoformat(match[1])
    number=int(match[2])
    limits=re.findall(r'\blastPage\s*=\s*(\d+)\s*;',raw.decode('utf-8'))
    if len(limits)!=1 or not 1<=number<=int(limits[0]):
        raise ValueError('requested page is outside the original issue or has ambiguous bounds')
    title=page.title.get_text(' ',strip=True) if page.title else ''
    expected=f'Borba, {issue:%d. %m. %Y.}, S. {number} —'
    if not title.startswith(expected):
        raise ValueError('original issue title does not match download date and page')
    return url


def capture(key):
    _,raw,binding=source_rows(key)
    url=original_download_url(raw)
    destination=ROOT.parent/'borba-original-scans'/f'{key}.jpg'
    receipt=destination.with_name(destination.name+'.source.json')
    if destination.exists():
        previous=pipeline.read_json_file(receipt)
        if (previous['source_binding']!=binding or previous['url']!=url
                or previous['sha256']!=registry.sha256_file(destination)):
            raise ValueError('retained original page source changed')
        return destination
    if shutil.disk_usage(ROOT).free<8*1024**3+5*1024**2:
        raise ValueError('original page capture would cross8GiB reserve')
    with urlopen(Request(url,method='POST',data=b'',headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:
        if response.geturl()!=url:
            raise ValueError('original public scan redirected to another endpoint')
        payload=response.read(5*1024**2+1)
    if len(payload)>5*1024**2 or not payload.startswith(b'\xff\xd8'):
        raise ValueError('original scan exceeds5MiB or is not a JPEG')
    atomic_bytes(destination,payload)
    pipeline.write_canonical_json(receipt,dict(url=url,sha256=registry.sha256_file(destination),source_binding=binding,
        method='POST-public-original-download-form',bytes=len(payload),reviewed=False,native_writes=0))
    return destination
