from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import apply_stock_kit_seed_remap_v1 as remap


ARCHIVES = remap.ARCHIVES
SOURCE_HASHES = {name: f"{i:064x}" for name, i in zip(ARCHIVES, (1, 2, 3))}
PARENT_ARCHIVES = {name: f"{i + 10:064x}" for i, name in enumerate(ARCHIVES)}
BITMAP_SOURCE = {name: f"{i + 20:064x}" for i, name in enumerate(ARCHIVES)}
BITMAP_TARGET = {name: f"{i + 30:064x}" for i, name in enumerate(ARCHIVES)}


def candidate(*, source_id=1107, target_id=1104, club_id="club-1104", artifacts=None):
    original = {"kit_policy": "preserve-existing-mode1", "kit_artifact_ids": artifacts or []}
    row = {
        "season": "2000-01",
        "club_id": club_id,
        "target_carrier_id": target_id,
        "source_baseline_carrier_id": source_id,
        "status": "candidate-only; no kit change approved",
        "candidate_source": "25-season fixed-registry audit",
        "current_logical_club": "Basel",
        "current_carrier_id": target_id,
        "target_stock_seed_name": "Basel",
        "target_stock_seed_full_name": "FC BASEL",
        "source_candidate_sha256": hashlib.sha256(pipeline.canonical_json_bytes(original)).hexdigest(),
        "audit_binding": {
            "catalog_release_id": "release-parent",
            "catalog_manifest_sha256": "a" * 64,
            "rebound_package_sha256": "b" * 64,
            "current_actual_compact_archive_sha256": PARENT_ARCHIVES,
        },
        "stock_seed_and_pixel_evidence": {
            "target_current_pixels_equal_own_clean_seed_all_archives": True,
            "source_target_record_shape_compatible_all_archives": True,
            "source_bitmap_sha256_by_archive": BITMAP_SOURCE,
            "target_current_bitmap_sha256_by_archive": BITMAP_TARGET,
            "target_clean_seed_bitmap_sha256_by_archive": BITMAP_TARGET,
        },
        "preserved_original_candidate_row": original,
    }
    row["case_id"] = remap.case_id_for(row)
    return row


def checklist_with(*rows):
    return {
        "schema": remap.SCHEMA,
        "validation": {"unique_case_ids": True, "total_cases": len(rows)},
        "source_inputs": {"legacy_seed_dbdat_hashes": SOURCE_HASHES},
        "cases": list(rows),
    }


def validate(doc, *, case_ids=(), source_hashes=None, parent_manifest="a" * 64):
    raw = pipeline.canonical_json_bytes(doc)
    return remap.validate_checklist_bytes(
        raw,
        expected_checklist_sha256=hashlib.sha256(raw).hexdigest(),
        season="2000-01",
        parent_release_id="release-parent",
        parent_manifest_sha256=parent_manifest,
        source_archive_sha256s=source_hashes or SOURCE_HASHES,
        case_ids=case_ids,
    )


def test_valid_candidate_is_selected_and_normalized():
    row = candidate()
    _, selected = validate(checklist_with(row), case_ids=[row["case_id"]])
    assert len(selected) == 1
    assert selected[0]["source_carrier_id"] == 1107
    assert selected[0]["target_carrier_id"] == 1104
    assert selected[0]["artifact_ids"] == []


def test_current_archive_sha256_binding_field_is_supported():
    row = candidate()
    binding = row["audit_binding"]
    binding["current_archive_sha256"] = binding.pop("current_actual_compact_archive_sha256")
    _, selected = validate(checklist_with(row))
    assert selected[0]["current_archive_sha256s"] == PARENT_ARCHIVES


def test_repeated_clean_donor_is_allowed_for_distinct_targets():
    first = candidate(source_id=1107, target_id=1104, club_id="club-1104")
    second = candidate(source_id=1107, target_id=1105, club_id="club-1105")
    _, selected = validate(checklist_with(first, second))
    assert [row["source_carrier_id"] for row in selected] == [1107, 1107]
    assert [row["target_carrier_id"] for row in selected] == [1104, 1105]


def test_duplicate_target_carrier_is_rejected():
    first = candidate(source_id=1107, target_id=1104, club_id="club-1104")
    second = candidate(source_id=1106, target_id=1104, club_id="club-1104-other")
    with pytest.raises(remap.StockKitRemapError, match="reuse a target"):
        validate(checklist_with(first, second))


def test_changed_checklist_bytes_fail_explicit_hash_binding():
    raw = pipeline.canonical_json_bytes(checklist_with(candidate())) + b" "
    with pytest.raises(remap.StockKitRemapError, match="checklist SHA"):
        remap.validate_checklist_bytes(raw, expected_checklist_sha256="0" * 64,
            season="2000-01", parent_release_id="release-parent",
            parent_manifest_sha256="a" * 64, source_archive_sha256s=SOURCE_HASHES)


def test_changed_source_archive_hash_fails():
    with pytest.raises(remap.StockKitRemapError, match="hashes differ"):
        validate(checklist_with(candidate()), source_hashes={**SOURCE_HASHES, "MINIESC.PKF": "f" * 64})


def test_changed_parent_manifest_fails():
    with pytest.raises(remap.StockKitRemapError, match="another parent"):
        validate(checklist_with(candidate()), parent_manifest="c" * 64)


def test_sourced_kit_artifacts_are_rejected():
    row = candidate(artifacts=["reviewed-season-kit"])
    with pytest.raises(remap.StockKitRemapError, match="sourced/protected"):
        validate(checklist_with(row))


def test_wrong_case_id_is_rejected():
    row = candidate()
    row["case_id"] = "kit-stock-seed-remap-" + "0" * 20
    with pytest.raises(remap.StockKitRemapError, match="case ID"):
        validate(checklist_with(row))


def test_own_seed_preimage_must_equal_current_target():
    row = candidate()
    row["stock_seed_and_pixel_evidence"]["target_clean_seed_bitmap_sha256_by_archive"] = {
        **BITMAP_TARGET, "RIDIESC.PKF": "f" * 64
    }
    with pytest.raises(remap.StockKitRemapError, match="not its own clean-seed"):
        validate(checklist_with(row))


def test_selection_cannot_include_another_seasons_case():
    row = candidate()
    with pytest.raises(remap.StockKitRemapError, match="do not belong to this season"):
        validate(checklist_with(row), case_ids=["kit-stock-seed-remap-" + "1" * 20])


def test_legacy_2015_candidate_row_shape_is_supported():
    row = {
        "season": "2015-16", "club_id": "legacy-carrier-1104", "target_carrier_id": 1104,
        "source_baseline_carrier_id": 1107, "current_carrier_id": 1104,
        "current_logical_club": "Basel", "target_stock_seed_club_name": "Basel",
        "target_stock_seed_full_name": "FC BASEL", "status": "candidate-only; no kit change approved",
        "current_package_kit_policy": "preserve-existing-mode1", "current_package_kit_artifact_ids": [],
        "source_candidate_sha256": "d" * 64,
        "audit_binding": {"release_id": "release-parent", "release_manifest_sha256": "a" * 64,
            "package_sha256": "b" * 64, "current_compact_archive_sha256": PARENT_ARCHIVES},
        "archives": {name: {"current_equals_own_clean_seed": True,
            "source_target_size_compatible": True,
            "source_clean_seed_bitmap_sha256": BITMAP_SOURCE[name],
            "carrier_current_bitmap_sha256": BITMAP_TARGET[name],
            "own_clean_seed_bitmap_sha256": BITMAP_TARGET[name]} for name in ARCHIVES},
    }
    row["case_id"] = remap.case_id_for(row)
    doc = {"schema": remap.SCHEMA, "validation": {"unique_case_ids": True, "total_cases": 1},
        "source_inputs": {"legacy_seed_dbdat_hashes": SOURCE_HASHES}, "cases": [row]}
    raw = pipeline.canonical_json_bytes(doc)
    _, selected = remap.validate_checklist_bytes(raw,
        expected_checklist_sha256=hashlib.sha256(raw).hexdigest(), season="2015-16",
        parent_release_id="release-parent", parent_manifest_sha256="a" * 64,
        source_archive_sha256s=SOURCE_HASHES, case_ids=[row["case_id"]])
    assert selected[0]["target_carrier_id"] == 1104
    assert selected[0]["artifact_ids"] == []


def test_materialisation_approval_must_bind_exact_cases_and_sources(tmp_path):
    row = candidate()
    selected_id = row["case_id"]
    approval = {
        "schema": remap.APPROVAL_SCHEMA,
        "checklist_sha256": "c" * 64,
        "season": "2000-01",
        "parent_release_id": "release-parent",
        "parent_manifest_sha256": "a" * 64,
        "source_archive_sha256s": SOURCE_HASHES,
        "approved_case_ids": [selected_id],
        "scope": "stock-seed-carrier-remap-only; historical kit design not certified",
    }
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(approval))
    assert remap._approved_case_ids(path, checklist_sha="c" * 64, season="2000-01",
        parent_release_id="release-parent", parent_manifest_sha="a" * 64,
        source_hashes=SOURCE_HASHES) == {selected_id}
    with pytest.raises(remap.StockKitRemapError, match="exact checklist"):
        remap._approved_case_ids(path, checklist_sha="d" * 64, season="2000-01",
            parent_release_id="release-parent", parent_manifest_sha="a" * 64,
            source_hashes=SOURCE_HASHES)


def test_materialisation_rejects_tampered_mapping_before_creating_output(tmp_path, monkeypatch):
    row = {"case_id": "kit-stock-seed-remap-" + "1" * 20,
        "target_file_by_archive": {name: "EQ961104.BMP" for name in ARCHIVES}}
    fresh = {"schema": remap.PLAN_SCHEMA, "status": "dry-run-candidate-only",
        "season": "2000-01", "parent_release_id": "release-parent",
        "parent_manifest_sha256": "a" * 64, "checklist_sha256": "c" * 64,
        "source_archive_sha256s": SOURCE_HASHES, "source_dbdat": str(tmp_path / "seed"),
        "checklist_path": str(tmp_path / "checklist.json"), "selected_cases": [row],
        "record_preflight": {name: {} for name in ARCHIVES}, "palette_binding": {}}
    submitted = json.loads(pipeline.canonical_json_bytes(fresh))
    submitted["selected_cases"][0]["target_file_by_archive"]["MINIESC.PKF"] = "EQ961105.BMP"
    output = tmp_path / ".local/season-stock-kit-seed-remaps-v1/tampered"
    monkeypatch.setattr(remap.registry, "ROOT", tmp_path)
    monkeypatch.setattr(remap, "_root_path", lambda value, **kwargs: Path(value))
    monkeypatch.setattr(remap, "_approved_case_ids", lambda *args, **kwargs: {row["case_id"]})
    release = SimpleNamespace(season="2000-01", release_id="release-parent", manifest_sha256="a" * 64)
    monkeypatch.setattr(remap.registry, "load_registered_release", lambda *args: release)
    monkeypatch.setattr(remap.registry, "load_preferred_release", lambda *args: release)
    monkeypatch.setattr(remap, "prepare", lambda **kwargs: fresh)

    with pytest.raises(remap.StockKitRemapError, match="freshly prepared plan differs"):
        remap.materialise(plan=submitted, approval_path=tmp_path / "approval.json", output_root=output)
    assert not output.exists()
