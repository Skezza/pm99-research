from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_2015_world_assets import AssetAuditError, build_asset_manifest, canonical_json_bytes  # noqa: E402


def _row(slot: int, *, fifa_id: int | None, url: str = "") -> dict[str, object]:
    fifa: dict[str, object] = {"status": "fallback-required" if fifa_id is None else "fifa16-exact-name-and-birth-date"}
    if fifa_id is not None:
        fifa.update({"fifa16_player_id": fifa_id, "fifa16_name": f"FIFA Player {slot}", "fifa16_headshot_url": url})
    return {
        "slot_index": slot,
        "player_carrier_id": 100 + slot,
        "player_family": "dd6360",
        "source_squad_index": slot + 1,
        "source_player": {"name": f"Player {slot}"},
        "fifa16": fifa,
    }


def _inputs() -> tuple[dict[str, object], dict[str, object]]:
    draft = {
        "schema_version": "pm99-world-2015-source-carrier-drafts-v1",
        "proposals": [
            {
                "carrier_id": 2,
                "baseline_name": "Example FC",
                "group": "spain",
                "fixed_roster_slot_count": 2,
                "source_country_catalog": "spain",
                "source_club_name": "Example",
                "source_selector": {"source_path": "example.txt"},
                "status": "source-squad-ready",
            },
            {
                "carrier_id": 9,
                "baseline_name": "Unresolved",
                "group": "unknown",
                "fixed_roster_slot_count": 1,
                "status": "no-captured-source-country",
            },
        ],
    }
    reconciliation = {
        "schema_version": "pm99-world-2015-source-player-reconciliation-v1",
        "carrier_plans": [{"carrier_id": 2, "rows": [_row(0, fifa_id=7, url="https://example/7.png"), _row(1, fifa_id=None)]}],
    }
    return draft, reconciliation


def test_manifest_marks_base_kits_as_unapproved_and_portrait_candidates() -> None:
    draft, reconciliation = _inputs()
    records = {
        "MINIESC.PKF": {2: {"file_name": "EQ960002.BMP", "bitmap_length": 10, "bitmap_sha256": "a" * 64}},
        "NANOESC.PKF": {2: {"file_name": "EQ960002.BMP", "bitmap_length": 8, "bitmap_sha256": "b" * 64}},
        "RIDIESC.PKF": {},
    }
    result = build_asset_manifest(draft=draft, reconciliation=reconciliation, kit_records=records)
    assert result["coverage"] == {
        "foreign_carrier_count": 2,
        "kit_status_counts": {"base-art-partial-needs-era-source": 1, "base-art-missing-needs-era-source": 1},
        "portrait_cached_approved_count": 0,
        "portrait_candidate_url_count": 1,
        "portrait_native_no_photo_count": 0,
        "portrait_needs_identity_safe_source_count": 1,
        "portrait_status_counts": {"fifa16-url-candidate": 1, "needs-identity-safe-era-source": 1},
        "source_squad_ready_carrier_count": 1,
        "source_squad_ready_fixed_slot_count": 2,
        "unique_final_player_carrier_count": 2,
        "recycled_player_carrier_count": 0,
    }
    club = result["clubs"][0]
    assert club["kit"]["archives"]["MINIESC.PKF"]["status"] == "base-art-present-not-era-approved"
    assert club["players"][0]["portrait"]["status"] == "fifa16-url-candidate"
    assert club["players"][1]["portrait"]["status"] == "needs-identity-safe-era-source"


def test_matching_receipt_is_the_only_cached_approved_portrait() -> None:
    draft, reconciliation = _inputs()
    result = build_asset_manifest(
        draft=draft,
        reconciliation=reconciliation,
        kit_records={name: {} for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")},
        portrait_receipts={"7": {"status": "cached-approved-era", "receipt": "receipt.json"}},
    )
    player = result["clubs"][0]["players"][0]
    assert player["portrait"]["status"] == "cached-approved-era"
    assert result["coverage"]["portrait_cached_approved_count"] == 1


def test_missing_reconciliation_for_source_ready_carrier_is_rejected() -> None:
    draft, reconciliation = _inputs()
    reconciliation["carrier_plans"] = []
    with pytest.raises(AssetAuditError, match="has no reconciliation plan"):
        build_asset_manifest(
            draft=draft,
            reconciliation=reconciliation,
            kit_records={name: {} for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")},
        )


def test_output_is_deterministic() -> None:
    draft, reconciliation = _inputs()
    kwargs = {
        "draft": draft,
        "reconciliation": reconciliation,
        "kit_records": {name: {} for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")},
    }
    first = build_asset_manifest(**kwargs)
    second = build_asset_manifest(**kwargs)
    assert hashlib.sha256(canonical_json_bytes(first)).hexdigest() == hashlib.sha256(canonical_json_bytes(second)).hexdigest()


def test_recycle_allocation_remaps_shared_foreign_slot_before_assets() -> None:
    draft, reconciliation = _inputs()
    reconciliation["carrier_plans"][0]["rows"][1]["player_carrier_id"] = 100
    allocation = {
        "schema_version": "pm99-world-2015-mode1-recycle-allocation-v1",
        "allocations": [{
            "recycle_team_carrier_id": 2,
            "recycle_team_slot_index": 1,
            "old_shared_mode1_carrier_id": 100,
            "new_foreign_player_carrier_id": 700,
            "mode0_source_team_carrier_id": 301,
            "appended_mode0_clone_carrier_id": 33366,
            "required_primary_fine_role_code": 4,
        }],
    }
    result = build_asset_manifest(
        draft=draft,
        reconciliation=reconciliation,
        kit_records={name: {} for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")},
        recycle_allocation=allocation,
    )
    player = result["clubs"][0]["players"][1]
    assert player["player_carrier_id"] == 700
    assert player["recycled_from_shared_player_carrier_id"] == 100
    assert result["coverage"]["unique_final_player_carrier_count"] == 2
    assert result["coverage"]["recycled_player_carrier_count"] == 1


def test_unallocated_duplicate_player_carrier_is_rejected() -> None:
    draft, reconciliation = _inputs()
    reconciliation["carrier_plans"][0]["rows"][1]["player_carrier_id"] = 100
    with pytest.raises(AssetAuditError, match="remains shared"):
        build_asset_manifest(
            draft=draft,
            reconciliation=reconciliation,
            kit_records={name: {} for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")},
        )
