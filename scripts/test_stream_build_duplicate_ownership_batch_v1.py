import pytest
from scripts import stream_build_duplicate_ownership_batch_v1 as mod


def test_priority_changes_only_scheduling_not_pending_membership():
    pending={'2000-01','2021-22','2010-11'}
    assert mod.ordered_seasons(pending,['2021-22'])==['2021-22','2000-01','2010-11']
    assert pending=={'2000-01','2021-22','2010-11'}


def test_completed_priority_is_not_reintroduced():
    assert mod.ordered_seasons({'2000-01'},['2021-22'])==['2000-01']


@pytest.mark.parametrize('priority',[['2021-22','2021-22'],['wrong-season']])
def test_invalid_priority_is_refused(priority):
    with pytest.raises(ValueError):mod.ordered_seasons({'2000-01'},priority)
