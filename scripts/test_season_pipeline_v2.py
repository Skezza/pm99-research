from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline


def write_file(path: Path, value: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_bytes(value)
    return path


def make_tree(root: Path, *, second: str = "world") -> Path:
    write_file(root / "DBDAT" / "database.bin", b"database-v1")
    write_file(root / "assets" / "nested" / "portrait.bmp", b"bitmap-v1")
    write_file(root / "readme.txt", second)
    return root


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_canonical_json_is_key_order_independent_and_season_is_normalised() -> None:
    first = {"b": [3, {"y": 2, "x": 1}], "a": "hello"}
    second = {"a": "hello", "b": [3, {"x": 1, "y": 2}]}

    assert pipeline.canonical_json_bytes(first) == pipeline.canonical_json_bytes(second)
    assert pipeline.canonical_json_sha256(first) == pipeline.canonical_json_sha256(second)
    assert pipeline.normalise_season_id("1999/00") == "1999-00"
    assert pipeline.normalise_season_id("2015/16") == "2015-16"
    assert pipeline.normalise_season_id("2025-26") == "2025-26"
    with pytest.raises(pipeline.PipelineError, match="consecutive"):
        pipeline.normalise_season_id("2015-19")
    with pytest.raises(pipeline.PipelineError, match="between"):
        pipeline.normalise_season_id("1898-99")


def test_inventory_is_full_path_independent_and_reports_content_difference(tmp_path: Path) -> None:
    first = make_tree(tmp_path / "first")
    second = make_tree(tmp_path / "second")

    first_inventory = pipeline.build_tree_inventory(first)
    second_inventory = pipeline.build_tree_inventory(second)

    assert first_inventory == second_inventory
    assert first_inventory["file_count"] == 3
    assert first_inventory["files"][0]["path"] == "DBDAT/database.bin"
    assert str(tmp_path) not in json.dumps(first_inventory)

    write_file(second / "assets" / "nested" / "portrait.bmp", b"bitmap-v2")
    difference = pipeline.inventory_difference(first_inventory, pipeline.build_tree_inventory(second))
    assert difference["equal"] is False
    assert difference["only_left"] == []
    assert difference["only_right"] == []
    assert difference["changed"][0]["path"] == "assets/nested/portrait.bmp"
    with pytest.raises(pipeline.PipelineError, match="does not match locked inventory"):
        pipeline.assert_tree_matches_inventory(second, first_inventory)


def test_inventory_fails_closed_on_symlinks(tmp_path: Path) -> None:
    target = write_file(tmp_path / "target.txt", "target")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:  # pragma: no cover - Windows without symlink permission.
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(pipeline.PipelineError, match="symlinks"):
        pipeline.build_tree_inventory(root)


def test_verified_base_rejects_any_mutated_authoritative_input(tmp_path: Path) -> None:
    base = make_tree(tmp_path / "pristine")
    descriptor = pipeline.make_verified_base_descriptor(base_id="pm99-gog-en-1.00", tree=base)

    assert pipeline.verify_base_tree(tree=base, verified_base=descriptor)["file_count"] == 3
    write_file(base / "DBDAT" / "database.bin", b"not-pristine")
    with pytest.raises(pipeline.PipelineError, match="does not match locked inventory"):
        pipeline.verify_base_tree(tree=base, verified_base=descriptor)


def test_external_artifacts_are_path_free_and_must_match(tmp_path: Path) -> None:
    source = write_file(tmp_path / "outside" / "face-source.jpg", b"source-photo")
    descriptor = pipeline.external_artifact_descriptor(
        artifact_id="portrait-source-catalogue", path=source, role="asset"
    )

    assert "path" not in descriptor
    assert str(tmp_path) not in json.dumps(descriptor)
    pipeline.verify_external_artifact(path=source, descriptor=descriptor)
    write_file(source, b"changed-photo")
    with pytest.raises(pipeline.PipelineError, match="differs"):
        pipeline.verify_external_artifact(path=source, descriptor=descriptor)


def test_stage_keys_are_content_addressed_and_order_independent(tmp_path: Path) -> None:
    implementation = write_file(tmp_path / "compile.py", "print('compiler')\n")
    asset_a = write_file(tmp_path / "a.json", "a")
    asset_b = write_file(tmp_path / "b.json", "b")
    a = pipeline.external_artifact_descriptor(artifact_id="a", path=asset_a)
    b = pipeline.external_artifact_descriptor(artifact_id="b", path=asset_b)
    inputs = {"season-package": "a" * 64, "base-tree": "b" * 64}

    first = pipeline.content_addressed_stage_key(
        stage_id="database", implementation_sha256=pipeline.sha256_file(implementation),
        input_fingerprints=inputs, parameters={"flag": True, "order": [1, 2]},
        external_artifacts=[b, a],
    )
    second = pipeline.content_addressed_stage_key(
        stage_id="database", implementation_sha256=pipeline.sha256_file(implementation),
        input_fingerprints={"base-tree": "b" * 64, "season-package": "a" * 64},
        parameters={"order": [1, 2], "flag": True}, external_artifacts=[a, b],
    )
    changed = pipeline.content_addressed_stage_key(
        stage_id="database", implementation_sha256=pipeline.sha256_file(implementation),
        input_fingerprints=inputs, parameters={"flag": False, "order": [1, 2]},
        external_artifacts=[a, b],
    )

    assert first == second
    assert first != changed
    record = pipeline.make_stage_record(
        stage_id="database", implementation_path=implementation, input_fingerprints=inputs,
        parameters={"flag": True, "order": [1, 2]}, external_artifacts=[a, b],
    )
    assert pipeline.validate_stage_record(record)["cache_key"] == first
    record["cache_key"] = "0" * 64
    with pytest.raises(pipeline.PipelineError, match="does not match"):
        pipeline.validate_stage_record(record)


def test_release_metadata_is_canonical_and_attestation_is_separate(tmp_path: Path) -> None:
    base = make_tree(tmp_path / "verified-base")
    output = make_tree(tmp_path / "finished-output", second="season build")
    package = write_json(
        tmp_path / "season-package.json",
        {"schema": "pm99-season-package-test-v1", "clubs": [], "season": "2015-16"},
    )
    source_asset = write_file(tmp_path / "source" / "portrait.jpg", b"portrait")
    implementation = write_file(tmp_path / "compiler.py", "# a deterministic stage\n")
    verified_base = pipeline.make_verified_base_descriptor(base_id="pm99-verified-test", tree=base)
    artifact = pipeline.external_artifact_descriptor(artifact_id="portraits", path=source_asset, role="asset")
    stage = pipeline.make_stage_record(
        stage_id="database", implementation_path=implementation,
        input_fingerprints={
            "base-tree": verified_base["inventory"]["files_fingerprint"],
            "season-package": pipeline.canonical_json_document_descriptor(
                package, document_id="season-package"
            )["canonical_sha256"],
        },
        parameters={"write-lane": "known-fields-only"}, external_artifacts=[artifact],
    )

    result = pipeline.write_release_metadata(
        season="2015/16", base_tree=base, verified_base=verified_base,
        season_package=package, output_tree=output, metadata_dir=tmp_path / "metadata",
        external_artifacts=[artifact], stages=[stage],
    )

    manifest_path = Path(result["paths"]["manifest"])
    manifest = pipeline.read_json_file(manifest_path)
    assert pipeline.validate_release_manifest(manifest) == manifest
    assert manifest["season"] == "2015-16"
    assert manifest["output"]["inventory_fingerprint"] == result["output_inventory"]["files_fingerprint"]
    canonical_text = manifest_path.read_text(encoding="utf-8")
    assert "created_utc" not in canonical_text
    assert str(tmp_path) not in canonical_text
    assert Path(result["paths"]["base_inventory"]).is_file()
    assert Path(result["paths"]["output_inventory"]).is_file()
    assert pipeline.verify_release_output(manifest=manifest, output_tree=output)["file_count"] == 3

    attestation = pipeline.create_attestation(
        release_manifest=manifest, output_tree=output, run_id="native-windows-smoke",
        note="runtime passed", runtime_receipts=[{"case": "fresh-game", "ok": True}],
    )
    assert attestation["schema"] == pipeline.ATTESTATION_SCHEMA
    assert attestation["release_manifest_sha256"] == pipeline.canonical_json_sha256(manifest)
    assert "created_utc" in attestation
    assert "created_utc" not in manifest
    write_file(output / "readme.txt", "output mutated")
    with pytest.raises(pipeline.PipelineError, match="does not match release manifest"):
        pipeline.verify_release_output(manifest=manifest, output_tree=output)


def test_release_metadata_rejects_overlapping_or_wrong_base(tmp_path: Path) -> None:
    base = make_tree(tmp_path / "base")
    package = write_json(tmp_path / "season.json", {"schema": "example"})
    verified = pipeline.make_verified_base_descriptor(base_id="base-test", tree=base)

    with pytest.raises(pipeline.PipelineError, match="disjoint"):
        pipeline.write_release_metadata(
            season="2015-16", base_tree=base, verified_base=verified, season_package=package,
            output_tree=base, metadata_dir=tmp_path / "metadata",
        )

    output = make_tree(tmp_path / "output")
    write_file(base / "readme.txt", "mutated")
    with pytest.raises(pipeline.PipelineError, match="does not match locked inventory"):
        pipeline.write_release_metadata(
            season="2015-16", base_tree=base, verified_base=verified, season_package=package,
            output_tree=output, metadata_dir=tmp_path / "metadata-two",
        )


def test_cli_full_metadata_and_double_build_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = make_tree(tmp_path / "base")
    output_a = make_tree(tmp_path / "output-a", second="compiled")
    output_b = make_tree(tmp_path / "output-b", second="compiled")
    package = write_json(tmp_path / "season.json", {"schema": "example", "clubs": []})
    verified_path = tmp_path / "verified-base.json"

    assert pipeline.main([
        "verified-base", "--base-id", "pm99-cli-test", "--tree", str(base), "--output", str(verified_path),
    ]) == 0
    capsys.readouterr()
    assert pipeline.main([
        "release-metadata", "--season", "2015-16", "--base-tree", str(base),
        "--verified-base", str(verified_path), "--season-package", str(package),
        "--output-tree", str(output_a), "--metadata-dir", str(tmp_path / "release-metadata"),
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["ok"] is True
    assert pipeline.main([
        "double-build", "--first-tree", str(output_a), "--second-tree", str(output_b),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["equal"] is True
    write_file(output_b / "readme.txt", "not the same")
    assert pipeline.main([
        "double-build", "--first-tree", str(output_a), "--second-tree", str(output_b),
    ]) == 1
    assert json.loads(capsys.readouterr().out)["equal"] is False
