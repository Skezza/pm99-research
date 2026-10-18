"""Adversarial checks for original coach sources and narrow conflict decisions."""
import json
from urllib.error import HTTPError
import pytest
from bs4 import BeautifulSoup
from scripts import capture_deferred_manager_originals_20261016 as capture
from scripts import manager_primary_conflict_resolutions_20261016 as primary


def test_published_date_reads_original_metadata_and_structured_article():
    page = BeautifulSoup('<meta property="article:published_time" content="2014-01-15T01:00:00Z">'
        '<script type="application/ld+json">{"@graph":[{"datePublished":"2014-01-15T01:00:00Z"}]}</script>', 'html.parser')
    assert primary.published_dates(page) == {'2014-01-15'}


def article_fixture(tmp_path, monkeypatch, body='Original named manager and dated role'):
    monkeypatch.setattr(primary.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(primary.articles, 'ROOT', tmp_path)
    monkeypatch.setattr(primary.articles, 'SOURCES', (('source', 'https://club.example/source'),))
    raw = tmp_path / 'source.html'
    raw.write_text('<meta property="article:published_time" content="2014-01-15T01:00:00Z"><p>' + body + '</p>')
    receipt = dict(status='public-original-captured', url='https://club.example/source',
        raw_path='source.html', raw_sha256=primary.registry.sha256_file(raw))
    path = tmp_path / 'source.json'; path.write_text(json.dumps(receipt))
    return raw, path, receipt


def test_reviewed_article_requires_exact_raw_sha(tmp_path, monkeypatch):
    raw, _, _ = article_fixture(tmp_path, monkeypatch)
    raw.write_text('Different page with same title')
    with pytest.raises(ValueError, match='original bytes changed'):
        primary.original_article('source', published='2014-01-15')


def test_article_url_cannot_be_relabelled_as_original(tmp_path, monkeypatch):
    _, path, receipt = article_fixture(tmp_path, monkeypatch)
    receipt['url'] = 'https://another.example/unrelated'; path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='original URL'):
        primary.original_article('source')


def test_current_article_cannot_substitute_for_required_contemporary_date(tmp_path, monkeypatch):
    article_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='publication date differs'):
        primary.original_article('source', published='2016-01-15')


def test_context_required_not_just_correct_headline(tmp_path, monkeypatch):
    article_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='source facts'):
        primary.original_article('source', published='2014-01-15', anchors=('Former coach replaced before August',))


def test_hidden_script_text_does_not_count_as_visible_historical_article(tmp_path, monkeypatch):
    article_fixture(tmp_path, monkeypatch, body='<script>Former coach replaced before August</script>')
    with pytest.raises(ValueError, match='source facts'):
        primary.original_article('source', anchors=('Former coach replaced before August',))


def test_matching_original_period_and_facts_replay(tmp_path, monkeypatch):
    _, _, receipt = article_fixture(tmp_path, monkeypatch)
    actual = primary.original_article('source', published='2014-01-15', anchors=('named manager', 'dated role'))
    assert actual['sha256'] == receipt['raw_sha256'] and actual['published_dates'] == ['2014-01-15']


def test_two_published_dates_are_not_silently_chosen(tmp_path, monkeypatch):
    raw, path, receipt = article_fixture(tmp_path, monkeypatch)
    raw.write_text(raw.read_text() + '<script type="application/ld+json">{"datePublished":"2014-01-16"}</script>')
    receipt['raw_sha256'] = primary.registry.sha256_file(raw); path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='ambiguous'):
        primary.original_article('source', published='2014-01-15')


def test_source_club_url_needs_original_exact_decision_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.registry, 'ROOT', tmp_path)
    decision = tmp_path / 'decision.json'; decision.write_text('{}')
    case = dict(decision_path='decision.json', decision_sha256='0' * 64)
    with pytest.raises(ValueError, match='decision changed'):
        capture.history_url(case)


def test_access_refusal_stops_host_requests_but_keeps_all32_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(capture, 'ROOT', tmp_path / 'capture')
    audit = tmp_path / 'audit.json'
    cases = [dict(season='2000-01', club='Club ' + str(i), club_id='club-' + str(i), source_club_id=i,
        status='no-readable-cached-tenure-at-target-date', claims=[]) for i in range(1, 33)]
    audit.write_text(json.dumps(dict(rows=cases))); monkeypatch.setattr(capture, 'AUDIT', audit)
    monkeypatch.setattr(capture, 'history_url', lambda case: 'https://www.transfermarkt.co.uk/club/mitarbeiterhistorie/verein/' + str(case['source_club_id']))
    attempts = []
    def blocked(url, club):
        attempts.append(club)
        raise HTTPError(url, 403, 'Forbidden', None, None)
    monkeypatch.setattr(capture, 'original_page', blocked)
    capture.main()
    assert attempts == [1]
    result = capture.pipeline.read_json_file(capture.ROOT / 'capture-summary.json')
    assert len(result['rows']) == 32 and result['access_control_pause'] == '403'
    assert result['manager_cases_closed'] == result['native_writes'] == 0


def test_completed_source_capture_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, 'ROOT', tmp_path)
    (tmp_path / 'capture-summary.json').write_text('{}')
    with pytest.raises(ValueError, match='must not repeat'):
        capture.main()
