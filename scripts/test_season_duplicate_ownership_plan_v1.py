"""Ownership is chronological; club order and missing facts are not proof."""
import copy
import pytest
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import pm99_simple_season_v1 as simple
from scripts import season_package_v2 as package_v2
from scripts.test_season_package_v2 import _valid_package


def inputs():
    players = [{'id': 'p1', 'club_id': 'a'}, {'id': 'p2', 'club_id': 'b'}]
    evidence = {
        'a': {'source_club_id': 1, 'date': '2014-08-16', 'starting_xi': {'10': 'Player'}, 'substitutes': {}},
        'b': {'source_club_id': 2, 'date': '2014-08-17', 'starting_xi': {}, 'substitutes': {}},
    }
    person = {'source_player_id': 10}
    events = [{'date': '2013-07-01', 'from_club_id': 3, 'to_club_id': 1},
              {'date': '2015-07-01', 'from_club_id': 1, 'to_club_id': 4}]
    for event in events:
        event.update(from_club=str(event['from_club_id']), to_club=str(event['to_club_id']))
    return players, evidence, person, events


def test_owner_requires_positive_opening_id_and_bracket_at_both_dates():
    players, sources, person, events = inputs()
    assert planner.decide_owner(players, sources, person, events)[0] == players[0]
    assert planner.decide_owner(list(reversed(players)), sources, person, events)[0] == players[0]
    sources['a']['starting_xi'] = {}
    assert planner.decide_owner(players, sources, person, events)[0] is None


def test_unbridged_provider_person_cannot_use_another_providers_missing_id_as_absence():
    players,sources,person,events=inputs()
    person.update(source_player_id='soccerbase:10',source_provider='soccerbase')
    assert planner.decide_owner(players,sources,person,events)[0] is None


def test_positive_losing_bench_membership_is_not_dismissed_as_absence():
    players, sources, person, events = inputs()
    sources['b']['substitutes']['10'] = 'Player'
    assert planner.decide_owner(players, sources, person, events)[0] is None


def test_original_common_date_xi_can_resolve_incomplete_transfer_history():
    from scripts.test_season_common_date_ownership_v1 import inputs as common_inputs
    players, sources, person, events = common_inputs()
    winner, basis = planner.decide_owner(players, sources, person, events)
    assert winner == players[0] and basis == planner.common_date.BASIS


def test_unresolved_original_substitution_cannot_be_treated_as_absence():
    players, sources, person, events = inputs()
    sources['b']['unresolved_substitution_events'] = [{'incoming_player_ids': {'10': 'Player'}}]
    winner, reason = planner.decide_owner(players, sources, person, events)
    assert winner is None and reason == 'original-substitution-appearance-needs-reconciliation'


def test_review_event_notes_are_bound_to_their_exact_carrier_without_mutating_review():
    row = {'carrier_id': 1, 'evidence': {'starting_xi': {'10': 'Player'}}}
    event = {'incoming_player_ids': {'20': 'Possible'}}
    review = {'used_substitute_refresh': {'summary': {'unresolved': [
        {'carrier_id': 1, 'events': [event]}, {'carrier_id': 2, 'events': [{'incoming_player_ids': {'30': 'Opponent'}}]}]}}}
    result = planner.source_evidence(row, review)
    assert result['unresolved_substitution_events'] == [event]
    assert 'unresolved_substitution_events' not in row['evidence']


@pytest.mark.parametrize('problem', ['missing-club', 'entry-only', 'same-day', 'two-owners', 'duplicate-club'])
def test_ambiguous_or_incomplete_chronology_never_authorises_write(problem):
    players, sources, person, events = inputs()
    if problem == 'missing-club': del sources['b']
    if problem == 'entry-only': events.pop()
    if problem == 'same-day': events.insert(1, dict(events[0]))
    if problem == 'two-owners':
        events.insert(1, {'date': '2014-08-17', 'from_club_id': 1, 'to_club_id': 2})
    if problem == 'duplicate-club': sources['b']['source_club_id'] = 1
    assert planner.decide_owner(players, sources, person, events)[0] is None


def test_capture_does_not_choose_owner_by_first_club_or_drop_later_claim():
    player = {'name': 'Real Player', 'facts': {'birth_date': '1980-01-01'}}
    capture = {'clubs': [{'club_name': 'A', 'players': [player, copy.deepcopy(player)]},
                         {'club_name': 'B', 'players': [copy.deepcopy(player)]}], 'summary': {}}
    original = copy.deepcopy(capture)
    result, audit = simple._normalise_capture(capture)
    assert [len(c['players']) for c in result['clubs']] == [1, 1]
    assert audit['suppressed_count'] == 1
    assert audit['cross_club_claim_count'] == 1
    assert capture == original


def test_country_disagreement_cannot_hide_duplicate_in_strict_validation():
    package = _valid_package()
    first, second = package['players'][:2]
    second['name'] = first['name']
    second['facts'] = copy.deepcopy(first['facts'])
    second['facts']['nationality'] = 'XXX'
    with pytest.raises(package_v2.PackageValidationError, match='same-person'):
        package_v2.validate_package(package, strict=True)


def test_same_display_alias_and_birthday_do_not_conflate_distinct_people():
    package = _valid_package()
    first, second = package['players'][:2]
    first.update(name='E. Espinal', source_name='Elpys Jose Espinal')
    second.update(name='E. Espinal', source_name='Elpys Vinicio Espinal')
    second['facts'] = copy.deepcopy(first['facts'])
    assert package_v2._person_candidate_key(first) != package_v2._person_candidate_key(second)


def test_country_and_carrier_are_not_identity_keys():
    a = {'id': 'a', 'carrier_id': 1, 'name': 'Alias', 'source_name': 'Full Player',
         'facts': {'birth_date': '1980-01-01', 'nationality': 'ENG'}}
    b = copy.deepcopy(a)
    b.update(id='b', carrier_id=2)
    b['facts']['nationality'] = 'XXX'
    assert planner.candidate_groups([a, b], {}) == [[a, b]]


@pytest.mark.parametrize('membership', ['bench', 'dated-reserve', 'later-signing', 'entry-only', 'wrong-club', 'starter'])
def test_opening_replacement_needs_positive_bench_or_dated_ownership(membership):
    from types import SimpleNamespace
    facts = {'name': 'Reserve Player', 'birth_date': '1990-01-01', 'position': 'M'}
    person = {'source_player_id': 10, 'name': 'Reserve Player', 'birth_date': '1990-01-01'}
    index = {('reserveplayer', '1990-01-01'): {10: person}}
    club = {'name': 'Example', 'division': 'Premier League', 'carrier_id': 300}
    source = {'source_club_id': 1, 'date': '2014-08-16', 'starting_xi': {}, 'substitutes': {}}
    capture = {'country_catalog': 'eng', 'club_name': 'Example', 'players': [facts],
               'source_path': 'raw.html', 'source_sha256': 'raw'}
    events = [{'date': '2013-07-01', 'from_club_id': 3, 'to_club_id': 1,
               'from_club': 'Previous', 'to_club': 'Example'},
              {'date': '2015-07-01', 'from_club_id': 1, 'to_club_id': 4,
               'from_club': 'Example', 'to_club': 'Next'}]
    if membership == 'bench': source['substitutes']['10'] = 'Reserve Player'
    if membership == 'starter': source['starting_xi']['10'] = 'Reserve Player'
    if membership == 'later-signing': events[0]['date'] = '2014-09-01'
    if membership == 'entry-only': events.pop()
    if membership == 'wrong-club': source['source_club_id'] = 99
    verifier = SimpleNamespace(verify=lambda r: {'status': 'raw-source-reparsed'})
    result = planner.verified_replacements(club, source, [capture], verifier, index, {10: events})
    assert bool(result) == (membership in {'bench', 'dated-reserve'})
    if result:
        assert result[0]['opening_eligibility']['source_club_id'] == 1


def test_unverified_squad_cannot_supply_an_opening_reserve():
    from types import SimpleNamespace
    club = {'name': 'Example', 'division': 'Premier League', 'carrier_id': 300}
    capture = {'country_catalog': 'eng', 'club_name': 'Example', 'players': []}
    verifier = SimpleNamespace(verify=lambda r: {'status': 'raw-capture-disagrees'})
    assert planner.verified_replacements(club, {}, [capture], verifier, {}) == []
