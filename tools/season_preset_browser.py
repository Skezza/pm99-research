#!/usr/bin/env python3
"""Serve a local PM99 season preset browser and amendment workbench.

The browser discovers manifests and supporting documents below ``seasons/`` at
startup.  It binds only to loopback and never accepts uploads.  Frozen inputs
and PM99 game files remain read-only; the only editable surface is a
hash-bound ``editorial-amendments/working.json`` sidecar for each season.  A
materialisation creates new local source copies and a receipt, never an
in-place database edit.  It is deliberately separate from the PM99 database
editor and the hosted Manifest Desk.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import re
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import season_manifest_amendments as amendments
from tools import season_preset_spreadsheet as spreadsheet
from scripts import season_release_registry_v1 as release_registry


DEFAULT_SEASONS_ROOT = ROOT / "seasons"
DEFAULT_PLAYTESTS_ROOT = ROOT / ".local/provisional-playtests"
DEFAULT_AUTHORING_ROOT = ROOT / ".local/season-historical-squad-backfill-v1"
DEFAULT_RECIPE_ROOT = ROOT / ".local/season-worldwide-merged-v1"
DEFAULT_STATIC_INGRESS_ROOT = ROOT / ".local/season-static-ingress-v1"
DEFAULT_RUNTIME_CANDIDATES_ROOT = ROOT / ".local/season-runtime-candidates-v1"
DEFAULT_KIT_RENDER_ROOT = ROOT / ".local/season-kit-renders-v1"
DEFAULT_PORTRAIT_RENDER_ROOT = ROOT / ".local/season-portrait-renders-v1"
DEFAULT_BASELINE_INDEX = ROOT / ".local/season-baselines-v1/calendar-bound-v2.json"
DEFAULT_MANAGER_OVERLAY_INDEX = ROOT / ".local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-v1.json"
DEFAULT_OVERLAYS_ROOT = ROOT / ".local/season-overlays-v1"
DEFAULT_LEGACY_2015_ROOT = ROOT / ".local/season-workspace-v1/2015-16-final-build"
DEFAULT_LEGACY_2015_DEFECTS = ROOT / "docs/2015_16_WORLD_PLAYTEST_DEFECTS_2026-09-04.md"
DEFAULT_AMENDMENT_OUTPUT_ROOT = ROOT / ".local/season-editorial-amendments-v1"
SEASON_NAME = re.compile(r"^(?:1999|20[0-2][0-9])-[0-9]{2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_PRESET_BYTES = 32 * 1024 * 1024
IMAGE_SUFFIXES = {".bmp", ".png", ".jpg", ".jpeg", ".gif"}
SPREADSHEET_PAGE = (Path(__file__).with_name("season_preset_spreadsheet.html")).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Preset:
    """One approved-to-display file below a season directory."""

    season: str
    relative_path: str
    kind: str
    role: str
    title: str
    schema: str | None
    size: int
    sha256: str
    path: Path | None
    generated: dict[str, Any] | None = None

    @property
    def id(self) -> str:
        return self.relative_path

    def index_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "relative_path": self.relative_path,
            "kind": self.kind,
            "role": self.role,
            "title": self.title,
            "schema": self.schema,
            "size": self.size,
            "sha256": self.sha256,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_regular_file(path: Path, *, root: Path | None = None) -> Path | None:
    """Resolve one explicitly declared local file without following links."""

    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError:
        return None
    if root is not None:
        try:
            resolved.relative_to(root.expanduser().resolve(strict=True))
        except ValueError:
            return None
    if path.is_symlink() or resolved.is_symlink() or not resolved.is_file():
        return None
    return resolved


def _workspace_file(value: object) -> Path | None:
    """Return a regular repository-local file for a manifest-declared path."""

    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return _safe_regular_file(candidate, root=ROOT)


def _preset_from_file(
    *,
    season: str,
    relative_path: str,
    kind: str,
    role: str,
    path: Path,
    locked_sha256: str | None = None,
    title: str | None = None,
) -> Preset:
    """Create an allowlisted display entry, preserving a declared input hash."""

    if path.suffix == ".json":
        discovered_title, schema = _json_summary(path)
    else:
        discovered_title, schema = path.stem.replace("-", " "), None
    return Preset(
        season=season,
        relative_path=relative_path,
        kind=kind,
        role=role,
        title=title or discovered_title,
        schema=schema,
        size=path.stat().st_size,
        sha256=locked_sha256 if isinstance(locked_sha256, str) and SHA256.fullmatch(locked_sha256) else sha256_file(path),
        path=path,
    )


def _json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _json_summary(path: Path) -> tuple[str, str | None]:
    """Return a compact stable label without treating JSON as an executable input."""

    # Full season packages can be tens of megabytes.  Their canonical top-level
    # identity fields occur near the start, so avoid decoding the complete
    # player/club payload merely to populate the selector label.
    if path.stat().st_size > 1024 * 1024:
        try:
            with path.open("rb") as handle:
                prefix = handle.read(128 * 1024).decode("utf-8")
                handle.seek(max(0, path.stat().st_size - 128 * 1024))
                suffix = handle.read(128 * 1024).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return path.stem.replace("-", " "), None
        fields: dict[str, str] = {}
        for key in ("schema_version", "schema", "workspace_id", "package_id", "ledger_id", "registry_id", "audit_id"):
            match = re.search(rf'"{key}"\s*:\s*("(?:[^"\\]|\\.)*")', prefix + suffix)
            if match:
                try:
                    fields[key] = str(json.loads(match.group(1)))
                except json.JSONDecodeError:
                    pass
        schema = fields.get("schema_version") or fields.get("schema")
        label = next((fields[key] for key in ("workspace_id", "package_id", "ledger_id", "registry_id", "audit_id") if key in fields), path.stem.replace("-", " "))
        return label, schema
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return path.stem.replace("-", " "), None
    if not isinstance(value, dict):
        return path.stem.replace("-", " "), None
    schema = value.get("schema_version") or value.get("schema")
    label = (
        value.get("workspace_id")
        or value.get("package_id")
        or value.get("ledger_id")
        or value.get("registry_id")
        or value.get("audit_id")
        or path.stem.replace("-", " ")
    )
    return str(label), str(schema) if isinstance(schema, str) else None


def _preset_kind(relative_path: Path) -> str:
    if relative_path.name == "README.md":
        return "overview"
    if relative_path.parts and relative_path.parts[0] == "sources":
        return "source-capture"
    if relative_path.suffix == ".md":
        return "documentation"
    return "manifest"


def _structured_summary(value: Any) -> dict[str, Any] | None:
    """Return a compact table model for common season authoring documents."""

    if not isinstance(value, dict):
        return None
    schema = value.get("schema_version")
    if schema == "pm99-local-season-assembly-map-v1":
        state = value.get("state") if isinstance(value.get("state"), dict) else {}
        rows = []
        for component in value.get("components", []):
            if not isinstance(component, dict):
                continue
            rows.append({
                "role": component.get("role"),
                "kind": component.get("kind"),
                "manifest": component.get("relative_path"),
                "sha256": component.get("sha256"),
            })
        return {
            "title": "Read-only season assembly map",
            "counts": {
                "components": len(rows),
                "playable": state.get("playable", False),
                "release_status": state.get("release_status", "not declared"),
            },
            "columns": ["role", "kind", "manifest", "sha256"],
            "rows": rows,
        }
    if schema == "pm99-season-package-v2":
        managers = {str(row.get("id")): row for row in value.get("managers", []) if isinstance(row, dict)}
        players = {str(row.get("id")): row for row in value.get("players", []) if isinstance(row, dict)}
        rows = []
        for club in value.get("clubs", []):
            if not isinstance(club, dict):
                continue
            opening = club.get("opening") if isinstance(club.get("opening"), dict) else {}
            xi = [players.get(str(player_id), {}).get("name", str(player_id)) for player_id in opening.get("starting_xi_player_ids", [])]
            rows.append({
                "carrier": club.get("carrier_id"), "club": club.get("name"),
                "division": club.get("division"),
                "manager": managers.get(str(club.get("manager_id")), {}).get("name"),
                "roster": len(club.get("roster_player_ids", [])),
                "fixture": opening.get("fixture_date"), "formation": opening.get("formation"),
                "starting_xi": ", ".join(str(name) for name in xi),
            })
        return {
            "title": "Club, manager and opening-lineup overview",
            "counts": {"clubs": len(rows), "players": len(players), "managers": len(managers)},
            "columns": ["carrier", "club", "division", "manager", "roster", "fixture", "formation", "starting_xi"],
            "rows": rows,
        }
    if schema == "pm99-season-carrier-allocation-v1":
        rows = []
        for assignment in value.get("assignments", []):
            if isinstance(assignment, dict):
                rows.append({key: assignment.get(key) for key in ("carrier_id", "country_group", "club_name", "assignment_method")})
        return {
            "title": "Fixed-carrier allocation",
            "counts": dict(value.get("coverage") or {}),
            "columns": ["carrier_id", "country_group", "club_name", "assignment_method"],
            "rows": rows,
        }
    if schema == "pm99-historical-squad-backfill-current-v1":
        rows = []
        for name, artifact in sorted((value.get("artifacts") or {}).items()):
            if isinstance(artifact, dict):
                rows.append({
                    "artifact": name,
                    "path": artifact.get("path"),
                    "sha256": artifact.get("sha256"),
                })
        return {
            "title": "Immutable current season revision",
            "counts": {"artifacts": len(rows), "revision": value.get("revision_id")},
            "columns": ["artifact", "path", "sha256"],
            "rows": rows,
        }
    if schema in {
        "pm99-historical-squad-backfill-batch-v1",
        "pm99-historical-squad-current-coverage-matrix-v1",
    }:
        rows = [dict(row) for row in value.get("seasons", []) if isinstance(row, dict)]
        preferred = [
            "season", "status", "revision_id", "source_club_count", "composed_club_count",
            "assigned_real_carrier_count", "allocation_count", "release_capacity_eligible_count",
            "unassigned_real_carrier_count", "thin_below_xi_source_count", "gap_count",
        ]
        columns = [key for key in preferred if any(key in row for row in rows)]
        return {
            "title": "Cross-season historical squad coverage",
            "counts": {"seasons": len(rows)},
            "columns": columns,
            "rows": rows,
        }
    return None


def discover_presets(seasons_root: Path, *, include_source_captures: bool = False) -> dict[str, list[Preset]]:
    """Discover regular JSON/Markdown season files without following links."""

    seasons_root = seasons_root.expanduser().resolve()
    if not seasons_root.is_dir() or seasons_root.is_symlink():
        raise ValueError(f"season root must be an ordinary directory: {seasons_root}")
    discovered: dict[str, list[Preset]] = {}
    for season_dir in sorted(seasons_root.iterdir(), key=lambda item: item.name):
        if not season_dir.is_dir() or season_dir.is_symlink() or not SEASON_NAME.fullmatch(season_dir.name):
            continue
        presets: list[Preset] = []
        for path in sorted(season_dir.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_symlink() or not path.is_file() or path.suffix not in {".json", ".md"}:
                continue
            relative = path.relative_to(season_dir)
            if relative.parts and relative.parts[0] == "sources" and not include_source_captures:
                continue
            size = path.stat().st_size
            if size > MAX_PRESET_BYTES:
                continue
            kind = _preset_kind(relative)
            presets.append(_preset_from_file(
                season=season_dir.name,
                relative_path=relative.as_posix(),
                kind=kind,
                role="Season notes" if kind in {"overview", "documentation"} else "Registered season manifest",
                path=path,
            ))
        discovered[season_dir.name] = presets
    return discovered


def discover_playtest_presets(playtests_root: Path) -> dict[str, list[Preset]]:
    """Discover prepared local playtest manifests without accepting uploads.

    The immutable playtest cache is intentionally outside ``seasons/`` because
    it contains proprietary game trees.  Only its small manifest is exposed in
    the browser, grouped beside the matching season's source manifests.
    """

    playtests_root = playtests_root.expanduser().resolve()
    if not playtests_root.exists():
        return {}
    if playtests_root.is_symlink() or not playtests_root.is_dir():
        raise ValueError(f"playtest root must be an ordinary directory: {playtests_root}")
    discovered: dict[str, list[Preset]] = {}
    for directory in sorted(playtests_root.iterdir(), key=lambda item: item.name):
        if not directory.is_dir() or directory.is_symlink():
            continue
        path = directory / "provisional-playtest-manifest.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PRESET_BYTES:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        season = value.get("target_season")
        variant_id = value.get("variant_id")
        schema = value.get("schema_version")
        if (
            not isinstance(season, str)
            or not SEASON_NAME.fullmatch(season)
            or not isinstance(variant_id, str)
            or not isinstance(schema, str)
        ):
            continue
        relative_path = f"local-playtest/{directory.name}/provisional-playtest-manifest.json"
        discovered.setdefault(season, []).append(_preset_from_file(
            season=season,
            relative_path=relative_path,
            kind="playtest",
            role="Provisional playtest receipt",
            path=path,
            title=variant_id,
        ))
    return discovered


def discover_current_authoring_presets(authoring_root: Path) -> dict[str, list[Preset]]:
    """Expose only the selected revision and the hash-bound inputs it names.

    The authoring cache contains many superseded probes and raw captures.  A
    recursive directory browser makes it hard to see what actually feeds the
    next build and makes startup needlessly slow.  ``current.json`` is the
    immutable pointer, so it is the only cache entry used to admit its inputs.
    """

    authoring_root = authoring_root.expanduser().resolve()
    if not authoring_root.exists():
        return {}
    if authoring_root.is_symlink() or not authoring_root.is_dir():
        raise ValueError(f"authoring root must be an ordinary directory: {authoring_root}")
    discovered: dict[str, list[Preset]] = {}
    for season_dir in sorted(authoring_root.iterdir(), key=lambda item: item.name):
        if not season_dir.is_dir() or season_dir.is_symlink() or not SEASON_NAME.fullmatch(season_dir.name):
            continue
        current_path = _safe_regular_file(season_dir / "current.json", root=season_dir)
        if current_path is None:
            continue
        current = _json_object(current_path)
        if current is None or current.get("schema_version") != "pm99-historical-squad-backfill-current-v1":
            continue
        presets = [
            _preset_from_file(
                season=season_dir.name,
                relative_path="authoring/current.json",
                kind="authoring-current",
                role="Selected source revision",
                path=current_path,
                title=f"Current revision · {current.get('revision_id', 'unlabelled')}",
            )
        ]
        artifacts = current.get("artifacts")
        if isinstance(artifacts, dict):
            for name, artifact in sorted(artifacts.items()):
                if not isinstance(name, str) or not isinstance(artifact, dict):
                    continue
                artifact_path = artifact.get("path")
                if not isinstance(artifact_path, str):
                    continue
                path = _safe_regular_file(season_dir / artifact_path, root=season_dir)
                if path is None or path.stat().st_size > MAX_PRESET_BYTES:
                    continue
                presets.append(_preset_from_file(
                    season=season_dir.name,
                    relative_path=f"authoring/{artifact_path}",
                    kind="authoring-input",
                    role=f"Selected revision input · {name}",
                    path=path,
                    locked_sha256=artifact.get("sha256"),
                    title=f"{name} · {current.get('revision_id', 'selected revision')}",
                ))
        discovered[season_dir.name] = presets
    return discovered


def _revision_sort_key(name: str) -> tuple[int, str]:
    """Sort the published recipe labels deterministically (r12 after r3)."""

    match = re.fullmatch(r"r([0-9]+)", name)
    return (int(match.group(1)), name) if match else (-1, name)


def _static_ingress_event(value: Mapping[str, Any]) -> tuple[Path, Path] | None:
    """Return the package and runtime-candidate path declared by a receipt.

    Promotion receipts contain the exact static-ingress command.  Reading that
    command is deliberately narrower than guessing from a directory name.
    """

    events = value.get("events")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, Mapping) or event.get("returncode") != 0:
            continue
        command = event.get("command")
        if not isinstance(command, list) or not any(
            isinstance(item, str) and item.endswith("/scripts/season_static_ingress_v1.py")
            for item in command
        ):
            continue
        try:
            package = command[command.index("--package") + 1]
            output = command[command.index("--output-dir") + 1]
        except (ValueError, IndexError):
            continue
        if isinstance(package, str) and isinstance(output, str):
            return Path(package), Path(output)
    return None


def discover_published_recipe_presets(
    recipe_root: Path, runtime_candidates_root: Path,
) -> tuple[dict[str, list[Preset]], dict[str, dict[str, Any]]]:
    """Discover one current, playable package per season from promotion receipts.

    The workbench is year-first: it does not expose every historical probe or
    make a reviewer choose a file.  A candidate is admitted only when its
    promotion receipt declares the package and the matching local runtime game
    tree exists.  If several qualify, the highest numbered receipt revision is
    selected deterministically.
    """

    recipe_root = recipe_root.expanduser().resolve()
    runtime_candidates_root = runtime_candidates_root.expanduser().resolve()
    if not recipe_root.exists():
        return {}, {}
    if recipe_root.is_symlink() or not recipe_root.is_dir():
        raise ValueError(f"recipe root must be an ordinary directory: {recipe_root}")
    discovered: dict[str, list[Preset]] = {}
    states: dict[str, dict[str, Any]] = {}
    for season_dir in sorted(recipe_root.iterdir(), key=lambda item: item.name):
        season = season_dir.name
        if not season_dir.is_dir() or season_dir.is_symlink() or not SEASON_NAME.fullmatch(season):
            continue
        candidates: list[tuple[tuple[int, str], Path, str]] = []
        for revision_dir in season_dir.iterdir():
            if not revision_dir.is_dir() or revision_dir.is_symlink():
                continue
            package_path = _safe_regular_file(revision_dir / "strict-season-package.json", root=recipe_root)
            if package_path is None:
                continue
            ingress_name: str | None = None
            receipt_path = _safe_regular_file(revision_dir / "promotion-receipt.json", root=revision_dir)
            receipt = _json_object(receipt_path) if receipt_path is not None else None
            declared = _static_ingress_event(receipt) if receipt is not None else None
            if declared is not None:
                declared_package, ingress_output = declared
                if _safe_regular_file(declared_package, root=recipe_root) == package_path:
                    ingress_name = ingress_output.name
            # Older successful promotions pre-date the receipt convention.
            # Their runtime directory is nevertheless a narrow, deterministic
            # confirmation: exactly the revision-labelled candidate with a
            # local game tree, not a search for arbitrary old packages.
            if ingress_name is None:
                runtime_season = runtime_candidates_root / season
                if runtime_season.is_dir() and not runtime_season.is_symlink():
                    matches = [
                        path.name for path in runtime_season.iterdir()
                        if path.is_dir() and not path.is_symlink()
                        and path.name.endswith(f"-{revision_dir.name}")
                        and (path / "game").is_dir() and not (path / "game").is_symlink()
                    ]
                    if len(matches) == 1:
                        ingress_name = matches[0]
            if ingress_name is not None:
                candidates.append((_revision_sort_key(revision_dir.name), package_path, ingress_name))
        if not candidates:
            continue
        _revision, package_path, ingress_name = sorted(candidates)[-1]
        revision = package_path.parent.name
        discovered[season] = [_preset_from_file(
            season=season,
            relative_path=f"published-recipe/{revision}/strict-season-package.json",
            kind="published-recipe",
            role="Current local playable source package",
            path=package_path,
            title=f"Current playable recipe · {revision}",
        )]
        states[season] = {
            "state": "local-playable-candidate",
            "playable": True,
            "release_status": f"Local runtime candidate declared from {ingress_name}",
        }
    return discovered, states


def discover_runtime_recipe_presets(
    static_ingress_root: Path, runtime_candidates_root: Path,
) -> tuple[dict[str, list[Preset]], dict[str, dict[str, Any]]]:
    """Admit the exact source package behind each existing local game tree.

    A static-ingress directory has one source-writable package and a
    deterministic runtime directory name.  This is a stronger current-recipe
    reference than an older draft or raw source capture: it is the source
    package that was used to create the selectable local game candidate.
    """

    static_ingress_root = static_ingress_root.expanduser().resolve()
    runtime_candidates_root = runtime_candidates_root.expanduser().resolve()
    if not static_ingress_root.exists():
        return {}, {}
    if static_ingress_root.is_symlink() or not static_ingress_root.is_dir():
        raise ValueError(f"static ingress root must be an ordinary directory: {static_ingress_root}")
    candidates: dict[str, list[tuple[tuple[int, str], Path, str]]] = {}
    for directory in static_ingress_root.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        match = re.fullmatch(r"((?:1999|20[0-2][0-9])-[0-9]{2})-(.+)", directory.name)
        if match is None:
            continue
        season, runtime_name = match.groups()
        package_path = _safe_regular_file(directory / "season-package.source-writable.json", root=static_ingress_root)
        runtime_game = runtime_candidates_root / season / runtime_name / "game"
        if package_path is None or not runtime_game.is_dir() or runtime_game.is_symlink():
            continue
        _title, schema = _json_summary(package_path)
        if schema != "pm99-season-package-v2":
            continue
        revision_match = re.search(r"-(r[0-9]+)$", runtime_name)
        revision = revision_match.group(1) if revision_match else runtime_name
        candidates.setdefault(season, []).append((_revision_sort_key(revision), package_path, runtime_name))
    discovered: dict[str, list[Preset]] = {}
    states: dict[str, dict[str, Any]] = {}
    for season, rows in candidates.items():
        _sort, package_path, runtime_name = sorted(rows)[-1]
        discovered[season] = [_preset_from_file(
            season=season,
            relative_path=f"runtime-recipe/{runtime_name}/season-package.source-writable.json",
            kind="runtime-recipe",
            role="Current local playable source package",
            path=package_path,
            title=f"Current playable recipe · {runtime_name}",
        )]
        states[season] = {
            "state": "local-playable-candidate",
            "playable": True,
            "release_status": f"Local runtime candidate declared from {runtime_name}",
        }
    return discovered, states


def discover_kit_assets(kit_render_root: Path, *, season: str, revision: str) -> dict[int, list[dict[str, Any]]]:
    """Return allowlisted rendered BMPs indexed by their fixed club carrier.

    The kit bindings receipt is the authority for the asset-to-club mapping;
    filenames are hashes and therefore not useful or safe UI identifiers on
    their own.  The caller exposes these through a carrier-based route, never
    an arbitrary path supplied by a browser request.
    """

    kit_render_root = kit_render_root.expanduser().resolve()
    candidates = [
        kit_render_root / season / f"source-backed-{revision}" / "kit-render-bindings-v1.json",
        kit_render_root / season / "kit-render-bindings-v1.json",
    ]
    bindings_path = next((_safe_regular_file(path, root=kit_render_root) for path in candidates if _safe_regular_file(path, root=kit_render_root) is not None), None)
    if bindings_path is None:
        return {}
    bindings = _json_object(bindings_path)
    if bindings is None or bindings.get("schema_version") != "pm99-season-kit-render-bindings-v1":
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    for row in bindings.get("clubs", []):
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            continue
        assets: list[dict[str, Any]] = []
        for artifact in row.get("artifacts", []):
            if not isinstance(artifact, Mapping):
                continue
            relative = artifact.get("relative_path")
            if not isinstance(relative, str):
                continue
            path = _safe_regular_file(bindings_path.parent / relative, root=bindings_path.parent)
            if path is None or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            artifact_id = artifact.get("id")
            label = str(artifact_id).rsplit("-", 1)[-1] if isinstance(artifact_id, str) else path.name
            declared_sha256 = artifact.get("sha256")
            # The receipt already locks the asset hash.  Do not rehash every
            # BMP at browser startup; validate the selected bitmap lazily when
            # it is actually opened instead.
            if not isinstance(declared_sha256, str) or not SHA256.fullmatch(declared_sha256):
                continue
            assets.append({"label": label, "path": path, "sha256": declared_sha256})
        if assets:
            result[row["carrier_id"]] = assets
    return result


def discover_portrait_assets(
    portrait_render_root: Path, *, season: str, revision: str | None,
) -> dict[str, dict[str, Any]]:
    """Return only receipt-bound player portrait BMPs for one source package.

    Portrait filenames and player-carrier ids have both changed across PM99
    builds, so neither is a safe identity key.  This deliberately accepts an
    asset only when a dedicated receipt names the immutable package player id,
    a relative BMP path and its expected SHA-256.
    """

    portrait_render_root = portrait_render_root.expanduser().resolve()
    candidates = [portrait_render_root / season / "portrait-render-bindings-v1.json"]
    if revision is not None:
        candidates.insert(
            0, portrait_render_root / season / f"source-backed-{revision}" / "portrait-render-bindings-v1.json",
        )
    bindings_path = next((
        _safe_regular_file(path, root=portrait_render_root)
        for path in candidates if _safe_regular_file(path, root=portrait_render_root) is not None
    ), None)
    if bindings_path is None:
        return {}
    bindings = _json_object(bindings_path)
    if (
        bindings is None
        or bindings.get("schema_version") != "pm99-season-portrait-render-bindings-v1"
        or bindings.get("season") != season
    ):
        return {}
    if revision is not None and bindings.get("revision") not in {None, revision}:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for row in bindings.get("players", []):
        if not isinstance(row, Mapping):
            continue
        player_id = row.get("player_id")
        artifact = row.get("artifact")
        if not isinstance(player_id, str) or not player_id or not isinstance(artifact, Mapping):
            continue
        relative = artifact.get("relative_path")
        declared_sha256 = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(declared_sha256, str) or not SHA256.fullmatch(declared_sha256):
            continue
        path = _safe_regular_file(bindings_path.parent / relative, root=bindings_path.parent)
        if path is None or path.suffix.lower() != ".bmp" or player_id in result:
            continue
        label = artifact.get("label")
        result[player_id] = {
            "label": label if isinstance(label, str) and label.strip() else "View BMP",
            "path": path,
            "sha256": declared_sha256,
        }
    return result


def _add_declared_workspace_preset(
    entries: dict[str, list[Preset]], *, season: str, relative_path: str,
    kind: str, role: str, declared: object, title: str,
) -> None:
    """Add an artifact only when it is explicitly named by a small index."""

    if not isinstance(declared, dict):
        return
    path = _workspace_file(declared.get("path"))
    if path is None or path.stat().st_size > MAX_PRESET_BYTES:
        return
    entries.setdefault(season, []).append(_preset_from_file(
        season=season,
        relative_path=relative_path,
        kind=kind,
        role=role,
        path=path,
        locked_sha256=declared.get("sha256"),
        title=title,
    ))


def discover_selected_overlay_presets(
    baseline_index: Path, manager_overlay_index: Path, overlays_root: Path,
) -> tuple[dict[str, list[Preset]], dict[str, dict[str, Any]]]:
    """Discover the frozen per-season base and selected overlays by their indexes."""

    entries: dict[str, list[Preset]] = {}
    states: dict[str, dict[str, Any]] = {}
    baseline = _json_object(baseline_index)
    if baseline is not None:
        for row in baseline.get("seasons", []):
            if not isinstance(row, dict) or not isinstance(row.get("season"), str):
                continue
            season = row["season"]
            if not SEASON_NAME.fullmatch(season):
                continue
            state = str(row.get("state", "unlabelled baseline"))
            playable = row.get("playable") is True
            states[season] = {
                "state": state,
                "playable": playable,
                "release_status": "Playable baseline declared" if playable else "Source and overlay authoring only — no playable release declared",
            }
            _add_declared_workspace_preset(
                entries, season=season, relative_path="assembly/frozen-calendar-base.json",
                kind="frozen-base", role="Frozen calendar-bound base",
                declared=row.get("base_draft"), title="Frozen calendar-bound base",
            )
            _add_declared_workspace_preset(
                entries, season=season, relative_path="assembly/calendar-binding-audit.json",
                kind="base-audit", role="Calendar binding receipt",
                declared=row.get("calendar_binding_audit"), title="Calendar binding audit",
            )

    manager_index = _json_object(manager_overlay_index)
    if manager_index is not None:
        for row in manager_index.get("seasons", []):
            if not isinstance(row, dict) or not isinstance(row.get("season"), str):
                continue
            season = row["season"]
            if not SEASON_NAME.fullmatch(season):
                continue
            overlay_id = str(row.get("overlay_id", "selected"))
            _add_declared_workspace_preset(
                entries, season=season, relative_path=f"assembly/{overlay_id}/manager-overlay-audit.json",
                kind="manager-overlay", role="Selected manager overlay audit",
                declared=row.get("manager_overlay_audit"), title=f"Manager overlay audit · {overlay_id}",
            )
            _add_declared_workspace_preset(
                entries, season=season, relative_path=f"assembly/{overlay_id}/opening-manager-ledger.json",
                kind="manager-overlay", role="Selected opening-manager ledger",
                declared=row.get("opening_manager_ledger"), title=f"Opening-manager ledger · {overlay_id}",
            )

    overlays_root = overlays_root.expanduser().resolve()
    if overlays_root.exists() and not overlays_root.is_symlink() and overlays_root.is_dir():
        for season_dir in sorted(overlays_root.iterdir(), key=lambda item: item.name):
            if not season_dir.is_dir() or season_dir.is_symlink() or not SEASON_NAME.fullmatch(season_dir.name):
                continue
            audit_path = _safe_regular_file(
                season_dir / "opening-xi-v1/opening-lineup-overlay-audit.json", root=season_dir
            )
            if audit_path is None:
                continue
            audit = _json_object(audit_path)
            locked_reconciliation_sha = None
            if isinstance(audit, dict) and isinstance(audit.get("outputs"), dict):
                locked_reconciliation_sha = audit["outputs"].get("opening_reconciliation_sha256")
            entries.setdefault(season_dir.name, []).append(_preset_from_file(
                season=season_dir.name,
                relative_path="assembly/opening-xi-v1/opening-lineup-overlay-audit.json",
                kind="opening-xi-overlay", role="Selected opening-XI overlay audit",
                path=audit_path, title="Opening-XI overlay audit · opening-xi-v1",
            ))
            reconciliation_path = _safe_regular_file(
                season_dir / "opening-xi-v1/opening-lineup-reconciliation.json", root=season_dir
            )
            if reconciliation_path is not None and reconciliation_path.stat().st_size <= MAX_PRESET_BYTES:
                entries[season_dir.name].append(_preset_from_file(
                    season=season_dir.name,
                    relative_path="assembly/opening-xi-v1/opening-lineup-reconciliation.json",
                    kind="opening-xi-overlay", role="Selected opening-XI reconciliation",
                    path=reconciliation_path,
                    locked_sha256=locked_reconciliation_sha,
                    title="Opening-XI reconciliation · opening-xi-v1",
                ))
    return entries, states


def discover_legacy_2015_presets() -> list[Preset]:
    """Add the V1 world package and its semantic-release warning explicitly."""

    presets: list[Preset] = []
    package = _safe_regular_file(DEFAULT_LEGACY_2015_ROOT / "season-package.effective.json", root=ROOT)
    if package is not None and package.stat().st_size <= MAX_PRESET_BYTES:
        presets.append(_preset_from_file(
            season="2015-16", relative_path="legacy-world/season-package.effective.json",
            kind="legacy-world-package", role="Legacy world V1 package (semantic QA failed)",
            path=package, title="Legacy world V1 effective package",
        ))
    defects = _safe_regular_file(DEFAULT_LEGACY_2015_DEFECTS, root=ROOT)
    if defects is not None:
        presets.append(_preset_from_file(
            season="2015-16", relative_path="legacy-world/semantic-qa-defects.md",
            kind="release-qa", role="Current semantic release finding",
            path=defects, title="2015/16 V1 semantic QA defects",
        ))
    return presets


def discover_preferred_release_recipe_presets(catalog_path: Path) -> dict[str, list[Preset]]:
    """Hash-locked current main recipes; old source revisions stay available."""
    discovered: dict[str, list[Preset]] = {}
    for season, binding in release_registry.load_catalog(catalog_path).items():
        release = release_registry.load_registered_release(season, binding["release_id"])
        if release.manifest_sha256 != binding["release_manifest_sha256"]:
            raise ValueError("preferred recipe manifest no longer matches registered catalogue")
        path = _safe_regular_file(release.package_path, root=ROOT)
        if path is None or _json_summary(path)[1] != "pm99-season-package-v2":
            raise ValueError("preferred release recipe is unavailable or unsupported")
        discovered[season] = [_preset_from_file(
            season=season,
            relative_path=f"preferred-release/{release.release_id}/season-package.json",
            kind="preferred-release-recipe",
            role="Current preferred registered recipe (amendment sidecar)",
            path=path, title=f"Preferred release recipe · {release.release_id}",
        )]
    return discovered


class PresetCatalog:
    """An in-memory allowlist; request paths never address the filesystem directly."""

    def __init__(
        self, seasons_root: Path, *, include_source_captures: bool,
        playtests_root: Path | None = None,
        authoring_root: Path | None = None,
        recipe_root: Path | None = None,
        static_ingress_root: Path | None = None,
        runtime_candidates_root: Path | None = None,
        kit_render_root: Path | None = None,
        portrait_render_root: Path | None = None,
        baseline_index: Path = DEFAULT_BASELINE_INDEX,
        manager_overlay_index: Path = DEFAULT_MANAGER_OVERLAY_INDEX,
        overlays_root: Path = DEFAULT_OVERLAYS_ROOT,
        amendment_output_root: Path = DEFAULT_AMENDMENT_OUTPUT_ROOT,
        preferred_catalog_path: Path | None = None,
    ) -> None:
        self.seasons_root = seasons_root.expanduser().resolve()
        self.amendment_output_root = amendment_output_root.expanduser().resolve()
        self.entries = discover_presets(
            self.seasons_root, include_source_captures=include_source_captures
        )
        self.states: dict[str, dict[str, Any]] = {}
        if playtests_root is not None:
            for season, presets in discover_playtest_presets(playtests_root).items():
                self.entries.setdefault(season, []).extend(presets)
        if authoring_root is not None and authoring_root.exists():
            for season, presets in discover_current_authoring_presets(authoring_root).items():
                self.entries.setdefault(season, []).extend(presets)
        self.kit_render_root = kit_render_root
        self.kit_assets: dict[str, dict[int, list[dict[str, Any]]]] = {}
        self.portrait_render_root = portrait_render_root
        self.portrait_assets: dict[str, dict[str, dict[str, Any]]] = {}
        self._kit_revisions: dict[str, str] = {}
        if recipe_root is not None and runtime_candidates_root is not None:
            published, published_states = discover_published_recipe_presets(
                recipe_root, runtime_candidates_root
            )
            for season, presets in published.items():
                self.entries.setdefault(season, []).extend(presets)
            self.states.update(published_states)
            for season, presets in published.items():
                recipe = presets[0]
                self._kit_revisions.setdefault(season, Path(recipe.id).parts[1])
        if static_ingress_root is not None and runtime_candidates_root is not None:
            runtime_recipes, runtime_states = discover_runtime_recipe_presets(
                static_ingress_root, runtime_candidates_root
            )
            for season, presets in runtime_recipes.items():
                self.entries.setdefault(season, []).extend(presets)
            self.states.update(runtime_states)
            for season, presets in runtime_recipes.items():
                runtime_name = Path(presets[0].id).parts[1]
                match = re.search(r"-(r[0-9]+)$", runtime_name)
                if match is not None:
                    self._kit_revisions[season] = match.group(1)
        overlay_entries, overlay_states = discover_selected_overlay_presets(
            baseline_index, manager_overlay_index, overlays_root
        )
        for season, state in overlay_states.items():
            self.states.setdefault(season, state)
        for season, presets in overlay_entries.items():
            self.entries.setdefault(season, []).extend(presets)
        self.entries.setdefault("2015-16", []).extend(discover_legacy_2015_presets())
        self.states["2015-16"] = {
            "state": "legacy-world-v1-semantic-qa-failed",
            "playable": False,
            "release_status": "V1 starts but is not historically release-ready; V2 correction is required",
        }
        if preferred_catalog_path is not None:
            for season, presets in discover_preferred_release_recipe_presets(preferred_catalog_path).items():
                self.entries.setdefault(season, []).extend(presets)
                self.states[season] = {
                    "state": "registered-preferred-release",
                    "playable": True,
                    "release_status": "Registered preferred release; gameplay review pending",
                }
        for presets in self.entries.values():
            presets.sort(key=lambda item: (item.kind != "season-map", item.relative_path))
        self._by_key = {
            (season, item.id): item
            for season, items in self.entries.items()
            for item in items
        }
        self._spreadsheet_sources: dict[tuple[str, str], dict[str, Any]] = {}

    def index(self) -> dict[str, Any]:
        seasons = []
        for season, items in self.entries.items():
            state = self.states.get(season, {
                "state": "registered-research-preset",
                "playable": False,
                "release_status": "Registered research preset; no playable release declared",
            })
            overview = next((item for item in items if item.kind == "season-map"), None)
            if overview is None:
                overview = Preset(
                    season=season,
                    relative_path="overview/season-assembly-map.json",
                    kind="season-map",
                    role="Read-only assembly map",
                    title=f"{season.replace('-', '/')} assembly map",
                    schema="pm99-local-season-assembly-map-v1",
                    size=0,
                    sha256="generated-from-registered-inputs",
                    path=None,
                    generated={
                        "schema_version": "pm99-local-season-assembly-map-v1",
                        "season": season,
                        "read_only": True,
                        "state": state,
                        "components": [item.index_row() for item in items],
                    },
                )
                items.insert(0, overview)
                self._by_key[(season, overview.id)] = overview
            seasons.append({
                "id": season,
                "label": season.replace("-", "/"),
                "preset_count": len(items),
                "state": state,
                "spreadsheet_ready": any(
                    item.schema == "pm99-season-package-v2" and item.path is not None
                    for item in items
                ),
                "presets": [item.index_row() for item in items],
            })
        return {
            "read_only": True,
            "editorial_amendments": True,
            "season_count": len(self.entries),
            "seasons": seasons,
        }

    def _amendment_path(self, season: str) -> Path:
        if season not in self.entries or not SEASON_NAME.fullmatch(season):
            raise KeyError("season is not in the local catalog")
        season_root = self.seasons_root / season
        if season_root.is_symlink() or not season_root.is_dir():
            raise FileNotFoundError("season directory is not a regular local directory")
        return season_root / "editorial-amendments" / "working.json"

    def amendments(self, season: str) -> dict[str, Any]:
        return amendments.load_or_empty(self._amendment_path(season), season=season)

    def _editable_json_manifest(self, season: str, manifest_id: str) -> tuple[Preset, Any, str]:
        item = self._by_key.get((season, manifest_id))
        if item is None or item.generated is not None or item.path is None or item.path.suffix != ".json":
            raise amendments.AmendmentError("choose an original JSON manifest, not a generated map or document")
        if item.path.is_symlink() or not item.path.is_file():
            raise FileNotFoundError("selected manifest is no longer a regular local file")
        actual_sha256 = sha256_file(item.path)
        if actual_sha256 != item.sha256:
            raise amendments.AmendmentError("selected manifest changed after catalog startup; restart before staging an edit")
        try:
            value = json.loads(item.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise amendments.AmendmentError(f"selected manifest is not editable JSON: {exc}") from exc
        return item, value, actual_sha256

    def stage_amendment(
        self, *, season: str, manifest_id: str, json_pointer: str,
        replacement: Any, reason: str, evidence: str | None,
    ) -> dict[str, Any]:
        item, source, actual_sha256 = self._editable_json_manifest(season, manifest_id)
        expected = amendments.value_at(source, json_pointer)
        document = self.amendments(season)
        # A spreadsheet cell may be corrected again before the reviewer
        # materialises its sidecar.  Replace its one existing staged target,
        # retaining the immutable source value as the expected value.
        existing = next((
            row for row in document["changes"]
            if row["manifest_id"] == item.id and row["json_pointer"] == json_pointer
        ), None)
        if existing is not None:
            document = amendments.remove_change(document, change_id=existing["id"])
        document = amendments.stage_change(
            document,
            manifest_id=item.id,
            manifest_sha256=actual_sha256,
            json_pointer=json_pointer,
            expected=expected,
            replacement=replacement,
            reason=reason,
            evidence=evidence,
        )
        amendments.write_document(self._amendment_path(season), document)
        return document

    def _spreadsheet_preset(self, season: str) -> Preset:
        if season not in self.entries or not SEASON_NAME.fullmatch(season):
            raise KeyError("season is not in the local catalog")
        items = self.entries[season]
        current = [item for item in items if item.kind == "preferred-release-recipe"
                   and item.schema == "pm99-season-package-v2"]
        if current:
            if len(current) != 1:
                raise ValueError("ambiguous preferred release recipe for season")
            return current[0]
        preferred = [
            item for item in items
            if item.kind == "runtime-recipe" and item.schema == "pm99-season-package-v2"
        ]
        if not preferred:
            preferred = [
                item for item in items
                if item.kind == "published-recipe" and item.schema == "pm99-season-package-v2"
            ]
        if not preferred:
            preferred = [
                item for item in items
                if item.id == "season-package.json" and item.schema == "pm99-season-package-v2"
            ]
        if not preferred:
            preferred = [
                item for item in items
                if item.schema == "pm99-season-package-v2" and item.path is not None
            ]
        if not preferred:
            raise ValueError("no selected season package is available for this year")
        return sorted(preferred, key=lambda item: item.id)[0]

    def _spreadsheet_source(self, season: str) -> tuple[Preset, dict[str, Any]]:
        item = self._spreadsheet_preset(season)
        key = (season, item.id)
        cached = self._spreadsheet_sources.get(key)
        if cached is None:
            _item, cached, digest = self._editable_json_manifest(season, item.id)
            if cached.get("schema_version") != "pm99-season-package-v2":
                raise ValueError("selected recipe does not use the season-package-v2 contract")
            # Retain only the locked, immutable source in the cache.  Each
            # request below receives a fresh preview so one staged correction
            # cannot mutate the original package or leak into another season.
            self._spreadsheet_sources[key] = cached
        else:
            digest = item.sha256

        preview = copy.deepcopy(cached)
        for change in self.amendments(season)["changes"]:
            if change["manifest_id"] != item.id:
                continue
            if change["manifest_sha256"] != digest:
                raise amendments.AmendmentError(
                    "a staged amendment targets a different source revision; "
                    "review or remove it before previewing this package"
                )
            actual = amendments.value_at(preview, change["json_pointer"])
            if actual != change["expected"]:
                raise amendments.AmendmentError(
                    f"stale amendment {change['id']}: expected value differs at "
                    f"{change['json_pointer']}"
                )
            amendments.replace_at(preview, change["json_pointer"], change["set"])
        return item, preview

    def _kit_links(self, season: str) -> dict[int, list[dict[str, str]]]:
        if season not in self.kit_assets:
            revision = self._kit_revisions.get(season)
            self.kit_assets[season] = (
                discover_kit_assets(self.kit_render_root, season=season, revision=revision)
                if self.kit_render_root is not None and revision is not None else {}
            )
        result: dict[int, list[dict[str, str]]] = {}
        for carrier, assets in self.kit_assets.get(season, {}).items():
            result[carrier] = [
                {
                    "label": str(asset["label"]),
                    "href": f"/api/kit?season={season}&carrier={carrier}&variant={index}",
                }
                for index, asset in enumerate(assets)
            ]
        return result

    def _portrait_links(self, season: str) -> dict[str, dict[str, str]]:
        if season not in self.portrait_assets:
            revision = self._kit_revisions.get(season)
            self.portrait_assets[season] = (
                discover_portrait_assets(self.portrait_render_root, season=season, revision=revision)
                if self.portrait_render_root is not None else {}
            )
        return {
            player_id: {
                "label": str(asset["label"]),
                "href": f"/api/portrait?season={season}&player={player_id}",
            }
            for player_id, asset in self.portrait_assets.get(season, {}).items()
        }

    def spreadsheet_metadata(self, season: str) -> dict[str, Any]:
        item, source = self._spreadsheet_source(season)
        kit_links = self._kit_links(season)
        return {
            "season": season,
            "source": item.index_row(),
            "workbook": spreadsheet.package_choices(
                source, kit_count=sum(len(value) for value in kit_links.values())
            ),
        }

    def spreadsheet_tab(
        self, *, season: str, tab: str, query: str, offset: int, limit: int,
    ) -> dict[str, Any]:
        item, source = self._spreadsheet_source(season)
        return {
            "season": season,
            "source": item.index_row(),
            "table": spreadsheet.tab_payload(
                source, tab=tab, query=query, offset=offset, limit=limit,
                kit_assets=self._kit_links(season),
                portrait_assets=self._portrait_links(season),
            ),
        }

    def kit_asset(self, *, season: str, carrier: int, variant: int) -> Path:
        assets = self.kit_assets.get(season, {}).get(carrier, [])
        if variant < 0 or variant >= len(assets):
            raise FileNotFoundError("kit bitmap is not in the local allowlist")
        asset = assets[variant]
        path = asset.get("path")
        if not isinstance(path, Path) or _safe_regular_file(path, root=ROOT) is None:
            raise FileNotFoundError("kit bitmap is no longer a local regular file")
        if sha256_file(path) != asset.get("sha256"):
            raise ValueError("kit bitmap changed after the workbench started; restart before viewing it")
        return path

    def portrait_asset(self, *, season: str, player_id: str) -> Path:
        asset = self.portrait_assets.get(season, {}).get(player_id)
        if asset is None:
            raise FileNotFoundError("portrait bitmap is not in the local allowlist")
        path = asset.get("path")
        if not isinstance(path, Path) or _safe_regular_file(path, root=ROOT) is None:
            raise FileNotFoundError("portrait bitmap is no longer a local regular file")
        if sha256_file(path) != asset.get("sha256"):
            raise ValueError("portrait bitmap changed after the workbench started; restart before viewing it")
        return path

    def remove_amendment(self, *, season: str, change_id: str) -> dict[str, Any]:
        document = amendments.remove_change(self.amendments(season), change_id=change_id)
        amendments.write_document(self._amendment_path(season), document)
        return document

    def materialise_amendments(self, *, season: str) -> dict[str, Any]:
        document = self.amendments(season)

        def resolve_manifest(manifest_id: str) -> tuple[Path, str]:
            item, _source, digest = self._editable_json_manifest(season, manifest_id)
            if item.path is None:
                raise amendments.AmendmentError("selected manifest has no local source")
            return item.path, digest

        return amendments.materialise(
            document,
            resolve_manifest=resolve_manifest,
            output_root=self.amendment_output_root,
        )

    def read(self, season: str, preset_id: str) -> dict[str, Any]:
        item = self._by_key.get((season, preset_id))
        if item is None:
            raise KeyError("preset is not in the local catalog")
        if item.generated is not None:
            content = json.dumps(item.generated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            return {
                "season": item.season,
                "preset": item.index_row(),
                "content_type": "json",
                "content": content,
                "summary": _structured_summary(item.generated),
            }
        path = item.path
        if path is None or path.is_symlink() or not path.is_file():
            raise FileNotFoundError("preset no longer exists as a regular file")
        payload = path.read_bytes()
        if len(payload) > MAX_PRESET_BYTES:
            raise ValueError("preset is too large for the local browser")
        if sha256_file(path) != item.sha256:
            raise ValueError("preset changed after catalog startup; restart to refresh its lock")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("preset is not UTF-8 text") from exc
        parsed: Any | None = None
        if path.suffix == ".json":
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            except json.JSONDecodeError:
                pass
        return {
            "season": item.season,
            "preset": item.index_row(),
            "content_type": "json" if parsed is not None else "text",
            "content": text,
            "summary": _structured_summary(parsed),
        }


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM99 Local Preset Browser</title><style>
:root{--ink:#172325;--muted:#627174;--paper:#f5f6f3;--panel:#fff;--line:#d8dfda;--green:#123d36;--lime:#c8e86d;--soft:#eef5ef;--warn:#835d12}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{padding:26px max(20px,5vw);background:var(--green);color:white}header h1{margin:0;font:700 clamp(25px,4vw,42px)/1.05 Georgia,serif;letter-spacing:-.035em}header p{max-width:750px;margin:9px 0 0;color:#d9e7e2}.status{display:inline-block;margin-top:14px;padding:5px 8px;border-radius:4px;background:#224e47;color:var(--lime);font-size:12px;font-weight:700}.layout{max-width:1500px;margin:0 auto;padding:24px max(20px,5vw) 50px;display:grid;grid-template-columns:290px minmax(0,1fr);gap:18px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px}.controls{padding:18px;align-self:start}.controls h2,.amendments h2{margin:0 0 15px;font:700 20px Georgia,serif}.controls label,.amendments label{display:grid;gap:6px;margin:0 0 15px;color:#405153;font-weight:700;font-size:12px}.controls select,.controls input,.amendments input,.amendments textarea{width:100%;padding:9px;border:1px solid #c6d1cb;border-radius:6px;background:#fff;color:var(--ink);font:inherit}.amendments textarea{min-height:78px;resize:vertical;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}.hint{color:var(--muted);font-size:12px}.document{min-width:0}.dochead{padding:18px 21px;border-bottom:1px solid var(--line)}.dochead h2{margin:0;font:700 22px Georgia,serif}.meta{margin:8px 0 0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.empty,.loading{padding:50px 25px;text-align:center;color:var(--muted)}.summary{padding:18px;overflow:auto}.summary h3{margin:0 0 8px}.counts{color:var(--muted);margin:0 0 12px}.summary table{border-collapse:collapse;width:100%;font-size:12px}.summary th,.summary td{padding:7px 9px;border:1px solid var(--line);text-align:left;vertical-align:top}.summary th{position:sticky;top:0;background:#eef3ef}.summary td:last-child{min-width:280px}details{border-top:1px solid var(--line)}summary{cursor:pointer;padding:12px 20px;font-weight:700}pre{margin:0;padding:22px;min-height:300px;overflow:auto;background:#fcfdfb;color:#1a2829;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;tab-size:2;white-space:pre}.error{color:#9b3324}.amendments{grid-column:2;padding:21px}.amendments p{margin:0 0 17px;color:var(--muted);font-size:13px}.edit-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.edit-grid .wide{grid-column:1/-1}.current-value,.amendment-notice{margin:-4px 0 14px!important;padding:8px 10px;border-radius:6px;background:var(--soft);color:#35534d!important;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.amendment-notice{background:#fff5dc;color:var(--warn)!important}.actions{display:flex;flex-wrap:wrap;gap:9px}.actions button,.remove-change{border:0;border-radius:6px;padding:9px 12px;background:var(--green);color:white;font:700 12px system-ui;cursor:pointer}.actions button.secondary,.remove-change{background:white;color:var(--green);border:1px solid #9fb4aa}.change-list{margin-top:22px;border-top:1px solid var(--line)}.change{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}.change strong,.change code,.change span{display:block}.change code{color:#34534d;font-size:12px;overflow-wrap:anywhere}.change span{color:var(--muted);font-size:12px}@media(max-width:800px){.layout{grid-template-columns:1fr}.controls{display:grid;grid-template-columns:1fr 1fr;gap:12px}.controls h2,.controls .hint{grid-column:1/-1}.controls label{margin:0}.amendments{grid-column:1}.edit-grid{grid-template-columns:1fr}}
</style></head><body><header><h1>PM99 Local Preset Browser</h1><p>Choose a registered season. Its assembly map shows the exact frozen base, selected source revision and overlays; every original manifest remains available below it. Editorial changes are saved as a hash-bound sidecar, never an in-place edit of a frozen source or game database.</p><span class="status">Localhost only · source amendments · no binary edits</span></header><main class="layout"><aside class="panel controls"><h2>Preset selection</h2><label>Season<select id="season" aria-label="Season"></select></label><label>Find input<input id="filter" type="search" placeholder="Filter exact inputs"></label><label>Manifest<select id="preset" size="12" aria-label="Manifest"></select></label><p class="hint" id="hint">Loading local catalog…</p></aside><section class="panel document"><div class="dochead"><h2 id="title">Select a preset</h2><p class="meta" id="meta"></p></div><div id="summary" class="summary" hidden></div><details id="raw"><summary>Raw manifest</summary><pre id="content" class="empty">The local catalog is loading.</pre></details></section><section class="panel amendments" aria-label="Editorial amendments"><h2>Stage a precise source change</h2><p>Choose an original JSON manifest above, enter the existing field path and its replacement. The current value and source hash are locked automatically. A materialised copy can then feed a selected-season reprocessing run without touching the frozen input.</p><div class="edit-grid"><label class="wide">JSON path<input id="json-pointer" placeholder="/clubs/0/club_name" autocomplete="off"></label><p id="current-value" class="current-value wide">Select an original JSON manifest, then enter an existing JSON path.</p><label class="wide">Replacement JSON<textarea id="replacement" placeholder='"Correct club name"'></textarea></label><label>Reason<input id="reason" placeholder="What is wrong and why?"></label><label>Evidence (optional)<input id="evidence" placeholder="Source URL or local receipt"></label></div><div class="actions"><button id="stage-change" type="button">Stage change</button><button id="materialise" class="secondary" type="button">Materialise staged copies</button></div><p id="amendment-notice" class="amendment-notice">No staged changes loaded.</p><div id="change-list" class="change-list"></div></section></main><script>
const state={catalog:null,season:null,document:null,amendments:null};const $=id=>document.getElementById(id);const season=$('season'),preset=$('preset'),filter=$('filter'),hint=$('hint'),title=$('title'),meta=$('meta'),content=$('content'),summary=$('summary'),raw=$('raw'),pointer=$('json-pointer'),replacement=$('replacement'),reason=$('reason'),evidence=$('evidence'),currentValue=$('current-value'),amendmentNotice=$('amendment-notice'),changeList=$('change-list');
function current(){return state.catalog.seasons.find(x=>x.id===state.season)}
function showNotice(message){amendmentNotice.textContent=message}
function pointerValue(value,path){if(typeof path!=='string'||!path.startsWith('/')||path==='/')throw Error('Enter an existing JSON path starting with /.');let current=value;for(const rawPart of path.slice(1).split('/')){const part=rawPart.replaceAll('~1','/').replaceAll('~0','~');if(Array.isArray(current)&&/^\d+$/.test(part)&&Number(part)<current.length)current=current[Number(part)];else if(current&&typeof current==='object'&&Object.hasOwn(current,part))current=current[part];else throw Error('That path does not exist in this manifest.')}return current}
function updateCurrentValue(){if(!state.document||state.document.content_type!=='json'||state.document.preset.kind==='season-map'){currentValue.textContent='Select an original JSON manifest, then enter an existing JSON path.';return}try{const value=pointerValue(JSON.parse(state.document.content),pointer.value.trim());currentValue.textContent=`Current locked value: ${JSON.stringify(value)}`}catch(error){currentValue.textContent=String(error.message||error)}}
function renderPresets(){const item=current();preset.innerHTML='';if(!item)return;const query=filter.value.trim().toLowerCase();for(const row of item.presets.filter(x=>[x.relative_path,x.title,x.schema||'',x.kind,x.role].join(' ').toLowerCase().includes(query))){const option=document.createElement('option');option.value=row.id;option.textContent=`${row.role} · ${row.relative_path}`;preset.append(option)}hint.textContent=`${item.state.release_status} · ${item.preset_count} manifest${item.preset_count===1?'':'s'} · ${state.catalog.season_count} seasons`;if(preset.options.length){preset.selectedIndex=0;loadPreset()}};
function renderSummary(model){summary.replaceChildren();if(!model){summary.hidden=true;raw.open=true;return}summary.hidden=false;raw.open=false;const h=document.createElement('h3');h.textContent=model.title;summary.append(h);const counts=document.createElement('p');counts.className='counts';counts.textContent=Object.entries(model.counts||{}).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ');summary.append(counts);const table=document.createElement('table'),head=document.createElement('tr');for(const key of model.columns){const th=document.createElement('th');th.textContent=key.replaceAll('_',' ');head.append(th)}table.append(head);for(const row of model.rows){const tr=document.createElement('tr');for(const key of model.columns){const td=document.createElement('td');td.textContent=row[key]??'';tr.append(td)}table.append(tr)}summary.append(table)}
function renderAmendments(){changeList.replaceChildren();const changes=state.amendments?.changes||[];if(!changes.length){const empty=document.createElement('p');empty.textContent='No staged changes for this season.';changeList.append(empty);return}for(const change of changes){const row=document.createElement('div');row.className='change';const detail=document.createElement('div');const name=document.createElement('strong');name.textContent=change.id;const target=document.createElement('code');target.textContent=`${change.manifest_id}  ${change.json_pointer}`;const values=document.createElement('span');values.textContent=`${JSON.stringify(change.expected)} → ${JSON.stringify(change.set)}`;const note=document.createElement('span');note.textContent=change.reason;detail.append(name,target,values,note);const remove=document.createElement('button');remove.className='remove-change';remove.type='button';remove.textContent='Remove';remove.onclick=()=>removeChange(change.id);row.append(detail,remove);changeList.append(row)}showNotice(`${changes.length} staged change${changes.length===1?'':'s'}: originals remain unchanged.`)}
async function refreshAmendments(){try{const response=await fetch(`/api/amendments?season=${encodeURIComponent(state.season)}`);const value=await response.json();if(!response.ok)throw Error(value.error||'Could not load staged changes');state.amendments=value.amendments;renderAmendments()}catch(error){showNotice(String(error.message||error))}}
async function requestChange(path,payload){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const value=await response.json();if(!response.ok)throw Error(value.error||'The local change could not be saved');return value}
async function stageChange(){try{if(!state.document||state.document.content_type!=='json'||state.document.preset.kind==='season-map')throw Error('Choose an original JSON manifest before staging a change.');const path=pointer.value.trim();const expected=pointerValue(JSON.parse(state.document.content),path);void expected;const set=JSON.parse(replacement.value);const value=await requestChange('/api/amendments/stage',{season:state.season,manifest_id:state.document.preset.id,json_pointer:path,set,reason:reason.value,evidence:evidence.value||null});state.amendments=value.amendments;replacement.value='';reason.value='';evidence.value='';renderAmendments();updateCurrentValue()}catch(error){showNotice(String(error.message||error))}}
async function removeChange(changeId){try{const value=await requestChange('/api/amendments/remove',{season:state.season,change_id:changeId});state.amendments=value.amendments;renderAmendments()}catch(error){showNotice(String(error.message||error))}}
async function materialiseChanges(){try{const value=await requestChange('/api/amendments/materialise',{season:state.season});showNotice(`Materialised ${value.receipt.change_count} change${value.receipt.change_count===1?'':'s'} into ${value.receipt.outputs.length} hash-bound source copy/copies. They are not promoted automatically.`)}catch(error){showNotice(String(error.message||error))}}
async function loadPreset(){const id=preset.value;if(!id)return;content.textContent='Loading preset…';content.className='loading';summary.hidden=true;try{const response=await fetch(`/api/preset?season=${encodeURIComponent(state.season)}&id=${encodeURIComponent(id)}`);const value=await response.json();if(!response.ok)throw Error(value.error||'Could not load preset');state.document=value;title.textContent=value.preset.title;meta.textContent=`${value.season} · ${value.preset.role} · ${value.preset.relative_path} · ${value.preset.kind}${value.preset.schema?' · '+value.preset.schema:''} · SHA-256 ${value.preset.sha256}`;renderSummary(value.summary);content.textContent=value.content;content.className='';updateCurrentValue()}catch(error){content.textContent=String(error);content.className='error';raw.open=true}}
async function boot(){try{const response=await fetch('/api/index');state.catalog=await response.json();for(const row of state.catalog.seasons){const option=document.createElement('option');option.value=row.id;option.textContent=`${row.label} · ${row.state.playable?'playable declared':'not released'} (${row.preset_count})`;season.append(option)}state.season=state.catalog.seasons[0]?.id||null;season.value=state.season||'';renderPresets();refreshAmendments()}catch(error){content.textContent=String(error);content.className='error'}}season.onchange=()=>{state.season=season.value;renderPresets();refreshAmendments()};filter.oninput=renderPresets;preset.onchange=loadPreset;pointer.oninput=updateCurrentValue;$('stage-change').onclick=stageChange;$('materialise').onclick=materialiseChanges;boot();
const picker=document.createElement('div');picker.className='wide';picker.innerHTML='<div class="edit-grid"><label>Record type<select id="record-kind"><option value="club">Club / team</option><option value="player">Player</option><option value="manager">Manager</option></select></label><label>Find record<input id="record-search" placeholder="Type Stoke, Arnautović…" autocomplete="off"></label><label class="wide">Record<select id="record"><option>Select an original JSON manifest first</option></select></label><label class="wide">Field<select id="record-field"><option>Select a record first</option></select></label></div>';document.querySelector('.edit-grid').prepend(picker);const recordKind=$('record-kind'),recordSearch=$('record-search'),record=$('record'),recordField=$('record-field');let editableRecords=[];
function sourceValue(){try{return state.document?.content_type==='json'&&state.document?.preset.kind!=='season-map'?JSON.parse(state.document.content):null}catch{return null}}
function pointerPart(value){return String(value).replaceAll('~','~0').replaceAll('/','~1')}
function labelFor(value,fallback){return String(value?.name||value?.club_name||value?.source_name||value?.display_name||value?.manager_name||fallback)}
function availableRecords(){const source=sourceValue();if(!source||typeof source!=='object')return[];const type=recordKind.value,rows=[];if(type==='club'&&Array.isArray(source.clubs))source.clubs.forEach((row,index)=>rows.push({label:labelFor(row,`Club ${index+1}`),prefix:['clubs',String(index)],value:row}));if(type==='manager'&&Array.isArray(source.managers))source.managers.forEach((row,index)=>rows.push({label:labelFor(row,`Manager ${index+1}`),prefix:['managers',String(index)],value:row}));if(type==='player'){if(Array.isArray(source.players))source.players.forEach((row,index)=>rows.push({label:labelFor(row,`Player ${index+1}`),prefix:['players',String(index)],value:row}));if(Array.isArray(source.clubs))source.clubs.forEach((club,clubIndex)=>{if(Array.isArray(club?.players))club.players.forEach((row,index)=>rows.push({label:`${labelFor(club,`Club ${clubIndex+1}`)} · ${labelFor(row,`Player ${index+1}`)}`,prefix:['clubs',String(clubIndex),'players',String(index)],value:row}))})}return rows}
function scalarFields(value,parts=[],result=[]){if(value===null||['string','number','boolean'].includes(typeof value)){result.push(parts);return result}if(value&&typeof value==='object'&&!Array.isArray(value))Object.keys(value).sort().forEach(key=>scalarFields(value[key],[...parts,key],result));return result}
function renderRecordFields(){recordField.replaceChildren();const selected=record.value===''?null:editableRecords[Number(record.value)];if(!selected){recordField.append(new Option('Select a record first',''));return}const fields=scalarFields(selected.value);recordField.append(new Option('Choose a field',''));fields.forEach(parts=>recordField.append(new Option(parts.join(' › '),JSON.stringify(parts))))}
function renderRecordPicker(){editableRecords=availableRecords();record.replaceChildren();const query=recordSearch.value.trim().toLowerCase();const filtered=editableRecords.map((value,index)=>({value,index})).filter(row=>row.value.label.toLowerCase().includes(query));if(!query&&filtered.length>250){record.append(new Option(`Type a name to narrow ${filtered.length} records`,''));renderRecordFields();return}if(!filtered.length){record.append(new Option('No matching records',''));renderRecordFields();return}record.append(new Option('Choose a record',''));filtered.slice(0,500).forEach(row=>record.append(new Option(row.value.label,String(row.index))));renderRecordFields()}
function applyPickedField(){const selected=record.value===''?null:editableRecords[Number(record.value)];if(!selected||!recordField.value)return;const parts=JSON.parse(recordField.value);pointer.value='/' + [...selected.prefix,...parts].map(pointerPart).join('/');updateCurrentValue()}
recordKind.onchange=renderRecordPicker;recordSearch.oninput=renderRecordPicker;record.onchange=renderRecordFields;recordField.onchange=applyPickedField;new MutationObserver(renderRecordPicker).observe(content,{childList:true,subtree:true,characterData:true});
</script></body></html>"""


def make_handler(catalog: PresetCatalog) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

        def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A browser can cancel an older table request when a newer
                # tab/query request supersedes it.  That is normal for this
                # local workbench and must not produce a server traceback.
                return

        def _send_page(self, page: str = SPREADSHEET_PAGE) -> None:
            body = page.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_asset(self, path: Path) -> None:
            payload = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _request_object(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("request has an invalid Content-Length") from exc
            if length < 2 or length > 1024 * 1024:
                raise ValueError("request body must be a JSON object below 1 MiB")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_page()
                return
            if parsed.path == "/manifests":
                self._send_page(PAGE)
                return
            if parsed.path == "/api/index":
                self._send_json(HTTPStatus.OK, catalog.index())
                return
            if parsed.path == "/api/spreadsheet/metadata":
                query = parse_qs(parsed.query)
                try:
                    self._send_json(HTTPStatus.OK, catalog.spreadsheet_metadata(query.get("season", [""])[0]))
                except KeyError:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "season not found in local catalog"})
                except (ValueError, amendments.AmendmentError) as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            if parsed.path == "/api/spreadsheet/table":
                query = parse_qs(parsed.query)
                try:
                    offset = int(query.get("offset", ["0"])[0])
                    limit = int(query.get("limit", ["200"])[0])
                    if offset < 0 or limit < 1 or limit > 500:
                        raise ValueError("spreadsheet page arguments are out of range")
                    self._send_json(HTTPStatus.OK, catalog.spreadsheet_tab(
                        season=query.get("season", [""])[0],
                        tab=query.get("tab", [""])[0],
                        query=query.get("q", [""])[0], offset=offset, limit=limit,
                    ))
                except KeyError:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "season not found in local catalog"})
                except (ValueError, amendments.AmendmentError) as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            if parsed.path == "/api/kit":
                query = parse_qs(parsed.query)
                try:
                    carrier = int(query.get("carrier", [""])[0])
                    variant = int(query.get("variant", [""])[0])
                    self._send_asset(catalog.kit_asset(
                        season=query.get("season", [""])[0], carrier=carrier, variant=variant,
                    ))
                except (ValueError, FileNotFoundError):
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "kit bitmap is not in the local allowlist"})
                return
            if parsed.path == "/api/portrait":
                query = parse_qs(parsed.query)
                try:
                    self._send_asset(catalog.portrait_asset(
                        season=query.get("season", [""])[0], player_id=query.get("player", [""])[0],
                    ))
                except (ValueError, FileNotFoundError):
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "portrait bitmap is not in the local allowlist"})
                return
            if parsed.path == "/api/preset":
                query = parse_qs(parsed.query)
                try:
                    self._send_json(
                        HTTPStatus.OK,
                        catalog.read(query.get("season", [""])[0], query.get("id", [""])[0]),
                    )
                except (KeyError, FileNotFoundError):
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "preset not found in local catalog"})
                except ValueError as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            if parsed.path == "/api/amendments":
                query = parse_qs(parsed.query)
                try:
                    self._send_json(HTTPStatus.OK, {
                        "amendments": catalog.amendments(query.get("season", [""])[0])
                    })
                except (KeyError, FileNotFoundError):
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "season not found in local catalog"})
                except amendments.AmendmentError as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown local browser route"})

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            try:
                request = self._request_object()
                season = request.get("season")
                if not isinstance(season, str):
                    raise ValueError("request must name a season")
                if parsed.path == "/api/amendments/stage":
                    manifest_id = request.get("manifest_id")
                    pointer = request.get("json_pointer")
                    reason = request.get("reason")
                    if not isinstance(manifest_id, str) or not isinstance(pointer, str) or not isinstance(reason, str):
                        raise ValueError("staging requires manifest_id, json_pointer and reason")
                    evidence = request.get("evidence")
                    if evidence is not None and not isinstance(evidence, str):
                        raise ValueError("evidence must be a string when supplied")
                    document = catalog.stage_amendment(
                        season=season,
                        manifest_id=manifest_id,
                        json_pointer=pointer,
                        replacement=request.get("set"),
                        reason=reason,
                        evidence=evidence,
                    )
                    self._send_json(HTTPStatus.OK, {"amendments": document})
                    return
                if parsed.path == "/api/amendments/remove":
                    change_id = request.get("change_id")
                    if not isinstance(change_id, str):
                        raise ValueError("removal requires change_id")
                    self._send_json(HTTPStatus.OK, {
                        "amendments": catalog.remove_amendment(season=season, change_id=change_id)
                    })
                    return
                if parsed.path == "/api/amendments/materialise":
                    self._send_json(HTTPStatus.OK, {
                        "receipt": catalog.materialise_amendments(season=season)
                    })
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown local browser write route"})
            except (KeyError, FileNotFoundError):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "season or manifest not found in local catalog"})
            except (ValueError, amendments.AmendmentError) as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons-root", type=Path, default=DEFAULT_SEASONS_ROOT)
    parser.add_argument(
        "--playtests-root", type=Path, default=DEFAULT_PLAYTESTS_ROOT,
        help="Local provisional-playtest cache to inspect alongside season manifests",
    )
    parser.add_argument(
        "--authoring-root", type=Path, default=DEFAULT_AUTHORING_ROOT,
        help="Generated per-season authoring manifests to include automatically",
    )
    parser.add_argument(
        "--recipe-root", type=Path, default=DEFAULT_RECIPE_ROOT,
        help="Published per-season recipe receipts; one current package is selected per year",
    )
    parser.add_argument(
        "--static-ingress-root", type=Path, default=DEFAULT_STATIC_INGRESS_ROOT,
        help="Exact source packages behind the local playable runtime candidates",
    )
    parser.add_argument(
        "--runtime-candidates-root", type=Path, default=DEFAULT_RUNTIME_CANDIDATES_ROOT,
        help="Local runtime candidates used to admit a published recipe",
    )
    parser.add_argument(
        "--kit-render-root", type=Path, default=DEFAULT_KIT_RENDER_ROOT,
        help="Hash-bound rendered kit BMP cache to link from the spreadsheet",
    )
    parser.add_argument(
        "--portrait-render-root", type=Path, default=DEFAULT_PORTRAIT_RENDER_ROOT,
        help="Hash-bound player portrait BMP cache to link from the spreadsheet",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Loopback host only (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Port; 0 asks the OS for a free port")
    parser.add_argument("--include-source-captures", action="store_true", help="Include raw sources/ JSON files")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening it")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Refusing non-loopback host: this local browser must not expose season files on a network")
    try:
        catalog = PresetCatalog(
            args.seasons_root,
            preferred_catalog_path=release_registry.CATALOG_PATH,
            include_source_captures=args.include_source_captures,
            playtests_root=args.playtests_root,
            authoring_root=args.authoring_root,
            recipe_root=args.recipe_root,
            static_ingress_root=args.static_ingress_root,
            runtime_candidates_root=args.runtime_candidates_root,
            kit_render_root=args.kit_render_root,
            portrait_render_root=args.portrait_render_root,
        )
    except ValueError as exc:
        raise SystemExit(f"preset browser error: {exc}") from exc
    server = ThreadingHTTPServer((args.host, args.port), make_handler(catalog))
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"PM99 Local Preset Browser: {url}")
    print(f"Discovered {len(catalog.entries)} seasons; press Ctrl-C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLocal preset browser stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
