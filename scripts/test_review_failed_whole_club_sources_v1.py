import pytest
from scripts import review_failed_whole_club_sources_v1 as review


def test_forward_review_excludes_successes_and_unchanged_failures():
    rows = [
        {'status': 'complete-source-fit', 'reason': None},
        {'status': 'allocation-gap', 'reason': 'name capacity'},
        {'status': 'source-gap', 'reason': 'fixed capacity lacks 2 reserves'},
        {'status': 'source-gap', 'reason': 'provider birthday conflicts with annual'},
        {'status': 'source-gap', 'reason': 'the exact first fixture needs eleven identified players and one starting keeper'},
    ]
    assert review.selected_decisions({'decisions': rows}) == rows[3:]


def test_alias_cannot_become_second_target_club():
    assert review.represented('Fylde', [{'name': 'AFC Fylde'}])
    assert not review.represented('Fylde', [{'name': 'Fylde Women'}])


def test_forward_review_retains_and_finds_original_source_binding():
    original={'prior_plan_path':'original.json','prior_plan_sha256':'hash'}
    nested={'old_decision':{'old_decision':original,'baseline':'intermediate'},'baseline':'current'}
    assert review.original_decision(nested) is original
    assert 'old_decision' in nested  # Audit chain not flattened/overwritten.


def test_completed_or_partial_review_cannot_be_repeated(tmp_path):
    with pytest.raises(ValueError, match='immutable'):
        review.review(tmp_path / 'missing-input', tmp_path)
