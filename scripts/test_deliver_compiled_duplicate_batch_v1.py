import pytest
from scripts import deliver_compiled_duplicate_batch_v1 as delivery


def test_batch_count_comes_from_actual_plans_not_a_hardcoded_progress_total():
    plans = {'a': {'updates': [1, 2]}, 'b': {'updates': []}}
    proof = {'players': 2, 'seasons': [{'season': 'a', 'players': 2}]}
    assert delivery.verify_batch_size(plans, proof) == ['a']
    with pytest.raises(ValueError, match='exact planned'):
        delivery.verify_batch_size(plans, dict(proof, players=1))


def test_extra_or_repeated_native_seasons_cannot_be_promoted():
    plans = {'a': {'updates': [1]}}
    for rows in [[{'season': 'b', 'players': 1}], [{'season': 'a', 'players': 1}] * 2]:
        with pytest.raises(ValueError, match='exact planned'):
            delivery.verify_batch_size(plans, {'players': 1, 'seasons': rows})


def report(ids, policy='one-fixed-reader'):
    return {'policy': policy, 'cross_club_candidate_groups': len(ids),
            'seasons': [{'season': 'a', 'candidates': [{'identity': ['person', id]} for id in ids]}]}


def test_same_reader_reports_only_removed_groups_and_refuses_new_duplicates():
    assert delivery.identity_difference(report([1, 2]), report([1]))['removed'] == 1
    with pytest.raises(ValueError, match='introduced'):
        delivery.identity_difference(report([1]), report([1, 2]))
    with pytest.raises(ValueError, match='matching rules differ'):
        delivery.identity_difference(report([1]), report([1], 'another-reader'))
