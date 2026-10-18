import pytest
from scripts.deliver_morecambe_owned_opening_20261017 import check_profile_observation


@pytest.mark.parametrize('label,position',[('mark_smith','GOALKEEPER'),('kenny_takano','MIDFIELDER'),
    ('john_norman','FORWARD'),('andy_banks','GOALKEEPER')])
def test_literal_original_positions_must_match_source_broad_class(label,position):
    review=dict(observed_club='Morecambe',observed_position=position,observed_nationality='ENGLAND')
    check_profile_observation(label,review)
    for bad in ('DEFENDER','SWEEPER',None):
        with pytest.raises(ValueError):check_profile_observation(label,dict(review,observed_position=bad))
    with pytest.raises(ValueError):check_profile_observation(label,dict(review,observed_club='Barrow'))


def test_new_keeper_cannot_inherit_missing_or_unproved_nationality():
    with pytest.raises(ValueError):check_profile_observation('mark_smith',
        dict(observed_club='Morecambe',observed_position='GOALKEEPER',observed_nationality='XXX'))
