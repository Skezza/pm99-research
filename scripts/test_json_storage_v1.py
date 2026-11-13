"""Storage transitions must preserve exact bytes and existing evidence rules."""
import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts import json_storage_v1 as storage
from scripts import season_package_v2 as package
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


pytestmark = pytest.mark.skipif(shutil.which("zstd") is None or os.name != "posix",
                               reason="POSIX and zstd CLI required for the migration pilot")


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "season-package.json"
    # Deliberate whitespace and Unicode exercise byte identity, not JSON equality.
    raw = ('{\n "name": "Jos\u00e9", "players": ' + json.dumps(["unchanged"] * 6000) + '\n}\n').encode()
    path.write_bytes(raw)
    path.chmod(0o640)
    return path, raw


def test_real_migration_preserves_hashes_discovery_copy_and_exact_rollback(document, tmp_path):
    path, raw = document
    digest = hashlib.sha256(raw).hexdigest()
    descriptor = pipeline.external_artifact_descriptor(artifact_id="season-input", path=path)
    semantic = pipeline.canonical_json_document_descriptor(path, document_id="season-input")
    receipt = storage.compress_file(path)
    assert receipt["allocated_released"] > 0
    assert receipt["sha256"] == digest
    assert not path.exists() and storage.is_file(path)
    assert storage.read_bytes(path) == raw
    assert storage.read_bytes(storage.compressed_path(path)) == raw
    assert storage.size(path) == len(raw)
    assert list(storage.iter_json_paths(tmp_path)) == [path]
    assert registry.sha256_file(path) == package.sha256_file(path) == digest
    assert pipeline.external_artifact_descriptor(artifact_id="season-input", path=path) == descriptor
    assert pipeline.canonical_json_document_descriptor(path, document_id="season-input") == semantic
    assert pipeline.read_json_file(path) == json.loads(raw)
    destination = tmp_path / "copy.json"
    storage.copy_json(path, destination)
    assert not destination.exists() and storage.compressed_path(destination).is_file()
    assert storage.read_bytes(destination) == raw
    storage.restore_file(path)
    assert path.read_bytes() == raw
    assert path.stat().st_mode & 0o777 == 0o640
    assert not storage.compressed_path(path).exists()


def test_canonical_package_reader_and_writer_keep_original_byte_contract(tmp_path):
    path = tmp_path / "package.json"
    value = {"name": "Jos\u00e9", "players": ["same"] * 6000}
    package.write_canonical_package(path, value, compressed=True)
    assert package.read_canonical_package(path) == value
    assert package.sha256_file(path) == hashlib.sha256(package.canonical_json_bytes(value)).hexdigest()
    value["name"] = "Changed"
    package.write_canonical_package(path, value)
    assert not path.exists()  # ordinary writes preserve the existing compressed format
    assert package.read_canonical_package(path) == value


def test_noncanonical_compressed_package_is_still_rejected(document):
    path, _ = document
    storage.compress_file(path)
    with pytest.raises(package.PackageValidationError, match="canonically"):
        package.read_canonical_package(path)


def test_new_evidence_writer_refuses_a_compressed_existing_file(tmp_path):
    path = tmp_path / "receipt.json"
    digest = pipeline.write_canonical_json(path, {"name": "proof"}, compressed=True)
    assert digest == hashlib.sha256(pipeline.canonical_json_bytes({"name": "proof"}) + b"\n").hexdigest()
    with pytest.raises(pipeline.PipelineError, match="overwrite"):
        pipeline.write_canonical_json(path, {"name": "replacement"})
    assert pipeline.read_json_file(path) == {"name": "proof"}


def test_migration_rejects_symlinks_shared_inodes_and_other_file_types(document, tmp_path):
    path, raw = document
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(storage.StorageError, match="regular"):
        storage.compress_file(link)
    link.unlink()
    os.link(path, link)
    with pytest.raises(storage.StorageError, match="shared inodes"):
        storage.compress_file(path)
    assert path.read_bytes() == link.read_bytes() == raw
    with pytest.raises(storage.StorageError, match="restricted"):
        storage.compress_file(tmp_path / "database.FDI")


def test_ambiguous_raw_and_compressed_copies_fail_closed(document):
    path, raw = document
    storage.compress_file(path)
    path.write_bytes(raw)
    for operation in [storage.read_bytes, storage.sha256_file, storage.compress_file, storage.restore_file]:
        with pytest.raises(storage.StorageError, match="ambiguous"):
            operation(path)


def test_corrupt_frames_are_never_treated_as_missing_or_plain_json(document):
    path, _ = document
    storage.compress_file(path)
    storage.compressed_path(path).write_bytes(b"not a zstd frame")
    with pytest.raises(storage.StorageError, match="decompress"):
        storage.read_json(path)
    with pytest.raises(pipeline.PipelineError):
        pipeline.read_json_file(path)


def test_decoder_limit_stops_an_oversized_frame(document, monkeypatch):
    path, _ = document
    storage.compress_file(path)
    monkeypatch.setattr(storage, "MAX_DECODED_BYTES", 100)
    with pytest.raises(storage.StorageError, match="exceeds"):
        storage.read_bytes(path)


def test_missing_codec_never_retires_the_source(document, monkeypatch):
    path, raw = document
    monkeypatch.setenv("PATH", "")
    with pytest.raises(storage.StorageError, match="zstd executable"):
        storage.compress_file(path)
    assert path.read_bytes() == raw and not storage.compressed_path(path).exists()
    assert not list(path.parent.glob(".json-storage-*"))


def test_failure_before_retirement_keeps_raw_source_and_cleans_own_sidecar(document, monkeypatch):
    path, raw = document
    unlink = Path.unlink

    def fail_retirement(self, *args, **kwargs):
        if self == path:
            raise PermissionError("simulated retirement failure")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_retirement)
    with pytest.raises(PermissionError):
        storage.compress_file(path)
    assert path.read_bytes() == raw
    assert not storage.compressed_path(path).exists()
    assert not list(path.parent.glob(".json-storage-*"))


def test_concurrent_no_clobber_writers_have_exactly_one_winner(tmp_path):
    path = tmp_path / "evidence.json"

    def write(compressed):
        try:
            storage.write_bytes(path, b'{"proof":true}\n', compressed=compressed)
            return "written"
        except FileExistsError:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [False, True]))
    assert sorted(results) == ["refused", "written"]
    assert storage.read_json(path) == {"proof": True}


def test_game_inventory_remains_a_physical_byte_inventory(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    path = game / "config.json"
    storage.write_bytes(path, b'{"a":1}\n', compressed=True)
    inventory = pipeline.build_tree_inventory(game)
    packed = storage.compressed_path(path)
    row = inventory["files"][0]
    assert row["path"] == "config.json.zst"
    assert row["size"] == packed.stat().st_size
    assert row["sha256"] == hashlib.sha256(packed.read_bytes()).hexdigest()


def test_direct_script_imports_still_work():
    for script in ["season_pipeline_v2.py", "season_package_v2.py", "season_release_registry_v1.py"]:
        subprocess.run([os.sys.executable, str(Path(__file__).with_name(script)), "--help"],
                       check=True, stdout=subprocess.DEVNULL)


def test_plain_io_does_not_require_posix_locking(tmp_path, monkeypatch):
    path = tmp_path / "plain.json"
    monkeypatch.setattr(storage, "fcntl", None)
    storage.write_bytes(path, b'{"a":1}\n')
    assert storage.read_json(path) == {"a": 1}
    with pytest.raises(storage.StorageError, match="POSIX"):
        storage.compress_file(path)


def test_package_writer_refuses_a_broken_compressed_symlink(tmp_path):
    path = tmp_path / "package.json"
    storage.compressed_path(path).symlink_to(tmp_path / "missing-frame")
    with pytest.raises(storage.StorageError, match="regular"):
        package.write_canonical_package(path, {"name": "unchanged"})
    assert not path.exists()


def test_migration_cli_is_explicit_hash_locked_and_reversible(tmp_path):
    from scripts import migrate_json_storage_v1 as migration
    root = tmp_path
    (root / "data").mkdir()
    catalog = root / "data/preferred-season-releases-v1.json"
    catalog.write_text('{"seasons":[]}\n')
    local = root / ".local/inactive"
    local.mkdir(parents=True)
    path = local / "report.json"
    raw = json.dumps({"players": ["unchanged"] * 6000}).encode()
    path.write_bytes(raw)
    manifest = root / "manifest.json"
    value = {"schema": "pm99-json-storage-migration-v1",
             "preferred_catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
             "files": [{"path": ".local/inactive/report.json", "sha256": hashlib.sha256(raw).hexdigest(),
                        "logical_bytes": len(raw)}]}
    manifest.write_text(json.dumps(value))
    assert migration.run(manifest, root=root)["apply"] is False
    assert path.read_bytes() == raw
    receipt = root / "compressed.jsonl"
    result = migration.run(manifest, root=root, apply=True, receipt_path=receipt)
    assert result["allocated_released"] > 0 and not path.exists()
    events = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert events[0]["event"] == "prepared" and events[-1]["event"] == "complete"
    migration.run(manifest, root=root, apply=True, restore=True,
                  receipt_path=root / "restored.jsonl")
    assert path.read_bytes() == raw
    # A previously registered input must never silently become a pilot candidate.
    locators = root / ".local/season-release-registry-v1/releases/2000-01/release"
    locators.mkdir(parents=True)
    (locators / "locator.json").write_text(json.dumps({"package_path": ".local/inactive/report.json"}))
    with pytest.raises(ValueError, match="registered input"):
        migration.run(manifest, root=root)


def test_migration_cli_refuses_changed_or_escaping_inputs(tmp_path):
    from scripts import migrate_json_storage_v1 as migration
    path = tmp_path / "input.json"
    path.write_text('{}')
    for name in [str(path), "../input.json", "data/input.json", ".local/game/input.json"]:
        manifest = {"schema": "pm99-json-storage-migration-v1", "files": [
            {"path": name, "sha256": "a" * 64, "logical_bytes": 2}]}
        with pytest.raises(ValueError, match="unsafe"):
            migration.checked_rows(manifest, tmp_path)


def test_migration_keeps_source_if_it_changes_during_compression(document, monkeypatch):
    path, raw = document
    stage = storage._stage

    def change_source(*args, **kwargs):
        temporary = stage(*args, **kwargs)
        path.write_bytes(raw + b" ")
        return temporary

    monkeypatch.setattr(storage, "_stage", change_source)
    with pytest.raises(storage.StorageError, match="source changed"):
        storage.compress_file(path)
    assert path.read_bytes() == raw + b" "
    assert not storage.compressed_path(path).exists()
