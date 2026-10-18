"""Synthetic safety coverage for the hash-bound calendar materialisation lane."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_season_calendar_v1 as materialiser  # noqa: E402
from scripts import season_calendar_package_overlay_v1 as calendar_overlay  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_buildplan_v2 as buildplan_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts import test_season_package_v2 as fixtures  # noqa: E402


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package_v2.canonical_json_bytes(value))


def _bound_inputs(tmp_path: Path) -> dict[str, Path]:
    base = tmp_path / "base"
    game = tmp_path / "game"
    for tree in (base, game):
        (tree / "DBDAT").mkdir(parents=True)
        (tree / "DBDAT" / "JUG98030.FDI").write_bytes(b"database-row")
        (tree / "MANAGPRE.EXE").write_bytes(b"clean-calendar-executable")
    patched = tmp_path / "calendar" / "MANAGPRE.EXE"
    patched.parent.mkdir()
    patched.write_bytes(b"target-season-calendar-executable")
    calendar_receipt = {
        "schema_version": "pm99-calendar-patch-v1",
        "base_year": 1998,
        "target_year": 2015,
        "target_rollover_year": 2016,
        "before_sha256": pipeline_v2.sha256_file(base / "MANAGPRE.EXE"),
        "after_sha256": pipeline_v2.sha256_file(patched),
        "patch_count": 853,
        "source_operand_counts": {"1998": 50, "1999": 803},
    }
    receipt_path = tmp_path / "calendar" / "calendar-receipt.json"
    _write_json(receipt_path, calendar_receipt)
    package, binding_audit = calendar_overlay.bind_calendar(
        package=fixtures._valid_package(),
        receipt=calendar_receipt,
        receipt_relative_path="calendar-receipt.json",
        receipt_sha256=pipeline_v2.sha256_file(receipt_path),
        executable_sha256=pipeline_v2.sha256_file(patched),
    )
    package_path = tmp_path / "package.json"
    package_v2.write_canonical_package(package_path, package)
    binding_audit["output_package_sha256"] = package_v2.sha256_file(package_path)
    audit_path = tmp_path / "calendar-binding-audit.json"
    _write_json(audit_path, binding_audit)
    descriptor_path = tmp_path / "verified-base.json"
    _write_json(
        descriptor_path,
        pipeline_v2.make_verified_base_descriptor(base_id="fixture-clean", tree=base),
    )
    return {
        "package": package_path,
        "audit": audit_path,
        "receipt": receipt_path,
        "executable": patched,
        "base": descriptor_path,
        "base_tree": base,
        "game": game,
    }


def test_materialises_only_the_bound_calendar_and_retains_runtime_gate(tmp_path: Path) -> None:
    paths = _bound_inputs(tmp_path)

    result = materialiser.materialise_calendar(
        package_path=paths["package"],
        calendar_audit_path=paths["audit"],
        calendar_receipt_path=paths["receipt"],
        calendar_executable_path=paths["executable"],
        verified_base_path=paths["base"],
        game_tree=paths["game"],
    )

    assert (paths["game"] / "MANAGPRE.EXE").read_bytes() == paths["executable"].read_bytes()
    assert (paths["game"] / "DBDAT" / "JUG98030.FDI").read_bytes() == b"database-row"
    assert result["schema_version"] == materialiser.RECEIPT_SCHEMA
    assert result["release_eligible"] is False
    assert result["runtime_validation_pending"] is True
    assert result["mutation"] == {
        "allowed_changed_paths": ["MANAGPRE.EXE"],
        "added_paths": [],
        "removed_paths": [],
        "changed_paths": ["MANAGPRE.EXE"],
    }


def test_refuses_a_game_tree_that_already_has_a_non_base_calendar(tmp_path: Path) -> None:
    paths = _bound_inputs(tmp_path)
    target = paths["game"] / "MANAGPRE.EXE"
    target.write_bytes(b"another-calendar")
    before = target.read_bytes()

    with pytest.raises(materialiser.CalendarMaterialisationError, match="refusing overwrite"):
        materialiser.materialise_calendar(
            package_path=paths["package"],
            calendar_audit_path=paths["audit"],
            calendar_receipt_path=paths["receipt"],
            calendar_executable_path=paths["executable"],
            verified_base_path=paths["base"],
            game_tree=paths["game"],
        )

    assert target.read_bytes() == before


def test_refuses_an_audit_that_does_not_bind_the_exact_calendar_receipt(tmp_path: Path) -> None:
    paths = _bound_inputs(tmp_path)
    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    audit["receipt_sha256"] = "0" * 64
    _write_json(paths["audit"], audit)
    before = (paths["game"] / "MANAGPRE.EXE").read_bytes()

    with pytest.raises(materialiser.CalendarMaterialisationError, match="does not bind this exact receipt"):
        materialiser.materialise_calendar(
            package_path=paths["package"],
            calendar_audit_path=paths["audit"],
            calendar_receipt_path=paths["receipt"],
            calendar_executable_path=paths["executable"],
            verified_base_path=paths["base"],
            game_tree=paths["game"],
        )

    assert (paths["game"] / "MANAGPRE.EXE").read_bytes() == before


def test_build_plan_adapter_materialises_only_bound_executable(tmp_path: Path) -> None:
    paths = _bound_inputs(tmp_path)
    adapter = Path(materialiser.__file__).resolve()
    package_descriptor = pipeline_v2.canonical_json_document_descriptor(
        paths["package"], document_id="season-package"
    )
    verified_base = pipeline_v2.read_json_file(paths["base"])
    artifacts = pipeline_v2.normalise_external_artifacts([
        pipeline_v2.external_artifact_descriptor(
            artifact_id="calendar-binding-audit", path=paths["audit"]
        ),
        pipeline_v2.external_artifact_descriptor(
            artifact_id="calendar-executable", path=paths["executable"], role="tool"
        ),
        pipeline_v2.external_artifact_descriptor(
            artifact_id="calendar-receipt", path=paths["receipt"]
        ),
        pipeline_v2.external_artifact_descriptor(
            artifact_id="verified-base", path=paths["base"]
        ),
    ])

    reference = tmp_path / "reference"
    shutil.copytree(paths["base_tree"], reference, copy_function=shutil.copyfile)
    shutil.copyfile(paths["executable"], reference / materialiser.EXECUTABLE_NAME)
    outputs = [materialiser.EXECUTABLE_NAME]
    stage_inventory = buildplan_v2._build_declared_output_inventory(reference, outputs)
    final_inventory = pipeline_v2.build_tree_inventory(reference)
    stage_record = pipeline_v2.make_stage_record(
        stage_id="target-calendar",
        implementation_path=adapter,
        input_fingerprints={
            "base-tree": verified_base["inventory"]["files_fingerprint"],
            "season-package": package_descriptor["canonical_sha256"],
        },
        parameters={
            "adapter": "pm99-season-calendar-materialisation-v1",
            "outputs": outputs,
            "runtime_validation_pending": True,
        },
        external_artifacts=artifacts,
    )
    plan = {
        "schema": buildplan_v2.BUILD_PLAN_SCHEMA,
        "season": "2015-16",
        "base": {
            "base_id": verified_base["base_id"],
            "inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
        },
        "season_package": {
            "canonical_sha256": package_descriptor["canonical_sha256"],
            "canonical_size": package_descriptor["canonical_size"],
            "schema": package_descriptor["schema"],
        },
        "external_artifacts": artifacts,
        "forbidden_runtime_state_directories": [
            "CACHE", "RUNTIME", "SAVE", "SAVEGAME", "SAVEGAMES", "SAVES", "TEMP", "TMP"
        ],
        "stages": [{
            "id": "target-calendar",
            "order": 1,
            "command": {
                "id": "target-calendar-adapter",
                "sha256": pipeline_v2.sha256_file(adapter),
                "args": [
                    "--build-plan-adapter",
                    "--package", "{season-package}",
                    "--calendar-audit", "{external-artifact:calendar-binding-audit}",
                    "--calendar-receipt", "{external-artifact:calendar-receipt}",
                    "--calendar-executable", "{external-artifact:calendar-executable}",
                    "--verified-base", "{external-artifact:verified-base}",
                    "--game-tree", "{materialisation-tree}",
                ],
                "timeout_seconds": 30,
            },
            "outputs": outputs,
            "expected_receipt": stage_record,
            "expected_output_inventory": stage_inventory,
        }],
        "expected_final_output_inventory": final_inventory,
    }
    plan_path = tmp_path / "build-plan.json"
    buildplan_v2.write_canonical_build_plan(plan_path, plan)

    result = buildplan_v2.run_build_plan_from_paths(
        plan_path=plan_path,
        verified_base_path=paths["base"],
        base_tree=paths["base_tree"],
        season_package=paths["package"],
        materialisation_tree=tmp_path / "materialised",
        metadata_dir=tmp_path / "metadata",
        local_command_specs=[f"target-calendar-adapter={adapter}"],
        external_artifact_specs=[
            f"calendar-binding-audit={paths['audit']}",
            f"calendar-executable={paths['executable']}",
            f"calendar-receipt={paths['receipt']}",
            f"verified-base={paths['base']}",
        ],
    )

    tree = Path(result["materialisation_tree"])
    assert (tree / materialiser.EXECUTABLE_NAME).read_bytes() == paths["executable"].read_bytes()
    assert not list(tree.glob("*receipt*.json"))
    assert result["manifest"]["stages"] == [stage_record]
    assert result["final_inventory"] == final_inventory
