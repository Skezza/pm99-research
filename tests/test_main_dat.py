import pytest

from app.main_dat import (
    MainDatParseError,
    PM99MainDatExtendedPrelude,
    PM99MainDatFile,
    PM99MainDatPrefix,
    PM99PackedDate,
    decode_pm99_u16_xor_string,
    decode_pm99_u8_xor_string,
    encode_pm99_u16_xor_string,
    encode_pm99_u8_xor_string,
    load_main_dat,
    parse_main_dat,
    save_main_dat,
    update_main_dat,
)


def _sample_prefix():
    return PM99MainDatPrefix(
        header_version=0x1E,
        format_version=0x0C,
        primary_label="Manager Slot",
        secondary_label="Save Profile",
        save_date=PM99PackedDate(day=26, month=2, year=2026),
        hour=14,
        minute=37,
        flag_bytes=(1, 0, 1, 1, 0, 0, 1, 0, 1, 0),
        scalar_byte=7,
    )


def test_u16_xor_string_roundtrip():
    encoded = encode_pm99_u16_xor_string("Premier Manager 99")
    assert decode_pm99_u16_xor_string(encoded) == "Premier Manager 99"


def test_u8_xor_string_roundtrip():
    encoded = encode_pm99_u8_xor_string("Short Field")
    assert decode_pm99_u8_xor_string(encoded) == "Short Field"


def test_parse_main_dat_roundtrips_prefix_only():
    parsed = PM99MainDatFile(prefix=_sample_prefix())

    data = parsed.to_bytes()
    reparsed = parse_main_dat(data)

    assert reparsed.prefix == parsed.prefix
    assert reparsed.extended_prelude is None
    assert reparsed.opaque_tail == b""
    assert reparsed.source_size == len(data)
    assert reparsed.to_bytes() == data


def test_parse_main_dat_roundtrips_extended_prelude_and_opaque_tail():
    parsed = PM99MainDatFile(
        prefix=_sample_prefix(),
        extended_prelude=PM99MainDatExtendedPrelude(
            global_byte_a=0x41,
            global_byte_b=0x19,
            secondary_date=PM99PackedDate(day=27, month=2, year=2026),
        ),
        opaque_tail=bytes.fromhex("112233445566778899aabbcc"),
    )

    data = parsed.to_bytes()
    reparsed = parse_main_dat(data)

    assert reparsed.prefix == parsed.prefix
    assert reparsed.extended_prelude == parsed.extended_prelude
    assert reparsed.opaque_tail == parsed.opaque_tail
    assert reparsed.to_bytes() == data


def test_load_and_save_main_dat(tmp_path):
    source = tmp_path / "main.dat"
    target = tmp_path / "main_copy.dat"
    parsed = PM99MainDatFile(
        prefix=_sample_prefix(),
        extended_prelude=PM99MainDatExtendedPrelude(
            global_byte_a=2,
            global_byte_b=3,
            secondary_date=PM99PackedDate(day=1, month=3, year=2026),
        ),
        opaque_tail=b"\xAA\xBB\xCC",
    )
    source.write_bytes(parsed.to_bytes())

    loaded = load_main_dat(source)
    written = save_main_dat(target, loaded)

    assert written == target
    assert target.read_bytes() == source.read_bytes()


def test_parse_main_dat_rejects_truncated_prefix():
    with pytest.raises(MainDatParseError):
        parse_main_dat(b"\x1e\x00")


def test_update_main_dat_preserves_unresolved_tail():
    original = PM99MainDatFile(
        prefix=_sample_prefix(),
        extended_prelude=PM99MainDatExtendedPrelude(
            global_byte_a=0x12,
            global_byte_b=0x34,
            secondary_date=PM99PackedDate(day=28, month=2, year=2026),
        ),
        opaque_tail=bytes.fromhex("00112233"),
    )

    updated = update_main_dat(
        original,
        primary_label="Edited Slot",
        hour=22,
        minute=59,
        scalar_byte=9,
        flag_updates={0: 7, 9: 3},
    )

    assert updated.prefix.primary_label == "Edited Slot"
    assert updated.prefix.hour == 22
    assert updated.prefix.minute == 59
    assert updated.prefix.scalar_byte == 9
    assert updated.prefix.flag_bytes[0] == 7
    assert updated.prefix.flag_bytes[9] == 3
    assert updated.opaque_tail == original.opaque_tail
    reparsed = parse_main_dat(updated.to_bytes())
    assert reparsed.extended_prelude == original.extended_prelude
    assert reparsed.opaque_tail == original.opaque_tail
