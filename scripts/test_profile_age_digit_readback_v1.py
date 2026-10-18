from pathlib import Path
import pytest
from PIL import Image
from scripts import read_profile_age_digits_v1 as subject

ORIGINAL=subject.registry.ROOT/'.local/consolidated-audit-20261009/public-fixture-batch-20261017-v2/2024-25/runtime/replacement_17925/public_original_fixture_2024_25_r124a_20261017_replacement_17925/screens/53_profile_only_replacement_17925_done.png'


@pytest.mark.skipif(not ORIGINAL.exists(),reason='original runner reference is local-only')
def test_original_diabate_age_is23_not_transcribed22():
    result=subject.read(ORIGINAL)
    assert result['observed_age']==23
    assert result['recipe_values_used_for_decoding'] is False


def test_other_geometry_refused():
    with pytest.raises(ValueError,match='geometry'):
        subject.decode(Image.new('RGB',(320,240)),{})


def test_empty_or_unknown_age_is_not_guessed():
    with pytest.raises(ValueError,match='age glyph'):
        subject.decode(Image.new('RGB',(640,480),'black'),{})
