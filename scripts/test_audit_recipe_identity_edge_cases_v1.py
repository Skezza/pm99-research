from datetime import date
import copy
from scripts import audit_recipe_identity_edge_cases_v1 as audit


def player(carrier, name, birthday, club='A'):
    return {'carrier_id': carrier, 'name': name, 'club_id': club,
        'facts': {'birth_date': birthday}, 'person_id': f'person-{carrier}'}


def test_different_birthdays_do_not_hide_same_name_but_never_authorise_a_merge():
    players = [player(1, 'Keanu Marsh-Brown', '1992-08-10'),
        player(2, 'Keanu Marsh-Brown', '1992-10-08')]
    before = copy.deepcopy(players)
    result = audit.inspect(players, {'A': {'name': 'Barnet'}}, date(2014, 8, 1))
    assert result['candidate_group_count'] == 1
    assert result['within_club_name_candidates'][0]['automatic_merge_authorised'] is False
    assert players == before


def test_genuine_namesakes_stay_review_candidates_and_different_clubs_are_separate():
    players = [player(1, 'Pepe', '1983-02-26'), player(2, 'Pepê', '1997-02-24'),
        player(3, 'Pepe', '1983-02-26', 'B')]
    result = audit.inspect(players, {'A': {'name': 'Porto'}, 'B': {'name': 'Elsewhere'}}, date(2023, 8, 1))
    assert result['candidate_group_count'] == 1
    assert len(result['within_club_name_candidates'][0]['players']) == 2
    assert not result['within_club_name_candidates'][0]['automatic_merge_authorised']


def test_full_source_name_not_shortened_native_label_drives_comparison():
    first = player(1, 'Crawford', '1991-12-10'); first['source_name'] = 'Harry Crawford'
    second = player(2, 'H Crawford', '1991-12-10'); second['source_name'] = 'Harry Crawford'
    result = audit.inspect([first, second], {'A': {'name': 'Dartford'}}, date(2014, 8, 1))
    assert result['within_club_name_candidates'][0]['classification'] == 'same-full-name-and-literal-DOB-review'


def test_child_or_future_identity_is_flagged_but_valid_young_player_and_preserved_dates_are_not_invented():
    players = [player(1, 'Recycled Profile', '2007-02-03'), player(2, 'Future Person', '2015-01-01'),
        player(3, 'Lamine Yamal', '1999-07-13'), player(4, 'Preserved Date', {'policy': 'preserve-existing-mode1'}),
        player(5, 'Invalid Date', '1990-02-31')]
    result = audit.inspect(players, {'A': {'name': 'Club'}}, date(2014, 8, 1))
    assert {r['carrier_id'] for r in result['DOB_review_candidates']} == {1, 2, 5}
    assert result['DOB_counts']['DOB-not-a-sourced-literal'] == 1
    assert result['DOB_counts']['age-within-broad-triage-range'] == 1
