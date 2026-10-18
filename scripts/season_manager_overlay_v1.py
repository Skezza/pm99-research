#!/usr/bin/env python3
"""Create one append-only opening-manager overlay for a frozen season base.

Raw manager supplements are independently captured evidence.  This tool
composes compatible supplements, materialises their one manager ledger, and
pins both outputs to one frozen baseline package.  It never changes that base,
the raw sources, or another season.  A later authoring pass may consume this
overlay only when the base-package hash still matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compose_opening_manager_supplements_v1 as composer  # noqa: E402
from scripts import materialise_opening_manager_ledger_v1 as ledger_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-manager-overlay-v1"
BASELINE_SCHEMA = "pm99-season-baseline-index-v1"


class ManagerOverlayError(ValueError):
    """A manager overlay would not be a safe forward extension."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerOverlayError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ManagerOverlayError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _baseline_entry(*, baseline: Mapping[str, Any], season: str) -> Mapping[str, Any]:
    if baseline.get("schema_version") != BASELINE_SCHEMA or baseline.get("state") != "frozen-provisional-base":
        raise ManagerOverlayError("unsupported or mutable baseline index")
    matches = [row for row in baseline.get("seasons", []) if isinstance(row, Mapping) and row.get("season") == season]
    if len(matches) != 1:
        raise ManagerOverlayError(f"baseline does not select exactly one {season} package")
    entry = matches[0]
    package = entry.get("base_draft")
    if not isinstance(package, Mapping):
        raise ManagerOverlayError(f"baseline {season} entry has no base draft")
    expected = package.get("sha256")
    path_value = package.get("path")
    if not isinstance(expected, str) or not package_v2.SHA256_RE.fullmatch(expected):
        raise ManagerOverlayError(f"baseline {season} base hash is invalid")
    if not isinstance(path_value, str) or not path_value or Path(path_value).is_absolute() or ".." in Path(path_value).parts:
        raise ManagerOverlayError(f"baseline {season} base path is unsafe")
    package_path = ROOT / path_value
    if not package_path.is_file() or _sha256_file(package_path) != expected:
        raise ManagerOverlayError(f"baseline {season} base package is missing or hash-mismatched")
    return entry


def build_overlay(
    *, baseline: Mapping[str, Any], baseline_sha256: str, season: str,
    source_capture: Mapping[str, Any], source_capture_sha256: str,
    opening_lineups: Mapping[str, Any], opening_lineups_sha256: str,
    supplements: Sequence[tuple[Path, Mapping[str, Any], str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compose dated manager evidence and return ledger plus immutable receipt."""
    entry = _baseline_entry(baseline=baseline, season=season)
    if not supplements:
        raise ManagerOverlayError("at least one manager supplement is required")
    if not isinstance(source_capture.get("clubs"), list):
        raise ManagerOverlayError("source capture has no club list")
    if opening_lineups.get("season_start_year") != int(season[:4]):
        raise ManagerOverlayError("opening lineup receipt targets a different season")
    ordered = sorted(supplements, key=lambda item: str(item[0].resolve()))
    try:
        composed = composer.compose([(document, digest) for _path, document, digest in ordered])
        composed_bytes = composer.canonical_json_bytes(composed)
        composed_sha256 = hashlib.sha256(composed_bytes).hexdigest()
        materialised = ledger_v1.materialise(
            source_capture=source_capture,
            source_capture_sha256=source_capture_sha256,
            lineup=opening_lineups,
            lineup_sha256=opening_lineups_sha256,
            supplement=composed,
            supplement_sha256=composed_sha256,
        )
    except (composer.ManagerSupplementCompositionError, ledger_v1.ManagerLedgerError) as exc:
        raise ManagerOverlayError(str(exc)) from exc
    materialised_bytes = ledger_v1._canonical_json_bytes(materialised)
    receipt = {
        "schema_version": SCHEMA,
        "season": season,
        "state": "manager-overlay-provisional-not-release",
        "base": {
            "baseline_index_sha256": baseline_sha256,
            "base_draft_sha256": entry["base_draft"]["sha256"],
        },
        "inputs": {
            "source_capture_sha256": source_capture_sha256,
            "opening_lineups_sha256": opening_lineups_sha256,
            "supplements": [
                {"path": _relative(path), "sha256": digest}
                for path, _document, digest in ordered
            ],
        },
        "outputs": {
            "composed_supplement_sha256": composed_sha256,
            "opening_manager_ledger_sha256": hashlib.sha256(materialised_bytes).hexdigest(),
        },
        "coverage": dict(materialised["summary"]),
        "not_performed": [
            "opening-XI integration", "kit integration", "rating integration",
            "strict package promotion", "database compilation", "PM99 runtime validation", "screenshot capture",
        ],
    }
    return composed, materialised, receipt


def write_overlay(
    *, baseline_index: Path, season: str, source_capture: Path, opening_lineups: Path,
    supplements: Sequence[Path], output_root: Path,
) -> dict[str, Any]:
    """Write a new overlay root once, preserving all prior evidence untouched."""
    output_root = output_root.resolve()
    if output_root.exists():
        raise ManagerOverlayError(f"refusing to overwrite manager overlay root: {output_root}")
    baseline, baseline_sha256 = _read(baseline_index, "baseline index")
    source, source_sha256 = _read(source_capture, "source capture")
    lineups, lineups_sha256 = _read(opening_lineups, "opening lineups")
    loaded_supplements = [
        (path.resolve(), *_read(path, "manager supplement"))
        for path in supplements
    ]
    composed, materialised, receipt = build_overlay(
        baseline=baseline, baseline_sha256=baseline_sha256, season=season,
        source_capture=source, source_capture_sha256=source_sha256,
        opening_lineups=lineups, opening_lineups_sha256=lineups_sha256,
        supplements=loaded_supplements,
    )
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "manager-supplement.composed.json").write_bytes(composer.canonical_json_bytes(composed))
    (output_root / "opening-manager-ledger.json").write_bytes(ledger_v1._canonical_json_bytes(materialised))
    (output_root / "manager-overlay-audit.json").write_bytes(package_v2.canonical_json_bytes(receipt))
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", required=True, type=Path)
    parser.add_argument("--season", required=True)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--opening-lineups", required=True, type=Path)
    parser.add_argument("--supplement", required=True, type=Path, action="append")
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = write_overlay(
            baseline_index=args.baseline_index, season=args.season,
            source_capture=args.source_capture, opening_lineups=args.opening_lineups,
            supplements=args.supplement, output_root=args.output_root,
        )
    except (OSError, ManagerOverlayError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
