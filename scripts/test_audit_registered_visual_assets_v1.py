"""Keep the visual audit from reporting malformed active photos as missing."""

from scripts import audit_registered_visual_assets_v1 as audit
from app.minifoto_bitmap_archive import encode_obfuscated_bitmap_name


def directory_entry(player_id, *, active=True):
    row = bytearray(38)
    row[0] = 2 if active else 0
    row[1:21] = encode_obfuscated_bitmap_name(f"J96{player_id:05d}.BMP")
    row[26:30] = (9999).to_bytes(4, "little")
    row[30:34] = (100).to_bytes(4, "little")
    return bytes(row)


def test_active_malformed_bitmap_is_not_counted_as_no_photo(tmp_path):
    path = tmp_path / "MINIFOTO.PKF"
    path.write_bytes(directory_entry(25))
    result = audit.invalid_photo_entries(path, {})
    assert result[25]["bitmap_offset"] == 9999
    assert "malformed" in result[25]["issue"]


def test_inactive_photo_is_ignored(tmp_path):
    path = tmp_path / "MINIFOTO.PKF"
    path.write_bytes(directory_entry(25, active=False))
    assert audit.invalid_photo_entries(path, {}) == {}


def test_already_decoded_entries_are_not_reported_invalid(tmp_path):
    path = tmp_path / "MINIFOTO.PKF"
    path.write_bytes(directory_entry(25))
    assert audit.invalid_photo_entries(path, {25: object()}) == {}
