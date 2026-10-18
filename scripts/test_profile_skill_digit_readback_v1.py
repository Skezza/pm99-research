from pathlib import Path
from PIL import Image
import pytest
from scripts import read_profile_skill_digits_v1 as subject


def font():
    if not all(p.exists() for p in subject.REFERENCES):pytest.skip('original reviewed runner corpus not available')
    return subject.build_font()[0]


def test_all_ten_font_digits_are_established_from_actual_reviewed_originals():
    assert set(font().values())==set('0123456789')


def test_actual_danny_fox_tackling_is_read_from_pixels_not_a_recipe():
    path=subject.registry.ROOT/'.local/consolidated-audit-20261009/frozen-fixture-batch-20261017-v1/2011-12/runtime/retained_9624/frozen_original_fixture_2011_12_r123a_20261017_retained_9624/screens/48_profile_only_retained_9624_done.png'
    if not path.exists():pytest.skip('original Fox profile not available')
    with Image.open(path) as image:
        assert subject.decode(image,font())==dict(speed=67,stamina=77,aggression=76,quality=73,
            handling=10,passing=70,dribbling=63,heading=78,tackling=79,shooting=53)


def test_unknown_digit_pixel_is_rejected_not_guessed():
    review=subject.pipeline.read_json_file(subject.REFERENCES[0])
    with Image.open(subject.registry.ROOT/review['screenshot']) as original:image=original.convert('RGB')
    # An isolated new ink component is not a known native font glyph.
    image.putpixel((352,54),(0,0,0))
    with pytest.raises(ValueError,match='digit glyph'):subject.decode(image,font())


def test_other_screen_geometry_cannot_accidentally_pass():
    with pytest.raises(ValueError,match='geometry'):subject.decode(Image.new('RGB',(800,600),'white'),font())
