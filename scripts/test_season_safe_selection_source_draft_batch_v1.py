"""Focused contract checks for the safe-selection source-draft batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_safe_selection_source_draft_batch_v1 as batch  # noqa: E402


def test_missing_safe_manifest_is_a_written_skip_not_a_fallback(tmp_path: Path) -> None:
    current = tmp_path / "current"
    (current / "2000-01").mkdir(parents=True)
    output = tmp_path / "result"
    result = batch.run_batch(
        current_root=current,
        selection_manifest_root=tmp_path / "selections",
        opening_root=tmp_path / "opening",
        template_root=tmp_path / "templates",
        registry_root=tmp_path / "registries",
        output_root=output,
        seasons=["2000-01"],
        expected_season_count=1,
    )

    assert result["summary"]["source_draft_revision_count"] == 0
    assert result["summary"]["skipped_no_safe_selection_manifest_count"] == 1
    receipt = json.loads((output / "2000-01/source-draft-receipt.json").read_text())
    assert receipt["state"] == "skipped-no-safe-selection-manifest"
    assert receipt["release_eligible"] is False
    assert receipt["not_performed"] == [
        "release package creation",
        "database compilation",
        "PM99 runtime validation",
        "playable claim",
    ]


def test_existing_output_or_staging_root_is_never_reused(tmp_path: Path) -> None:
    current = tmp_path / "current"
    (current / "2000-01").mkdir(parents=True)
    output = tmp_path / "result"
    output.mkdir()
    with pytest.raises(batch.SourceDraftBatchError, match="refusing to overwrite"):
        batch.run_batch(
            current_root=current,
            selection_manifest_root=tmp_path / "selections",
            opening_root=tmp_path / "opening",
            template_root=tmp_path / "templates",
            registry_root=tmp_path / "registries",
            output_root=output,
            seasons=["2000-01"],
        )
    output.rmdir()
    staging = tmp_path / ".result.staging"
    staging.mkdir()
    with pytest.raises(batch.SourceDraftBatchError, match="incomplete staging"):
        batch.run_batch(
            current_root=current,
            selection_manifest_root=tmp_path / "selections",
            opening_root=tmp_path / "opening",
            template_root=tmp_path / "templates",
            registry_root=tmp_path / "registries",
            output_root=output,
            seasons=["2000-01"],
        )


def test_draft_receipt_binds_every_written_source_output(tmp_path: Path) -> None:
    paths = {
        name: tmp_path / f"{name}.json"
        for name in (
            "current_pointer", "source_capture", "source_intake", "carrier_allocation",
            "safe_selection_manifest", "registry", "opening_lineup_capture",
            "opening_reconciliation", "opening_additions", "calendar_bound_template",
            "calendar_binding_audit",
        )
    }
    selection = {"selection": True}
    selection_audit = {"audit": True}
    preallocation = {"preallocation": True}
    draft = {"draft": True}
    build_audit = {"hard_blockers": [{"code": "fixture", "count": 2}], "release_eligible": False}
    hashes = {f"{name}_sha256": "a" * 64 for name in paths}
    hashes.update({
        "source_club_selection_sha256": batch._sha_document(selection),
        "source_club_selection_audit_sha256": batch._sha_document(selection_audit),
        "opening_squad_preallocation_sha256": batch._sha_document(preallocation),
        "draft_package_sha256": batch._sha_document(draft),
        "source_package_build_audit_sha256": batch._sha_document(build_audit),
    })
    result = {
        "revision_id": "safe-selection-source-draft-2000-01-fixture",
        "selection": selection,
        "selection_audit": selection_audit,
        "preallocation": preallocation,
        "draft": draft,
        "build_audit": build_audit,
        "hashes": hashes,
        "inputs": {"paths": paths, "intake": {"season": {"label": "2000/01"}}},
    }

    row = batch._write_draft_result(root=tmp_path, season_id="2000-01", result=result)

    assert row["state"] == "source-draft-blocked-no-release"
    receipt = json.loads(next(tmp_path.glob("**/source-draft-receipt.json")).read_text())
    assert receipt["outputs"]["source_club_selection_audit_sha256"] == batch._sha_document(selection_audit)
