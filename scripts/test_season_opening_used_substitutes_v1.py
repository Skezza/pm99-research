import pytest
from scripts import season_opening_used_substitutes_v1 as substitutes


def event(club=1, incoming=20, outgoing=10, extra_crest=''):
    return f'''<li><span class="sb-aktion-wechsel-ein"><a href="/reserve/leistungsdatendetails/spieler/{incoming}/saison/2005" title="Incoming Full Name">Short label</a></span>
      <span class="sb-aktion-wechsel-aus"><a href="/starter/leistungsdatendetails/spieler/{outgoing}/saison/2005">Starter</a></span>
      <div class="sb-aktion-wappen"><a href="/club/startseite/verein/{club}/saison_id/2005">Club</a>{extra_crest}</div></li>'''


def test_explicit_own_incoming_substitute_is_positive_first_fixture_evidence():
    row = substitutes.parse(event().encode(), 1, {'10': 'Starter'})
    assert row == {'used_substitutes': {'20': 'Incoming Full Name'}, 'unresolved_events': []}


def test_opponent_and_outgoing_players_are_not_added_to_the_bench():
    row = substitutes.parse((event() + event(club=2, incoming=30)).encode(), 1, {'10': 'Starter'})
    assert set(row['used_substitutes']) == {'20'}


@pytest.mark.parametrize('problem', ['ambiguous-crest', 'unknown-outgoing', 'incoming-is-starter'])
def test_conflicting_substitution_event_is_retained_unresolved(problem):
    html = event(extra_crest='<a href="/other/verein/2/">Other</a>') if problem == 'ambiguous-crest' else (
        event(outgoing=99) if problem == 'unknown-outgoing' else event(incoming=10))
    row = substitutes.parse(html.encode(), 1, {'10': 'Starter'})
    assert not row['used_substitutes'] and row['unresolved_events']


def test_a_published_substitute_can_later_be_substituted_again():
    row = substitutes.parse((event() + event(incoming=30, outgoing=20)).encode(), 1, {'10': 'Starter'})
    assert set(row['used_substitutes']) == {'20', '30'}
