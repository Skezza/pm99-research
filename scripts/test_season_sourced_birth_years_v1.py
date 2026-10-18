import copy
import pytest
from scripts import season_sourced_birth_years_v1 as module


def test_literal_full_name_and_birthday_only():
    capture = {'players': [{'name': 'Josef Bursik', 'birth_date': '2000-07-12'}]}
    before = copy.deepcopy(capture)
    assert module.original_person(capture, 'Josef BURSIK', '2000-07-12') == capture['players'][0]
    assert module.original_person(capture, 'J. Bursik', '2000-07-12') is None
    assert module.original_person(capture, 'Josef Bursik', '1967-07-12') is None
    assert capture == before


def test_duplicate_name_with_conflicting_DOB_refuses():
    capture = {'players': [{'name': 'Joe Keeper', 'birth_date': '2004-02-29'},
                           {'name': 'Joe Keeper', 'birth_date': '1973-02-28'}]}
    assert module.original_person(capture, 'Joe Keeper', '2004-02-29') is None
