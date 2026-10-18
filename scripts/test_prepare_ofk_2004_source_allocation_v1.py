import pytest

from scripts import prepare_ofk_2004_source_allocation_v1 as source


def annual(title='OFK Beograd - Detailed squad 04/05', role='Defender', extra=''):
    return f'<title>{title}</title><table class="items"><tbody><tr><td class="rueckennummer" title="{role}"></td><td><a href="/player/profil/spieler/10">Player</a>{extra}</td></tr></tbody></table>'.encode()


def test_period_bound_annual_role_uses_stable_id_not_current_sidebars():
    assert source.annual_roles(annual() + b'<a href="/wrong/profil/spieler/99">Current player</a>') == {10: 'D'}


@pytest.mark.parametrize('raw', [annual('OFK Beograd - Detailed squad 24/25'),
    annual('Other Club - Detailed squad 04/05'), annual(role='Unknown'),
    annual(extra='<a href="/other/profil/spieler/11">Other</a>')])
def test_annual_wrong_period_identity_or_unknown_role_refused(raw):
    with pytest.raises(ValueError): source.annual_roles(raw)


def moves(id, entries):
    return [dict(date=date, from_club=f'published-club-id:{old}', from_club_id=old,
        to_club=f'published-club-id:{new}', to_club_id=new) for date, old, new in entries]


def test_annual_member_away_on_loan_is_not_a_positive_opening_reserve():
    at_club = moves(10, [('2003-07-01', 9, 53), ('2005-01-01', 53, 8)])
    away = moves(11, [('2003-07-01', 9, 53), ('2004-07-01', 53, 99),
        ('2005-01-01', 99, 53), ('2006-07-01', 53, 8)])
    events = {10: at_club, 11: away, 12: at_club, 13: at_club}
    chosen = source.select_reserves(events, {10: 'At Club', 11: 'On Loan', 12: 'Starter'},
        '2004-08-20', {12})
    assert [r['source_player_id'] for r in chosen] == [10]
    assert chosen[0]['bracket']['source_owner_club_id'] == 53


def match():
    return b'''<div class="sb-team sb-heim"><a class="sb-vereinslink" href="/ofk-belgrad/startseite/verein/53/saison_id/2004">OFK Beograd</a></div>
    <p class="sb-datum"><a href="/aktuell/waspassiertheute/aktuell/new/datum/2004-08-20">20/08/04</a></p>
    <a href="/stadion/stadion/verein/53/saison_id/2004">Omladinski stadion</a>
    <div class="aufstellung-box"><div class="aufstellung-unterueberschrift-mannschaft"><a class="sb-vereinslink" href="/ofk-belgrad/startseite/verein/53/saison_id/2004">OFK Beograd</a></div><a href="/branko-babic/profil/trainer/4219">Branko Babic</a></div>
    <div class="sidebar"><a href="/modern-coach/profil/trainer/1">Modern Coach</a></div>'''


def test_dated_manager_and_ground_from_exact_home_lineup_not_sidebar():
    proof = source.dated_manager_ground(match())
    assert proof['manager'] == 'Branko Babic' and proof['source_manager_id'] == 4219
    assert proof['ground'] == 'Omladinski stadion'


@pytest.mark.parametrize('raw', [match().replace(b'sb-heim', b'sb-gast'),
    match().replace(b'/datum/2004-08-20', b'/datum/2004-08-21'),
    match().replace(b'/branko-babic/profil/trainer/4219', b'/another/profil/trainer/1'),
    match().replace(b'Omladinski stadion', b'Current renamed ground'),
    match() + b'<a href="/stadion/stadion/verein/53/saison_id/2004">Omladinski stadion</a>'])
def test_wrong_date_away_renaming_or_coach_refused(raw):
    with pytest.raises(ValueError): source.dated_manager_ground(raw)
