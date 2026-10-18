#!/usr/bin/env python3
"""Attach fresh, inventory-bound runner evidence to one registered season."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


class RuntimeAttestationError(ValueError):
    """Runner evidence does not prove the registered release."""


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeAttestationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeAttestationError(f"{label} must be a JSON object: {path}")
    return value


def _atomic_replace_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = pipeline.canonical_json_bytes(dict(value)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
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


def attest(*, season: str, evidence_dir: Path) -> dict[str, Any]:
    release = registry.load_preferred_release(season)
    if release.release_manifest_path is None or release.manifest_sha256 is None:
        raise RuntimeAttestationError("registered release has no canonical manifest")
    manifest = pipeline.read_json_file(release.release_manifest_path)
    inventory = pipeline.verify_release_output(manifest=manifest, output_tree=release.game_path)
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_relative = registry.relative_workspace_path(evidence_dir)
    except registry.RegistryError as exc:
        raise RuntimeAttestationError(str(exc)) from exc
    summary_path = evidence_dir / "summary.json"
    summary = _read_object(summary_path, label="runner summary")
    expected_manifest = registry.sha256_file(release.release_manifest_path)
    expected_inventory = inventory["files_fingerprint"]
    checks = {
        "runner_success": summary.get("success") is True,
        "lineup_phase_reached": summary.get("phase_reached") == "return_from_line_up",
        "release_manifest_bound": summary.get("release_manifest_sha256") == expected_manifest,
        "output_inventory_bound": summary.get("output_inventory_fingerprint") == expected_inventory,
    }
    line_up_summary = (summary.get("route_summaries") or {}).get("line_up")
    team_identity = line_up_summary.get("team_identity") if isinstance(line_up_summary, Mapping) else None
    checks["requested_club_visibly_matched"] = bool(
        isinstance(team_identity, Mapping)
        and team_identity.get("matched") is True
        and "stoke" in str(team_identity.get("observed_normalized") or "").split()
    )
    screenshots = sorted((evidence_dir / "screens").glob("*line_up_inspect*.png"))
    checks["one_lineup_screenshot"] = len(screenshots) == 1
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeAttestationError(
            "runner evidence failed registered-release checks: " + ", ".join(failed)
        )

    screenshot = screenshots[0]
    receipt = {
        "runner_summary": registry.relative_workspace_path(summary_path),
        "runner_summary_sha256": registry.sha256_file(summary_path),
        "release_manifest_file_sha256": expected_manifest,
        "output_inventory_fingerprint": expected_inventory,
        "phase_reached": "return_from_line_up",
        "success": True,
        "team_identity": dict(team_identity),
        "lineup_screenshot": registry.relative_workspace_path(screenshot),
        "lineup_screenshot_sha256": registry.sha256_file(screenshot),
    }
    attestation = pipeline.create_attestation(
        release_manifest=manifest,
        output_tree=release.game_path,
        run_id=f"season-{release.season.replace('-', '.')}-registered-runtime",
        note="Fresh route capture bound to the exact preferred release inventory.",
        runtime_receipts=[receipt],
    )
    attestation_path = release.release_manifest_path.parent / "attestation.json"
    if attestation_path.exists():
        existing = _read_object(attestation_path, label="existing runtime attestation")
        if (
            existing.get("release_manifest_sha256") != attestation["release_manifest_sha256"]
            or existing.get("output_inventory_fingerprint") != expected_inventory
            or existing.get("runtime_receipts") != [receipt]
        ):
            raise RuntimeAttestationError(
                f"a different immutable attestation already exists: {attestation_path}"
            )
    else:
        pipeline.write_canonical_json(attestation_path, attestation)

    locator_path = registry.locator_path(release.season, release.release_id)
    locator = _read_object(locator_path, label="local release locator")
    locator.update({
        "attestation_path": registry.relative_workspace_path(attestation_path),
        "runtime_evidence_path": evidence_relative,
        "technical_status": "technically-verified",
    })
    _atomic_replace_json(locator_path, locator)
    refreshed = registry.load_preferred_release(release.season)
    playable = registry.validate_preferred_release(release.season, level="playable")
    attestation_issues = registry._validate_runtime_attestation(refreshed)
    if not playable["valid"] or attestation_issues:
        raise RuntimeAttestationError(
            "attestation was written but its immediate validation failed: "
            + ", ".join(
                [row["detail"] for row in playable["issues"]]
                + [row["detail"] for row in attestation_issues]
            )
        )
    return {
        "season": release.season,
        "release_id": release.release_id,
        "technical_status": "technically-verified",
        "evidence": evidence_relative,
        "lineup_screenshot": receipt["lineup_screenshot"],
        "output_inventory_fingerprint": expected_inventory,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = attest(season=args.season, evidence_dir=args.evidence_dir)
    except (OSError, pipeline.PipelineError, registry.RegistryError, RuntimeAttestationError) as exc:
        print(f"runtime attestation error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
