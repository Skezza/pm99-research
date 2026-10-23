"""Portable exact-page guards and optional retained-source replay evidence."""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts import season_original_carrier_label_restoration_v1 as v1
from scripts import season_original_carrier_label_restoration_v2 as subject

ROOT = v1.registry.ROOT
PROPOSAL = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/hayes-label-v2-proposal-plan.json'
OLD_PLANS = (
    'original-carrier-label-restoration-20261017/2000-01/club-plan.json',
    'hertha2000-cohort-label-20261017/club-plan.json',
    'hertha2001-cohort-label-20261017/club-plan.json',
    'hertha-dated-cohort-coach-20261017/2002-03/club-plan.json',
    'hertha-dated-cohort-coach-20261017/2003-04/club-plan.json',
)


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setattr(v1.registry, 'ROOT', tmp_path)
    expected = subject.EXPECTED['coach']
    raw = (f'<html><head><link rel="canonical" href="{expected["url"]}"></head>'
           f'<h1 id="firstHeading">{expected["title"]}</h1><table class="infobox">'
           '<tr><th>Managerial career</th></tr>'
           '<tr><td>1993–2002</td><td><a>Hayes</a></td></tr></table></html>').encode()
    body = tmp_path / 'body.html'
    body.write_bytes(raw)
    receipt = tmp_path / 'receipt.json'
    receipt.write_bytes(v1.pipeline.canonical_json_bytes(dict(
        schema='pm99-original-source-capture-receipt-v1', status='original-captured',
        url=expected['url'], requested_url=expected['url'],
        sha256=v1.registry.sha256_file(body), raw_body_path='body.html')))
    binding = dict(path='body.html', sha256=v1.registry.sha256_file(body),
        source_receipt_path='receipt.json', source_receipt_sha256=v1.registry.sha256_file(receipt),
        url=expected['url'])
    return raw, binding


def test_exact_source_page_and_closed_spell(page):
    _, binding = page
    result = subject._qualified_reader('coach', binding, 'Terry Brown', 'Hayes', 2000)
    assert result['from_year'] == 1993 and result['to_year'] == 2002


@pytest.mark.parametrize('fault', ['url', 'club', 'year', 'body_hash', 'receipt_hash',
                                 'absolute_body', 'escape_receipt'])
def test_source_or_ownership_context_mismatch_rejects(page, fault):
    _, binding = page
    binding = copy.deepcopy(binding)
    club, year = 'Hayes', 2000
    if fault == 'url': binding['url'] = 'https://en.wikipedia.org/wiki/Terry_Brown'
    elif fault == 'club': club = 'Chelsea'
    elif fault == 'year': year = 2002
    elif fault == 'body_hash': binding['sha256'] = '0' * 64
    elif fault == 'receipt_hash': binding['source_receipt_sha256'] = '0' * 64
    elif fault == 'absolute_body': binding['path'] = '/etc/hosts'
    elif fault == 'escape_receipt': binding['source_receipt_path'] = '../outside.json'
    with pytest.raises(ValueError):
        subject._qualified_reader('coach', binding, 'Terry Brown', club, year)


@pytest.mark.parametrize('fault', ['missing_canonical', 'duplicate_canonical', 'wrong_url', 'wrong_h1'])
def test_raw_page_identity_is_not_inferred_from_receipt(page, fault):
    raw, _ = page
    if fault == 'missing_canonical': raw = raw.replace(b'rel="canonical"', b'rel="other"')
    elif fault == 'duplicate_canonical':
        raw = raw.replace(b'</head>', ('<link rel="canonical" href="' + subject.EXPECTED['coach']['url'] + '"></head>').encode())
    elif fault == 'wrong_url': raw = raw.replace(b'Terry_Brown_(football_manager)', b'Terry_Brown')
    elif fault == 'wrong_h1': raw = raw.replace(b'Terry Brown (football manager)', b'Another person')
    with pytest.raises(ValueError):
        subject._require_page_identity(raw, subject.EXPECTED['coach'])


@pytest.fixture
def corpus():
    if os.environ.get('PM99_SKIP_LOCAL_LABEL_CORPUS') == '1' or not PROPOSAL.is_file():
        pytest.skip('optional retained original-source/native corpus unavailable')
    return v1.pipeline.read_json_file(PROPOSAL)


def test_actual_canonical_plan_survives_json_roundtrip(corpus):
    base = v1.registry.load_registered_release('2000-01', 'sourced-keeper-profile-countries-20261023-r181a')
    plan = subject.prepare(base, [3307], corpus['source_inputs'])
    saved = json.loads(json.dumps(plan))
    subject.verify(base, saved)
    assert [(r['carrier_id'], r['before'], r['after']) for r in saved['updates']] == [(3307, 'Cheltenham Town', 'Hayes')]


@pytest.mark.parametrize('relative', OLD_PLANS)
def test_five_retained_old_policies_still_reproduce(corpus, relative):
    from scripts import season_period_squad_carrier_label_v2 as annual
    from scripts import season_period_cohort_coach_v3 as coach
    path = ROOT / '.local/consolidated-audit-20261009' / relative
    plan = v1.pipeline.read_json_file(path)
    policy = {v1.SCHEMA: v1, annual.SCHEMA: annual, coach.SCHEMA: coach}[plan['schema_version']]
    policy.verify(v1.registry.load_registered_release(plan['season'], plan['release_id']), plan)


def test_concurrent_canonical_prepares_do_not_mutate_old_globals(corpus):
    base = v1.registry.load_registered_release('2000-01', 'sourced-keeper-profile-countries-20261023-r181a')
    before = (v1.coach, v1.ground)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(subject.prepare, base, [3307], corpus['source_inputs']) for _ in range(2)]
        results = [f.result() for f in futures]
    assert results[0] == results[1]
    assert (v1.coach, v1.ground) == before
