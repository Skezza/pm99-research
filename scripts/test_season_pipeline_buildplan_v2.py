from __future__ import annotations

import copy
import json
import shutil
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_buildplan_v2 as buildplan
from scripts import season_pipeline_v2 as pipeline


FORBIDDEN_RUNTIME_DIRS = [
    "CACHE", "RUNTIME", "SAVE", "SAVEGAME", "SAVEGAMES", "SAVES", "TEMP", "TMP"
]


def write_file(path: Path, value: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_bytes(value)
    return path


def make_fake_adapter(path: Path) -> Path:
    source = f"""#!{sys.executable}
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--base', required=True)
parser.add_argument('--tree', required=True)
parser.add_argument('--package', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--make-runtime', action='store_true')
parser.add_argument('--unexpected', action='store_true')
args = parser.parse_args()
base_marker = (Path(args.base) / 'DBDAT' / 'base.bin').read_bytes()
season = json.loads(Path(args.package).read_text(encoding='utf-8'))['season']
target = Path(args.tree) / args.output
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(base_marker + b'|' + season.encode('ascii') + b'|compiled')
if args.make_runtime:
    (Path(args.tree) / 'RUNTIME').mkdir()
if args.unexpected:
    (Path(args.tree) / 'junk.bin').write_bytes(b'unexpected')
"""
    write_file(path, source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def make_case(tmp_path: Path, *, extra_args: list[str] | None = None) -> dict[str, object]:
    base = tmp_path / "base"
    write_file(base / "DBDAT" / "base.bin", b"vanilla")
    write_file(base / "README.TXT", "pristine")
    package = tmp_path / "season-package.json"
    pipeline.write_canonical_json(
        package,
        {"schema": "pm99-season-package-test-v1", "season": "2015-16", "teams": []},
    )
    adapter = make_fake_adapter(tmp_path / "fake-adapter")
    verified_base = pipeline.make_verified_base_descriptor(base_id="pm99-test-base", tree=base)
    verified_base_path = tmp_path / "verified-base.json"
    pipeline.write_canonical_json(verified_base_path, verified_base)
    package_descriptor = pipeline.canonical_json_document_descriptor(
        package, document_id="season-package"
    )

    reference = tmp_path / "reference-output"
    shutil.copytree(base, reference, copy_function=shutil.copyfile)
    generated = write_file(reference / "DBDAT" / "season.bin", b"vanilla|2015-16|compiled")
    outputs = ["DBDAT/season.bin"]
    stage_output_inventory = buildplan._build_declared_output_inventory(reference, outputs)
    final_inventory = pipeline.build_tree_inventory(reference)
    receipt = pipeline.make_stage_record(
        stage_id="database",
        implementation_path=adapter,
        input_fingerprints={
            "base-tree": verified_base["inventory"]["files_fingerprint"],
            "season-package": package_descriptor["canonical_sha256"],
        },
        parameters={"adapter": "fake-v1", "outputs": outputs},
    )
    command_args = [
        "--base", "{base-tree}", "--tree", "{materialisation-tree}",
        "--package", "{season-package}", "--output", "DBDAT/season.bin",
        *(extra_args or []),
    ]
    plan = {
        "schema": buildplan.BUILD_PLAN_SCHEMA,
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
        "external_artifacts": [],
        "forbidden_runtime_state_directories": FORBIDDEN_RUNTIME_DIRS,
        "stages": [
            {
                "id": "database",
                "order": 1,
                "command": {
                    "id": "fake-adapter",
                    "sha256": pipeline.sha256_file(adapter),
                    "args": command_args,
                    "timeout_seconds": 30,
                },
                "outputs": outputs,
                "expected_receipt": receipt,
                "expected_output_inventory": stage_output_inventory,
            }
        ],
        "expected_final_output_inventory": final_inventory,
    }
    plan_path = tmp_path / "build-plan.json"
    buildplan.write_canonical_build_plan(plan_path, plan)
    return {
        "base": base,
        "package": package,
        "adapter": adapter,
        "verified_base": verified_base,
        "verified_base_path": verified_base_path,
        "plan": plan,
        "plan_path": plan_path,
        "generated": generated,
    }


def run_case(case: dict[str, object], *, root: Path, tag: str) -> dict[str, object]:
    return buildplan.run_build_plan_from_paths(
        plan_path=case["plan_path"],  # type: ignore[arg-type]
        verified_base_path=case["verified_base_path"],  # type: ignore[arg-type]
        base_tree=case["base"],  # type: ignore[arg-type]
        season_package=case["package"],  # type: ignore[arg-type]
        materialisation_tree=root / f"materialised-{tag}",
        metadata_dir=root / f"metadata-{tag}",
        local_command_specs=[f"fake-adapter={case['adapter']}"],
        external_artifact_specs=[],
    )


def test_fake_adapter_two_clean_materialisations_are_identical(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    first = run_case(case, root=tmp_path, tag="one")
    second = run_case(case, root=tmp_path, tag="two")

    first_tree = Path(first["materialisation_tree"])
    second_tree = Path(second["materialisation_tree"])
    assert pipeline.inventory_difference(
        pipeline.build_tree_inventory(first_tree), pipeline.build_tree_inventory(second_tree)
    )["equal"] is True
    assert (first_tree / "DBDAT" / "season.bin").read_bytes() == b"vanilla|2015-16|compiled"
    first_manifest = Path(first["metadata"]["manifest"])  # type: ignore[index]
    second_manifest = Path(second["metadata"]["manifest"])  # type: ignore[index]
    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    first_receipt = Path(first["build_plan_receipt"])
    second_receipt = Path(second["build_plan_receipt"])
    assert first_receipt.read_bytes() == second_receipt.read_bytes()
    assert pipeline.verify_release_output(
        manifest=pipeline.read_json_file(first_manifest), output_tree=first_tree
    )["files_fingerprint"] == first["final_inventory"]["files_fingerprint"]  # type: ignore[index]


def test_stage_runtime_state_directory_fails_closed(tmp_path: Path) -> None:
    case = make_case(tmp_path, extra_args=["--make-runtime"])

    with pytest.raises(buildplan.BuildPlanError, match="runtime-state directory"):
        run_case(case, root=tmp_path, tag="runtime")
    assert not (tmp_path / "metadata-runtime").exists()


def test_stage_unexpected_file_fails_closed(tmp_path: Path) -> None:
    case = make_case(tmp_path, extra_args=["--unexpected"])

    with pytest.raises(buildplan.BuildPlanError, match="undeclared file"):
        run_case(case, root=tmp_path, tag="unexpected")
    assert not (tmp_path / "metadata-unexpected").exists()


def test_plan_rejects_overlapping_outputs_and_noncanonical_bytes(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    broken = copy.deepcopy(case["plan"])
    broken["stages"][0]["outputs"] = ["DBDAT/season.bin", "DBDAT/season.bin"]
    with pytest.raises(buildplan.BuildPlanError, match="unique"):
        buildplan.validate_build_plan(broken)

    noncanonical = tmp_path / "noncanonical-plan.json"
    noncanonical.write_text(json.dumps(case["plan"], indent=2), encoding="utf-8")
    with pytest.raises(buildplan.BuildPlanError, match="canonical JSON"):
        buildplan.load_canonical_build_plan(noncanonical)


def test_existing_materialisation_or_undeclared_command_mapping_is_rejected(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    existing = tmp_path / "materialised-existing"
    existing.mkdir()
    with pytest.raises(buildplan.BuildPlanError, match="must not already exist"):
        run_case(case, root=tmp_path, tag="existing")

    with pytest.raises(buildplan.BuildPlanError, match="exactly match"):
        buildplan.run_build_plan_from_paths(
            plan_path=case["plan_path"],  # type: ignore[arg-type]
            verified_base_path=case["verified_base_path"],  # type: ignore[arg-type]
            base_tree=case["base"],  # type: ignore[arg-type]
            season_package=case["package"],  # type: ignore[arg-type]
            materialisation_tree=tmp_path / "materialised-command",
            metadata_dir=tmp_path / "metadata-command",
            local_command_specs=[
                f"fake-adapter={case['adapter']}",
                f"extra={case['adapter']}",
            ],
            external_artifact_specs=[],
        )


def test_expected_stage_inventory_mismatch_refuses_final_manifest(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    broken = copy.deepcopy(case["plan"])
    broken["stages"][0]["expected_output_inventory"]["files"][0]["sha256"] = "0" * 64
    # Recalculate neither the entry list fingerprint nor the plan; a malformed
    # expected receipt must be rejected before an adapter executes.
    with pytest.raises(pipeline.PipelineError, match="files_fingerprint"):
        buildplan.validate_build_plan(broken)
