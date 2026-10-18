import json
import pytest
from scripts import capture_match_archive_sources_v1 as capture


@pytest.mark.parametrize('url', ['http://www.11v11.com/teams/boston-united/',
    'https://other.example/teams/boston-united/', 'https://www.11v11.com/teams/x/?season=2003',
    'https://www.11v11.com/teams/x/#other', 'https://www.11v11.com:443/teams/x/',
    'https://user@www.11v11.com/teams/x/', 'https://www.11v11.com/admin/'])
def test_off_publisher_or_non_original_requests_are_refused(url):
    with pytest.raises(ValueError): capture.validate_url(url)


def test_cached_original_receipt_is_replayed_without_request(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.registry, 'ROOT', tmp_path)
    url = 'https://www.11v11.com/teams/boston-united/tab/matches/season/2004/'
    key = capture.hashlib.sha256(url.encode()).hexdigest()
    page, receipt = tmp_path / (key + '.html'), tmp_path / (key + '.source.json')
    page.write_bytes(b'original source')
    receipt.write_text(json.dumps({'url': url, 'sha256': capture.registry.sha256_file(page)}))
    monkeypatch.setattr(capture, 'urlopen', lambda *a, **k: pytest.fail('cached source refetched'))
    assert capture.capture(url, tmp_path)['reused']
    page.write_bytes(b'changed source')
    with pytest.raises(ValueError, match='receipt changed'):
        capture.capture(url, tmp_path)


def test_receipt_without_original_page_is_not_overwritten(tmp_path):
    url = 'https://www.11v11.com/players/example-10/'
    key = capture.hashlib.sha256(url.encode()).hexdigest()
    (tmp_path / (key + '.source.json')).write_text('{}')
    with pytest.raises(ValueError, match='source page is missing'):
        capture.capture(url, tmp_path)
