import shutil
from pathlib import Path
import pytest

from app.io import FDIFile
from app.file_writer import write_name_only_record
from app.xor import decode_entry
from app.models import PlayerRecord


FIXTURE = Path("tests/debug_roundtrip.fdi")


def _choose_player_with_name(fdi: FDIFile):
    """Return (offset, record) for the first player with a reasonable name."""
    for offset, rec in getattr(fdi, "records_with_offsets", []):
        name = getattr(rec, "name", None) or f"{getattr(rec, 'given_name','') or ''} {getattr(rec,'surname','') or ''}".strip()
        if name and len(name) >= 3:
            return offset, rec
    return None, None


def _read_decoded_at(path: Path, offset: int):
    data = path.read_bytes()
    decoded, length = decode_entry(data, offset)
    return decoded


def test_same_length_name_change_preserves_attributes(tmp_path):
    """Changing a name to another same-length name should succeed and preserve attributes."""
    dst = tmp_path / "roundtrip.fdi"
    shutil.copy2(FIXTURE, dst)

    fdi = FDIFile(str(dst))
    fdi.load()

    offset, rec = _choose_player_with_name(fdi)
    assert offset is not None, "No suitable player found in fixture"

    orig_attrs = list(rec.attributes)
    orig_name = getattr(rec, "name", "") or f"{getattr(rec,'given_name','') or ''} {getattr(rec,'surname','') or ''}".strip()
    # create a same-length different name by reversing the string (keeps bytes length)
    new_name = orig_name[::-1]
    assert len(new_name) == len(orig_name)

    ok = write_name_only_record(str(dst), offset, orig_name, new_name)
    assert ok, "write_name_only_record failed for same-length replacement"

    decoded = _read_decoded_at(dst, offset)
    parsed = PlayerRecord.from_bytes(decoded, offset)
    assert parsed.attributes == orig_attrs, "Attributes changed after same-length name save"
    # verify the text appears in decoded payload
    assert new_name.encode("latin1") in decoded


def test_shorter_name_pads_and_preserves_attributes(tmp_path):
    """Shorter replacement should be padded and preserve attributes."""
    dst = tmp_path / "roundtrip2.fdi"
    shutil.copy2(FIXTURE, dst)

    fdi = FDIFile(str(dst))
    fdi.load()

    offset, rec = _choose_player_with_name(fdi)
    assert offset is not None

    orig_attrs = list(rec.attributes)
    orig_name = getattr(rec, "name", "") or f"{getattr(rec,'given_name','') or ''} {getattr(rec,'surname','') or ''}".strip()
    # produce a shorter name (trim last 2 chars) but keep at least length 1
    if len(orig_name) <= 2:
        pytest.skip("Fixture name too short for shorter-name test")
    new_name = orig_name[:-2]

    ok = write_name_only_record(str(dst), offset, orig_name, new_name)
    assert ok, "write_name_only_record failed for shorter replacement"

    decoded = _read_decoded_at(dst, offset)
    parsed = PlayerRecord.from_bytes(decoded, offset)
    assert parsed.attributes == orig_attrs, "Attributes changed after shorter name save"
    assert new_name.encode("latin1") in decoded


def test_longer_name_without_slack_fails_and_file_unchanged(tmp_path):
    """Longer replacement that cannot be expanded in-place should fail and leave the file unchanged."""
    dst = tmp_path / "roundtrip3.fdi"
    shutil.copy2(FIXTURE, dst)

    original_bytes = dst.read_bytes()

    fdi = FDIFile(str(dst))
    fdi.load()

    offset, rec = _choose_player_with_name(fdi)
    assert offset is not None

    orig_name = getattr(rec, "name", "") or f"{getattr(rec,'given_name','') or ''} {getattr(rec,'surname','') or ''}".strip()
    # produce a longer name by appending characters
    new_name = orig_name + "EXTRA"
    # best-effort: if slack exists in fixture this might succeed; if so skip the "fails" assertion
    ok = write_name_only_record(str(dst), offset, orig_name, new_name)
    if ok:
        pytest.skip("Fixture contained slack allowing expansion; skipping the 'failure' assertion")
    # file must remain unchanged
    after_bytes = dst.read_bytes()
    assert after_bytes == original_bytes, "File modified despite failing safe name-only write"
