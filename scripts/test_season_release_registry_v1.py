from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def _write(path: Path, value: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def _json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_real_catalog_has_one_sorted_entry_for_all_26_seasons() -> None:
    catalog = registry.load_catalog()
    assert len(catalog) == 26
    assert list(catalog) == sorted(catalog)
    assert list(catalog)[0] == "2000-01"
    assert list(catalog)[-1] == "2025-26"
    assert "2015-16" in catalog


def test_runtime_selector_catalog_covers_the_same_26_seasons() -> None:
    selectors = json.loads((registry.ROOT / "data/season-runtime-selectors-v1.json").read_text())
    rows = selectors["seasons"]
    assert selectors["schema_version"] == "pm99-season-runtime-selectors-v1"
    assert [row["season"] for row in rows] == registry.supported_seasons()
    assert len({row["season"] for row in rows}) == 26
    assert all(row["team_name"] in {"Stoke City", "Stoke C."} for row in rows)


def test_retained_release_selection_does_not_change_preferred_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    monkeypatch.setattr(registry, 'LOCAL_ROOT', tmp_path / 'registry')
    for name in ('game', 'package.json', 'inventory.json'):
        path = tmp_path / name
        if name == 'game': path.mkdir()
        else: path.write_text('{}')
    locator = {'schema_version': registry.LOCATOR_SCHEMA, 'season': '2015-16',
               'release_id': 'original', 'game_path': 'game', 'package_path': 'package.json',
               'inventory_path': 'inventory.json'}
    _json(registry.locator_path('2015-16', 'original'), locator)
    catalog = {'2015-16': {'release_id': 'new-preferred', 'release_manifest_sha256': None}}
    monkeypatch.setattr(registry, 'load_catalog', lambda: catalog)
    release = registry.load_registered_release('2015-16', 'original')
    assert release.release_id == 'original'
    assert catalog['2015-16']['release_id'] == 'new-preferred'
    with pytest.raises(registry.RegistryError, match='invalid retained release ID'):
        registry.load_registered_release('2015-16', '../../escape')


def test_playable_validation_is_bound_to_locator_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    monkeypatch.setattr(registry, "LOCAL_ROOT", tmp_path / ".local/registry")
    season, release_id = "2014-15", "test-r1"
    game = tmp_path / "game"
    for relative in registry.REQUIRED_GAME_FILES:
        _write(game / relative, relative.encode("ascii"))
    package = _json(tmp_path / "package.json", {"schema_version": "test", "season": season})
    inventory_path = _json(tmp_path / "inventory.json", pipeline.build_tree_inventory(game))
    required = {
        relative: registry.sha256_file(game / relative)
        for relative in registry.REQUIRED_GAME_FILES
    }
    locator = {
        "schema_version": registry.LOCATOR_SCHEMA,
        "season": season,
        "release_id": release_id,
        "game_path": "game",
        "package_path": "package.json",
        "package_canonical_sha256": registry.canonical_document_sha256(package),
        "compiler_receipt_path": None,
        "static_ingress_receipt_path": None,
        "inventory_path": "inventory.json",
        "release_manifest_path": None,
        "attestation_path": None,
        "runtime_evidence_path": None,
        "legacy_revision": None,
        "technical_status": "playable-unverified",
        "editorial_warning_count": 0,
        "required_file_hashes": required,
    }
    _json(registry.locator_path(season, release_id), locator)
    monkeypatch.setattr(registry, "load_catalog", lambda: {
        season: {"season": season, "release_id": release_id, "release_manifest_sha256": None}
    })

    assert registry.validate_preferred_release(season, level="playable")["valid"] is True
    portrait = _write(game / "DBDAT/MINIFOTO/J9600042.BMP", b"reviewed-portrait")
    locator["required_visual_file_hashes"] = {"DBDAT/MINIFOTO/J9600042.BMP": registry.sha256_file(portrait)}
    locator["required_visual_absent_paths"] = ["DBDAT/MINIFOTO/J9600043.BMP"]
    _json(registry.locator_path(season, release_id), locator)
    assert registry.validate_preferred_release(season, level="playable")["valid"] is True
    _write(portrait, b"wrong-portrait")
    assert registry.validate_preferred_release(season, level="playable")["valid"] is False
    _write(portrait, b"reviewed-portrait")
    _write(game / "DBDAT/MINIFOTO/J9600043.BMP", b"unexpected-stock-face")
    assert registry.validate_preferred_release(season, level="playable")["valid"] is False
    (game / "DBDAT/MINIFOTO/J9600043.BMP").unlink()
    _write(game / "DBDAT/JUG98030.FDI", b"mutated")
    report = registry.validate_preferred_release(season, level="playable")
    assert report["valid"] is False
    assert any(row["code"] == "required-file-hash-mismatch" for row in report["issues"])


def test_release_validation_rejects_unbound_recipe_and_missing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    monkeypatch.setattr(registry, "LOCAL_ROOT", tmp_path / ".local/registry")
    season, release_id = "2014-15", "test-r1"
    game = tmp_path / "game"
    for relative in registry.REQUIRED_GAME_FILES:
        _write(game / relative, relative.encode("ascii"))
    package = _json(tmp_path / "package.json", {"schema_version": "test", "season": season})
    inventory_path = _json(tmp_path / "inventory.json", pipeline.build_tree_inventory(game))
    receipt = _json(tmp_path / "compiler.json", {
        "season_package_sha256": "0" * 64,
        "outputs": [],
    })
    locator = {
        "schema_version": registry.LOCATOR_SCHEMA,
        "season": season,
        "release_id": release_id,
        "game_path": "game",
        "package_path": "package.json",
        "package_canonical_sha256": registry.canonical_document_sha256(package),
        "compiler_receipt_path": "compiler.json",
        "static_ingress_receipt_path": None,
        "inventory_path": "inventory.json",
        "release_manifest_path": None,
        "attestation_path": None,
        "runtime_evidence_path": None,
        "legacy_revision": None,
        "technical_status": "playable-unverified",
        "editorial_warning_count": 0,
        "required_file_hashes": {
            relative: registry.sha256_file(game / relative)
            for relative in registry.REQUIRED_GAME_FILES
        },
    }
    _json(registry.locator_path(season, release_id), locator)
    monkeypatch.setattr(registry, "load_catalog", lambda: {
        season: {"season": season, "release_id": release_id, "release_manifest_sha256": None}
    })

    report = registry.validate_preferred_release(season, level="release")
    codes = {row["code"] for row in report["issues"]}
    assert "compiler-package-mismatch" in codes
    assert "canonical-release-manifest-unregistered" in codes
    assert "runtime-attestation-missing" in codes


def test_registered_qa_is_hash_and_release_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "ROOT", tmp_path)
    game = tmp_path / "game"
    game.mkdir()
    package = _json(tmp_path / "package.json", {"season": "2014-15"})
    report = _json(tmp_path / "qa-report.json", {
        "schema_version": "pm99-season-quality-qa-v1",
        "season": "2014-15",
        "result": "pass",
        "inputs": {
            "game_tree": "game",
            "package_sha256": registry.sha256_file(package),
        },
        "summary": {"warning_count": 3},
    })
    locator = {
        "qa_status": "pass",
        "qa_report_path": "qa-report.json",
        "qa_report_sha256": registry.sha256_file(report),
        "editorial_warning_count": 3,
    }
    release = registry.PreferredRelease(
        season="2014-15", release_id="test-r1", manifest_sha256=None,
        game_path=game, package_path=package, compiler_receipt_path=None,
        static_ingress_receipt_path=None, inventory_path=tmp_path / "inventory.json",
        release_manifest_path=None, attestation_path=None, runtime_evidence_path=None,
        build_chain_path=None, revision=None, locator=locator,
    )

    assert registry._validate_registered_qa(release) == []
    report.write_text("{}", encoding="utf-8")
    issues = registry._validate_registered_qa(release)
    assert [row["code"] for row in issues] == ["qa-report-hash-mismatch"]
