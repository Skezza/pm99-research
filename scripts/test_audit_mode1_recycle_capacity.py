"""Unit coverage for the read-only shared foreign-carrier release gate."""

from __future__ import annotations

from app.fdi_indexed import IndexedFDIFile
from scripts import audit_mode1_recycle_capacity as audit
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _write_mode1_recycle_fixture_base


def test_audit_reports_one_extra_slot_and_role_capacity(tmp_path) -> None:
    base, _package = _write_mode1_recycle_fixture_base(tmp_path)
    dbdat = base / "DBDAT"
    eq_path = dbdat / "EQ98030.FDI"
    original = eq_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(original)
    records = []
    for entry in indexed.entries:
        records.append((int(entry.record_id), entry.key, entry.decode_payload(original)))
    mode1_payload = next(payload for carrier, _key, payload in records if carrier == 308)
    records.append((309, "", mode1_payload))
    eq_path.write_bytes(_indexed_fdi(records))

    report = audit.audit_mode1_recycle_capacity(dbdat=dbdat)

    # The copied synthetic team duplicates all sixteen fixed foreign rows;
    # each therefore contributes one extra slot to the required transaction.
    assert report["shared_compact_player_count"] == 16
    assert report["recycle_required_slot_count"] == 16
    assert report["duplicate_slots"][0] == {
        "shared_compact_carrier_id": 1,
        "baseline_name": "Carrier A",
        "baseline_fine_roles": [0],
        "retained_mode1_team_carrier_id": 308,
        "recycle_required_for_mode1_team_carrier_ids": [309],
    }
    assert report["eligible_mode0_dd6361_source_count_by_primary_role"]["0"] == 16
    assert len(report["eligible_mode0_dd6361_sources_by_primary_role"]["0"]) == 16
    assert report["eligible_mode0_dd6361_sources_by_primary_role"]["0"][0]["carrier_id"] == 101
    assert report["role_codes_without_eligible_mode0_source"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    assert report["role_codes_with_qualified_paired_clone_provision_route"] == [3]
    assert report["role_codes_without_eligible_or_provisioned_mode0_source"] == [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    assert report["runtime_qualified_primary_fine_role_codes"] == [0, 3, 4, 8, 9, 12]
    assert report["release_status"] == "blocked"
