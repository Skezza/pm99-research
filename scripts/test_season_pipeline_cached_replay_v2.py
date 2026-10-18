from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_buildplan_v2 as buildplan
from scripts import season_pipeline_cached_replay_v2 as replay
from scripts import season_pipeline_v2 as pipeline


def _write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _package(path: Path) -> None:
    pipeline.write_canonical_json(path, {"season": {"label": "2015/16"}})


def test_cached_replay_rebuilds_two_identical_clean_trees(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _write(base / "DBDAT" / "base.bin", b"base")
    _write(base / "README.TXT", b"pristine")
    reference = tmp_path / "old-release"
    shutil.copytree(base, reference)
    _write(reference / "DBDAT" / "base.bin", b"changed")
    _write(reference / "DBDAT" / "MINIFOTO" / "J9600001.BMP", b"portrait")
    package = tmp_path / "season.json"
    _package(package)
    bundle = tmp_path / "bundle"
    replay.create_bundle(
        base_tree=base,
        reference_tree=reference,
        season_package=package,
        bundle_root=bundle,
        include=["DBDAT/base.bin"],
        include_directories=["DBDAT/MINIFOTO"],
    )
    adapter = ROOT / "scripts" / "season_pipeline_cached_replay_v2.py"
    plan_path = tmp_path / "plan.json"
    replay._write_plan(
        base_id="pm99-test-base",
        base_tree=base,
        season_package=package,
        bundle_index=bundle / "index.json",
        adapter=adapter,
        output=plan_path,
    )
    verified = plan_path.with_name("verified-base.json")
    first = buildplan.run_build_plan_from_paths(
        plan_path=plan_path,
        verified_base_path=verified,
        base_tree=base,
        season_package=package,
        materialisation_tree=tmp_path / "first",
        metadata_dir=tmp_path / "metadata-first",
        local_command_specs=[f"cached-replay-adapter={adapter}"],
        external_artifact_specs=[f"cached-release-bundle={bundle / 'index.json'}"],
    )
    second = buildplan.run_build_plan_from_paths(
        plan_path=plan_path,
        verified_base_path=verified,
        base_tree=base,
        season_package=package,
        materialisation_tree=tmp_path / "second",
        metadata_dir=tmp_path / "metadata-second",
        local_command_specs=[f"cached-replay-adapter={adapter}"],
        external_artifact_specs=[f"cached-release-bundle={bundle / 'index.json'}"],
    )
    assert (tmp_path / "first" / "DBDAT" / "base.bin").read_bytes() == b"changed"
    assert (tmp_path / "first" / "DBDAT" / "MINIFOTO" / "J9600001.BMP").read_bytes() == b"portrait"
    assert pipeline.inventory_difference(first["final_inventory"], second["final_inventory"])["equal"] is True
    assert Path(first["build_plan_receipt"]).read_bytes() == Path(second["build_plan_receipt"]).read_bytes()


def test_cached_replay_refuses_base_or_package_drift(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _write(base / "DBDAT" / "base.bin", b"base")
    reference = tmp_path / "reference"
    shutil.copytree(base, reference)
    _write(reference / "DBDAT" / "base.bin", b"changed")
    package = tmp_path / "season.json"
    _package(package)
    bundle = tmp_path / "bundle"
    replay.create_bundle(
        base_tree=base, reference_tree=reference, season_package=package,
        bundle_root=bundle, include=["DBDAT/base.bin"], include_directories=[],
    )
    _write(base / "README.TXT", b"drift")
    target = tmp_path / "target"
    shutil.copytree(base, target)
    with pytest.raises(replay.CachedReplayError, match="different base"):
        replay.apply_bundle(
            base_tree=base, materialisation_tree=target, season_package=package,
            bundle_index=bundle / "index.json",
        )
