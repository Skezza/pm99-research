#!/usr/bin/env python3
"""Resolve and verify the one preferred local release for each PM99 season."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


CATALOG_PATH = ROOT / "data/preferred-season-releases-v1.json"
LOCAL_ROOT = ROOT / ".local/season-release-registry-v1"
CATALOG_SCHEMA = "pm99-preferred-season-releases-v1"
LOCATOR_SCHEMA = "pm99-local-season-release-locator-v1"
REQUIRED_GAME_FILES = (
    "MANAGPRE.EXE",
    "DBDAT/JUG98030.FDI",
    "DBDAT/EQ98030.FDI",
    "DBDAT/ENT98030.FDI",
    "DBDAT/RIDIESC.PKF",
    "DBDAT/MINIESC.PKF",
    "DBDAT/NANOESC.PKF",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")


class RegistryError(ValueError):
    """The preferred release catalogue or local binding is invalid."""


def _read_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read {label}: {path}") from exc


def _workspace_path(value: str, *, label: str, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{label} must be a workspace-relative path")
    path = (ROOT / value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RegistryError(f"{label} escapes the workspace: {value}") from exc
    if must_exist and not path.exists():
        raise RegistryError(f"{label} does not exist: {value}")
    return path


def relative_workspace_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise RegistryError(f"release path is outside the workspace: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_document_sha256(path: Path) -> str:
    value = _read_json(path, label="season package")
    # Season packages have an established pretty/canonical byte contract that
    # predates Pipeline V2's compact generic JSON documents.  Compiler receipts
    # use this exact encoding, so release binding must use it too.
    return package_v2.sha256_bytes(package_v2.canonical_json_bytes(value))


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, dict[str, Any]]:
    payload = _read_json(path, label="preferred release catalogue")
    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA:
        raise RegistryError(f"preferred release catalogue must use {CATALOG_SCHEMA}")
    rows = payload.get("seasons")
    if not isinstance(rows, list) or not rows:
        raise RegistryError("preferred release catalogue has no seasons")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "season", "release_id", "release_manifest_sha256"
        }:
            raise RegistryError("preferred release row has invalid fields")
        try:
            season = pipeline.normalise_season_id(row["season"])
        except pipeline.PipelineError as exc:
            raise RegistryError(str(exc)) from exc
        release_id = row["release_id"]
        if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
            raise RegistryError(f"invalid release ID for {season}: {release_id!r}")
        manifest_hash = row["release_manifest_sha256"]
        if manifest_hash is not None and (
            not isinstance(manifest_hash, str) or not _SHA256_RE.fullmatch(manifest_hash)
        ):
            raise RegistryError(f"invalid release manifest hash for {season}")
        if season in result:
            raise RegistryError(f"duplicate preferred season: {season}")
        result[season] = dict(row)
    if list(result) != sorted(result):
        raise RegistryError("preferred release rows must be season-sorted")
    return result


def supported_seasons() -> list[str]:
    return list(load_catalog())


def locator_path(season: str, release_id: str) -> Path:
    return LOCAL_ROOT / "releases" / season / release_id / "locator.json"


@dataclass(frozen=True)
class PreferredRelease:
    season: str
    release_id: str
    manifest_sha256: str | None
    game_path: Path
    package_path: Path
    compiler_receipt_path: Path | None
    static_ingress_receipt_path: Path | None
    inventory_path: Path
    release_manifest_path: Path | None
    attestation_path: Path | None
    runtime_evidence_path: Path | None
    build_chain_path: Path | None
    revision: str | None
    locator: Mapping[str, Any]


def _optional_path(locator: Mapping[str, Any], key: str) -> Path | None:
    value = locator.get(key)
    if value is None:
        return None
    return _workspace_path(value, label=key)


def load_preferred_release(season: str) -> PreferredRelease:
    try:
        season = pipeline.normalise_season_id(season)
    except pipeline.PipelineError as exc:
        raise RegistryError(str(exc)) from exc
    catalog = load_catalog()
    preferred = catalog.get(season)
    if preferred is None:
        raise RegistryError(f"season is not registered: {season}")
    return _load_release(season, preferred)


def load_registered_release(season: str, release_id: str) -> PreferredRelease:
    """Read a retained release without changing the preferred catalogue."""
    season = pipeline.normalise_season_id(season)
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        raise RegistryError("invalid retained release ID")
    locator = _read_json(locator_path(season, release_id), label="retained release locator")
    manifest = _optional_path(locator, "release_manifest_path")
    return _load_release(season, {"release_id": release_id,
        "release_manifest_sha256": sha256_file(manifest) if manifest else None})


def _load_release(season: str, preferred: Mapping[str, Any]) -> PreferredRelease:
    path = locator_path(season, preferred["release_id"])
    locator = _read_json(path, label=f"local release locator for {season}")
    if not isinstance(locator, dict) or locator.get("schema_version") != LOCATOR_SCHEMA:
        raise RegistryError(f"local release locator must use {LOCATOR_SCHEMA}: {path}")
    if locator.get("season") != season or locator.get("release_id") != preferred["release_id"]:
        raise RegistryError(f"local locator identity does not match preferred {season} release")
    return PreferredRelease(
        season=season,
        release_id=preferred["release_id"],
        manifest_sha256=preferred["release_manifest_sha256"],
        game_path=_workspace_path(locator.get("game_path"), label="game_path"),
        package_path=_workspace_path(locator.get("package_path"), label="package_path"),
        compiler_receipt_path=_optional_path(locator, "compiler_receipt_path"),
        static_ingress_receipt_path=_optional_path(locator, "static_ingress_receipt_path"),
        inventory_path=_workspace_path(locator.get("inventory_path"), label="inventory_path"),
        release_manifest_path=_optional_path(locator, "release_manifest_path"),
        attestation_path=_optional_path(locator, "attestation_path"),
        runtime_evidence_path=_optional_path(locator, "runtime_evidence_path"),
        build_chain_path=_optional_path(locator, "build_chain_path"),
        revision=locator.get("legacy_revision") if isinstance(locator.get("legacy_revision"), str) else None,
        locator=locator,
    )


def _issue(code: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "detail": detail, **extra}


def _validate_build_chain(
    release: PreferredRelease, compiler_outputs: Mapping[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if release.build_chain_path is None:
        return [_issue("build-chain-missing", "release has no ordered build chain")]
    chain = _read_json(release.build_chain_path, label="release build chain")
    if not isinstance(chain, dict) or chain.get("schema_version") != "pm99-season-build-chain-v1":
        return [_issue("build-chain-invalid", "release build chain has an unsupported schema")]
    if chain.get("season") != release.season:
        issues.append(_issue("build-chain-season-mismatch", "build chain names a different season"))
    if chain.get("package_canonical_sha256") != release.locator.get("package_canonical_sha256"):
        issues.append(_issue("build-chain-package-mismatch", "build chain names a different package"))
    stages = chain.get("stages")
    if not isinstance(stages, list) or not stages or not isinstance(stages[0], dict):
        return [*issues, _issue("build-chain-stages-invalid", "build chain has no ordered stages")]
    database = stages[0]
    if database.get("id") != "database" or database.get("outputs") != dict(compiler_outputs):
        issues.append(_issue("build-chain-compiler-mismatch", "build chain does not begin with compiler outputs"))
    if release.compiler_receipt_path is not None and database.get("receipt_sha256") != sha256_file(release.compiler_receipt_path):
        issues.append(_issue("build-chain-compiler-receipt-mismatch", "build chain compiler receipt changed"))
    current = dict(compiler_outputs)
    for stage in stages[1:]:
        if not isinstance(stage, dict):
            issues.append(_issue("build-chain-stage-invalid", "build chain contains a malformed stage"))
            continue
        stage_id = str(stage.get("id") or "")
        if stage_id.startswith("declared-transform-"):
            before, after = stage.get("before"), stage.get("after")
            if not isinstance(before, dict) or not isinstance(after, dict):
                issues.append(_issue("build-chain-transform-invalid", stage_id))
                continue
            for relative, expected in before.items():
                if current.get(relative) != expected:
                    issues.append(_issue("build-chain-transform-before-mismatch", stage_id, path=relative))
            for relative, digest in after.items():
                if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                    issues.append(_issue("build-chain-transform-after-invalid", stage_id, path=relative))
                else:
                    current[relative] = digest
        outputs = stage.get("outputs")
        if isinstance(outputs, dict):
            current.update({str(path): str(digest) for path, digest in outputs.items()})
        for relative in stage.get("removed", []):
            if not isinstance(relative, str) or not re.fullmatch(r"DBDAT/MINIFOTO/J96\d{5}\.BMP", relative):
                issues.append(_issue("build-chain-removal-invalid", stage_id))
                continue
            if (release.game_path / relative).exists():
                issues.append(_issue("build-chain-removal-not-applied", relative))
            current.pop(relative, None)
    for relative, expected in current.items():
        path = release.game_path / relative
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            issues.append(_issue(
                "build-chain-output-mismatch", relative,
                expected_sha256=expected, actual_sha256=actual,
            ))
    return issues


def _validate_runtime_attestation(release: PreferredRelease) -> list[dict[str, Any]]:
    if release.attestation_path is None:
        return [_issue("runtime-attestation-missing", "release has no inventory-bound runtime attestation")]
    if release.release_manifest_path is None or release.manifest_sha256 is None:
        return [_issue("runtime-attestation-unbound", "attestation exists without a registered release manifest")]
    attestation = _read_json(release.attestation_path, label="runtime attestation")
    if not isinstance(attestation, dict) or attestation.get("schema") != pipeline.ATTESTATION_SCHEMA:
        return [_issue("runtime-attestation-invalid", "attestation has an unsupported schema")]
    manifest = _read_json(release.release_manifest_path, label="release manifest")
    issues: list[dict[str, Any]] = []
    expected_manifest = pipeline.canonical_json_sha256(manifest)
    expected_inventory = release.locator.get("game_inventory_fingerprint")
    if attestation.get("release_manifest_sha256") != expected_manifest:
        issues.append(_issue("runtime-attestation-manifest-mismatch", "attestation names a different release manifest"))
    if attestation.get("output_inventory_fingerprint") != expected_inventory:
        issues.append(_issue("runtime-attestation-inventory-mismatch", "attestation names a different game inventory"))
    receipts = attestation.get("runtime_receipts")
    if not isinstance(receipts, list) or len(receipts) != 1 or not isinstance(receipts[0], dict):
        return [*issues, _issue("runtime-attestation-receipt-invalid", "attestation must contain one runner receipt")]
    receipt = receipts[0]
    if (
        receipt.get("success") is not True
        or receipt.get("phase_reached") != "return_from_line_up"
        or receipt.get("release_manifest_file_sha256") != release.manifest_sha256
        or receipt.get("output_inventory_fingerprint") != expected_inventory
    ):
        issues.append(_issue("runtime-attestation-receipt-unbound", "runner receipt does not prove this exact release at Line-Up"))
    team_identity = receipt.get("team_identity")
    if not (
        isinstance(team_identity, dict)
        and team_identity.get("matched") is True
        and "stoke" in str(team_identity.get("observed_normalized") or "").split()
    ):
        issues.append(_issue(
            "runtime-attestation-club-unproven",
            "runner receipt does not visibly prove the requested Stoke line-up",
        ))
    for path_key, hash_key, label in (
        ("runner_summary", "runner_summary_sha256", "runner summary"),
        ("lineup_screenshot", "lineup_screenshot_sha256", "Line-Up screenshot"),
    ):
        try:
            path = _workspace_path(receipt.get(path_key), label=path_key)
        except RegistryError as exc:
            issues.append(_issue("runtime-attestation-artifact-missing", str(exc), artifact=label))
            continue
        actual = sha256_file(path)
        if actual != receipt.get(hash_key):
            issues.append(_issue("runtime-attestation-artifact-mismatch", f"{label} changed after attestation", path=receipt.get(path_key)))
    return issues


def _validate_registered_qa(release: PreferredRelease) -> list[dict[str, Any]]:
    """Verify an optional QA result against the exact preferred release."""
    qa_status = release.locator.get("qa_status")
    report_value = release.locator.get("qa_report_path")
    report_hash = release.locator.get("qa_report_sha256")
    if qa_status in {None, "not-recorded"} and report_value is None and report_hash is None:
        return []
    if qa_status != "pass" or not isinstance(report_value, str) or not isinstance(report_hash, str):
        return [_issue("qa-registration-invalid", "release has an incomplete QA registration")]
    try:
        report_path = _workspace_path(report_value, label="qa_report_path")
    except RegistryError as exc:
        return [_issue("qa-report-missing", str(exc))]
    if sha256_file(report_path) != report_hash:
        return [_issue("qa-report-hash-mismatch", "registered QA report changed after registration")]
    report = _read_json(report_path, label="registered QA report")
    inputs = report.get("inputs") if isinstance(report.get("inputs"), Mapping) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    expected_warning_count = release.locator.get("editorial_warning_count")
    issues: list[dict[str, Any]] = []
    if (
        report.get("schema_version") != "pm99-season-quality-qa-v1"
        or report.get("season") != release.season
        or report.get("result") != "pass"
    ):
        issues.append(_issue("qa-report-identity-mismatch", "QA report is not a passing result for this season"))
    if inputs.get("game_tree") != relative_workspace_path(release.game_path):
        issues.append(_issue("qa-report-game-mismatch", "QA report names a different game tree"))
    if inputs.get("package_sha256") != sha256_file(release.package_path):
        issues.append(_issue("qa-report-package-mismatch", "QA report names a different season package"))
    if summary.get("warning_count") != expected_warning_count:
        issues.append(_issue("qa-report-warning-count-mismatch", "recorded editorial warning count differs from QA report"))
    return issues


def validate_preferred_release(season: str, *, level: str = "release",
                               release_id: str | None = None) -> dict[str, Any]:
    if level not in {"playable", "release"}:
        raise RegistryError("validation level must be playable or release")
    release = load_registered_release(season, release_id) if release_id else load_preferred_release(season)
    issues: list[dict[str, Any]] = []
    expected_required = release.locator.get("required_file_hashes")
    if not isinstance(expected_required, dict):
        raise RegistryError(f"local locator for {season} has no required file hash map")
    actual_required: dict[str, str] = {}
    for relative in REQUIRED_GAME_FILES:
        path = release.game_path / relative
        expected = expected_required.get(relative)
        if not path.is_file():
            issues.append(_issue("required-file-missing", relative))
            continue
        actual = sha256_file(path)
        actual_required[relative] = actual
        if not isinstance(expected, str) or actual != expected:
            issues.append(_issue(
                "required-file-hash-mismatch", relative,
                expected_sha256=expected, actual_sha256=actual,
            ))

    visual_hashes = release.locator.get('required_visual_file_hashes', {})
    visual_absent = release.locator.get('required_visual_absent_paths', [])
    if not isinstance(visual_hashes, dict) or not isinstance(visual_absent, list):
        issues.append(_issue('visual-contract-invalid', 'visual file contract is malformed'))
    else:
        visual_pattern = re.compile(r'^DBDAT/(?:(?:MINIFOTO|MINIESC|NANOESC|RIDIESC)\.PKF|MINIFOTO/J96\d{5}\.BMP)$')
        for relative, expected in visual_hashes.items():
            if not isinstance(relative, str) or not visual_pattern.fullmatch(relative):
                issues.append(_issue('visual-contract-path-invalid', str(relative)))
                continue
            path = release.game_path / relative
            if not path.is_file() or sha256_file(path) != expected:
                issues.append(_issue('visual-file-hash-mismatch', relative))
        for relative in visual_absent:
            if not isinstance(relative, str) or not re.fullmatch(r'DBDAT/MINIFOTO/J96\d{5}\.BMP', relative):
                issues.append(_issue('visual-contract-path-invalid', str(relative)))
            elif (release.game_path / relative).exists():
                issues.append(_issue('visual-no-photo-override-reappeared', relative))

    if level == "release":
        inventory = pipeline.read_json_file(release.inventory_path)
        actual_inventory: Mapping[str, Any] | None = None
        try:
            actual_inventory = pipeline.assert_tree_matches_inventory(release.game_path, inventory)
        except pipeline.PipelineError as exc:
            issues.append(_issue("game-inventory-mismatch", str(exc)))
        package_hash = canonical_document_sha256(release.package_path)
        if package_hash != release.locator.get("package_canonical_sha256"):
            issues.append(_issue(
                "package-hash-mismatch", "season package differs from local release binding",
                expected_sha256=release.locator.get("package_canonical_sha256"),
                actual_sha256=package_hash,
            ))
        if release.compiler_receipt_path is None:
            issues.append(_issue("compiler-receipt-missing", "release has no compiler receipt"))
        else:
            receipt = _read_json(release.compiler_receipt_path, label="compiler receipt")
            expected_package = receipt.get("season_package_sha256")
            if expected_package != package_hash:
                issues.append(_issue(
                    "compiler-package-mismatch",
                    "compiler receipt is not bound to the registered package",
                    compiler_sha256=expected_package, package_sha256=package_hash,
                ))
            outputs = receipt.get("outputs")
            if not isinstance(outputs, list):
                issues.append(_issue("compiler-output-inventory-missing", "compiler receipt has no outputs"))
            else:
                compiler_outputs: dict[str, str] = {}
                for row in outputs:
                    if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                        issues.append(_issue("compiler-output-row-invalid", "compiler output row is malformed"))
                        continue
                    compiler_outputs[row["path"]] = str(row.get("sha256") or "")
                issues.extend(_validate_build_chain(release, compiler_outputs))
        if release.manifest_sha256 is None or release.release_manifest_path is None:
            issues.append(_issue(
                "canonical-release-manifest-unregistered",
                "preferred catalogue does not yet bind a canonical release manifest",
            ))
        else:
            manifest_hash = sha256_file(release.release_manifest_path)
            if manifest_hash != release.manifest_sha256:
                issues.append(_issue(
                    "release-manifest-hash-mismatch", "registered release manifest changed",
                    expected_sha256=release.manifest_sha256, actual_sha256=manifest_hash,
                ))
            else:
                try:
                    manifest = pipeline.validate_release_manifest(
                        pipeline.read_json_file(release.release_manifest_path)
                    )
                    expected_output = manifest["output"]
                    if actual_inventory is None or (
                        actual_inventory["files_fingerprint"] != expected_output["inventory_fingerprint"]
                        or actual_inventory["file_count"] != expected_output["file_count"]
                        or actual_inventory["total_bytes"] != expected_output["total_bytes"]
                    ):
                        raise pipeline.PipelineError(
                            "output inventory does not match the release manifest"
                        )
                except pipeline.PipelineError as exc:
                    issues.append(_issue("release-manifest-output-mismatch", str(exc)))
        issues.extend(_validate_runtime_attestation(release))
        issues.extend(_validate_registered_qa(release))

    return {
        "season": release.season,
        "release_id": release.release_id,
        "game": relative_workspace_path(release.game_path),
        "package": relative_workspace_path(release.package_path),
        "level": level,
        "valid": not issues,
        "technical_status": release.locator.get("technical_status"),
        "editorial_warning_count": (
            release.locator.get("editorial_warning_count")
            if release.locator.get("qa_status") == "pass"
            else None
        ),
        "issues": issues,
        "missing": [row["detail"] for row in issues],
        "sha256": actual_required,
    }
