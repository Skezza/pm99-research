#!/usr/bin/env python3
"""Print or execute an inventory-bound Stoke Line-Up proof for a release."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import attest_registered_season_runtime_v1 as attester  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


SELECTORS = ROOT / "data/season-runtime-selectors-v1.json"
ARTIFACT_ROOT = ROOT / ".local/runlogs/pm99_runner"


class CaptureError(ValueError):
    """A registered runtime proof cannot be planned or completed."""


def _selector(season: str) -> dict[str, Any]:
    value = json.loads(SELECTORS.read_text(encoding="utf-8"))
    if value.get("schema_version") != "pm99-season-runtime-selectors-v1":
        raise CaptureError("runtime selector catalogue has an unsupported schema")
    matches = [row for row in value.get("seasons", []) if row.get("season") == season]
    if len(matches) != 1:
        raise CaptureError(f"runtime selector catalogue needs exactly one {season} row")
    return matches[0]


def capture_command(*, season: str, worker: str, run_tag: str,
                    compact_evidence: bool = False,
                    release_id: str | None = None) -> tuple[list[str], Path]:
    # A candidate can be proved before promotion, without changing the user's
    # current play command. Attestation still requires the preferred release.
    release = (registry.load_registered_release(season, release_id) if release_id is not None
               else registry.load_preferred_release(season))
    if release.release_manifest_path is None or release.manifest_sha256 is None:
        raise CaptureError("registered release has no canonical manifest")
    validation = (registry.validate_preferred_release(season, level="playable", release_id=release_id)
                  if release_id is not None else registry.validate_preferred_release(season, level="playable"))
    if not validation["valid"]:
        raise CaptureError("registered game failed its immutable playable hash check")
    selector = _selector(season)
    command = [
        str(ROOT / "scripts/run_pm99_experiment.sh"), "route-capture",
        "--worker", worker, "--run-tag", run_tag, "--allow-dirty-runner", "--",
        "--skip-setup", "--skip-prepare", "--skip-build",
        "--dbdat-dir", str(release.game_path / "DBDAT"),
        "--exe-file", str(release.game_path / "MANAGPRE.EXE"),
        "--release-manifest-sha256", release.manifest_sha256,
        "--output-inventory-fingerprint", str(release.locator["game_inventory_fingerprint"]),
        "--manager-name", "AI",
        "--team-name", str(selector["team_name"]),
        "--team-select-x", str(selector["team_select_x"]),
        "--team-select-y", str(selector["team_select_y"]),
        "--division-select-x", str(selector["division_select_x"]),
        "--division-select-y", str(selector["division_select_y"]),
        "--profile-count", "0",
        "--capture-route", "line_up",
    ]
    if compact_evidence:
        command.extend(['--artifact-screen-scope', 'lineup'])
    return command, ARTIFACT_ROOT / run_tag


def capture_one(*, season: str, args: argparse.Namespace) -> dict[str, Any]:
    """Serialize proof creation per season, then recheck completed evidence.

    Multiple batches may share the worker's three lanes, but must not launch
    the same release twice or race its immutable attestation. The kernel drops
    this local advisory lock if the coordinator exits; no stale lease deletion
    or worker-lock override is required.
    """
    season = pipeline.normalise_season_id(season)
    if not args.execute:
        return _capture_one_unlocked(season=season, args=args)
    locks = ROOT / '.local/season-runtime-coordination-v1'
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (season + '.lock')).open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _capture_one_unlocked(season=season, args=args)


def _capture_one_unlocked(*, season: str, args: argparse.Namespace) -> dict[str, Any]:
    release = registry.load_preferred_release(season)
    expected_release = getattr(args, 'expect_release_id', None)
    if expected_release is not None and release.release_id != expected_release:
        raise CaptureError(f'{season}: expected release {expected_release}, found {release.release_id}; no game launched')
    if args.execute and args.attest and release.attestation_path is not None:
        playable = registry.validate_preferred_release(season, level="playable")
        attestation_issues = registry._validate_runtime_attestation(release)
        manifest_unchanged = bool(
            release.release_manifest_path is not None
            and release.manifest_sha256 is not None
            and registry.sha256_file(release.release_manifest_path) == release.manifest_sha256
        )
        if playable["valid"] and not attestation_issues and manifest_unchanged:
            return {"season": season, "technical_status": "technically-verified", "status": "reused"}
    tag = args.run_tag or (
        f"registered_{season.replace('-', '_')}_stoke_lineup_"
        + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    )
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", tag):
        raise CaptureError("run tag must use lowercase letters, digits, dot, underscore or hyphen")
    command, evidence = capture_command(season=season, worker=args.worker, run_tag=tag,
                                        compact_evidence=getattr(args, 'compact_evidence', False))
    if not args.execute:
        return {"season": season, "run_tag": tag, "argv": command, "evidence": str(evidence)}
    # Runtime qualification must not mutate or archive unrelated historic
    # runner workspaces. Host archival is a separate maintenance operation.
    environment = os.environ.copy()
    environment["PM99_RUNNER_ARCHIVE_COLD_RUNS"] = "0"
    environment["PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE"] = "0"
    completed = subprocess.run(command, cwd=ROOT, env=environment)
    if completed.returncode:
        raise CaptureError(f"runner exited with status {completed.returncode} for {season}")
    return attester.attest(season=season, evidence_dir=evidence) if args.attest else {
        "season": season, "evidence": registry.relative_workspace_path(evidence), "attested": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("--worker", default="tiny-m73")
    parser.add_argument('--expect-release-id', help='refuse to capture or reuse another preferred release')
    parser.add_argument("--run-tag")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument('--compact-evidence', action='store_true',
                        help='mirror lineup proof screens locally; preserve full captures on worker')
    parser.add_argument("--attest", action="store_true", help="after execution, verify and attach the evidence")
    args = parser.parse_args(argv)
    if args.attest and not args.execute:
        parser.error("--attest requires --execute")
    if args.season == "all" and args.run_tag:
        parser.error("--run-tag can only be used with one season")
    seasons = registry.supported_seasons() if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    results = []
    failures = []
    for season in seasons:
        try:
            result = capture_one(season=season, args=args)
        except (OSError, pipeline.PipelineError, registry.RegistryError, attester.RuntimeAttestationError, CaptureError) as exc:
            if args.season != "all":
                print(f"registered runtime capture error: {exc}", file=sys.stderr)
                return 2
            result = {"season": season, "status": "failed", "error": str(exc)}
            failures.append(result)
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    print(json.dumps({"season_count": len(results), "results": results}, indent=2, sort_keys=True))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
