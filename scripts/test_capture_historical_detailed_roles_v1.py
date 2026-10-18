from scripts import capture_historical_detailed_roles_v1 as capture
import pytest


@pytest.mark.parametrize('text,expected', [('13/07/2007 (18)', '2007-07-13'), ('Jul 13, 2007 (18)', '2007-07-13'), ('Unknown', None)])
def test_source_dob_is_not_discarded(text, expected):
    assert capture.birth_date(text) == expected


def test_real_detailed_table_extracts_identity_and_side_not_just_forward():
    html = b'''<table class="items"><tbody><tr><td>10</td><td><a href="/lamine-yamal/profil/spieler/937958">Lamine Yamal</a> Right Winger</td><td>13/07/2007 (18)</td><td><img class="flaggenrahmen" title="Spain"></td><td></td><td>1,83m</td></tr></tbody></table>'''
    assert capture.parse(html) == [{'name': 'Lamine Yamal', 'birth_date': '2007-07-13',
        'source_player_id': '937958', 'source_position': 'rightwinger', 'fine_roles': [11],
        'nationalities': ['Spain'], 'height_cm': 183, 'shirt_number': 10}]


def test_generic_position_does_not_invent_a_side():
    html = b'''<table class="items"><tbody><tr><td>10</td><td><a href="/unknown/profil/spieler/1">Unknown Player</a> Forward</td><td>13/07/2007 (18)</td><td></td></tr></tbody></table>'''
    assert capture.parse(html) == []
    complete = capture.parse_complete_squad(html)
    assert len(complete) == 1
    assert complete[0]['birth_date'] == '2007-07-13'
    assert complete[0]['fine_roles'] == []


def test_name_variant_requires_same_independently_pinned_club_id():
    selector = {'country_catalog': 'spain', 'transfermarkt_club_name': 'Deportivo La Coruña', 'transfermarkt_club_id': 897}
    html = b'<link rel="canonical" href="https://www.transfermarkt.com/deportivo/kader/verein/897">'
    assert capture.club_identity_bound(html, selector, 'Deportivo A Coruña')
    selector['transfermarkt_club_id'] = 131
    assert not capture.club_identity_bound(html, selector, 'Deportivo A Coruña')


def test_refused_requests_pause_fetching_but_do_not_prevent_offline_cache_reuse(tmp_path, monkeypatch):
    import json
    import hashlib
    from urllib.error import HTTPError
    from scripts import capture_ntf_historical_carrier_squads_v1 as source
    calls = []
    monkeypatch.setattr(source.Cache, 'blocked_hosts', {})
    def denied(url):
        calls.append(url)
        raise HTTPError(url, 405, 'Not Allowed', {}, None)
    monkeypatch.setattr(source, '_get', denied)
    cache = source.Cache(tmp_path, offline=False, delay=0, stop_on_http_block=True)
    with pytest.raises(HTTPError):
        cache.get('https://example.org/first', 'first.html')
    with pytest.raises(ValueError, match='paused'):
        cache.get('https://example.org/second', 'second.html')
    assert len(calls) == 1
    raw = tmp_path / 'saved.html'; raw.write_bytes(b'saved evidence')
    raw.with_suffix('.html.source.json').write_text(json.dumps({'url': 'https://example.org/saved',
        'sha256': hashlib.sha256(raw.read_bytes()).hexdigest()}))
    assert cache.get('https://example.org/saved', 'saved.html') == b'saved evidence'
