import pytest
from scripts.resume_original_country_runtime_20261017 import ascii_token


@pytest.mark.parametrize('name,expected',[('Sandro Ramírez','Ramirez'),('Kacper Łopata','Lopata'),('Guðmundur Þórarinsson','orarinsson')])
def test_ascii_token_is_separate_from_native_player_name(name,expected):
    assert ascii_token(name)==expected


def test_single_initial_is_not_a_reliable_profile_token():
    with pytest.raises(ValueError,match='reviewed ASCII word'):ascii_token('Player X')
