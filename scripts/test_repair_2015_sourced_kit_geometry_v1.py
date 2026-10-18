import pytest
from PIL import Image, ImageDraw

from scripts.repair_2015_sourced_kit_geometry_v1 import source_canvas


def test_source_projection_preserves_separate_sleeve_and_torso_colours():
    image = Image.new('RGBA', (68, 98), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((6, 22, 17, 50), fill='red')
    draw.rectangle((18, 19, 49, 85), fill='blue')
    draw.rectangle((50, 22, 61, 50), fill='green')
    result = source_canvas(image)
    assert result.size == (100, 100)
    assert result.getpixel((0, 0)) == (255, 0, 0)
    assert result.getpixel((30, 99)) == (255, 0, 0)
    assert result.getpixel((31, 0)) == (0, 0, 255)
    assert result.getpixel((68, 99)) == (0, 0, 255)
    assert result.getpixel((69, 0)) == (0, 128, 0)
    assert result.getpixel((99, 99)) == (0, 128, 0)


def test_transparent_source_pixels_are_composited_consistently():
    result = source_canvas(Image.new('RGBA', (68, 98), (0, 0, 0, 0)))
    assert result.getextrema() == ((255, 255), (255, 255), (255, 255))


@pytest.mark.parametrize('size', [(100, 100), (68, 97)])
def test_unknown_source_framing_is_not_guessed(size):
    with pytest.raises(ValueError, match='framing'):
        source_canvas(Image.new('RGB', size))
