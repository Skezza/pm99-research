import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_json_artifact_byte_repair_v1 as repair
from scripts import season_pipeline_v2 as pipeline


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path
    workspace = repo / ".local/historical-role-deltas-v1/2025-26/test-release"
    workspace.mkdir(parents=True)
    backup_root = repo / ".local/repair-backups"
    backup_root.mkdir(parents=True)
    return workspace, backup_root


def _declared(raw_without_lf: bytes) -> str:
    return hashlib.sha256(raw_without_lf).hexdigest()


def test_one_lf_repair_is_dry_run_then_atomic_and_preserves_hardlink(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.registry, "ROOT", tmp_path)
    workspace, backup_root = _workspace(tmp_path)
    target = workspace / "source.json"
    payload = {"rows": [{"carrier_id": 27080, "name": "Fortune Onoh"}], "schema": "test"}
    body = pipeline.canonical_json_bytes(payload)
    target.write_bytes(body + b"\n")
    alias = workspace / "sibling-hardlink.json"
    alias.hardlink_to(target)
    original_inode = target.stat().st_ino

    plan = repair.plan_repair(target, _declared(body), workspace_root=workspace)
    assert plan["status"] == "one-final-lf-repair-available"
    assert target.read_bytes() == body + b"\n"
    assert target.stat().st_ino == original_inode

    original_replace = repair.os.replace

    def guarded_replace(source, destination):
        if Path(destination) == target:
            assert (backup_root / "source.json.before").read_bytes() == body + b"\n"
            intent = json.loads((backup_root / "repair-ledger.json").read_text())
            assert intent["state"] == "backup-verified-replace-pending"
        return original_replace(source, destination)

    monkeypatch.setattr(repair.os, "replace", guarded_replace)
    result = repair.apply_repair(
        plan,
        backup_path=backup_root / "source.json.before",
        ledger_path=backup_root / "repair-ledger.json",
    )
    assert result["changed"] is True
    assert target.read_bytes() == body
    assert hashlib.sha256(target.read_bytes()).hexdigest() == plan["declared_sha256"]
    assert alias.read_bytes() == body + b"\n"
    assert alias.stat().st_ino == original_inode
    assert target.stat().st_ino != original_inode
    assert (backup_root / "source.json.before").read_bytes() == body + b"\n"
    ledger = json.loads((backup_root / "repair-ledger.json").read_text())
    assert ledger["state"] == "complete"
    assert ledger["backup_sha256"] == plan["before_sha256"]


def test_already_valid_artifact_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.registry, "ROOT", tmp_path)
    workspace, backup_root = _workspace(tmp_path)
    target = workspace / "source.json"
    raw = pipeline.canonical_json_bytes({"a": 1})
    target.write_bytes(raw)
    plan = repair.plan_repair(target, hashlib.sha256(raw).hexdigest(), workspace_root=workspace)
    assert plan["status"] == "already-valid"
    result = repair.apply_repair(plan, backup_path=backup_root / "unused", ledger_path=backup_root / "unused-ledger")
    assert result["changed"] is False
    assert target.read_bytes() == raw


@pytest.mark.parametrize(
    "raw, declared",
    [
        (b'{ "a":1}\n', hashlib.sha256(b'{ "a":1}').hexdigest()),
        (b'{"a":1}\n\n', hashlib.sha256(b'{"a":1}\n').hexdigest()),
        (b'{"a":1}\n', "0" * 64),
    ],
)
def test_noncanonical_repeated_lf_and_other_mismatch_rejected(tmp_path, monkeypatch, raw, declared):
    monkeypatch.setattr(repair.registry, "ROOT", tmp_path)
    workspace, _ = _workspace(tmp_path)
    target = workspace / "source.json"
    target.write_bytes(raw)
    with pytest.raises(ValueError):
        repair.plan_repair(target, declared, workspace_root=workspace)


def test_path_outside_explicit_known_workspace_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.registry, "ROOT", tmp_path)
    workspace, _ = _workspace(tmp_path)
    other = tmp_path / ".local/other/source.json"
    other.parent.mkdir()
    raw = pipeline.canonical_json_bytes({"a": 1}) + b"\n"
    other.write_bytes(raw)
    with pytest.raises(ValueError):
        repair.plan_repair(other, hashlib.sha256(raw[:-1]).hexdigest(), workspace_root=workspace)


def test_symlinked_artifact_path_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.registry, "ROOT", tmp_path)
    workspace, _ = _workspace(tmp_path)
    real = workspace / "real.json"
    raw = pipeline.canonical_json_bytes({"a": 1}) + b"\n"
    real.write_bytes(raw)
    link = workspace / "link.json"
    link.symlink_to(real)
    with pytest.raises(ValueError):
        repair.plan_repair(link, hashlib.sha256(raw[:-1]).hexdigest(), workspace_root=workspace)
