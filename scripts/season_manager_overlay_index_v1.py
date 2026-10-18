#!/usr/bin/env python3
"""Freeze explicit, hash-bound manager-overlay selections for one baseline.

This is deliberately an index builder, not an overlay discovery tool.  The
selection manifest names one ``manager-vN`` directory for every baseline
season; a later directory appearing on disk therefore cannot change a report
until a new explicit manifest and index are made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_SCHEMA = "pm99-season-baseline-index-v1"
OVERLAY_SCHEMA = "pm99-season-manager-overlay-v1"
SELECTION_SCHEMA = "pm99-season-manager-overlay-selection-manifest-v1"
SCHEMA = "pm99-season-manager-overlay-index-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OVERLAY_ID_RE = re.compile(r"manager-v[1-9][0-9]*$")


class OverlayIndexError(ValueError):
    """No unambiguous, hash-bound overlay exists for a baseline season."""


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OverlayIndexError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise OverlayIndexError(f"{label} must be a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def _safe_child(parent: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise OverlayIndexError(f"{label} path is unsafe")
    result = (parent / relative).resolve()
    if result != parent.resolve() and parent.resolve() not in result.parents:
        raise OverlayIndexError(f"{label} path escapes its parent")
    return result


def _relative(path: Path, *, workspace_root: Path) -> str:
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError as exc:
        raise OverlayIndexError(f"artifact lies outside workspace root: {path}") from exc


def _overlay_id(value: object, *, season: str) -> str:
    if not isinstance(value, str) or OVERLAY_ID_RE.fullmatch(value) is None:
        raise OverlayIndexError(f"{season}: overlay_id must be a manager-vN directory name")
    return value


def _selection_rows(
    *, baseline: Mapping[str, Any], baseline_sha256: str, selection: Mapping[str, Any],
) -> dict[str, str]:
    if selection.get("schema_version") != SELECTION_SCHEMA or selection.get("state") != "explicit-manager-overlay-selection":
        raise OverlayIndexError("selection manifest has an unsupported schema or state")
    if selection.get("baseline_index_sha256") != baseline_sha256:
        raise OverlayIndexError("selection manifest is bound to a different baseline index")
    baseline_rows = baseline.get("seasons")
    rows = selection.get("seasons")
    if not isinstance(baseline_rows, list) or not isinstance(rows, list):
        raise OverlayIndexError("baseline or selection manifest has no season list")
    expected: set[str] = set()
    for row in baseline_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("season"), str):
            raise OverlayIndexError("baseline index has a malformed season")
        season = row["season"]
        if season in expected:
            raise OverlayIndexError(f"baseline index duplicates {season}")
        expected.add(season)
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("season"), str):
            raise OverlayIndexError("selection manifest has a malformed season")
        season = row["season"]
        if season not in expected:
            raise OverlayIndexError(f"selection manifest names non-baseline season {season}")
        if season in result:
            raise OverlayIndexError(f"selection manifest selects {season} more than once")
        result[season] = _overlay_id(row.get("overlay_id"), season=season)
    omitted = sorted(expected - set(result))
    if omitted:
        raise OverlayIndexError(f"selection manifest omits baseline season {omitted[0]}")
    return result


def build_index(
    *, baseline: Mapping[str, Any], baseline_sha256: str, baseline_path: Path,
    overlays_root: Path, selection: Mapping[str, Any], selection_sha256: str,
    selection_path: Path, workspace_root: Path = ROOT,
) -> dict[str, Any]:
    """Return one immutable overlay selection for each baseline season.

    ``selection`` is compulsory so the function never derives an answer from
    directory ordering.  Every selected audit, ledger and the selection
    manifest itself are recorded by SHA-256 in the returned pointer.
    """

    if baseline.get("schema_version") != BASELINE_SCHEMA or baseline.get("state") != "frozen-provisional-base":
        raise OverlayIndexError("baseline index must be frozen-provisional-base")
    if SHA256_RE.fullmatch(baseline_sha256) is None or SHA256_RE.fullmatch(selection_sha256) is None:
        raise OverlayIndexError("baseline and selection hashes must be lowercase SHA-256")
    selected_ids = _selection_rows(
        baseline=baseline, baseline_sha256=baseline_sha256, selection=selection,
    )
    seasons = baseline.get("seasons")
    assert isinstance(seasons, list)  # established by _selection_rows
    rows: list[dict[str, Any]] = []
    for baseline_row in seasons:
        assert isinstance(baseline_row, Mapping)
        season = str(baseline_row["season"])
        overlay_id = selected_ids[season]
        selected = _safe_child(overlays_root / season, overlay_id, f"{season} selected manager overlay")
        audit_path = selected / "manager-overlay-audit.json"
        ledger_path = selected / "opening-manager-ledger.json"
        audit, audit_sha = _load(audit_path, f"{season} manager overlay audit")
        if audit.get("schema_version") != OVERLAY_SCHEMA or audit.get("season") != season:
            raise OverlayIndexError(f"{season}: manager overlay audit has an unexpected schema or season")
        base = audit.get("base")
        outputs = audit.get("outputs")
        if not isinstance(base, Mapping) or base.get("baseline_index_sha256") != baseline_sha256:
            raise OverlayIndexError(f"{season}: manager overlay is bound to a different baseline")
        try:
            ledger_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise OverlayIndexError(f"cannot read {season} selected manager ledger: {ledger_path}") from exc
        if not isinstance(outputs, Mapping) or outputs.get("opening_manager_ledger_sha256") != ledger_sha:
            raise OverlayIndexError(f"{season}: manager overlay ledger hash mismatch")
        rows.append({
            "season": season,
            "overlay_id": overlay_id,
            "manager_overlay_audit": {
                "path": _relative(audit_path, workspace_root=workspace_root), "sha256": audit_sha,
            },
            "opening_manager_ledger": {
                "path": _relative(ledger_path, workspace_root=workspace_root), "sha256": ledger_sha,
            },
            "coverage": audit.get("coverage"),
        })
    return {
        "schema_version": SCHEMA,
        "state": "frozen-manager-overlay-selection",
        "selection_policy": "every-overlay-id-is-explicitly-selected; no-directory-newest-selection",
        "baseline_index": {
            "path": _relative(baseline_path, workspace_root=workspace_root), "sha256": baseline_sha256,
        },
        "baseline_index_sha256": baseline_sha256,
        "selection_manifest": {
            "path": _relative(selection_path, workspace_root=workspace_root), "sha256": selection_sha256,
        },
        "seasons": rows,
        "summary": {"season_count": len(rows), "selected_overlay_count": len(rows)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", type=Path, default=ROOT / ".local/season-baselines-v1/calendar-bound-v2.json")
    parser.add_argument("--overlays-root", type=Path, default=ROOT / ".local/season-overlays-v1")
    parser.add_argument("--selection-manifest", required=True, type=Path,
                        help="one explicit overlay ID for every baseline season")
    parser.add_argument("--workspace-root", type=Path, default=ROOT,
                        help="root used for portable, safe artifact paths in the output")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise OverlayIndexError(f"refusing to overwrite overlay selection index: {args.output}")
        baseline, baseline_sha = _load(args.baseline_index, "baseline index")
        selection, selection_sha = _load(args.selection_manifest, "selection manifest")
        result = build_index(
            baseline=baseline, baseline_sha256=baseline_sha, baseline_path=args.baseline_index,
            overlays_root=args.overlays_root, selection=selection, selection_sha256=selection_sha,
            selection_path=args.selection_manifest, workspace_root=args.workspace_root,
        )
    except (OSError, OverlayIndexError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
