import pytest

from scripts import season_historical_opening_review_v1 as review


def schedule(rows):
    return ('<table>' + ''.join('<tr><td>' + date + '</td><td><a href="/x/test/spieltag/wettbewerb/' + code + '">league</a><a href="/spielbericht/index/spielbericht/' + id + '">match</a></td></tr>' for date, code, id in rows) + '</table>').encode()


def test_first_fixture_ignores_friendlies_and_sort_order():
    raw = schedule([('02/08/2000', 'GB1', '19'), ('01/07/2000', 'FS', '3'), ('01/08/2000', 'GB1', '7')])
    assert review.first_fixture(raw, 'GB1') == ('2000-08-01', '7')


def report(club=14, manager='Right Coach'):
    players = ''.join(f'<a title="Full Name {i}" href="/x/profil/spieler/{i}">Surname</a>' for i in range(11))
    return f'<meta name="description" content="match on 01/08/2000"><div class="large-6 aufstellung-box"><a href="/x/startseite/verein/{club}/saison_id/2000">Club</a><table><tr><td>Players</td><td>{players}</td></tr><tr><td>Manager</td><td><a href="/x/profil/trainer/5">{manager}</a></td></tr></table></div>'.encode()


def test_exact_club_identity_and_full_names():
    found = review.match_team(report(), 14, '2000-08-01')
    assert found['manager'] == 'Right Coach'
    assert found['starting_xi']['0'] == 'Full Name 0'
    with pytest.raises(ValueError, match='0 exact club'):
        review.match_team(report(), 1, '2000-08-01')


def test_match_date_disagreement_rejected():
    with pytest.raises(ValueError, match='date disagrees'):
        review.match_team(report(), 14, '2000-08-02')


def test_visible_header_and_schedule_agreement_retains_next_day_metadata_discrepancy():
    raw = report().replace(b'01/08/2000', b'02/08/2000') + b'<div class="sb-datum">Tue, 01/08/00 | 11:00 PM</div>'
    parsed = review.match_team(raw, 14, '2000-08-01')
    assert parsed['match_page_date_independently_published'] is True
    assert parsed['date_publication_discrepancy']['metadata_dates'] == ['2000-08-02']
    assert parsed['date_publication_discrepancy']['visible_header_date'] == '2000-08-01'


@pytest.mark.parametrize('metadata,headers', [
    ('02/08/2000', ['02/08/00']),
    ('02/08/2000', ['01/08/00', '02/08/00']),
    ('03/08/2000', ['01/08/00']),
    ('31/07/2000', ['01/08/00']),
])
def test_no_arbitrary_metadata_or_conflicting_header_date_waiver(metadata, headers):
    raw = report().replace(b'01/08/2000', metadata.encode())
    raw += ''.join(f'<div class="sb-datum">{value}</div>' for value in headers).encode()
    with pytest.raises(ValueError, match='date disagrees'):
        review.match_team(raw, 14, '2000-08-01')


def test_four_digit_header_date_can_independently_establish_fixture_date():
    raw = report().replace(b'01/08/2000', b'no SEO date') + b'<div class="sb-datum">01/08/2000</div>'
    assert review.match_team(raw, 14, '2000-08-01')['match_page_date_independently_published'] is True


def eleven_substitute_report(with_grid=True, wrapped=True):
    grid = ''.join(f'<div class="formation-player-container"><a href="/x/profil/spieler/{i}" title="Starter {i}">Starter</a></div>' for i in range(11)) if with_grid else ''
    rows = ''.join(f'<tr><td>Reserve</td><td><a href="/x/profil/spieler/{i}" title="Reserve {i}">Reserve</a></td></tr>' for i in range(100, 111))
    table = '<table class="ersatzbank">' + rows + '</table>'
    if wrapped:
        table = '<div class="aufstellung-ersatzbank-box">' + table + '</div>'
    return ('<meta name="description" content="match on 01/08/2000"><div class="large-6 aufstellung-box"><a href="/x/startseite/verein/14/">Club</a>' + grid + table + '</div>').encode()


def test_eleven_substitutes_never_override_the_eleven_published_pitch_starters():
    found = review.match_team(eleven_substitute_report(), 14, '2000-08-01')
    assert set(found['starting_xi']) == {str(i) for i in range(11)}
    assert set(found['substitutes']) == {str(i) for i in range(100, 111)}


@pytest.mark.parametrize('wrapped', [False, True])
def test_bench_only_does_not_invent_a_starting_xi(wrapped):
    with pytest.raises(ValueError, match='eleven starting'):
        review.match_team(eleven_substitute_report(with_grid=False, wrapped=wrapped), 14, '2000-08-01')


def test_accelerated_parser_retains_same_fixture_and_team_contract(monkeypatch):
    monkeypatch.setattr(review, 'HTML_PARSER', 'html.parser')
    expected = review.match_team(report(), 14, '2000-08-01')
    raw = schedule([('02/08/2000', 'GB1', '19'), ('01/08/2000', 'GB1', '7')])
    earliest = review.first_fixture(raw, 'GB1')
    pytest.importorskip('lxml')
    monkeypatch.setattr(review, 'HTML_PARSER', 'lxml')
    assert review.match_team(report(), 14, '2000-08-01') == expected
    assert review.first_fixture(raw, 'GB1') == earliest


def test_absence_from_match_does_not_authorise_removal():
    clubs = {'a': {'id': 'a', 'name': 'A'}, 'b': {'id': 'b', 'name': 'B'}}
    players = [{'id': 'p' + id, 'carrier_id': carrier, 'club_id': id, 'name': 'Joe Player', 'facts': {'birth_date': '1980-01-01', 'nationality': country}} for id, carrier, country in [('a', 1, 'ENG'), ('b', 2, 'UNK')]]
    rows = review.duplicate_queue(players, clubs, {'a': {'date': '2000-08-01', 'source_url': 'https://source.example/match', 'starting_xi': {'10': 'Joe Player'}}})
    assert len(rows) == 1  # wrong nationality must not hide a duplicate
    assert rows[0]['status'] == 'one-dated-club-hit-replacement-and-transfer-check-required'
    assert rows[0]['automatic_change_authorised'] is False
    assert 'DOB not published' in rows[0]['candidates'][0]['identity_match_basis']
