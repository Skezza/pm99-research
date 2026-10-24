from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from scripts.season_portrait_pipeline_v1 import copy_game_with_factory_media_links


def _write(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_game(root: Path) -> dict[str, Path]:
    return {
        "simul": _write(root, "SIMULDAT/Modelos.pkf", b"immutable model media"),
        "nested_sfx": _write(root, "SFX/nested/AMBIENTE.PKF", b"immutable sound media"),
        "resources": _write(root, "RECURSOS.PKF", b"immutable resources"),
        "images": _write(root, "IMG.PKF", b"immutable image media"),
        "jug": _write(root, "DBDAT/JUG98030.FDI", b"mutable roster"),
        "eq": _write(root, "DBDAT/EQ98030.FDI", b"mutable ownership"),
        "dat": _write(root, "DAT/BASE.DAT", b"regular data copy"),
        "exe": _write(root, "MANAGPRE.EXE", b"regular executable copy"),
        "config": _write(root, "manager.ini", b"fullscreen=1"),
        "save": _write(root, "SAVES/slot1.sav", b"mutable save copy"),
        "dbdat_simul_named": _write(root, "DBDAT/SIMULDAT/not-factory-root.pkf", b"must copy"),
    }


def test_only_exact_factory_media_is_hardlinked_and_mutable_files_are_isolated(tmp_path):
    source = tmp_path / "source"
    files = _sample_game(source)
    hashes_before = {key: _sha(path) for key, path in files.items()}
    output = tmp_path / "build" / "game"

    receipt = copy_game_with_factory_media_links(source, output)

    assert receipt["same_filesystem"] is True
    assert receipt["source_inventory_unchanged"] is True
    assert receipt["linked_media_paths"] == sorted(
        ["SIMULDAT/Modelos.pkf", "SFX/nested/AMBIENTE.PKF", "RECURSOS.PKF", "IMG.PKF"]
    )
    assert receipt["total_logical_bytes"] == receipt["linked_media_logical_bytes"] + receipt["regular_copy_logical_bytes"]
    for key in ("simul", "nested_sfx", "resources", "images"):
        assert os.path.samefile(files[key], output / files[key].relative_to(source))
    for key in ("jug", "eq", "dat", "exe", "config", "save", "dbdat_simul_named"):
        destination = output / files[key].relative_to(source)
        assert not os.path.samefile(files[key], destination)
        assert _sha(destination) == hashes_before[key]

    # Visual application writes can touch only copied files; the registered
    # source's configuration and native roster stay byte-identical.
    (output / "manager.ini").write_bytes(b"fullscreen=0")
    (output / "DBDAT/JUG98030.FDI").write_bytes(b"patched roster")
    assert files["config"].read_bytes() == b"fullscreen=1"
    assert files["jug"].read_bytes() == b"mutable roster"
    assert {key: _sha(path) for key, path in files.items()} == hashes_before


def test_hardlink_failure_fails_closed_without_regular_copy_fallback(tmp_path, monkeypatch):
    source = tmp_path / "source"
    files = _sample_game(source)
    before = {key: _sha(path) for key, path in files.items()}
    output = tmp_path / "build" / "game"

    def fail_link(*args, **kwargs):
        raise OSError("simulated hardlink failure")

    monkeypatch.setattr("scripts.season_portrait_pipeline_v1.os.link", fail_link)
    with pytest.raises(OSError, match="simulated hardlink failure"):
        copy_game_with_factory_media_links(source, output)

    assert not output.exists()
    assert {key: _sha(path) for key, path in files.items()} == before


def test_symlink_inputs_are_rejected_before_target_creation(tmp_path):
    source = tmp_path / "source"
    files = _sample_game(source)
    (source / "SIMULDAT" / "alias.pkf").symlink_to(files["simul"])
    output = tmp_path / "build" / "game"

    with pytest.raises(ValueError, match="does not accept symlinks"):
        copy_game_with_factory_media_links(source, output)

    assert not output.exists()


def test_low_copy_space_is_rejected_before_target_creation(tmp_path, monkeypatch):
    source = tmp_path / "source"
    files = _sample_game(source)
    before = {key: _sha(path) for key, path in files.items()}
    output = tmp_path / "build" / "game"

    class Usage:
        free = 1024**3

    monkeypatch.setattr("scripts.season_portrait_pipeline_v1.shutil.disk_usage", lambda _: Usage())
    with pytest.raises(OSError, match="regular game files plus 1 GiB reserve"):
        copy_game_with_factory_media_links(source, output)

    assert not output.exists()
    assert {key: _sha(path) for key, path in files.items()} == before
