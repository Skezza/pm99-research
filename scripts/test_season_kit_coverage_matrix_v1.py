import json
from pathlib import Path

import pytest

from scripts.season_kit_coverage_matrix_v1 import build_matrix, canonical_json_bytes


def test_matrix_binds_capture_and_render_hashes(tmp_path: Path) -> None:
    source, render = tmp_path / "source/2000-01", tmp_path / "render/2000-01"
    source.mkdir(parents=True); render.mkdir(parents=True)
    catalogue = {"schema_version": "pm99-season-kit-catalogue-v1", "coverage": {"status_counts": {"source-ready": 2}}}
    (source / "kit-catalogue-v1.json").write_bytes(canonical_json_bytes(catalogue))
    (source / "kit-source-capture-v1.json").write_bytes(canonical_json_bytes({"coverage": {"allocated_club_count": 3}}))
    import hashlib
    binding = {"kit_catalogue_sha256": hashlib.sha256(canonical_json_bytes(catalogue)).hexdigest(), "clubs": [{}, {}]}
    (render / "kit-render-bindings-v1.json").write_bytes(canonical_json_bytes(binding))
    (render / "kit-render-receipt-v1.json").write_bytes(canonical_json_bytes({"coverage": {"bound_club_count": 2, "artifact_count": 6}}))
    matrix = build_matrix(tmp_path / "source", tmp_path / "render")
    assert matrix["coverage"] == {"season_count": 1, "captured_season_count": 1, "rendered_season_count": 1, "immutable_verified_season_count": 0, "source_ready_club_count": 2, "bound_club_count": 2, "artifact_count": 6}


def test_matrix_rejects_stale_binding(tmp_path: Path) -> None:
    source, render = tmp_path / "source/s", tmp_path / "render/s"
    source.mkdir(parents=True); render.mkdir(parents=True)
    (source / "kit-catalogue-v1.json").write_bytes(canonical_json_bytes({"coverage": {}}))
    (source / "kit-source-capture-v1.json").write_bytes(canonical_json_bytes({"coverage": {}}))
    (render / "kit-render-bindings-v1.json").write_bytes(canonical_json_bytes({"kit_catalogue_sha256": "0" * 64, "clubs": []}))
    (render / "kit-render-receipt-v1.json").write_bytes(canonical_json_bytes({"coverage": {}}))
    with pytest.raises(ValueError, match="stale catalogue"):
        build_matrix(tmp_path / "source", tmp_path / "render")


def test_matrix_verifies_immutable_current_pointer(tmp_path: Path) -> None:
    source = tmp_path / "source/2000-01"; historical = tmp_path / "historical/2000-01"
    source.mkdir(parents=True); historical.mkdir(parents=True)
    current = {"schema_version": "pm99-historical-squad-backfill-current-v1", "revision_id": "rev-test", "artifacts": {"allocation": {"sha256": "a" * 64}}}
    (historical / "current.json").write_bytes(canonical_json_bytes(current))
    import hashlib
    current_sha = hashlib.sha256((historical / "current.json").read_bytes()).hexdigest()
    (source / "kit-catalogue-v1.json").write_bytes(canonical_json_bytes({"coverage": {}}))
    (source / "kit-source-capture-v1.json").write_bytes(canonical_json_bytes({"coverage": {}, "provenance": {"historical_revision_id": "rev-test", "historical_current_sha256": current_sha, "historical_allocation_file_sha256": "a" * 64}}))
    matrix = build_matrix(tmp_path / "source", tmp_path / "render", tmp_path / "historical")
    assert matrix["coverage"]["immutable_verified_season_count"] == 1
    assert matrix["rows"][0]["immutable_input_status"] == "current-pointer-hash-verified"
