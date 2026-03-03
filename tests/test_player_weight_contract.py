"""Contract tests for player weight extraction."""

import struct
from pathlib import Path
from types import SimpleNamespace

from app.editor_actions import (
    batch_edit_player_metadata_records,
    build_player_visible_skill_index_dd6361,
    edit_player_metadata_records,
    inspect_player_metadata_records,
    profile_indexed_player_attribute_prefixes,
    profile_player_legacy_weight_candidates,
    profile_indexed_player_leading_bytes,
    profile_indexed_player_suffix_bytes,
)
from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import decode_entry, write_string


def _build_legacy_weight_payload(*, weight: int = 78) -> bytes:
    year_bytes = struct.pack("<H", 1974)
    decoded = bytearray()
    decoded += struct.pack("<H", 42)
    decoded += bytes([8, 0, 0])
    decoded += write_string("Paul")
    decoded += write_string("SCHOLES")
    decoded += b"\x61" * 4
    metadata = bytearray(b"\x00" * 11)
    metadata[3] = 2 ^ 0x61
    metadata[4] = 44 ^ 0x61
    metadata[5] = 16 ^ 0x61
    metadata[6] = 11 ^ 0x61
    metadata[7] = year_bytes[0] ^ 0x61
    metadata[8] = year_bytes[1] ^ 0x61
    metadata[9] = 178 ^ 0x61
    metadata[10] = int(weight) ^ 0x61
    decoded += metadata
    decoded += bytes([50 ^ 0x61] * 12)
    decoded += b"\x00" * 7
    return bytes(decoded)


def test_weight_is_not_marker_backed_in_roundtrip():
    base = PlayerRecord(
        given_name="David",
        surname="Batty",
        team_id=42,
        squad_number=6,
        nationality=44,
        position_primary=2,
        birth_day=2,
        birth_month=12,
        birth_year=1968,
        height=178,
        weight=81,
        skills=[60] * 10,
        version=700,
    )

    encoded = base.to_bytes()
    decoded_payload, _ = decode_entry(encoded, 0)
    reparsed = PlayerRecord.from_bytes(decoded_payload, 0, 700)

    assert base.weight == 81
    assert reparsed.weight is None


def test_indexed_jug_payload_extracts_weight_from_suffix_block():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes
    payload = entry.decode_payload(player_file.read_bytes())

    reparsed = PlayerRecord.from_bytes(payload, entry.payload_offset, 700)

    assert reparsed.name == "Paul SCHOLES"
    assert reparsed.indexed_unknown_0 == 10
    assert reparsed.indexed_unknown_1 == 0
    assert reparsed.indexed_face_components == [12, 8, 15, 7]
    assert reparsed.nationality == 30
    assert reparsed.indexed_unknown_9 == 1
    assert reparsed.indexed_unknown_10 == 5
    assert reparsed.position_primary == 2
    assert (reparsed.birth_day, reparsed.birth_month, reparsed.birth_year) == (16, 11, 1974)
    assert reparsed.height == 170
    assert reparsed.weight == 68


def test_legacy_marker_backed_payload_extracts_weight_when_dedicated_slot_exists():
    payload = _build_legacy_weight_payload(weight=78)

    reparsed = PlayerRecord.from_bytes(payload, 0, 700)

    assert reparsed.name == "Paul SCHOLES"
    assert reparsed.nationality == 44
    assert reparsed.position_primary == 2
    assert (reparsed.birth_day, reparsed.birth_month, reparsed.birth_year) == (16, 11, 1974)
    assert reparsed.height == 178
    assert reparsed.weight == 78


def test_legacy_marker_backed_weight_roundtrips_on_write():
    payload = _build_legacy_weight_payload(weight=78)
    record = PlayerRecord.from_bytes(payload, 0, 700)
    record.weight = 81

    rewritten = record.to_bytes()
    reparsed = PlayerRecord.from_bytes(rewritten, 0, 700)

    assert reparsed.weight == 81


def test_indexed_jug_suffix_metadata_roundtrips_on_write():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes
    payload = entry.decode_payload(player_file.read_bytes())

    record = PlayerRecord.from_bytes(payload, entry.payload_offset, 700)
    original_leading_unknowns = (record.indexed_unknown_0, record.indexed_unknown_1)
    original_unknowns = (record.indexed_unknown_9, record.indexed_unknown_10)
    record.nationality = 44
    record.position_primary = 3
    record.birth_day = 1
    record.birth_month = 12
    record.birth_year = 1976
    record.height = 181
    record.weight = 81

    rewritten = record.to_bytes()
    reparsed = PlayerRecord.from_bytes(rewritten, entry.payload_offset, 700)

    assert reparsed.nationality == 44
    assert (reparsed.indexed_unknown_0, reparsed.indexed_unknown_1) == original_leading_unknowns
    assert (reparsed.indexed_unknown_9, reparsed.indexed_unknown_10) == original_unknowns
    assert reparsed.position_primary == 3
    assert (reparsed.birth_day, reparsed.birth_month, reparsed.birth_year) == (1, 12, 1976)
    assert reparsed.height == 181
    assert reparsed.weight == 81


def test_indexed_player_edit_stages_weight_change_without_writing():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes

    result = edit_player_metadata_records(
        str(player_file),
        "Paul SCHOLES",
        target_offset=entry.payload_offset,
        height=181,
        weight=81,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["height"] == (170, 181)
    assert result.changes[0].changed_fields["weight"] == (68, 81)
    assert len(result.staged_records) == 1


def test_indexed_player_edit_stages_name_change_without_writing():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes

    result = edit_player_metadata_records(
        str(player_file),
        target_offset=entry.payload_offset,
        new_name="Alan SMITH",
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["name"] == ("Paul SCHOLES", "Alan SMITH")
    assert len(result.staged_records) == 1


def test_indexed_player_batch_edit_stages_csv_changes_without_writing(tmp_path):
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes
    plan_path = tmp_path / "player_batch.csv"
    plan_path.write_text(
        "name,offset,new_name,height,weight\n"
        f"Paul SCHOLES,0x{entry.payload_offset:X},Alan SMITH,181,81\n",
        encoding="utf-8",
    )

    result = batch_edit_player_metadata_records(
        str(player_file),
        str(plan_path),
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.row_count == 1
    assert result.matched_row_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["name"] == ("Paul SCHOLES", "Alan SMITH")
    assert result.changes[0].changed_fields["height"] == (170, 181)
    assert result.changes[0].changed_fields["weight"] == (68, 81)
    assert len(result.staged_records) == 1


def test_indexed_player_inspect_surfaces_unknown_suffix_bytes():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes

    result = inspect_player_metadata_records(
        str(player_file),
        "Paul SCHOLES",
        target_offset=entry.payload_offset,
    )

    assert result.matched_count == 1
    assert len(result.records) == 1
    row = result.records[0]
    assert row.record_id == 3384
    assert row.attribute_prefix == [77, 89, 107]
    assert row.indexed_unknown_0 == 10
    assert row.indexed_unknown_1 == 0
    assert row.face_components == [12, 8, 15, 7]
    assert row.nationality == 30
    assert row.indexed_unknown_9 == 1
    assert row.indexed_unknown_10 == 5
    assert row.position == 2
    assert (row.birth_day, row.birth_month, row.birth_year) == (16, 11, 1974)
    assert row.height == 170
    assert row.weight == 68
    assert row.post_weight_byte == 30
    assert row.trailer_byte == 13
    assert row.sidecar_byte == 0


def test_non_indexed_player_inspect_surfaces_marker_backed_fields(tmp_path, monkeypatch):
    player_file = tmp_path / "LEGACY.FDI"
    player_file.write_bytes(b"legacy-player-data")

    legacy_record = PlayerRecord(
        given_name="David",
        surname="BATTY",
        team_id=42,
        squad_number=6,
        nationality=44,
        position_primary=2,
        birth_day=2,
        birth_month=12,
        birth_year=1968,
        height=178,
        skills=[60] * 10,
        version=700,
    )
    monkeypatch.setattr(
        "app.editor_actions.gather_player_records",
        lambda _path: ([SimpleNamespace(offset=0x200, record=legacy_record, source="entry")], []),
    )

    result = inspect_player_metadata_records(
        str(player_file),
        "David BATTY",
        target_offset=0x200,
    )

    assert result.storage_mode == "name_only"
    assert result.record_count == 1
    assert result.matched_count == 1
    row = result.records[0]
    assert row.offset == 0x200
    assert row.name == "David BATTY"
    assert row.source == "entry"
    assert row.attribute_prefix == list(legacy_record.attributes[:3])
    assert row.nationality == 44
    assert row.position == 2
    assert (row.birth_day, row.birth_month, row.birth_year) == (2, 12, 1968)
    assert row.height == 178
    assert row.weight is None
    assert row.post_weight_byte is None
    assert row.trailer_byte is None
    assert row.sidecar_byte is None
    assert row.face_components == []


def test_indexed_control_set_points_to_marker_plus_14_for_legacy_weight():
    result = profile_player_legacy_weight_candidates("DBDAT/JUG98030.FDI")

    assert result.record_count >= 10000
    assert result.candidate_record_count >= 1000
    assert result.recommended_offset == 14
    assert result.legacy_valid_record_count > 0
    assert result.legacy_slot_record_count > 0
    assert result.legacy_matched_record_count > 0
    assert result.legacy_exact_match_ratio > 0.5
    offset_14 = next(row for row in result.offsets if row.relative_offset == 14)
    offset_17 = next(row for row in result.offsets if row.relative_offset == 17)
    assert offset_14.exact_match_ratio > 0.45
    assert offset_17.exact_match_ratio == 0.0
    assert offset_14.exact_match_ratio > offset_17.exact_match_ratio


def test_indexed_tail_prefix_profile_surfaces_structural_buckets():
    result = profile_indexed_player_attribute_prefixes(
        "DBDAT/JUG98030.FDI",
        nationality=30,
        position=2,
        indexed_unknown_0=10,
        indexed_unknown_1=0,
        indexed_unknown_9=1,
        indexed_unknown_10=5,
        limit=5,
    )

    assert result.record_count >= 10000
    assert result.anchored_count >= 1000
    assert result.filtered_count >= 1
    assert result.layout_verified_count >= 1
    assert result.layout_mismatch_count == 0
    assert result.buckets
    assert result.attribute_2_counts
    assert result.attribute_2_counts[0][0] == 107
    assert result.post_weight_byte_counts
    assert result.post_weight_byte_counts[0][0] == 30
    assert result.post_weight_nationality_eligible_count >= 1
    assert result.post_weight_nationality_match_count >= 1
    assert result.post_weight_nationality_match_ratio >= 1.0
    assert result.sidecar_byte_counts
    top = result.buckets[0]
    assert (top.attribute_0, top.attribute_1, top.attribute_2) == (77, 89, 107)
    assert top.count >= 1
    assert result.signature_buckets
    top_signature = result.signature_buckets[0]
    assert (
        top_signature.attribute_0,
        top_signature.attribute_1,
        top_signature.attribute_2,
    ) == (77, 89, 107)
    assert top_signature.trailer_byte is not None
    assert top_signature.sidecar_byte is not None
    assert top_signature.count >= 1


def test_indexed_tail_signature_profile_can_isolate_a2_25_trailer_family():
    result = profile_indexed_player_attribute_prefixes(
        "DBDAT/JUG98030.FDI",
        attribute_2=25,
        trailer_byte=19,
        limit=3,
    )

    assert result.filtered_count >= 100
    assert result.layout_mismatch_count == 0
    assert result.signature_buckets
    top_signature = result.signature_buckets[0]
    assert (
        top_signature.attribute_0,
        top_signature.attribute_1,
        top_signature.attribute_2,
        top_signature.trailer_byte,
    ) == (1, 0, 25, 19)
    assert top_signature.sidecar_byte == 0
    assert top_signature.count >= 100


def test_indexed_tail_signature_profile_sidecar_filter_splits_a2_25_trail_19_family():
    result = profile_indexed_player_attribute_prefixes(
        "DBDAT/JUG98030.FDI",
        attribute_2=25,
        trailer_byte=19,
        sidecar_byte=1,
        limit=2,
    )

    assert result.filtered_count >= 10
    assert result.layout_mismatch_count == 0
    assert result.sidecar_byte_counts
    assert result.sidecar_byte_counts[0][0] == 1
    assert result.signature_buckets
    top_signature = result.signature_buckets[0]
    assert (
        top_signature.attribute_0,
        top_signature.attribute_1,
        top_signature.attribute_2,
        top_signature.trailer_byte,
        top_signature.sidecar_byte,
    ) == (1, 0, 25, 19, 1)
    assert top_signature.count >= 10


def test_indexed_tail_signature_profile_post_weight_filter_can_isolate_a2_25_family():
    result = profile_indexed_player_attribute_prefixes(
        "DBDAT/JUG98030.FDI",
        attribute_2=25,
        trailer_byte=19,
        post_weight_byte=30,
        limit=2,
    )

    assert result.filtered_count >= 100
    assert result.layout_mismatch_count == 0
    assert result.post_weight_byte_counts
    assert result.post_weight_byte_counts[0][0] == 30
    assert result.signature_buckets
    top_signature = result.signature_buckets[0]
    assert (
        top_signature.attribute_0,
        top_signature.attribute_1,
        top_signature.attribute_2,
        top_signature.trailer_byte,
        top_signature.sidecar_byte,
    ) == (1, 0, 25, 19, 0)


def test_indexed_post_weight_byte_mostly_matches_nationality_on_real_corpus():
    result = profile_indexed_player_attribute_prefixes(
        "DBDAT/JUG98030.FDI",
        limit=3,
    )

    assert result.anchored_count >= 1000
    assert result.post_weight_nationality_eligible_count >= 1000
    assert result.post_weight_nationality_match_count >= 1000
    assert result.post_weight_nationality_match_ratio > 0.9
    assert result.post_weight_divergent_counts
    assert result.post_weight_divergent_counts[0][0] == 30
    assert result.post_weight_nationality_mismatch_pairs
    top_mismatch = result.post_weight_nationality_mismatch_pairs[0]
    assert top_mismatch[0] == 30
    assert top_mismatch[1] == 31
    assert top_mismatch[2] >= 10


def test_indexed_tail_layout_helper_matches_current_real_record():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    entry = next(item for item in indexed.entries if item.record_id == 3384)  # Paul Scholes
    payload = entry.decode_payload(player_file.read_bytes())
    record = PlayerRecord.from_bytes(payload, entry.payload_offset)
    name = f"{record.given_name} {record.surname}".strip()

    layout = PlayerRecord._analyze_indexed_tail_layout(payload, name)

    assert layout is not None
    assert layout["layout_matches_expected"] is True
    assert layout["attribute_start"] == len(payload) - 19
    assert layout["final_block_cutoff"] == (len(payload) - 16)
    assert layout["fixed_skip_end"] == (len(payload) - 6)


def test_trailing_attribute_window_slots_3_to_11_match_dd6361_visible_skills():
    player_file = Path("DBDAT/JUG98030.FDI")
    indexed = IndexedFDIFile.from_path(player_file)
    visible_index = build_player_visible_skill_index_dd6361(file_path=str(player_file))
    expected_fields = {
        3: "speed",
        4: "stamina",
        5: "aggression",
        6: "quality",
        7: "heading",
        8: "dribbling",
        9: "passing",
        10: "shooting",
        11: "tackling",
    }
    exact_matches = {index: 0 for index in expected_fields}
    matched_count = 0
    file_bytes = player_file.read_bytes()

    for entry in indexed.entries:
        visible = visible_index.get(int(entry.record_id))
        if not visible:
            continue
        mapped10 = dict(visible.get("mapped10") or {})
        if any(field not in mapped10 for field in expected_fields.values()):
            continue
        payload = entry.decode_payload(file_bytes)
        record = PlayerRecord.from_bytes(payload, entry.payload_offset, 700)
        matched_count += 1
        for attr_index, field_name in expected_fields.items():
            if int(record.attributes[attr_index]) == int(mapped10[field_name]):
                exact_matches[attr_index] += 1

    assert matched_count >= 2000
    for attr_index in expected_fields:
        assert exact_matches[attr_index] / matched_count > 0.99


def test_indexed_player_suffix_profile_groups_nationality_44_players():
    player_file = Path("DBDAT/JUG98030.FDI")

    result = profile_indexed_player_suffix_bytes(
        str(player_file),
        nationality=44,
        limit=3,
    )

    assert result.anchored_count >= result.filtered_count >= 20
    assert result.nationality_filter == 44
    assert result.buckets
    top = result.buckets[0]
    assert (top.indexed_unknown_9, top.indexed_unknown_10) == (1, 1)
    assert top.count >= 20


def test_indexed_player_leading_profile_groups_nationality_30_players():
    player_file = Path("DBDAT/JUG98030.FDI")

    result = profile_indexed_player_leading_bytes(
        str(player_file),
        nationality=30,
        limit=3,
    )

    assert result.anchored_count >= result.filtered_count >= 1000
    assert result.nationality_filter == 30
    assert result.buckets
    top = result.buckets[0]
    assert (top.indexed_unknown_0, top.indexed_unknown_1) == (7, 0)
    assert top.count >= 50


def test_indexed_player_leading_profile_can_filter_by_suffix_pair():
    player_file = Path("DBDAT/JUG98030.FDI")

    result = profile_indexed_player_leading_bytes(
        str(player_file),
        nationality=30,
        indexed_unknown_9=1,
        indexed_unknown_10=5,
        limit=3,
    )

    assert result.filtered_count >= 20
    assert result.indexed_unknown_9_filter == 1
    assert result.indexed_unknown_10_filter == 5
    assert result.buckets
    top = result.buckets[0]
    assert (top.indexed_unknown_0, top.indexed_unknown_1) == (10, 0)
    assert top.count >= 4


def test_indexed_player_leading_profile_can_filter_by_u1_bucket():
    player_file = Path("DBDAT/JUG98030.FDI")

    result = profile_indexed_player_leading_bytes(
        str(player_file),
        indexed_unknown_1=1,
        limit=3,
    )

    assert result.filtered_count >= 400
    assert result.indexed_unknown_1_filter == 1
    assert result.buckets
    top = result.buckets[0]
    assert (top.indexed_unknown_0, top.indexed_unknown_1) == (19, 1)
    assert top.count >= 30
