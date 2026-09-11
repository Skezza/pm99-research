#!/usr/bin/env python3
"""Build and apply the V5 factory-tone kit overlay to playable seasons.

This deliberately updates only MINIESC, NANOESC and RIDIESC in each existing
preferred runtime.  The accepted database, executable and every non-kit file
remain untouched.  Original archive materialisations remain available, and a
hash-bound overlay receipt makes the operation resumable and reversible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
BASE_DBDAT = LOCAL / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"
PATTERN_CACHE = LOCAL / "source-cache" / "wikimedia-kit-patterns-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
SCHEMA = "pm99-season-kit-runtime-overlay-v1"
RENDERER = "pm99-factory-template-kit-v5-native-tone-transfer"

REVISIONS = {
    "2000-01": "r1", "2001-02": "r2", "2002-03": "r5", "2003-04": "r3",
    "2004-05": "r3", "2005-06": "r3", "2006-07": "r3", "2007-08": "r1",
    "2008-09": "r1", "2009-10": "r2", "2010-11": "r3", "2011-12": "r1",
    "2012-13": "r1", "2013-14": "r1", "2014-15": "r2", "2016-17": "r2",
    "2017-18": "r1", "2018-19": "r3", "2019-20": "r3", "2020-21": "r2",
    "2021-22": "r3", "2022-23": "r2", "2023-24": "r3", "2024-25": "r3",
    "2025-26": "r3",
}


class OverlayError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OverlayError(f"{label} is unavailable or invalid: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OverlayError(f"{label} must be an object: {path}")
    return value


def _run(command: list[str], terminal: Path) -> None:
    if terminal.is_file():
        return
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode or not terminal.is_file():
        raise OverlayError(
            json.dumps(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "expected_terminal": str(terminal),
                },
                indent=2,
            )
        )


def _archive_rows(receipt: Mapping[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = receipt.get("archives")
    if not isinstance(rows, Mapping):
        raise OverlayError(f"{label} has no archive map")
    result = {}
    for archive in ARCHIVES:
        row = rows.get(archive)
        digest = str(row.get("sha256_after") or "") if isinstance(row, Mapping) else ""
        if len(digest) != 64:
            raise OverlayError(f"{label} lacks a final hash for {archive}")
        result[archive] = dict(row)
    return result


def _revision_number(path: Path) -> tuple[int, str]:
    name = path.parent.name
    if name.startswith("r") and name[1:].isdigit():
        return int(name[1:]), name
    return -1, name


def _author_input(season: str, runtime_revision: str) -> Path:
    exact = LOCAL / "season-english-authoring-v1" / season / runtime_revision / "english-compiler-input.json"
    if exact.is_file():
        return exact
    candidates = sorted(
        (LOCAL / "season-english-authoring-v1" / season).glob("*/english-compiler-input.json"),
        key=_revision_number,
    )
    if not candidates:
        raise OverlayError(f"{season} has no English compiler input")
    return candidates[-1]


def _build(season: str, revision: str) -> tuple[Path, Path, Path]:
    author = _author_input(season, revision)
    render_root = LOCAL / "season-kit-renders-v1" / season / f"source-backed-{revision}-kit-v5"
    archive_root = LOCAL / "season-kit-archives-v1" / season / f"source-backed-{revision}-kit-v5"
    _run(
        [
            sys.executable,
            "scripts/season_kit_render_bindings_v1.py",
            "--english-compiler-input", str(author),
            "--clean-dbdat", str(BASE_DBDAT),
            "--output-dir", str(render_root),
            "--pattern-cache-dir", str(PATTERN_CACHE),
        ],
        render_root / "kit-render-receipt-v1.json",
    )
    render_receipt = _read(render_root / "kit-render-receipt-v1.json", "V5 render receipt")
    if (render_receipt.get("policy") or {}).get("reviewed_style_renderer") != RENDERER:
        raise OverlayError(f"{season} render receipt does not use {RENDERER}")
    _run(
        [
            sys.executable,
            "scripts/materialise_season_kit_archives_v1.py",
            "--kit-render-bindings", str(render_root / "kit-render-bindings-v1.json"),
            "--kit-render-receipt", str(render_root / "kit-render-receipt-v1.json"),
            "--clean-dbdat", str(BASE_DBDAT),
            "--output-dir", str(archive_root),
        ],
        archive_root / "kit-archive-materialisation-receipt-v1.json",
    )
    return render_root, archive_root, author


def apply(season: str, revision: str) -> dict[str, Any]:
    runtime = LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game"
    original_receipt_path = (
        LOCAL / "season-kit-archives-v1" / season / f"source-backed-{revision}"
        / "kit-archive-materialisation-receipt-v1.json"
    )
    overlay_receipt_path = LOCAL / "season-kit-runtime-overlays-v1" / season / "v5" / "receipt.json"
    if overlay_receipt_path.is_file():
        receipt = _read(overlay_receipt_path, "existing V5 overlay receipt")
        expected = _archive_rows(receipt, "existing V5 overlay receipt")
        mismatches = [
            archive for archive in ARCHIVES
            if not (runtime / "DBDAT" / archive).is_file()
            or _sha256(runtime / "DBDAT" / archive) != expected[archive]["sha256_after"]
        ]
        if mismatches:
            raise OverlayError(f"{season} has a stale V5 overlay receipt: {mismatches}")
        provenance = receipt.get("provenance") if isinstance(receipt.get("provenance"), dict) else {}
        if not provenance.get("english_compiler_input"):
            author_input = _author_input(season, revision)
            provenance["english_compiler_input"] = str(author_input.relative_to(ROOT))
            provenance["english_compiler_input_sha256"] = _sha256(author_input)
            receipt["provenance"] = provenance
            temp_receipt = overlay_receipt_path.with_suffix(".json.tmp")
            temp_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temp_receipt, overlay_receipt_path)
        return {"season": season, "status": "reused", "receipt": str(overlay_receipt_path.relative_to(ROOT))}

    original_receipt = _read(original_receipt_path, "original kit archive receipt")
    original_rows = _archive_rows(original_receipt, "original kit archive receipt")
    before = {}
    for archive in ARCHIVES:
        path = runtime / "DBDAT" / archive
        if not path.is_file():
            raise OverlayError(f"{season} runtime lacks {archive}")
        actual = _sha256(path)
        expected = original_rows[archive]["sha256_after"]
        if actual != expected:
            raise OverlayError(
                f"{season} {archive} is not the accepted pre-V5 archive: {actual} != {expected}"
            )
        before[archive] = actual

    render_root, archive_root, author_input = _build(season, revision)
    v5_receipt_path = archive_root / "kit-archive-materialisation-receipt-v1.json"
    v5_receipt = _read(v5_receipt_path, "V5 kit archive receipt")
    v5_rows = _archive_rows(v5_receipt, "V5 kit archive receipt")
    coverage = v5_receipt.get("coverage") if isinstance(v5_receipt.get("coverage"), Mapping) else {}

    dbdat = runtime / "DBDAT"
    with tempfile.TemporaryDirectory(prefix=f"pm99-{season}-kit-v5-", dir=dbdat) as temporary:
        temporary_root = Path(temporary)
        staged = {}
        backups = {}
        for archive in ARCHIVES:
            source = archive_root / "archives" / archive
            expected = v5_rows[archive]["sha256_after"]
            if not source.is_file() or _sha256(source) != expected:
                raise OverlayError(f"{season} V5 source archive is missing or stale: {archive}")
            staged_path = temporary_root / f"new-{archive}"
            backup_path = temporary_root / f"old-{archive}"
            shutil.copy2(source, staged_path)
            shutil.copy2(dbdat / archive, backup_path)
            staged[archive] = staged_path
            backups[archive] = backup_path
        replaced = []
        try:
            for archive in ARCHIVES:
                os.replace(staged[archive], dbdat / archive)
                replaced.append(archive)
            for archive in ARCHIVES:
                actual = _sha256(dbdat / archive)
                if actual != v5_rows[archive]["sha256_after"]:
                    raise OverlayError(f"{season} post-write hash mismatch for {archive}")
        except Exception:
            for archive in replaced:
                shutil.copy2(backups[archive], dbdat / archive)
            raise

    receipt = {
        "schema_version": SCHEMA,
        "season": season,
        "revision": revision,
        "renderer": RENDERER,
        "result": "applied-kit-only-overlay",
        "changed_file_count": len(ARCHIVES),
        "changed_files": [f"DBDAT/{archive}" for archive in ARCHIVES],
        "coverage": {
            "bound_carrier_count": int(coverage.get("bound_carrier_count") or 0),
            "patched_record_count": int(coverage.get("patched_record_count") or 0),
        },
        "archives": {
            archive: {
                "sha256_before": before[archive],
                "sha256_after": v5_rows[archive]["sha256_after"],
            }
            for archive in ARCHIVES
        },
        "provenance": {
            "original_archive_receipt": str(original_receipt_path.relative_to(ROOT)),
            "original_archive_receipt_sha256": _sha256(original_receipt_path),
            "v5_render_receipt": str((render_root / "kit-render-receipt-v1.json").relative_to(ROOT)),
            "v5_render_receipt_sha256": _sha256(render_root / "kit-render-receipt-v1.json"),
            "v5_archive_receipt": str(v5_receipt_path.relative_to(ROOT)),
            "v5_archive_receipt_sha256": _sha256(v5_receipt_path),
            "english_compiler_input": str(author_input.relative_to(ROOT)),
            "english_compiler_input_sha256": _sha256(author_input),
        },
    }
    overlay_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temp_receipt = overlay_receipt_path.with_suffix(".json.tmp")
    temp_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_receipt, overlay_receipt_path)
    return {
        "season": season,
        "status": "applied",
        "changed_file_count": len(ARCHIVES),
        "bound_carrier_count": receipt["coverage"]["bound_carrier_count"],
        "receipt": str(overlay_receipt_path.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="YYYY-YY or all")
    args = parser.parse_args()
    seasons = sorted(REVISIONS) if args.season == "all" else [args.season]
    unknown = [season for season in seasons if season not in REVISIONS]
    if unknown:
        parser.error("unsupported post-1999 season(s): " + ", ".join(unknown))
    results = []
    try:
        for season in seasons:
            result = apply(season, REVISIONS[season])
            results.append(result)
            print(json.dumps(result, sort_keys=True), flush=True)
    except (OSError, ValueError, OverlayError) as exc:
        print(json.dumps({"result": "failed", "completed": results, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"result": "pass", "season_count": len(results), "seasons": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
