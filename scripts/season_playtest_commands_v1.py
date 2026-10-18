#!/usr/bin/env python3
"""Prepare, verify and launch the 25 provisional PM99 calendar playtests.

This is a local usability layer over :mod:`season_playtest_variant_v1`, not a
second database builder.  It deliberately exposes one parameterised command
for every target season except 2015/16, which remains the known-good content
baseline:

* ``prepare`` makes or verifies 25 immutable calendar-only presets;
* ``verify`` proves those presets still match their locked inventories;
* ``commands`` prints the 25 copy-and-paste play commands; and
* ``play`` first verifies a preset, then opens a mutable named session copied
  from it with Wine.

The mutable session keeps user saves away from the verified preset.  A target
season's clock is correct, but its player, club, manager, kit and portrait
content is byte-identical to the verified 2015/16 baseline.  These are
therefore playable provisional targets, never historical target-season
database claims.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_playtest_variant_v1 as variants  # noqa: E402


BASELINE_ID = "pm99-2015-16-world-r0"
BASELINE_SEASON = "2015-16"
MATRIX_ID = "pm99-2000-2025-provisional-playtest-r1"
VARIANT_REVISION = "r1"
SESSION_SCHEMA = "pm99-provisional-playtest-session-v1"
DEFAULT_BASELINE_GAME_ROOT = ROOT / ".local/season-workspace-v1/2015-16-final-clean-game"
DEFAULT_CALENDAR_SOURCE_EXE = ROOT / ".local/season-pipeline-v2/pm99-base-clean/MANAGPRE.EXE"
DEFAULT_OUTPUT_ROOT = ROOT / ".local/provisional-playtests"


class PlayCommandError(ValueError):
    """The local command cannot safely prepare or launch a target."""


def target_seasons() -> tuple[str, ...]:
    """Return the 25 playtest targets, excluding the 2015/16 content baseline."""

    return tuple(season for season in variants.TARGET_26_SEASONS if season != BASELINE_SEASON)


def variant_id_for(season: str) -> str:
    season = variants._normalise_season(season)
    if season not in target_seasons():
        raise PlayCommandError(
            f"{season} is not a provisional target; {BASELINE_SEASON} is the known-good baseline"
        )
    return f"pm99-{season}-calendar-playtest-{VARIANT_REVISION}"


def _ordinary_directory(path: Path, *, label: str, create: bool = False) -> Path:
    path = path.expanduser().resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise PlayCommandError(f"{label} must be an existing ordinary directory: {path}")
    return path


def _canonical_read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlayCommandError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != pipeline.canonical_json_bytes(value) + b"\n":
        raise PlayCommandError(f"{label} must be canonical JSON: {path}")
    return value


def _session_manifest(
    *, season: str, session_id: str, variant_id: str, variant_manifest_sha256: str
) -> dict[str, Any]:
    return {
        "schema_version": SESSION_SCHEMA,
        "season": season,
        "session_id": session_id,
        "source_variant": {
            "variant_id": variant_id,
            "manifest_sha256": variant_manifest_sha256,
        },
        "purpose": "Mutable local save/session copied from a verified provisional calendar playtest.",
        "historical_status": "provisional-calendar-only-not-a-historical-target-season-database",
    }


def _validate_session_manifest(
    value: Mapping[str, Any], *, season: str, session_id: str,
    variant_id: str, variant_manifest_sha256: str,
) -> None:
    expected = _session_manifest(
        season=season,
        session_id=session_id,
        variant_id=variant_id,
        variant_manifest_sha256=variant_manifest_sha256,
    )
    if pipeline.canonical_json_bytes(value) != pipeline.canonical_json_bytes(expected):
        raise PlayCommandError("existing session does not belong to this verified provisional target")


def _prepare_one(
    *, season: str, output_root: Path, source_game_root: Path,
    calendar_source_exe: Path, run_database_validation: bool,
) -> dict[str, Any]:
    variant_id = variant_id_for(season)
    variant_root = output_root / variant_id
    if variant_root.exists() or variant_root.is_symlink():
        verified = variants.verify_variant(
            variant_root=variant_root,
            run_database_validation=run_database_validation,
        )
        return {
            "season": season,
            "variant_id": variant_id,
            "action": "reused-verified",
            "game_root": verified["game_root"],
        }
    created = variants.create_variant(
        source_game_root=source_game_root,
        calendar_source_exe=calendar_source_exe,
        output_root=output_root,
        variant_id=variant_id,
        baseline_id=BASELINE_ID,
        baseline_season=BASELINE_SEASON,
        target_season=season,
        skip_database_validation=not run_database_validation,
    )
    return {
        "season": season,
        "variant_id": variant_id,
        "action": "created",
        "game_root": created["game_root"],
    }


def prepare_matrix(
    *, output_root: Path = DEFAULT_OUTPUT_ROOT,
    source_game_root: Path = DEFAULT_BASELINE_GAME_ROOT,
    calendar_source_exe: Path = DEFAULT_CALENDAR_SOURCE_EXE,
    run_database_validation: bool = True,
) -> dict[str, Any]:
    """Create missing presets and verify existing presets without replacing either."""

    output_root = _ordinary_directory(output_root, label="output_root", create=True)
    source_game_root = _ordinary_directory(source_game_root, label="source_game_root")
    calendar_source_exe = calendar_source_exe.expanduser().resolve()
    if calendar_source_exe.is_symlink() or not calendar_source_exe.is_file():
        raise PlayCommandError(f"calendar_source_exe must be an ordinary file: {calendar_source_exe}")

    rows = [
        _prepare_one(
            season=season,
            output_root=output_root,
            source_game_root=source_game_root,
            calendar_source_exe=calendar_source_exe,
            run_database_validation=run_database_validation,
        )
        for season in target_seasons()
    ]
    matrix = variants.create_matrix(
        output_root=output_root,
        baseline_game_root=source_game_root,
        baseline_id=BASELINE_ID,
        baseline_season=BASELINE_SEASON,
        matrix_id=MATRIX_ID,
        require_target_26=True,
    )
    return {
        "ok": True,
        "release_class": variants.RELEASE_CLASS,
        "historical_status": "provisional-calendar-only-not-a-historical-target-season-database",
        "target_count": len(rows),
        "created_count": sum(row["action"] == "created" for row in rows),
        "reused_verified_count": sum(row["action"] == "reused-verified" for row in rows),
        "variants": rows,
        "matrix": matrix,
    }


def verify_matrix(
    *, output_root: Path = DEFAULT_OUTPUT_ROOT, run_database_validation: bool = False,
) -> dict[str, Any]:
    """Verify every one of the 25 immutable playtest presets without writing."""

    output_root = _ordinary_directory(output_root, label="output_root")
    rows: list[dict[str, Any]] = []
    for season in target_seasons():
        variant_root = output_root / variant_id_for(season)
        if not variant_root.is_dir() or variant_root.is_symlink():
            raise PlayCommandError(f"missing prepared provisional target for {season}: {variant_root}")
        verified = variants.verify_variant(
            variant_root=variant_root,
            run_database_validation=run_database_validation,
        )
        rows.append({"season": season, "variant_id": verified["variant_id"], "status": "verified"})
    return {
        "ok": True,
        "release_class": variants.RELEASE_CLASS,
        "target_count": len(rows),
        "variants": rows,
    }


def _session_root(output_root: Path, *, season: str, session_id: str) -> Path:
    try:
        session_id = variants._identifier(session_id, label="session")
    except variants.PlaytestVariantError as exc:
        raise PlayCommandError(str(exc)) from exc
    return output_root / "sessions" / season / session_id


def prepare_session(*, output_root: Path, season: str, session_id: str) -> dict[str, Any]:
    """Copy a verified preset to a named mutable local game session once."""

    output_root = _ordinary_directory(output_root, label="output_root")
    season = variants._normalise_season(season)
    variant_id = variant_id_for(season)
    variant_root = output_root / variant_id
    verified = variants.verify_variant(variant_root=variant_root, run_database_validation=False)
    variant_manifest = variant_root / variants.MANIFEST_NAME
    variant_manifest_sha256 = pipeline.sha256_file(variant_manifest)
    session_root = _session_root(output_root, season=season, session_id=session_id)
    session_manifest = session_root / "session.json"
    expected_manifest = _session_manifest(
        season=season,
        session_id=session_id,
        variant_id=variant_id,
        variant_manifest_sha256=variant_manifest_sha256,
    )

    if session_root.exists() or session_root.is_symlink():
        if session_root.is_symlink() or not session_root.is_dir():
            raise PlayCommandError(f"session root is not an ordinary directory: {session_root}")
        actual_manifest = _canonical_read(session_manifest, label="session manifest")
        _validate_session_manifest(
            actual_manifest,
            season=season,
            session_id=session_id,
            variant_id=variant_id,
            variant_manifest_sha256=variant_manifest_sha256,
        )
        game_root = session_root / "game"
        if game_root.is_symlink() or not (game_root / "MANAGPRE.EXE").is_file():
            raise PlayCommandError(f"session game root is incomplete: {game_root}")
        action = "resumed"
    else:
        session_root.mkdir(parents=True)
        game_root = session_root / "game"
        try:
            variants._copy_game_tree(variant_root / "game", game_root)
            pipeline.write_canonical_json(session_manifest, expected_manifest)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise PlayCommandError(f"failed to create isolated session: {exc}") from exc
        action = "created"
    return {
        "ok": True,
        "action": action,
        "season": season,
        "session_id": session_id,
        "game_root": str(game_root),
        "source_variant": verified["variant_id"],
        "historical_status": expected_manifest["historical_status"],
    }


def command_lines() -> list[str]:
    """Return exactly the user-facing local commands for all provisional targets."""

    return [
        "python3 scripts/season_playtest_commands_v1.py play "
        f"--season {season} --session review-{season}"
        for season in target_seasons()
    ]


def _require_desktop_launch_prerequisites(wine_bin: str) -> None:
    if shutil.which(wine_bin) is None:
        raise PlayCommandError(f"Wine executable is unavailable: {wine_bin}")
    if not os.environ.get("DISPLAY"):
        raise PlayCommandError("DISPLAY is not set; launch from a graphical desktop session")


def launch_session(*, output_root: Path, season: str, session_id: str,
                   wine_bin: str, wine_prefix: Path | None, command_only: bool) -> dict[str, Any]:
    """Open a mutable session only after its source preset verifies exactly."""

    if not command_only:
        _require_desktop_launch_prerequisites(wine_bin)
    session = prepare_session(output_root=output_root, season=season, session_id=session_id)
    game_root = Path(session["game_root"])
    command = [wine_bin, "MANAGPRE.EXE"]
    if command_only:
        return {**session, "command": command, "cwd": str(game_root), "launched": False}
    environment = os.environ.copy()
    environment.setdefault("WINEDEBUG", "-all")
    if wine_prefix is not None:
        environment["WINEPREFIX"] = str(wine_prefix.expanduser().resolve())
    completed = subprocess.run(command, cwd=str(game_root), env=environment, check=False)
    return {**session, "command": command, "cwd": str(game_root), "launched": True, "returncode": completed.returncode}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="make or verify all 25 immutable provisional presets")
    prepare.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    prepare.add_argument("--source-game-root", type=Path, default=DEFAULT_BASELINE_GAME_ROOT)
    prepare.add_argument("--calendar-source-exe", type=Path, default=DEFAULT_CALENDAR_SOURCE_EXE)
    prepare.add_argument("--skip-database-validation", action="store_true")

    verify = commands.add_parser("verify", help="verify all 25 immutable provisional presets")
    verify.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    verify.add_argument("--run-database-validation", action="store_true")

    commands.add_parser("commands", help="print the 25 copy-and-paste play commands")

    play = commands.add_parser("play", help="verify one preset, create/resume a mutable session, and launch it")
    play.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    play.add_argument("--season", required=True, choices=target_seasons())
    play.add_argument("--session", required=True, help="named mutable save/session directory")
    play.add_argument("--wine-bin", default=os.environ.get("PM99_WINE_BIN", "wine"))
    play.add_argument("--wine-prefix", type=Path)
    play.add_argument("--command-only", action="store_true", help="prepare the session but do not open Wine")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_matrix(
                output_root=args.output_root,
                source_game_root=args.source_game_root,
                calendar_source_exe=args.calendar_source_exe,
                run_database_validation=not args.skip_database_validation,
            )
        elif args.command == "verify":
            result = verify_matrix(
                output_root=args.output_root,
                run_database_validation=bool(args.run_database_validation),
            )
        elif args.command == "commands":
            result = {
                "ok": True,
                "target_count": len(target_seasons()),
                "release_class": variants.RELEASE_CLASS,
                "historical_status": "provisional-calendar-only-not-a-historical-target-season-database",
                "commands": command_lines(),
            }
        else:
            result = launch_session(
                output_root=args.output_root,
                season=args.season,
                session_id=args.session,
                wine_bin=args.wine_bin,
                wine_prefix=args.wine_prefix,
                command_only=bool(args.command_only),
            )
    except (OSError, pipeline.PipelineError, variants.PlaytestVariantError, PlayCommandError) as exc:
        print(f"provisional playtest command error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
