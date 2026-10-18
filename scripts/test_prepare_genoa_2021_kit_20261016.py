import pytest
from PIL import Image

from scripts.prepare_genoa_2021_kit_20261016 import CROPS, fabric_canvas


def test_original_fabric_regions_do_not_swap_body_or_sleeves():
    original = Image.new('RGB', (1500, 1113), 'white')
    # Deliberately distinct original garment planes, not identical colours.
    for box, colour in zip(CROPS, ((10, 20, 40), (160, 10, 20), (230, 20, 30))):
        original.paste(colour, box)
    result = fabric_canvas(original)
    assert result.size == (100, 100)
    assert result.getpixel((15, 50)) == (10, 20, 40)
    assert result.getpixel((50, 50)) == (160, 10, 20)
    assert result.getpixel((85, 50)) == (230, 20, 30)
    assert result.tobytes() == fabric_canvas(original).tobytes()


@pytest.mark.parametrize('size', [(800, 800), (1113, 1500), (1500, 1112)])
def test_wrong_photo_framing_is_rejected(size):
    with pytest.raises(ValueError, match='dimensions differ'):
        fabric_canvas(Image.new('RGB', size))
