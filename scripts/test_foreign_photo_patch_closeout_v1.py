from types import SimpleNamespace

from scripts import foreign_photo_patch_closeout_v1 as closeout


def test_preview_decodes_native_bottom_up_pixels_with_runtime_palette(monkeypatch):
    monkeypatch.setattr(closeout.portraits, 'validate_minifoto_bitmap', lambda raw:
        SimpleNamespace(width=2, height=2, pixel_offset=3, pixel_length=4))
    image = closeout.installed_preview(b'BMP\x01\x02\x03\x04', [(0, 0, 0), (10, 0, 0),
        (20, 0, 0), (30, 0, 0), (40, 0, 0)])
    assert list(image.getdata()) == [(30, 0, 0), (40, 0, 0), (10, 0, 0), (20, 0, 0)]
