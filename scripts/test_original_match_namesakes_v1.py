import pytest

from scripts.review_original_match_namesakes_v1 import distinct_profiles


def test_distinct_source_ids_and_published_dates_required():
    distinct_profiles([dict(source_player_id='1', published_birth_date='1980-05-17'),
                       dict(source_player_id='2', published_birth_date='1981-12-14')])


@pytest.mark.parametrize('rows', [[], [dict(source_player_id='1', published_birth_date='1980-05-17')],
    [dict(source_player_id='1', published_birth_date='1980-05-17'), dict(source_player_id='1', published_birth_date='1981-12-14')],
    [dict(source_player_id='1', published_birth_date='1980-05-17'), dict(source_player_id='2', published_birth_date='1980-05-17')],
    [dict(source_player_id='1', published_birth_date='1980-05-17'), dict(source_player_id='2', published_birth_date=None)]])
def test_same_or_missing_identity_evidence_does_not_clear_namesakes(rows):
    with pytest.raises(ValueError): distinct_profiles(rows)
