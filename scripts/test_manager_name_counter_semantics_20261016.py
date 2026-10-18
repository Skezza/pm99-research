"""A real full-profile display repair must not become a fabricated surname edit."""
from types import SimpleNamespace
import pytest
from scripts import season_kit_render_bindings_v1
from scripts import checkpoint_cached_managers_20261016 as check


def profile(surname,display):
    return SimpleNamespace(surname=surname,display_name=display)


def test_dawes_full_profile_display_changes_but_surname_does_not():
    assert check.profile_name_changes(profile('Dawes','Ian Dawes'),profile('Dawes','Dawes'))==(True,False)


def test_both_name_fields_change_for_different_coach():
    assert check.profile_name_changes(profile('King','John King'),profile('Parkinson','Parkinson'))==(True,True)


def test_compatible_surname_is_not_counted_as_native_change():
    assert check.profile_name_changes(profile('Cratz','Cratz'),profile('Cratz','Cratz'))==(False,False)


def test_surname_only_change_is_distinct_from_display_change():
    assert check.profile_name_changes(profile('Old','Same'),profile('New','Same'))==(False,True)


def test_progress_uses_native_graph_display_count_not_surname_count():
    check.check_progress_counts(dict(canonical_manager_corrections=49,native_manager_name_changes=48),49,48)


def test_underreported_display_count_is_still_rejected():
    with pytest.raises(ValueError,match='progress counts'):
        check.check_progress_counts(dict(canonical_manager_corrections=49,native_manager_name_changes=47),49,48)


def test_overreported_canonical_count_is_still_rejected():
    with pytest.raises(ValueError,match='progress counts'):
        check.check_progress_counts(dict(canonical_manager_corrections=50,native_manager_name_changes=48),49,48)
