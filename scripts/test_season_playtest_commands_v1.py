from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import season_playtest_commands_v1 as commands


def test_target_seasons_are_the_requested_25_without_2015_baseline() -> None:
    seasons = commands.target_seasons()
    assert len(seasons) == 25
    assert seasons[0] == "2000-01"
    assert seasons[-1] == "2025-26"
    assert commands.BASELINE_SEASON not in seasons


def test_command_lines_are_parameterised_for_every_target() -> None:
    lines = commands.command_lines()
    assert len(lines) == 25
    assert lines[0].endswith("--season 2000-01 --session review-2000-01")
    assert lines[-1].endswith("--season 2025-26 --session review-2025-26")
    assert all("season_playtest_commands_v1.py play" in line for line in lines)


def test_prepare_matrix_creates_then_indexes_every_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    created: list[str] = []
    indexed: dict[str, object] = {}
    source = tmp_path / "source"
    source.mkdir()
    calendar = tmp_path / "MANAGPRE.EXE"
    calendar.write_bytes(b"calendar")

    def fake_create_variant(**kwargs: object) -> dict[str, object]:
        created.append(str(kwargs["target_season"]))
        return {"game_root": f"/game/{kwargs['target_season']}"}

    def fake_create_matrix(**kwargs: object) -> dict[str, object]:
        indexed.update(kwargs)
        return {"matrix_path": "/matrix.json", "variant_count": 26}

    monkeypatch.setattr(commands.variants, "create_variant", fake_create_variant)
    monkeypatch.setattr(commands.variants, "create_matrix", fake_create_matrix)
    result = commands.prepare_matrix(
        output_root=tmp_path / "output",
        source_game_root=source,
        calendar_source_exe=calendar,
        run_database_validation=True,
    )

    assert created == list(commands.target_seasons())
    assert result["created_count"] == 25
    assert result["reused_verified_count"] == 0
    assert indexed["require_target_26"] is True


def test_prepare_session_copies_once_and_resumes_the_same_named_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    variant_id = commands.variant_id_for("2000-01")
    variant_root = output_root / variant_id
    (variant_root / "game").mkdir(parents=True)
    (variant_root / "game" / "MANAGPRE.EXE").write_bytes(b"game")
    pipeline.write_canonical_json(variant_root / "provisional-playtest-manifest.json", {"fixture": True})
    copied: list[tuple[Path, Path]] = []

    monkeypatch.setattr(
        commands.variants,
        "verify_variant",
        lambda **_kwargs: {"variant_id": variant_id, "game_root": str(variant_root / "game")},
    )

    def fake_copy(source: Path, target: Path) -> None:
        copied.append((source, target))
        target.mkdir()
        (target / "MANAGPRE.EXE").write_bytes(b"game")

    monkeypatch.setattr(commands.variants, "_copy_game_tree", fake_copy)
    created = commands.prepare_session(
        output_root=output_root,
        season="2000-01",
        session_id="first-save",
    )
    resumed = commands.prepare_session(
        output_root=output_root,
        season="2000-01",
        session_id="first-save",
    )

    assert created["action"] == "created"
    assert resumed["action"] == "resumed"
    assert copied == [(variant_root / "game", output_root / "sessions" / "2000-01" / "first-save" / "game")]
    session_manifest = json.loads(
        (output_root / "sessions" / "2000-01" / "first-save" / "session.json").read_text(encoding="utf-8")
    )
    assert session_manifest["season"] == "2000-01"
    assert session_manifest["source_variant"]["variant_id"] == variant_id


def test_command_only_prepares_session_without_needing_wine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    expected = {"ok": True, "game_root": str(tmp_path / "game"), "source_variant": "variant"}
    monkeypatch.setattr(commands, "prepare_session", lambda **_kwargs: expected)
    result = commands.launch_session(
        output_root=tmp_path,
        season="2000-01",
        session_id="review",
        wine_bin="wine",
        wine_prefix=None,
        command_only=True,
    )
    assert result["command"] == ["wine", "MANAGPRE.EXE"]
    assert result["launched"] is False


def test_real_launch_checks_desktop_before_creating_a_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(commands.shutil, "which", lambda _command: "/usr/bin/wine")
    monkeypatch.setattr(
        commands,
        "prepare_session",
        lambda **_kwargs: pytest.fail("session must not be created before desktop preflight"),
    )

    with pytest.raises(commands.PlayCommandError, match="DISPLAY"):
        commands.launch_session(
            output_root=tmp_path,
            season="2000-01",
            session_id="review",
            wine_bin="wine",
            wine_prefix=None,
            command_only=False,
        )
