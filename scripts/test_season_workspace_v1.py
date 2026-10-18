"""Tests for the consolidated, year-neutral season workspace."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_editorial_timeline_v1 as editorial  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts import season_workspace_v1 as workspace_v1  # noqa: E402
from test_season_package_v2 import _valid_package  # noqa: E402


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package_v2.canonical_json_bytes(value))


def _workspace(tmp_path: Path) -> tuple[Path, dict, dict]:
    package = _valid_package()
    package_v2.validate_package(package, strict=True)
    timeline = editorial.seed_timeline_from_package(
        package, timeline_id="pm99-editorial-2000-2026"
    )
    package_path = tmp_path / "season-package.json"
    timeline_path = tmp_path / "editorial-timeline.json"
    base_tree = tmp_path / "base"
    base_tree.mkdir()
    (base_tree / "fixture.bin").write_bytes(b"clean base")
    base_descriptor_path = tmp_path / "verified-base.json"
    _write(
        base_descriptor_path,
        pipeline_v2.make_verified_base_descriptor(base_id="fixture-clean-base", tree=base_tree),
    )
    _write(package_path, package)
    _write(timeline_path, timeline)
    workspace = {
        "schema_version": workspace_v1.SCHEMA,
        "workspace_id": "pm99-2015-16-fixture",
        "season": "2015-16",
        "base": {
            "role": "clean-original",
            "descriptor": {
                "relative_path": "verified-base.json",
                "sha256": package_v2.sha256_file(base_descriptor_path),
            },
        },
        "package": {
            "relative_path": "season-package.json",
            "sha256": package_v2.sha256_file(package_path),
        },
        "editorial": {
            "timeline": {
                "relative_path": "editorial-timeline.json",
                "sha256": package_v2.sha256_file(timeline_path),
            },
            "derived_package_id": "pm99-2015-16-fixture-effective",
            "override_id": "pm99-2015-16-fixture-editorial",
        },
        "ratings": {"precedence": workspace_v1.PRECEDENCE},
        "portraits": {"failure_policy": "native-no-photo", "record_missing": True},
    }
    workspace_path = tmp_path / "workspace.json"
    _write(workspace_path, workspace)
    return workspace_path, package, timeline


def test_workspace_prepares_effective_package_and_missing_photo_list(tmp_path: Path) -> None:
    workspace_path, package, _ = _workspace(tmp_path)
    output = workspace_v1.prepare_workspace(
        workspace_path=workspace_path, output_dir=tmp_path / "prepared"
    )
    assert output["season"] == "2015-16"
    assert output["editorial_patch_count"] == 0
    expected_missing = sum(
        row["status"] != "applied" for row in package["assets"]["portraits"]
    )
    assert output["missing_portrait_count"] == expected_missing
    effective = package_v2.read_canonical_package(Path(output["outputs"]["effective_package"]))
    assert effective["package_id"] == "pm99-2015-16-fixture-effective"
    package_v2.validate_package(effective, strict=True)


def test_workspace_applies_permanent_editorial_amendment(tmp_path: Path) -> None:
    workspace_path, package, timeline = _workspace(tmp_path)
    timeline["amendments"] = [{
        "id": "fixture-player-2-quality",
        "seasons": ["2015-16"],
        "target": {"entity": "player", "identity_id": "person-fixture-player-2"},
        "changes": {"ratings.values.quality": 92},
        "reason": "Playtest review raised the player's season quality.",
        "proof": {"grade": "reviewed-editorial", "artifact_id": "receipt-contract"},
        "rating_provenance": {
            "method": "reviewed editorial season rating",
            "proof_grade": "reviewed-editorial",
            "source_ids": ["source-ledger"],
        },
    }]
    timeline_path = tmp_path / "editorial-timeline.json"
    _write(timeline_path, timeline)
    workspace = package_v2.read_canonical_package(workspace_path)
    workspace["editorial"]["timeline"]["sha256"] = package_v2.sha256_file(timeline_path)
    _write(workspace_path, workspace)
    output = workspace_v1.prepare_workspace(
        workspace_path=workspace_path, output_dir=tmp_path / "prepared"
    )
    assert output["editorial_patch_count"] == 1
    effective = package_v2.read_canonical_package(Path(output["outputs"]["effective_package"]))
    player = next(row for row in effective["players"] if row["id"] == "player-2")
    assert player["ratings"]["values"]["quality"] == 92
    assert package["players"][1]["ratings"]["values"]["quality"] != 92


def test_workspace_refuses_stale_input_hash(tmp_path: Path) -> None:
    workspace_path, _, _ = _workspace(tmp_path)
    workspace = package_v2.read_canonical_package(workspace_path)
    workspace["package"]["sha256"] = "0" * 64
    _write(workspace_path, workspace)
    with pytest.raises(workspace_v1.WorkspaceError, match="hash mismatch"):
        workspace_v1.validate_workspace(workspace, workspace_path=workspace_path)


def test_rating_policy_is_fixed_and_reports_provenance_tiers(tmp_path: Path) -> None:
    _, package, _ = _workspace(tmp_path)
    changed = copy.deepcopy(package)
    changed["players"][0]["ratings"]["provenance"]["method"] = "FIFA nearest edition fallback"
    changed["players"][1]["ratings"]["provenance"]["method"] = "reviewed editorial season rating"
    report = workspace_v1.build_coverage_report(changed)
    assert report["rating_precedence"] == workspace_v1.PRECEDENCE
    assert report["rating_tier_counts"]["fifa-nearest-edition"] == 1
    assert report["rating_tier_counts"]["reviewed-editorial"] >= 1
    assert sum(report["rating_tier_counts"].values()) == len(changed["players"])


def test_preserve_only_unknown_manager_does_not_need_fake_person_identity() -> None:
    package = _valid_package()
    manager = package["managers"][0]
    manager.pop("person_id")
    manager["policy"] = "preserve-existing-mode1"
    package_v2.validate_package(package, strict=True)
    timeline = editorial.seed_timeline_from_package(
        package, timeline_id="pm99-editorial-2000-2026"
    )
    assert not any(
        row["entity"] == "manager" and row["package_record_id"] == manager["id"]
        for row in timeline["bindings"]
    )
    editorial.validate_timeline_against_package(timeline, package)


def test_space_efficient_copy_never_links_database_or_executable(tmp_path: Path) -> None:
    base = tmp_path / "base-game"
    (base / "DBDAT").mkdir(parents=True)
    (base / "SIMULDAT").mkdir()
    (base / "DBDAT" / "JUG98030.FDI").write_bytes(b"database")
    (base / "MANAGPRE.EXE").write_bytes(b"executable")
    (base / "SIMULDAT" / "Modelos.pkf").write_bytes(b"read-only asset")
    target = tmp_path / "season-game"

    workspace_v1.materialise_base_tree(
        base_tree=base, materialisation_tree=target, link_unchanged=True
    )

    assert (base / "DBDAT" / "JUG98030.FDI").stat().st_ino != (
        target / "DBDAT" / "JUG98030.FDI"
    ).stat().st_ino
    assert (base / "MANAGPRE.EXE").stat().st_ino != (
        target / "MANAGPRE.EXE"
    ).stat().st_ino
    assert (base / "SIMULDAT" / "Modelos.pkf").stat().st_ino == (
        target / "SIMULDAT" / "Modelos.pkf"
    ).stat().st_ino
    (target / "DBDAT" / "JUG98030.FDI").write_bytes(b"changed")
    assert (base / "DBDAT" / "JUG98030.FDI").read_bytes() == b"database"
