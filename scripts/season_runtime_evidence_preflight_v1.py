#!/usr/bin/env python3
"""Bind one future PM99 route capture to a finished season release.

This tool deliberately does *not* launch PM99, contact a runner, or create a
runtime/screenshot claim.  It is the hand-off immediately before a genuine
route capture: the selected club, selector coordinates, final game-tree
inventory, final season package and release manifest are all checked together
and a write-once, path-aware launch plan is emitted.

The PM99 runner's historic wrapper names still mention Stoke.  That is an
implementation detail, not permission to reuse Stoke's selector coordinates
or roster assumptions.  A profile supplied to this command must name the
target package club and its own four selector coordinates explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402


PROFILE_SCHEMA = "pm99-target-club-runtime-profile-v1"
RECEIPT_SCHEMA = "pm99-target-club-runtime-preflight-v1"
RUNNER_ROUTES = frozenset({
    "squad", "line_up", "tactics", "opponent", "transfers", "finance",
    "board_room", "ground", "staff", "results", "league_tables", "fixtures",
})
REQUIRED_DBDAT_FILES = (
    "JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF",
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class RuntimeEvidencePreflightError(ValueError):
    """The proposed capture is not bound to one finished release."""


def _normalise_season(package: Mapping[str, Any]) -> str:
    value = package.get("season")
    if not isinstance(value, Mapping):
        raise RuntimeEvidencePreflightError("season package has no season object")
    start, end = value.get("start_year"), value.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int):
        raise RuntimeEvidencePreflightError("season package season years must be integers")
    return pipeline.normalise_season_id(f"{start:04d}-{end % 100:02d}")


def _canonical_read(path: Path, *, label: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise RuntimeEvidencePreflightError(f"{label} must be a regular file: {path}")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeEvidencePreflightError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != pipeline.canonical_json_bytes(value) + b"\n":
        raise RuntimeEvidencePreflightError(f"{label} must be canonically encoded JSON: {path}")
    return value


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise RuntimeEvidencePreflightError(
            f"{label} must match {_IDENTIFIER.pattern!r}: {value!r}"
        )
    return value


def _coordinate(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 4096:
        raise RuntimeEvidencePreflightError(f"{label} must be an integer client coordinate from 0 through 4096")
    return value


def validate_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical target-club profile or fail before a runner launch."""

    required = {"schema_version", "season", "club", "selector", "capture"}
    if set(value) != required:
        raise RuntimeEvidencePreflightError("runtime profile has invalid keys")
    if value["schema_version"] != PROFILE_SCHEMA:
        raise RuntimeEvidencePreflightError("runtime profile has an unsupported schema")
    season = pipeline.normalise_season_id(str(value["season"] or ""))

    club = value["club"]
    if not isinstance(club, Mapping) or set(club) != {"id", "carrier_id", "name"}:
        raise RuntimeEvidencePreflightError("runtime profile club must contain exactly id, carrier_id and name")
    club_id = _identifier(club["id"], label="runtime profile club.id")
    carrier_id = club["carrier_id"]
    if not isinstance(carrier_id, int) or isinstance(carrier_id, bool) or carrier_id < 1:
        raise RuntimeEvidencePreflightError("runtime profile club.carrier_id must be a positive integer")
    club_name = club["name"]
    if not isinstance(club_name, str) or not club_name.strip():
        raise RuntimeEvidencePreflightError("runtime profile club.name must be a non-empty string")

    selector = value["selector"]
    selector_keys = {
        "team_name", "team_select_x", "team_select_y", "division_select_x", "division_select_y",
    }
    if not isinstance(selector, Mapping) or set(selector) != selector_keys:
        raise RuntimeEvidencePreflightError("runtime profile selector has invalid keys")
    team_name = selector["team_name"]
    if not isinstance(team_name, str) or not team_name.strip():
        raise RuntimeEvidencePreflightError("runtime profile selector.team_name must be a non-empty string")
    normalised_selector = {
        "team_name": team_name,
        "team_select_x": _coordinate(selector["team_select_x"], label="selector.team_select_x"),
        "team_select_y": _coordinate(selector["team_select_y"], label="selector.team_select_y"),
        "division_select_x": _coordinate(selector["division_select_x"], label="selector.division_select_x"),
        "division_select_y": _coordinate(selector["division_select_y"], label="selector.division_select_y"),
    }

    capture = value["capture"]
    if not isinstance(capture, Mapping) or set(capture) != {"routes", "profile_count"}:
        raise RuntimeEvidencePreflightError("runtime profile capture must contain exactly routes and profile_count")
    routes = capture["routes"]
    if not isinstance(routes, list) or not routes or any(not isinstance(route, str) for route in routes):
        raise RuntimeEvidencePreflightError("runtime profile capture.routes must be a non-empty string list")
    if routes != sorted(set(routes)):
        raise RuntimeEvidencePreflightError("runtime profile capture.routes must be unique and sorted")
    unsupported = sorted(set(routes) - RUNNER_ROUTES)
    if unsupported:
        raise RuntimeEvidencePreflightError(f"runtime profile requests unsupported runner routes: {unsupported}")
    if "squad" not in routes or "line_up" not in routes:
        raise RuntimeEvidencePreflightError("runtime profile must capture both squad and line_up")
    profile_count = capture["profile_count"]
    if not isinstance(profile_count, int) or isinstance(profile_count, bool) or not 0 <= profile_count <= 20:
        raise RuntimeEvidencePreflightError("runtime profile capture.profile_count must be an integer from 0 through 20")
    return {
        "schema_version": PROFILE_SCHEMA,
        "season": season,
        "club": {"id": club_id, "carrier_id": carrier_id, "name": club_name},
        "selector": normalised_selector,
        "capture": {"routes": routes, "profile_count": profile_count},
    }


def _index_by_id(rows: Any, *, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise RuntimeEvidencePreflightError(f"season package {label} must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise RuntimeEvidencePreflightError(f"season package {label} contains a malformed row")
        indexed[row["id"]] = row
    return indexed


def _selected_content(package: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    clubs = _index_by_id(package.get("clubs"), label="clubs")
    club_profile = profile["club"]
    club = clubs.get(club_profile["id"])
    if club is None:
        raise RuntimeEvidencePreflightError("runtime profile club.id is absent from the season package")
    if club.get("carrier_id") != club_profile["carrier_id"]:
        raise RuntimeEvidencePreflightError("runtime profile carrier ID does not match the selected package club")
    if club.get("name") != club_profile["name"]:
        raise RuntimeEvidencePreflightError("runtime profile club name does not match the selected package club")

    managers = _index_by_id(package.get("managers"), label="managers")
    manager = managers.get(str(club.get("manager_id") or ""))
    if manager is None or not isinstance(manager.get("name"), str) or not manager["name"].strip():
        raise RuntimeEvidencePreflightError("selected package club has no resolved manager name")

    opening = club.get("opening")
    if not isinstance(opening, Mapping) or opening.get("policy") == "preserve-existing-mode1":
        raise RuntimeEvidencePreflightError("selected package club has no target-season opening lineup")
    starters = opening.get("starting_xi_player_ids")
    if not isinstance(starters, list) or len(starters) != 11 or len(set(starters)) != 11:
        raise RuntimeEvidencePreflightError("selected package club opening lineup is not an exact eleven")
    players = _index_by_id(package.get("players"), label="players")
    selected_players: list[dict[str, Any]] = []
    for player_id in starters:
        player = players.get(str(player_id))
        if player is None or not isinstance(player.get("name"), str) or not player["name"].strip():
            raise RuntimeEvidencePreflightError(f"selected opening lineup player is unresolved: {player_id!r}")
        selected_players.append({"id": player["id"], "carrier_id": player.get("carrier_id"), "name": player["name"]})
    formation = opening.get("formation")
    if formation is not None and not isinstance(formation, str):
        raise RuntimeEvidencePreflightError("selected package opening formation must be a string or null")
    fixture_date = opening.get("fixture_date")
    if not isinstance(fixture_date, str) or not fixture_date:
        raise RuntimeEvidencePreflightError("selected package opening fixture date is missing")
    return {
        "club": {"id": club["id"], "carrier_id": club["carrier_id"], "name": club["name"]},
        "manager": {"id": manager["id"], "carrier_id": manager.get("carrier_id"), "name": manager["name"]},
        "opening_lineup": {
            "fixture_date": fixture_date,
            "formation": formation,
            "players": selected_players,
        },
    }


def _verify_release_binding(
    *, package_path: Path, package: Mapping[str, Any], release_manifest_path: Path, game_tree: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    release_manifest = _canonical_read(release_manifest_path, label="release manifest")
    try:
        pipeline.validate_release_manifest(release_manifest)
    except pipeline.PipelineError as exc:
        raise RuntimeEvidencePreflightError(f"release manifest is invalid: {exc}") from exc
    package_season = _normalise_season(package)
    if release_manifest["season"] != package_season:
        raise RuntimeEvidencePreflightError("release manifest season does not match the season package")
    descriptor = pipeline.canonical_json_document_descriptor(package_path, document_id="season-package")
    if release_manifest["season_document"] != descriptor:
        raise RuntimeEvidencePreflightError("release manifest is not bound to this exact season package")
    try:
        inventory = pipeline.verify_release_output(manifest=release_manifest, output_tree=game_tree)
    except pipeline.PipelineError as exc:
        raise RuntimeEvidencePreflightError(f"game tree does not match release manifest: {exc}") from exc
    missing = [
        name for name in (*REQUIRED_DBDAT_FILES,)
        if not (game_tree / "DBDAT" / name).is_file() or (game_tree / "DBDAT" / name).is_symlink()
    ]
    executable = game_tree / "MANAGPRE.EXE"
    if not executable.is_file() or executable.is_symlink():
        missing.append("MANAGPRE.EXE")
    if missing:
        raise RuntimeEvidencePreflightError(
            "finished release tree lacks required runner inputs: " + ", ".join(missing)
        )
    return release_manifest, inventory


def build_preflight(
    *, package_path: Path, release_manifest_path: Path, game_tree: Path,
    profile_path: Path, worker: str, run_tag: str,
) -> dict[str, Any]:
    """Check one planned capture and return a non-runtime evidence plan."""

    package_path = package_path.expanduser().resolve()
    game_tree = game_tree.expanduser().resolve()
    if not game_tree.is_dir() or game_tree.is_symlink():
        raise RuntimeEvidencePreflightError(f"game tree must be a regular directory: {game_tree}")
    try:
        package = package_v2.read_canonical_package(package_path)
        package_v2.validate_package(package, strict=True)
    except (OSError, package_v2.PackageValidationError) as exc:
        raise RuntimeEvidencePreflightError(f"season package is not a strict canonical package: {exc}") from exc
    profile = validate_profile(_canonical_read(profile_path, label="runtime profile"))
    package_season = _normalise_season(package)
    if profile["season"] != package_season:
        raise RuntimeEvidencePreflightError("runtime profile season does not match the season package")
    selected = _selected_content(package, profile)
    release_manifest, inventory = _verify_release_binding(
        package_path=package_path,
        package=package,
        release_manifest_path=release_manifest_path,
        game_tree=game_tree,
    )
    worker = _identifier(worker, label="worker")
    run_tag = _identifier(run_tag, label="run_tag")
    selector = profile["selector"]
    arguments = [
        "--dbdat-dir", str(game_tree / "DBDAT"),
        "--exe-file", str(game_tree / "MANAGPRE.EXE"),
        "--manager-name", "AI",
        "--team-name", selector["team_name"],
        "--team-select-x", str(selector["team_select_x"]),
        "--team-select-y", str(selector["team_select_y"]),
        "--division-select-x", str(selector["division_select_x"]),
        "--division-select-y", str(selector["division_select_y"]),
        "--profile-count", str(profile["capture"]["profile_count"]),
    ]
    for route in profile["capture"]["routes"]:
        arguments.extend(("--capture-route", route))
    command = [
        "./scripts/run_pm99_experiment.sh", "route-capture", "--worker", worker,
        "--run-tag", run_tag, "--", *arguments,
    ]
    return {
        "schema_version": RECEIPT_SCHEMA,
        "state": "preflight-passed-runtime-not-executed",
        "release_eligible": False,
        "season": package_season,
        "release": {
            "manifest_sha256": hashlib.sha256(release_manifest_path.read_bytes()).hexdigest(),
            "output_inventory_fingerprint": inventory["files_fingerprint"],
            "season_package_canonical_sha256": release_manifest["season_document"]["canonical_sha256"],
        },
        "runtime_profile": {
            "sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            "club": selected["club"],
            "selector": profile["selector"],
            "capture": profile["capture"],
        },
        "expected_target_content": {
            "manager": selected["manager"],
            "opening_lineup": selected["opening_lineup"],
        },
        "launch": {
            "launcher": "./scripts/run_pm99_experiment.sh",
            "experiment": "route-capture",
            "worker": worker,
            "run_tag": run_tag,
            "argv": command,
            "shell_command": shlex.join(command),
        },
        "required_follow_up": [
            "Run exactly launch.argv against the declared finished release tree.",
            "Retain the runner summary and screenshots under the declared run tag.",
            "Verify the runner reached the target club and required routes before treating any screenshot as evidence.",
            "Bind successful runtime receipts and screenshot hashes in a separate release attestation.",
        ],
        "not_claimed": [
            "PM99 was not launched by this preflight.",
            "No runtime route, screenshot, or playable-release claim follows from this receipt.",
            "Selector coordinates are profile inputs and are not inferred from the fixed carrier ID.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-package", required=True, type=Path)
    parser.add_argument("--release-manifest", required=True, type=Path)
    parser.add_argument("--game-tree", required=True, type=Path)
    parser.add_argument("--runtime-profile", required=True, type=Path)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = build_preflight(
            package_path=args.season_package,
            release_manifest_path=args.release_manifest,
            game_tree=args.game_tree,
            profile_path=args.runtime_profile,
            worker=args.worker,
            run_tag=args.run_tag,
        )
        pipeline.write_canonical_json(args.output, receipt)
    except (OSError, pipeline.PipelineError, RuntimeEvidencePreflightError) as exc:
        print(f"runtime evidence preflight error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "state": receipt["state"], "season": receipt["season"],
        "club": receipt["runtime_profile"]["club"]["name"], "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
