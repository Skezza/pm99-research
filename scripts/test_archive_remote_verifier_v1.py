"""Offline contract tests for the Pi-side archive stream verifier."""

import hashlib
import io
import json
import ast
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest


def _remote_verifier_code():
    """Load the exact helper without importing the archive script's SSH stack."""
    source_path = Path(__file__).with_name("archive_superseded_2004_probes_20261017.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "remote_verifier"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["remote_verifier"]()


def _expected(files):
    return {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        for name, data in files.items()
    }


def _write_tar(path, members):
    """Write (name, type, payload/linkname) tuples to a tiny gzip tar."""
    with tarfile.open(path, "w:gz") as archive:
        for name, kind, value in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                payload = value
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            else:
                info.type = tarfile.LNKTYPE if kind == "hardlink" else tarfile.SYMTYPE
                info.linkname = value
                archive.addfile(info)


def _verify(final_path, expected):
    return subprocess.run(
        [sys.executable, "-c", _remote_verifier_code(), str(final_path)],
        input=json.dumps(expected),
        text=True,
        capture_output=True,
        check=False,
    )


def test_accepts_regular_file_and_direct_internal_hardlink(tmp_path):
    final_path = tmp_path / "verified.tar.gz"
    files = {"probe/a.bin": b"first payload", "probe/b.bin": b"first payload"}
    _write_tar(
        tmp_path / "verified.tar.gz.partial",
        [
            ("probe/a.bin", "file", b"first payload"),
            ("probe/b.bin", "hardlink", "probe/a.bin"),
        ],
    )

    result = _verify(final_path, _expected(files))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "archive_sha256": hashlib.sha256(final_path.read_bytes()).hexdigest(),
        "members_verified": 2,
        "member_hashes_verified": True,
    }
    assert final_path.is_file()
    assert not (tmp_path / "verified.tar.gz.partial").exists()


@pytest.mark.parametrize(
    "members,expected,match",
    [
        (
            [("a", "file", b"payload"), ("b", "hardlink", "../outside")],
            {"a": b"payload", "b": b"payload"},
            "only direct internal regular-file hardlinks allowed",
        ),
        (
            [
                ("a", "file", b"payload"),
                ("b", "hardlink", "a"),
                ("c", "hardlink", "b"),
            ],
            {"a": b"payload", "b": b"payload", "c": b"payload"},
            "only direct internal regular-file hardlinks allowed",
        ),
        (
            [("a", "file", b"payload"), ("b", "symlink", "a")],
            {"a": b"payload", "b": b"payload"},
            "symlink/directory/special archive member forbidden",
        ),
        (
            [("a", "file", b"payload"), ("a", "file", b"payload")],
            {"a": b"payload"},
            "archive member set differs",
        ),
    ],
    ids=["external-hardlink", "hardlink-chain", "symlink", "duplicate-name"],
)
def test_rejects_unsafe_or_duplicate_members(tmp_path, members, expected, match):
    final_path = tmp_path / "archive.tar.gz"
    _write_tar(tmp_path / "archive.tar.gz.partial", members)

    result = _verify(final_path, _expected(expected))

    assert result.returncode != 0
    assert match in result.stderr
    assert not final_path.exists()
    assert (tmp_path / "archive.tar.gz.partial").exists()


@pytest.mark.parametrize(
    "members,expected,match",
    [
        ([("a", "file", b"wrong")], {"a": b"right"}, "archive member SHA differs"),
        ([("a", "file", b"payload")], {"a": b"payload!"}, "archive member size differs"),
        (
            [("a", "file", b"payload"), ("extra", "file", b"x")],
            {"a": b"payload"},
            "archive member set differs",
        ),
        (
            [("a", "file", b"payload")],
            {"a": b"payload", "missing": b"not present"},
            "archive member set differs",
        ),
    ],
    ids=["wrong-bytes", "wrong-size", "extra-member", "missing-member"],
)
def test_rejects_wrong_bytes_size_or_membership(tmp_path, members, expected, match):
    final_path = tmp_path / "archive.tar.gz"
    _write_tar(tmp_path / "archive.tar.gz.partial", members)

    result = _verify(final_path, _expected(expected))

    assert result.returncode != 0
    assert match in result.stderr
    assert not final_path.exists()
    assert (tmp_path / "archive.tar.gz.partial").exists()


def test_existing_final_archive_is_never_overwritten(tmp_path):
    final_path = tmp_path / "archive.tar.gz"
    original = b"pre-existing final archive"
    final_path.write_bytes(original)
    _write_tar(tmp_path / "archive.tar.gz.partial", [("a", "file", b"payload")])

    result = _verify(final_path, _expected({"a": b"payload"}))

    assert result.returncode != 0
    assert "archive destination already exists" in result.stderr
    assert final_path.read_bytes() == original
    assert (tmp_path / "archive.tar.gz.partial").exists()
