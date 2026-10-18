#!/usr/bin/env python3
"""Freeze passed season QA into source-only release-candidate manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pm99_season_play_v1 import REQUIRED, game_path  # noqa: E402
from scripts.pm99_season_qa_v1 import SEASONS, resolve_package  # noqa: E402
from scripts.season_package_v2 import canonical_json_bytes  # noqa: E402


SCHEMA = "pm99-season-release-candidate-v1"


class ReleaseCandidateError(ValueError):
    """A release candidate cannot be frozen from the supplied evidence."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    path = path.resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ReleaseCandidateError(f"release evidence lies outside workspace: {path}") from exc
    if not path.is_file() or path.is_symlink():
        raise ReleaseCandidateError(f"release evidence is missing or unsafe: {path}")
    return {"path": relative, "sha256": _sha256(path), "size": path.stat().st_size}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseCandidateError(f"cannot read JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseCandidateError(f"JSON object required: {path}")
    return value


def _manager_receipt(season: str) -> Path | None:
    for root in ("season-direct-target-manager-repairs-v2", "season-direct-target-manager-repairs-v1"):
        path = ROOT / ".local" / root / f"{season}.json"
        if path.is_file():
            return path
    return None


def cut(*, rc_id: str, qa_root: Path, output_root: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,39}", rc_id):
        raise ReleaseCandidateError("RC id must be a short lowercase filename-safe label")
    qa_root, output_root = qa_root.resolve(), output_root.resolve()
    if output_root.exists() or output_root.is_symlink():
        raise ReleaseCandidateError(f"refusing to replace release output: {output_root}")
    aggregate_path = qa_root / "qa-report.json"
    aggregate = _read(aggregate_path)
    if (
        aggregate.get("result") != "pass"
        or aggregate.get("passed_season_count") != len(SEASONS)
        or aggregate.get("blocker_count") != 0
    ):
        raise ReleaseCandidateError("all-season QA is not a clean 26-season pass")

    output_root.mkdir(parents=True)
    index_rows = []
    for season in SEASONS:
        qa_path = qa_root / season / "qa-report.json"
        qa = _read(qa_path)
        if qa.get("result") != "pass" or (qa.get("summary") or {}).get("blocker_count") != 0:
            raise ReleaseCandidateError(f"{season}: QA report is not a blocker-free pass")
        package_path = resolve_package(season)
        game = game_path(season)
        runtime = qa.get("checks", {}).get("runtime", {})
        screenshot_value = runtime.get("lineup_screenshot") if isinstance(runtime, dict) else None
        if not isinstance(screenshot_value, str):
            raise ReleaseCandidateError(f"{season}: line-up runner screenshot is not bound")
        manager_receipt = _manager_receipt(season)
        manifest = {
            "schema_version": SCHEMA,
            "rc_id": rc_id,
            "season": season,
            "classification": "playable-source-backed-release-candidate",
            "recipe": _record(package_path),
            "runtime": {
                "game_tree": game.resolve().relative_to(ROOT).as_posix(),
                "files": {relative: _record(game / relative) for relative in REQUIRED},
            },
            "quality": {
                "qa_report": _record(qa_path),
                "warning_count": int((qa.get("summary") or {}).get("warning_count") or 0),
                "warnings": qa.get("warnings") or [],
            },
            "evidence": {
                "runner_summary": _record(ROOT / str(runtime["summary"])),
                "lineup_screenshot": _record(ROOT / screenshot_value),
                "manager_repair_receipt": _record(manager_receipt) if manager_receipt else None,
            },
            "commands": {
                "validate": f"./pm99-season qa {season}",
                "play": f"./pm99-season play {season}",
            },
        }
        season_dir = output_root / season
        season_dir.mkdir()
        manifest_path = season_dir / "release-candidate.json"
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        index_rows.append({"season": season, "manifest": _record(manifest_path)})
    index = {
        "schema_version": "pm99-season-release-candidate-index-v1",
        "rc_id": rc_id,
        "state": "frozen",
        "season_count": len(index_rows),
        "qa_batch": _record(aggregate_path),
        "seasons": index_rows,
    }
    index_path = output_root / "release-candidate-index.json"
    index_path.write_bytes(canonical_json_bytes(index))
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rc-id", required=True)
    parser.add_argument("--qa-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = cut(rc_id=args.rc_id, qa_root=args.qa_root, output_root=args.output_root)
    except (OSError, ReleaseCandidateError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"state": index["state"], "rc_id": index["rc_id"], "season_count": index["season_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
