import numpy as np
from scripts.verify_foreign_photo_profile_v1 import compare


def test_native_portrait_pixels_found_in_header_and_colour_error_rejected():
    expected = np.random.default_rng(23).integers(0, 256, (32, 32, 3), dtype=np.int16)
    shot = np.zeros((480, 640, 3), dtype=np.uint8)
    shot[7:39, 600:632] = expected
    result = compare(expected, shot)
    assert result['passed'] and result['bounds'] == [600, 7, 32, 32]
    assert result['exact_pixels'] == 1024
    shot[20, 610] = (0, 0, 0)
    assert not compare(expected, shot)['passed']
