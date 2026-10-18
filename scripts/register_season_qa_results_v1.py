#!/usr/bin/env python3
"""Bind completed QA reports to their exact preferred season releases."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


class QaRegistrationError(ValueError):
    """A QA result does not describe the preferred release."""


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    encoded = pipeline.canonical_json_bytes(dict(value)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def register(season: str, report_path: Path) -> dict[str, object]:
    release = registry.load_preferred_release(season)
    report = pipeline.read_json_file(report_path)
    expected_package_hash = registry.sha256_file(release.package_path)
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    if (
        report.get("schema_version") != "pm99-season-quality-qa-v1"
        or report.get("season") != season
        or report.get("result") != "pass"
        or inputs.get("game_tree") != registry.relative_workspace_path(release.game_path)
        or inputs.get("package_sha256") != expected_package_hash
    ):
        raise QaRegistrationError(f"QA report is not a passing result for preferred {season}: {report_path}")
    summary = report.get("summary")
    if not isinstance(summary, Mapping) or not isinstance(summary.get("warning_count"), int):
        raise QaRegistrationError(f"QA report has no warning summary: {report_path}")
    locator_path = registry.locator_path(season, release.release_id)
    locator = pipeline.read_json_file(locator_path)
    locator.update({
        "qa_report_path": registry.relative_workspace_path(report_path),
        "qa_report_sha256": registry.sha256_file(report_path),
        "qa_status": "pass",
        "editorial_warning_count": int(summary["warning_count"]),
        "editorial_status": "review-required" if summary["warning_count"] else "checked",
    })
    _write_atomic(locator_path, locator)
    return {
        "season": season,
        "qa_status": "pass",
        "editorial_warning_count": int(summary["warning_count"]),
        "qa_report": locator["qa_report_path"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_root", type=Path)
    parser.add_argument("season", nargs="?", default="all")
    args = parser.parse_args()
    seasons = registry.supported_seasons() if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    try:
        results = [register(season, args.report_root / season / "qa-report.json") for season in seasons]
    except (OSError, pipeline.PipelineError, registry.RegistryError, QaRegistrationError) as exc:
        print(f"QA registration error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"registered": len(results), "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
