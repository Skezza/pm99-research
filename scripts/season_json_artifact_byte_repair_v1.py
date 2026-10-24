"""Repair a one-LF JSON artifact hash mismatch without writing through links.

This is a narrow source-workspace utility. It accepts only a file whose exact
bytes are canonical pipeline JSON plus one LF and whose bytes without that LF
match the caller's declared SHA-256. Planning is read-only; application also
requires a durable byte-for-byte backup and intent ledger before atomic replace.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


SCHEMA = "pm99-source-json-artifact-byte-repair-v1"
KNOWN_SOURCE_ROOT = Path(".local/historical-role-deltas-v1")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _resolve(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = registry.ROOT / value
    return value.resolve(strict=True)


def _validate_target(path: str | Path, workspace_root: str | Path) -> tuple[Path, Path]:
    root = _resolve(registry.ROOT)
    source_root = (root / KNOWN_SOURCE_ROOT).resolve(strict=True)
    workspace = _resolve(workspace_root)
    target = _resolve(path)
    requested_workspace = Path(workspace_root).expanduser()
    if not requested_workspace.is_absolute():
        requested_workspace = root / requested_workspace
    requested_target = Path(path).expanduser()
    if not requested_target.is_absolute():
        requested_target = root / requested_target
    if not workspace.is_dir() or not workspace.is_relative_to(source_root):
        raise ValueError("workspace must be a known historical-role-deltas release directory")
    if requested_workspace.is_symlink() or requested_workspace.resolve(strict=True) != workspace:
        raise ValueError("workspace path may not traverse a symlink")
    if target == workspace or not target.is_relative_to(workspace):
        raise ValueError("artifact path must be inside the explicit workspace")
    if requested_target.is_symlink() or requested_target.resolve(strict=True) != target or not target.is_file():
        raise ValueError("artifact must be an existing regular non-symlink file")
    return target, workspace


def plan_repair(
    path: str | Path,
    declared_sha256: str,
    *,
    workspace_root: str | Path,
) -> dict[str, Any]:
    """Return a read-only plan for exact one-LF repair or an already-valid no-op."""
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in declared_sha256
    ):
        raise ValueError("declared SHA-256 must be lowercase hexadecimal")
    target, workspace = _validate_target(path, workspace_root)
    before = target.read_bytes()
    before_sha = _sha(before)
    if not before.endswith(b"\n\n"):
        try:
            document = json.loads(before)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("artifact is not valid JSON") from exc
        canonical = pipeline.canonical_json_bytes(document)
        if before not in (canonical, canonical + b"\n"):
            raise ValueError("artifact is not canonical pipeline JSON")
    else:
        raise ValueError("repeated final LF is not repairable")
    identity = {
        "path": str(target.relative_to(registry.ROOT.resolve())),
        "workspace_root": str(workspace.relative_to(registry.ROOT.resolve())),
        "declared_sha256": declared_sha256,
        "before_sha256": before_sha,
        "inode": target.stat().st_ino,
        "nlink": target.stat().st_nlink,
        "size": len(before),
        "mode": stat.S_IMODE(target.stat().st_mode),
    }
    if before_sha == declared_sha256:
        return {"schema": SCHEMA, "status": "already-valid", **identity}
    if not before.endswith(b"\n") or before.endswith(b"\n\n"):
        raise ValueError("only exactly one final LF may be removed")
    canonical_with_lf = pipeline.canonical_json_bytes(document) + b"\n"
    if before != canonical_with_lf:
        raise ValueError("artifact is not exactly canonical pipeline JSON plus one LF")
    candidate = before[:-1]
    candidate_sha = _sha(candidate)
    if candidate_sha != declared_sha256:
        raise ValueError("bytes without one LF do not match the declared SHA-256")
    return {
        "schema": SCHEMA,
        "status": "one-final-lf-repair-available",
        **identity,
        "after_sha256": candidate_sha,
        "after_size": len(candidate),
        "repair_bytes": 1,
        "method": "fresh-file-fsync-and-atomic-replace",
    }


def _write_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    payload = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def apply_repair(
    plan: dict[str, Any],
    *,
    backup_path: str | Path,
    ledger_path: str | Path,
) -> dict[str, Any]:
    """Apply a still-current plan after writing and syncing backup plus ledger.

    The target entry is replaced atomically; other hardlink entries continue to
    reference the original inode and are never modified.
    """
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("repair plan schema mismatch")
    if plan.get("status") == "already-valid":
        target, _ = _validate_target(plan["path"], plan["workspace_root"])
        raw = target.read_bytes()
        if _sha(raw) != plan.get("declared_sha256") or _sha(raw) != plan.get("before_sha256"):
            raise ValueError("already-valid plan no longer matches the current artifact")
        return {"status": "already-valid", "changed": False, "path": plan.get("path")}
    if plan.get("status") != "one-final-lf-repair-available":
        raise ValueError("repair plan is not applicable")
    target, workspace = _validate_target(plan["path"], plan["workspace_root"])
    fresh = plan_repair(target, plan["declared_sha256"], workspace_root=workspace)
    if fresh != plan:
        raise ValueError("repair plan no longer matches the current file")
    root = registry.ROOT.resolve()
    backup = _resolve(backup_path) if Path(backup_path).exists() else Path(backup_path).expanduser()
    ledger = Path(ledger_path).expanduser()
    if not backup.is_absolute():
        backup = root / backup
    if not ledger.is_absolute():
        ledger = root / ledger
    backup = backup.parent.resolve(strict=True) / backup.name
    ledger = ledger.parent.resolve(strict=True) / ledger.name
    local_root = (root / ".local").resolve(strict=True)
    if not backup.is_relative_to(local_root) or not ledger.is_relative_to(local_root):
        raise ValueError("backup and ledger must remain under workspace .local")
    if backup == ledger:
        raise ValueError("backup and ledger must be distinct paths")
    if backup.exists() or backup.is_symlink() or ledger.exists() or ledger.is_symlink():
        raise ValueError("backup and ledger paths must be new, exclusive paths")

    before = target.read_bytes()
    if _sha(before) != plan["before_sha256"]:
        raise ValueError("artifact changed after planning")
    candidate = before[:-1]
    _write_exclusive(backup, before)
    if _sha(backup.read_bytes()) != plan["before_sha256"]:
        raise ValueError("durable backup verification failed")
    _fsync_dir(backup.parent)
    ledger_row = {
        "schema": SCHEMA + "-ledger",
        "state": "backup-verified-replace-pending",
        "target": plan["path"],
        "workspace_root": plan["workspace_root"],
        "declared_sha256": plan["declared_sha256"],
        "before_sha256": plan["before_sha256"],
        "after_sha256": plan["after_sha256"],
        "backup_path": str(backup.relative_to(root)),
        "backup_sha256": plan["before_sha256"],
        "original_inode": plan["inode"],
        "original_nlink": plan["nlink"],
    }
    _atomic_json(ledger, ledger_row)

    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".repair", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(candidate)
            handle.flush()
            os.fchmod(handle.fileno(), plan["mode"])
            os.fsync(handle.fileno())
        if _sha(temporary.read_bytes()) != plan["after_sha256"]:
            raise ValueError("staged repair bytes failed hash check")
        if target.is_symlink() or not target.is_file() or _sha(target.read_bytes()) != plan["before_sha256"]:
            raise ValueError("target changed immediately before atomic replacement")
        os.replace(temporary, target)
        _fsync_dir(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    if _sha(target.read_bytes()) != plan["after_sha256"]:
        raise ValueError("post-replacement artifact hash differs")
    ledger_row["state"] = "complete"
    ledger_row["replacement_sha256"] = _sha(target.read_bytes())
    ledger_row["replacement_inode"] = target.stat().st_ino
    _atomic_json(ledger, ledger_row)
    return {"status": "complete", "changed": True, "path": plan["path"],
            "backup_path": str(backup.relative_to(root)), "ledger_path": str(ledger.relative_to(root)),
            "before_sha256": plan["before_sha256"], "after_sha256": plan["after_sha256"]}
