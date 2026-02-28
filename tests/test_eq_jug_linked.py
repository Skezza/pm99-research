import struct

import app.eq_jug_linked as eq_jug_linked
from app.xor import xor_encode


def _encode_xor_u16_string(text: str) -> bytes:
    raw = text.encode("cp1252")
    return struct.pack("<H", len(raw)) + xor_encode(raw)


def _build_external_eq_payload(
    *,
    short_name: str,
    stadium_name: str,
    full_club_name: str,
    ent_ids: list[int],
    player_rows: list[tuple[int, int]],
    record_size: int = 700,
    mode_byte: int = 1,
):
    payload = bytearray(b"\x00" * 0x2A)
    payload[0x26:0x28] = struct.pack("<H", record_size)
    payload[0x29] = mode_byte

    cursor = 0x2A
    for text in (short_name, stadium_name):
        part = _encode_xor_u16_string(text)
        payload[cursor : cursor + len(part)] = part
        cursor += len(part)

    payload.extend(b"\x00")
    cursor += 1
    if record_size > 0x20C:
        payload.extend(b"\x00")
        cursor += 1

    part = _encode_xor_u16_string(full_club_name)
    payload[cursor : cursor + len(part)] = part
    cursor += len(part)

    cursor += 4
    if record_size >= 0x1FE:
        cursor += 4
    cursor += 2 + 2 + 2

    if mode_byte == 0:
        if record_size > 0x207:
            cursor += 2
        cursor += 4
        for text in ("Legacy A", "Legacy B", "Legacy C"):
            part = _encode_xor_u16_string(text)
            if len(payload) < cursor:
                payload.extend(b"\x00" * (cursor - len(payload)))
            payload[cursor : cursor + len(part)] = part
            cursor += len(part)
            if text == "Legacy A":
                cursor += 4
                cursor += 4
        cursor += 3
        cursor += 20 if record_size >= 0x1F9 else 10
        cursor += 15
        cursor += 46 if record_size >= 0x1F9 else 42
        if record_size < 700:
            if record_size < 0x1F9:
                pair_count = 7
            elif record_size < 0x203:
                pair_count = 17
            else:
                pair_count = 21
            cursor += pair_count * 2
        else:
            sparse_triplets = [(0, 90, 80)]
            if len(payload) <= cursor:
                payload.extend(b"\x00" * (cursor - len(payload)))
                payload.extend(b"\x00")
            payload[cursor] = len(sparse_triplets)
            cursor += 1
            for idx, left, right in sparse_triplets:
                payload[cursor : cursor + 3] = bytes([idx, left, right])
                cursor += 3

    link_base = cursor + 0x6E7
    total_size = link_base + 1 + len(ent_ids) * 4 + 1 + len(player_rows) * 5
    if len(payload) < total_size:
        payload.extend(b"\x00" * (total_size - len(payload)))

    payload[link_base] = len(ent_ids)
    pos = link_base + 1
    for ent_id in ent_ids:
        payload[pos : pos + 4] = struct.pack("<I", ent_id)
        pos += 4
    payload[pos] = len(player_rows)
    pos += 1
    for flag, player_id in player_rows:
        payload[pos] = flag
        payload[pos + 1 : pos + 5] = struct.pack("<I", player_id)
        pos += 5

    return bytes(payload)


def _build_single_entry_indexed_fdi(record_id: int, raw_payload: bytes) -> bytes:
    payload_offset = 0x14 + 4 + 1 + 4 + 4
    return (
        b"DMFIv1.0"
        + struct.pack("<I", 0)
        + struct.pack("<I", 0)
        + struct.pack("<I", 1)
        + struct.pack("<I", record_id)
        + b"\x00"
        + struct.pack("<I", payload_offset)
        + struct.pack("<I", len(raw_payload))
        + raw_payload
    )


def test_parse_eq_external_team_roster_payload_parses_external_jug_links():
    payload = _build_external_eq_payload(
        short_name="Real Madrid C.F.",
        stadium_name="Santiago Bernabeu",
        full_club_name="Real Madrid Club de Futbol",
        ent_ids=[501],
        player_rows=[(0, 5), (1, 83)],
    )

    roster = eq_jug_linked.parse_eq_external_team_roster_payload(
        payload,
        player_name_by_id={5: "Manuel SANCHIS", 83: "Fernando MORIENTES"},
    )

    assert roster is not None
    assert roster.short_name == "Real Madrid C.F."
    assert roster.stadium_name == "Santiago Bernabeu"
    assert roster.full_club_name == "Real Madrid Club de Futbol"
    assert roster.record_size == 700
    assert roster.mode_byte == 1
    assert roster.ent_count == 1
    assert roster.rows == [
        eq_jug_linked.EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=5, player_name="Manuel SANCHIS"),
        eq_jug_linked.EQLinkedRosterRow(slot_index=1, flag=1, player_record_id=83, player_name="Fernando MORIENTES"),
    ]


def test_parse_eq_external_team_roster_payload_rejects_legacy_mode_zero():
    payload = _build_external_eq_payload(
        short_name="Legacy Team",
        stadium_name="Legacy Ground",
        full_club_name="Legacy Club",
        ent_ids=[],
        player_rows=[],
        mode_byte=0,
    )

    roster = eq_jug_linked.parse_eq_external_team_roster_payload(payload, player_name_by_id={})
    assert roster is not None
    assert roster.mode_byte == 0
    assert roster.short_name == "Legacy Team"
    assert roster.rows == []


def test_parse_eq_external_team_roster_payload_parses_legacy_mode_zero_links():
    payload = _build_external_eq_payload(
        short_name="Blackburn R.",
        stadium_name="Ewood Park",
        full_club_name="Blackburn Rovers",
        ent_ids=[501],
        player_rows=[(0, 1851), (0, 1853)],
        mode_byte=0,
    )

    roster = eq_jug_linked.parse_eq_external_team_roster_payload(
        payload,
        player_name_by_id={1851: "David FLOWER", 1853: "Jude KENNA"},
    )

    assert roster is not None
    assert roster.mode_byte == 0
    assert roster.ent_count == 1
    assert roster.rows == [
        eq_jug_linked.EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=1851, player_name="David FLOWER"),
        eq_jug_linked.EQLinkedRosterRow(slot_index=1, flag=0, player_record_id=1853, player_name="Jude KENNA"),
    ]


def test_extract_jug_name_from_raw_payload_prefers_full_name_segment():
    decoded_prefix = b"\x00" * 10 + b"De Boer F.laFrank DE BOERxaaaa"
    raw_payload = xor_encode(decoded_prefix)

    assert eq_jug_linked._extract_jug_name_from_raw_payload(raw_payload) == "Frank de BOER"


def test_extract_jug_name_from_raw_payload_rejects_garbage():
    decoded_prefix = b"\x00" * 10 + b"junk data onlyaaaa"
    raw_payload = xor_encode(decoded_prefix)

    assert eq_jug_linked._extract_jug_name_from_raw_payload(raw_payload) == ""


def test_build_jug_player_name_index_uses_legacy_prefix_fallback(tmp_path):
    decoded_prefix = b"\x00" * 10 + b"De Boer F.laFrank DE BOERxaaaa"
    raw_payload = xor_encode(decoded_prefix)
    container = _build_single_entry_indexed_fdi(1790, raw_payload)
    player_file = tmp_path / "JUG98030.FDI"
    player_file.write_bytes(container)

    names = eq_jug_linked._build_jug_player_name_index(str(player_file))

    assert names == {1790: "Frank de BOER"}
