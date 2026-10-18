#!/usr/bin/env python3
"""Compile 25 frozen season drafts plus the legacy 2015 game as previews.

This is deliberately a preview-build surface.  It creates isolated game trees,
writes target-season JUG/EQ/ENT data from the selected V2 draft, installs the
already-generated target calendar executable, and records exact input/output
hashes.  It does not claim historical completeness, materialise unreviewed
kits, or replace any existing build.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pm99-season-preview-build-batch-v1"
MANIFEST_SCHEMA = "pm99-season-preview-build-v1"
LEGACY_SEASON = "2015-16"


class PreviewBuildError(ValueError):
    """The requested preview batch is incomplete or unsafe."""


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PreviewBuildError(f"expected ordinary file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def write_new_json(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise PreviewBuildError(f"refusing to replace output: {path}")
    payload = canonical_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def ordinary_directory(path: Path, *, label: str) -> Path:
    path = path.expanduser().resolve()
    if path.is_symlink() or not path.is_dir():
        raise PreviewBuildError(f"{label} must be an existing ordinary directory: {path}")
    return path


def clone_tree(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise PreviewBuildError(f"refusing to replace game tree: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    subprocess.run(["cp", "-a", "--reflink=auto", f"{source}/.", str(target)], check=True)


def database_hashes(game: Path) -> dict[str, str]:
    return {
        name: sha256_file(game / "DBDAT" / name)
        for name in ("ENT98030.FDI", "EQ98030.FDI", "JUG98030.FDI")
    }


def compile_one(
    *, season: str, package: Path, base_tree: Path, calendar_exe: Path, output_root: Path,
) -> dict[str, Any]:
    season_root = output_root / season
    game = season_root / "game"
    season_root.mkdir()
    clone_tree(base_tree, game)
    shutil.copy2(calendar_exe, game / "MANAGPRE.EXE")
    receipt = season_root / "compiler-receipt.json"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "season_package_compiler_v2.py"),
        "--base-tree", str(base_tree),
        "--tree", str(game),
        "--package", str(package),
        "--receipt", str(receipt),
    ]
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise PreviewBuildError(
            f"{season}: compiler failed ({completed.returncode}): "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "season": season,
        "status": "compiled-provisional-preview-not-certified",
        "release_eligible": False,
        "inputs": {
            "package_sha256": sha256_file(package),
            "base_calendar_sha256": sha256_file(base_tree / "MANAGPRE.EXE"),
            "target_calendar_sha256": sha256_file(calendar_exe),
        },
        "outputs": {
            "database_sha256": database_hashes(game),
            "calendar_sha256": sha256_file(game / "MANAGPRE.EXE"),
            "compiler_receipt_sha256": sha256_file(receipt),
        },
        "known_limitations": [
            "The source package is a frozen provisional draft, not a historically certified release.",
            "Target-season kit and portrait materialisation is incomplete; unchanged base assets remain.",
            "Manager, opening-XI, rating and source-conflict queues remain visible for later amendment.",
            "No PM99 runtime or screenshot evidence is claimed by compilation.",
        ],
    }
    manifest_path = season_root / "preview-manifest.json"
    manifest_sha = write_new_json(manifest_path, manifest)
    return {
        "season": season,
        "state": "compiled-provisional-preview-not-certified",
        "game": str(game),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
    }


def copy_legacy(*, source: Path, output_root: Path) -> dict[str, Any]:
    season_root = output_root / LEGACY_SEASON
    game = season_root / "game"
    season_root.mkdir()
    clone_tree(source, game)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "season": LEGACY_SEASON,
        "status": "legacy-runtime-proven-editorial-defects-known",
        "release_eligible": False,
        "outputs": {
            "database_sha256": database_hashes(game),
            "calendar_sha256": sha256_file(game / "MANAGPRE.EXE"),
        },
        "known_limitations": [
            "User playtest found incorrect manager links, malformed foreign kits and outfield handling defects.",
            "This isolated copy is retained for comparison and is not historically approved.",
        ],
    }
    manifest_path = season_root / "preview-manifest.json"
    manifest_sha = write_new_json(manifest_path, manifest)
    return {
        "season": LEGACY_SEASON,
        "state": "legacy-runtime-proven-editorial-defects-known",
        "game": str(game),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
    }


def run_batch(
    *, package_root: Path, base_tree: Path, calendar_root: Path, legacy_game: Path,
    output_root: Path, workers: int,
) -> dict[str, Any]:
    package_root = ordinary_directory(package_root, label="package root")
    base_tree = ordinary_directory(base_tree, label="base tree")
    calendar_root = ordinary_directory(calendar_root, label="calendar root")
    legacy_game = ordinary_directory(legacy_game, label="legacy 2015 game")
    output_root = output_root.expanduser().resolve()
    if output_root.exists() or output_root.is_symlink():
        raise PreviewBuildError(f"output root must not exist: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)

    packages = sorted(package_root.glob("*/draft-season-package.json"))
    if len(packages) != 25:
        raise PreviewBuildError(f"expected 25 non-2015 packages, found {len(packages)}")
    inputs: list[tuple[str, Path, Path]] = []
    for package in packages:
        season = package.parent.name
        if season == LEGACY_SEASON:
            raise PreviewBuildError("the 25-package root must exclude legacy 2015-16")
        calendar = calendar_root / season / "MANAGPRE.EXE"
        if calendar.is_symlink() or not calendar.is_file():
            raise PreviewBuildError(f"missing target calendar for {season}: {calendar}")
        inputs.append((season, package, calendar))

    base_bytes = sum(p.stat().st_size for p in base_tree.rglob("*") if p.is_file())
    free_bytes = shutil.disk_usage(output_root.parent).free
    required_bytes = base_bytes * 27 // 2
    if free_bytes < required_bytes:
        raise PreviewBuildError(
            f"insufficient free space: need safety floor {required_bytes}, have {free_bytes}"
        )

    output_root.mkdir()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {
            pool.submit(
                compile_one,
                season=season,
                package=package,
                base_tree=base_tree,
                calendar_exe=calendar,
                output_root=output_root,
            ): season
            for season, package, calendar in inputs
        }
        for future in concurrent.futures.as_completed(pending):
            season = pending[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                failures.append({"season": season, "error": str(exc)})

    try:
        rows.append(copy_legacy(source=legacy_game, output_root=output_root))
    except Exception as exc:
        failures.append({"season": LEGACY_SEASON, "error": str(exc)})

    result = {
        "schema_version": SCHEMA,
        "state": "complete" if not failures and len(rows) == 26 else "incomplete",
        "release_eligible": False,
        "summary": {
            "requested": 26,
            "created": len(rows),
            "failed": len(failures),
        },
        "builds": sorted(rows, key=lambda row: row["season"]),
        "failures": sorted(failures, key=lambda row: row["season"]),
    }
    write_new_json(output_root / "preview-build-matrix.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--calendar-root", type=Path, required=True)
    parser.add_argument("--legacy-2015-game", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")
    try:
        result = run_batch(
            package_root=args.package_root,
            base_tree=args.base_tree,
            calendar_root=args.calendar_root,
            legacy_game=args.legacy_2015_game,
            output_root=args.output_root,
            workers=args.workers,
        )
    except (PreviewBuildError, OSError, subprocess.SubprocessError) as exc:
        print(f"preview build error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if result["state"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
