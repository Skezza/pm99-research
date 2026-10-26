import copy
import pytest
from scripts import season_source_person_collision_guard_v1 as guard


def player(id, name, birth='1997-12-09'):
    return dict(id=str(id), carrier_id=id, club_id='club-' + str(id),
                source_name=name, facts=dict(birth_date=birth))


def test_new_copy_fails_even_when_the_legacy_actor_has_no_provider_id():
    before = {'players': [player(1, 'Marc Bola'), player(2, 'Other Person')]}
    after = copy.deepcopy(before)
    after['players'][1]['source_name'] = 'Marc Bola'
    with pytest.raises(ValueError, match='dated disposition'):
        guard.require_no_new_collisions(before, after)
    row = guard.new_collisions(before, after)[0]
    assert (row['before_count'], row['after_count']) == (1, 2)
    assert [a['carrier_id'] for a in row['actors']] == [1, 2]


def test_unchanged_existing_duplicates_are_not_reopened_or_cleared():
    package = {'players': [player(1, 'Marc Bola'), player(2, 'Marc Bola')]}
    assert guard.new_collisions(package, copy.deepcopy(package)) == []
    report = guard.require_no_new_collisions(package, package)
    assert 'not cleared' in report['limits']


def test_new_namesakes_with_different_births_do_not_share_a_key():
    before = {'players': [player(1, 'Víctor Ruiz', '1989-01-25')]}
    after = {'players': before['players'] + [player(2, 'Víctor Ruiz', '1993-11-02')]}
    assert guard.new_collisions(before, after) == []


def test_source_caption_and_accents_do_not_hide_a_new_copy():
    before = {'players': [player(1, '#7 Víctor Ruiz')]}
    after = {'players': before['players'] + [player(2, 'Victor Ruiz')]}
    assert len(guard.new_collisions(before, after)) == 1


def test_missing_births_and_initials_are_not_identity_proofs():
    before = {'players': []}
    after = {'players': [player(1, 'M. Bola'), player(2, 'M. Bola'),
                          player(3, 'Marc Bola', {'policy': 'preserve-existing-mode1'}),
                          player(4, 'Marc Bola', 'unknown')]}
    assert guard.new_collisions(before, after) == []
