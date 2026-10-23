"""Versioned exact-page evidence for original-carrier club-label restoration.

This does not edit or replace V1. It wraps V1's unchanged evidence readers
only after binding each raw page to an exact canonical URL and actual h1.
V1's prepare code runs with a private globals dictionary: no V1 module global
is temporarily replaced, so concurrent callers cannot observe this policy.
"""
from types import FunctionType
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import season_original_carrier_label_restoration_v1 as v1

SCHEMA = 'pm99-unanimous-source-original-carrier-label-restoration-v2-exact-page'
BASE_COACH, BASE_GROUND = v1.coach, v1.ground
EXPECTED = {
    'coach': {
        'url': 'https://en.wikipedia.org/wiki/Terry_Brown_(football_manager)',
        'title': 'Terry Brown (football manager)',
        'native': 'Terry Brown',
    },
    'ground': {
        'url': 'https://en.wikipedia.org/wiki/Church_Road_(football_stadium)',
        'title': 'Church Road (football stadium)',
        'native': 'Church Road',
    },
}


def _qualified_reader(kind, binding, native_name, club, year):
    expected = EXPECTED[kind]
    if binding.get('url') != expected['url'] or native_name != expected['native']:
        raise ValueError('source URL/native-name pair is not the exact reviewed disambiguation')
    body_path = _workspace_file(binding.get('path'), 'raw source body')
    receipt_path = _workspace_file(binding.get('source_receipt_path'), 'source receipt')
    if v1.registry.sha256_file(receipt_path) != binding['source_receipt_sha256']:
        raise ValueError('source capture receipt changed')
    receipt = v1.pipeline.read_json_file(receipt_path)
    if (receipt.get('schema') != 'pm99-original-source-capture-receipt-v1'
            or receipt.get('status') != 'original-captured'
            or receipt.get('url') != expected['url']
            or receipt.get('requested_url') != expected['url']
            or receipt.get('sha256') != binding['sha256']
            or receipt.get('raw_body_path') != binding['path']):
        raise ValueError('receipt does not bind the exact canonical URL and original body')
    raw = body_path.read_bytes()
    if v1.registry.sha256_file(body_path) != binding['sha256']:
        raise ValueError('raw source body changed')
    _require_page_identity(raw, expected)
    if kind == 'coach':
        return BASE_COACH(raw, expected['title'], club, year)
    return BASE_GROUND(raw, expected['title'], club, year)


def _require_page_identity(raw, expected):
    page = BeautifulSoup(raw, 'lxml')
    canonical_links = page.select('link[rel~=canonical]')
    canonical_urls = [link.get('href') for link in canonical_links]
    if canonical_urls != [expected['url']]:
        raise ValueError('raw HTML canonical URL is missing, duplicated, or not the exact reviewed URL')
    headings = [h.get_text(' ', strip=True) for h in page.select('h1#firstHeading')]
    if headings != [expected['title']]:
        raise ValueError('actual page heading differs from exact reviewed title')
    return True


def _workspace_file(value, label):
    if (not isinstance(value, str) or not value or Path(value).is_absolute()
            or '..' in Path(value).parts):
        raise ValueError(label + ' path must be a canonical workspace-relative path')
    unresolved = v1.registry.ROOT / value
    if unresolved.is_symlink():
        raise ValueError(label + ' path must not be a symlink')
    path = v1.registry._workspace_path(value, label=label)
    if v1.registry.relative_workspace_path(path) != value or not path.is_file():
        raise ValueError(label + ' path is not a canonical workspace file')
    return path


def prepare(base, targets, source_inputs):
    # V1 reads these bindings later, so validate before invoking it to ensure
    # no untrusted absolute/escaping path is opened even transiently.
    for key in ('coach', 'ground'):
        binding = source_inputs[key]
        _workspace_file(binding.get('path'), key + ' raw source body')
        _workspace_file(binding.get('source_receipt_path'), key + ' source receipt')
    scoped_globals = dict(v1.prepare.__globals__)
    scoped_globals['coach'] = lambda raw, name, club, year: _qualified_reader(
        'coach', source_inputs['coach'], name, club, year)
    scoped_globals['ground'] = lambda raw, name, club, year: _qualified_reader(
        'ground', source_inputs['ground'], name, club, year)
    scoped_prepare = FunctionType(v1.prepare.__code__, scoped_globals,
                                  name='prepare_exact_page_scoped',
                                  argdefs=v1.prepare.__defaults__,
                                  closure=v1.prepare.__closure__)
    plan = scoped_prepare(base, targets, source_inputs)
    plan['schema_version'] = SCHEMA
    plan['implementation_inputs'].append(v1.bind(Path(__file__)))
    plan['transaction_id'] = v1.pipeline.canonical_json_sha256(
        {k: value for k, value in plan.items() if k != 'transaction_id'})[:24]
    return plan


def verify(base, plan):
    if plan.get('schema_version') != SCHEMA or prepare(
            base, plan['targets'], plan['source_inputs']) != plan:
        raise ValueError('exact-page original carrier label restoration does not reproduce')
