from __future__ import annotations

import copy
import shlex
from pathlib import Path

import pytest

from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_runtime_evidence_preflight_v1 as preflight
from scripts.test_season_package_v2 import _valid_package


def _write_release_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    package_path = tmp_path / "season-package.json"
    package_v2.write_canonical_package(package_path, _valid_package())
    game_tree = tmp_path / "game"
    for relative in (
        "MANAGPRE.EXE",
        "DBDAT/JUG98030.FDI",
        "DBDAT/EQ98030.FDI",
        "DBDAT/ENT98030.FDI",
        "DBDAT/MINIFOTO.PKF",
    ):
        target = game_tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode("ascii"))
    descriptor = pipeline.canonical_json_document_descriptor(package_path, document_id="season-package")
    inventory = pipeline.build_tree_inventory(game_tree)
    manifest = {
        "schema": pipeline.SEASON_MANIFEST_SCHEMA,
        "season": "2015-16",
        "base": {
            "base_id": "pm99-fixture-base",
            "inventory_fingerprint": "a" * 64,
            "file_count": 0,
            "total_bytes": 0,
        },
        "season_document": descriptor,
        "external_artifacts": [],
        "stages": [],
        "output": {
            "inventory_fingerprint": inventory["files_fingerprint"],
            "file_count": inventory["file_count"],
            "total_bytes": inventory["total_bytes"],
        },
    }
    manifest_path = tmp_path / "season-manifest.json"
    pipeline.write_canonical_json(manifest_path, manifest)
    profile = {
        "schema_version": preflight.PROFILE_SCHEMA,
        "season": "2015-16",
        "club": {"id": "club-100", "carrier_id": 100, "name": "Fixture Town"},
        "selector": {
            "team_name": "Fixture Town",
            "team_select_x": 321,
            "team_select_y": 222,
            "division_select_x": 555,
            "division_select_y": 111,
        },
        "capture": {"routes": ["line_up", "squad"], "profile_count": 2},
    }
    profile_path = tmp_path / "fixture-town.runtime-profile.json"
    pipeline.write_canonical_json(profile_path, profile)
    return package_path, manifest_path, game_tree, profile_path


def test_preflight_binds_target_club_to_exact_finished_release(tmp_path: Path) -> None:
    package_path, manifest_path, game_tree, profile_path = _write_release_fixture(tmp_path)

    receipt = preflight.build_preflight(
        package_path=package_path,
        release_manifest_path=manifest_path,
        game_tree=game_tree,
        profile_path=profile_path,
        worker="fixture-worker",
        run_tag="season-2015-16-fixture-town-r1",
    )

    assert receipt["state"] == "preflight-passed-runtime-not-executed"
    assert receipt["release_eligible"] is False
    assert receipt["runtime_profile"]["club"]["name"] == "Fixture Town"
    assert receipt["expected_target_content"]["manager"]["name"] == "Fixture Manager"
    assert len(receipt["expected_target_content"]["opening_lineup"]["players"]) == 11
    # Multiword names must be one shell argument, not an unquoted substring.
    command = shlex.split(receipt["launch"]["shell_command"])
    assert command == receipt["launch"]["argv"]
    assert command[command.index("--team-name") + 1] == "Fixture Town"
    route_indices = [i for i, arg in enumerate(command) if arg == "--capture-route"]
    assert [command[i + 1] for i in route_indices] == ["line_up", "squad"]


def test_preflight_rejects_any_finished_tree_drift(tmp_path: Path) -> None:
    package_path, manifest_path, game_tree, profile_path = _write_release_fixture(tmp_path)
    (game_tree / "DBDAT/JUG98030.FDI").write_bytes(b"drift")

    with pytest.raises(preflight.RuntimeEvidencePreflightError, match="game tree does not match"):
        preflight.build_preflight(
            package_path=package_path,
            release_manifest_path=manifest_path,
            game_tree=game_tree,
            profile_path=profile_path,
            worker="fixture-worker",
            run_tag="season-2015-16-fixture-town-r1",
        )


def test_profile_requires_lineup_and_squad_capture() -> None:
    profile = {
        "schema_version": preflight.PROFILE_SCHEMA,
        "season": "2015-16",
        "club": {"id": "club-100", "carrier_id": 100, "name": "Fixture Town"},
        "selector": {
            "team_name": "Fixture Town",
            "team_select_x": 321,
            "team_select_y": 222,
            "division_select_x": 555,
            "division_select_y": 111,
        },
        "capture": {"routes": ["squad"], "profile_count": 0},
    }
    with pytest.raises(preflight.RuntimeEvidencePreflightError, match="squad and line_up"):
        preflight.validate_profile(copy.deepcopy(profile))
