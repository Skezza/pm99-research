from scripts import season_opening_used_substitutes_v2 as new
from scripts.test_season_opening_used_substitutes_v1 import event


def actual(**kwargs):
    return event(**kwargs).replace('class="sb-aktion-wechsel-ein">',
        'class="sb-aktion-wechsel-ein"><span class="sb-ein"></span>').replace(
        'class="sb-aktion-wechsel-aus">', 'class="sb-aktion-wechsel-aus"><span class="sb-aus"></span>')


def test_actual_substitution_retains_positive_evidence():
    result = new.parse(actual().encode(), 1, {'10': 'Starter'})
    assert result['used_substitutes'] == {'20': 'Incoming Full Name'}
    assert not result['unresolved_events']


def test_penalty_shared_css_is_not_a_substitution_or_conflict():
    penalty = event(incoming=10, outgoing=99).replace('<li>',
        '<li><div class="sb-aktion-spielstand"><a href="/opponent/verein/2/">Opponent</a></div>').replace(
        'class="sb-aktion-wechsel-ein">', 'class="sb-aktion-wechsel-ein">Penalty for handball, ')
    result = new.parse((penalty + actual()).encode(), 1, {'10': 'Starter'})
    assert result['used_substitutes'] == {'20': 'Incoming Full Name'}
    assert not result['unresolved_events'] and result['ignored_penalty_events'] == 1


def test_markerless_events_remain_protected_not_positive():
    result = new.parse(event().encode(), 1, {'10': 'Starter'})
    assert not result['used_substitutes']
    assert result['unresolved_events'][0]['incoming_player_ids'] == {'20': 'Incoming Full Name'}
    assert result['unresolved_events'][0]['outgoing_player_ids'] == {'10': 'Starter'}


def test_score_badge_alone_cannot_erase_an_unclassified_event():
    html = event().replace('<li>', '<li><div class="sb-aktion-spielstand"><a href="/club/verein/1/">Club</a></div>')
    result = new.parse(html.encode(), 1, {'10': 'Starter'})
    assert result['unresolved_events'] and not result['ignored_penalty_events']


def test_actual_unmatched_outgoing_still_remains_unresolved():
    result = new.parse(actual(outgoing=99).encode(), 1, {'10': 'Starter'})
    assert result['unresolved_events'] and not result['used_substitutes']


def test_chained_substitutions_still_work():
    result = new.parse((actual() + actual(incoming=30, outgoing=20)).encode(), 1, {'10': 'Starter'})
    assert set(result['used_substitutes']) == {'20', '30'}
