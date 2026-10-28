from types import SimpleNamespace
import pytest
from app.bitmap_pixel_rows import read_top_down_bitmap_rows
from scripts.season_factory_bitmap_envelope_v1 import wrap_factory_pixels


def record(offset, pixels, width=3, height=2, bpp=8):
    raw = bytes([73] * offset) + bytes(pixels) + b'opaque-tail'
    return SimpleNamespace(width=width, height=height, bits_per_pixel=bpp,
        pixel_offset=offset, raw_bitmap=raw)


def test_different_header_lengths_copy_literal_indices_preserve_opaque_bytes():
    # Width3 uses4-byte native scanlines; preserve fourth-byte row padding.
    source = record(28, [1, 2, 3, 17, 4, 5, 6, 18])
    target = record(26, [8, 8, 8, 99, 9, 9, 9, 98])
    raw, proof = wrap_factory_pixels(source, target)
    assert raw[:26] == target.raw_bitmap[:26]
    assert raw[26:34] == bytes([1, 2, 3, 99, 4, 5, 6, 98])
    assert raw[34:] == b'opaque-tail'
    assert len(raw) == len(target.raw_bitmap)
    assert source.raw_bitmap[28:36] == bytes([1, 2, 3, 17, 4, 5, 6, 18])
    wrapped = SimpleNamespace(**{**vars(target), 'raw_bitmap': raw})
    assert read_top_down_bitmap_rows(wrapped) == read_top_down_bitmap_rows(source)
    assert proof['target_header_padding_and_length_preserved']


@pytest.mark.parametrize('field,value', [('width', 2), ('height', 1), ('bits_per_pixel', 24)])
def test_reject_incompatible_geometry(field, value):
    source = record(28, range(8))
    target = record(26, range(8))
    setattr(target, field, value)
    with pytest.raises(ValueError, match='identical indexed geometry'):
        wrap_factory_pixels(source, target)


def archive(source_offset=28, source_tail=b''):
    import struct
    from app.minifoto_bitmap_archive import encode_obfuscated_bitmap_name
    def bmp(offset, pixels, tail=b''):
        raw = bytearray(offset + 8 + len(tail))
        raw[:2] = b'BM'
        struct.pack_into('<I', raw, 2, len(raw))
        struct.pack_into('<II', raw, 10, offset, 12)
        struct.pack_into('<HHHH', raw, 18, 3, 2, 1, 8)
        raw[offset:offset+8] = bytes(pixels)
        raw[offset+8:] = tail
        return bytes(raw)
    items = [('EQ960818.BMP', bmp(source_offset, [1, 2, 3, 17, 4, 5, 6, 18], source_tail)),
             ('EQ960819.BMP', bmp(26, [7, 7, 7, 19, 7, 7, 7, 20])),
             ('EQ960821.BMP', bmp(26, [8, 8, 8, 99, 9, 9, 9, 98]))]
    result = bytearray(38 * len(items))
    for index, (name, raw) in enumerate(items):
        start = index * 38
        result[start] = 2
        result[start+1:start+21] = encode_obfuscated_bitmap_name(name)
        struct.pack_into('<II', result, start+26, len(result), len(raw))
        result.extend(raw)
    return bytes(result)


@pytest.mark.parametrize('offset,tail', [(28, b''), (26, b'xy')])
def test_source_pkf_absolute_offsets_and_unselected_records_survive(tmp_path, monkeypatch, offset, tail):
    from scripts import season_factory_bitmap_envelope_v1 as envelope
    monkeypatch.setattr(envelope.registry, 'ROOT', tmp_path)
    source = tmp_path/'factory'; target = tmp_path/'game/DBDAT'
    source.mkdir(); target.mkdir(parents=True)
    original = archive(offset, tail)
    for name in envelope.ARCHIVES:
        (source/name).write_bytes(original)
        (target/name).write_bytes(original)
    release = SimpleNamespace(season='2002-03', release_id='fixture',
        game_path=target.parent, manifest_sha256='a'*64)
    output = tmp_path/'source-envelope'
    receipt = envelope.create_source_envelope(release=release, source_dir=source,
        source_team_id=818, target_team_id=821, output=output)
    for name in envelope.ARCHIVES:
        transformed = (output/name).read_bytes()
        before = envelope.records(name, original)
        after = envelope.records(name, transformed)
        assert len(transformed) == len(original)
        assert [(r.file_name, r.bitmap_offset) for r in before] == [
            (r.file_name, r.bitmap_offset) for r in after]
        assert after[0].bitmap_length == before[0].bitmap_length-2
        assert read_top_down_bitmap_rows(after[0]) == read_top_down_bitmap_rows(before[0])
        assert [r.raw_bitmap for r in after[1:]] == [r.raw_bitmap for r in before[1:]]
        assert (target/name).read_bytes() == original
        assert (source/name).read_bytes() == original
    assert receipt['no_playable_game_or_original_source_writes']
    with pytest.raises(ValueError, match='must be new'):
        envelope.create_source_envelope(release=release, source_dir=source,
            source_team_id=818, target_team_id=821, output=output)
