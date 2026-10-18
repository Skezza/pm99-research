#!/usr/bin/env python3
"""Materialise one strict season package through the reusable static ingress.

The command derives a new static candidate only.  It repairs the historical
source-write-policy bug where necessary, binds parser-safe display aliases,
restores only exact mode-1 base-row omissions, compiles a fresh clean-base
copy, and performs the declared-change audit.  Every output is hash-bound and
new; inputs and prior materialisations remain untouched.

This is deliberately not a release command.  Calendar runtime validation,
historical manager/source review, kits, portraits, ratings, opening-XI proof,
PM99 runtime validation and screenshots are separate gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_season_clean_base_v1 as clean_audit  # noqa: E402
from scripts import lift_mode1_source_write_policy_v1 as policy_lift  # noqa: E402
from scripts import reconcile_mode1_roster_base_batch_v1 as mode1_batch  # noqa: E402
from scripts import reconcile_stale_mode1_source_candidates_v1 as stale_candidates  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_display_alias_repair_v1 as aliases  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-static-ingress-receipt-v1"
STATE = "clean-static-ingress-complete-not-playable"


class StaticIngressError(ValueError):
    """A strict input package cannot complete the static-only ingress."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise StaticIngressError(f"refusing to replace existing output: {path}")
    payload = _canonical_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _source_bound_whole_record_preserve_count(package: dict[str, Any]) -> int:
    return sum(
        player.get("policy") == "preserve-existing-mode1"
        and str(player.get("person_id") or "").startswith("person-source-")
        for player in package["players"]
    )


def ingress(
    *, package_path: Path, base_tree: Path, verified_base_path: Path, output_dir: Path
) -> dict[str, Any]:
    package_path = package_path.resolve()
    base_tree = base_tree.resolve()
    verified_base_path = verified_base_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists() or output_dir.is_symlink():
        raise StaticIngressError(f"output directory must be new: {output_dir}")
    if not output_dir.parent.is_dir() or output_dir.parent.is_symlink():
        raise StaticIngressError(f"output parent must be an existing non-symlink directory: {output_dir.parent}")

    source_package = package_v2.read_canonical_package(package_path)
    # Read the package structurally before deciding whether a safe source
    # candidate repair is available.  Strict validation remains mandatory
    # before any alias, roster, compiler, or binary-writing stage.
    package_v2.validate_package(source_package, strict=False)
    input_sha256 = _sha256(package_path)
    stages: list[dict[str, Any]] = []

    current_path = package_path
    try:
        package_v2.validate_package(source_package, strict=True)
    except package_v2.PackageValidationError as strict_error:
        try:
            stale_package, stale_audit = stale_candidates.reconcile_stale_candidates(
                package_path=package_path,
                base_tree=base_tree,
                verified_base_path=verified_base_path,
            )
        except stale_candidates.StaleCandidateReconciliationError as stale_error:
            if str(stale_error) == "no exact one-current/one-stale mode-1 candidate pairs were found":
                raise strict_error
            raise

        output_dir.mkdir()
        current_path = output_dir / "season-package.stale-candidates-reconciled.json"
        stale_audit["output"] = {
            "package_path": str(current_path),
            "package_sha256": _write_new(current_path, stale_package),
        }
        stale_audit_path = output_dir / "stale-source-candidate-reconciliation-audit.json"
        _write_new(stale_audit_path, stale_audit)
        stages.append({
            "name": "stale-source-candidate-reconciliation",
            "audit": stale_audit_path.name,
            "package": current_path.name,
            "repaired_pair_count": stale_audit["reconciliation"]["repaired_pair_count"],
        })
        source_package = stale_package
        try:
            package_v2.validate_package(source_package, strict=True)
        except package_v2.PackageValidationError as remaining_error:
            blocked_receipt_path = output_dir / "static-ingress-preflight-blocked.json"
            _write_new(blocked_receipt_path, {
                "schema_version": "pm99-season-static-ingress-preflight-blocked-v1",
                "state": "blocked-before-static-compilation",
                "release_eligible": False,
                "season": source_package["season"],
                "input": {
                    "package_path": str(package_path),
                    "package_sha256": input_sha256,
                    "verified_base_path": str(verified_base_path),
                    "verified_base_sha256": _sha256(verified_base_path),
                    "base_tree": str(base_tree),
                },
                "completed_source_only_stages": stages,
                "remaining_strict_validation_error": str(remaining_error),
                "not_performed": [
                    "display-alias-repair",
                    "mode1-roster-reconciliation",
                    "binary-compiler-materialisation",
                    "clean-static-audit",
                    "release-manifest-generation",
                    "PM99-runtime-validation",
                    "target-season-screenshot",
                ],
            })
            raise StaticIngressError(
                "strict package remains blocked after safe stale-source reconciliation; "
                f"read {blocked_receipt_path}: {remaining_error}"
            ) from remaining_error
    else:
        output_dir.mkdir()
        stages.append({"name": "stale-source-candidate-reconciliation", "state": "not-needed"})

    if _source_bound_whole_record_preserve_count(source_package):
        lifted, lift_audit = policy_lift.lift_source_write_policy(
            package_path=current_path,
            base_tree=base_tree,
            verified_base_path=verified_base_path,
        )
        current_path = output_dir / "season-package.source-writable.json"
        lift_audit["output"] = {
            "package_path": str(current_path),
            "package_sha256": _write_new(current_path, lifted),
        }
        lift_audit_path = output_dir / "source-write-policy-lift-audit.json"
        _write_new(lift_audit_path, lift_audit)
        stages.append({"name": "source-write-policy-lift", "audit": lift_audit_path.name,
                       "package": current_path.name, "changed_player_count": lift_audit["lift"]["changed_player_count"]})
    else:
        stages.append({"name": "source-write-policy-lift", "state": "not-needed"})

    alias_package, alias_audit = aliases.derive_alias_bound_package(
        package_path=current_path,
        base_tree=base_tree,
        verified_base_path=verified_base_path,
    )
    alias_path = output_dir / "season-package.alias-bound.json"
    alias_audit["output"] = {
        "package_path": str(alias_path),
        "package_sha256": _write_new(alias_path, alias_package),
    }
    alias_audit_path = output_dir / "display-alias-repair-audit.json"
    _write_new(alias_audit_path, alias_audit)
    stages.append({"name": "display-alias-repair", "audit": alias_audit_path.name,
                   "package": alias_path.name, "changed_display_name_count": alias_audit["coverage"]["changed_display_name_count"]})

    try:
        reconciled_package, reconciliation_audit = mode1_batch.reconcile_batch(
            package_path=alias_path,
            base_tree=base_tree,
            verified_base_path=verified_base_path,
            preservation_artifact_id="world-mode1-runtime-contract",
            preservation_source_id="baseline-runtime-contract",
        )
    except mode1_batch.BatchReconciliationError as exc:
        if str(exc) != "no mode-1 clubs were eligible for whole-row base preservation":
            raise
        reconciled_package = alias_package
        reconciliation_audit = {
            "schema_version": mode1_batch.SCHEMA,
            "state": "no-mode1-base-row-reconciliation-needed",
            "season": reconciled_package["season"],
            "release_eligible": False,
            "input": {"package_sha256": _sha256(alias_path)},
            "batch": {"selection_policy": "all-eligible-mode1-whole-row-preserve-only",
                      "eligible_club_count": 0, "eligible_player_row_count": 0},
            "not_performed": ["source acquisition", "binary compiler materialisation", "runtime validation"],
        }
    reconciled_path = output_dir / "season-package.reconciled.json"
    reconciliation_audit["output"] = {
        "package_path": str(reconciled_path),
        "package_sha256": _write_new(reconciled_path, reconciled_package),
    }
    reconciliation_audit_path = output_dir / "mode1-roster-reconciliation-audit.json"
    _write_new(reconciliation_audit_path, reconciliation_audit)
    stages.append({"name": "mode1-roster-reconciliation", "audit": reconciliation_audit_path.name,
                   "package": reconciled_path.name,
                   "eligible_club_count": reconciliation_audit["batch"]["eligible_club_count"]})

    game_tree = output_dir / "game"
    shutil.copytree(base_tree, game_tree, symlinks=False, copy_function=shutil.copyfile)
    compiler_receipt = compiler_v2.compile_package_to_tree(
        package_path=reconciled_path,
        base_tree=base_tree,
        materialisation_tree=game_tree,
    )
    compiler_receipt_path = output_dir / "compiler-receipt.json"
    compiler_v2.write_canonical_receipt(compiler_receipt_path, compiler_receipt)
    stages.append({"name": "compiler", "receipt": compiler_receipt_path.name,
                   "clubs_written": compiler_receipt["clubs_written"],
                   "players_written": compiler_receipt["players_written"]})

    static_audit = clean_audit.audit(
        package_path=reconciled_path,
        base_tree=base_tree,
        output_tree=game_tree,
    )
    static_audit_path = output_dir / "clean-static-audit.json"
    _write_new(static_audit_path, static_audit)
    stages.append({"name": "clean-static-audit", "audit": static_audit_path.name,
                   "result": static_audit["result"]})

    receipt = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": reconciled_package["season"],
        "release_eligible": False,
        "input": {
            "package_path": str(package_path),
            "package_sha256": input_sha256,
            "verified_base_path": str(verified_base_path),
            "verified_base_sha256": _sha256(verified_base_path),
            "base_tree": str(base_tree),
        },
        "outputs": {
            "package_path": reconciled_path.name,
            "package_sha256": _sha256(reconciled_path),
            "game_tree": game_tree.name,
            "compiler_receipt": compiler_receipt_path.name,
            "compiler_receipt_sha256": _sha256(compiler_receipt_path),
            "clean_static_audit": static_audit_path.name,
            "clean_static_audit_sha256": _sha256(static_audit_path),
        },
        "stages": stages,
        "remaining_release_gates": [
            "calendar-runtime-validation",
            "target-season-manager-source-review",
            "target-season-kit-materialisation",
            "portrait/no-photo-materialisation",
            "ratings-reconciliation",
            "opening-xi-and-formation-review",
            "PM99-runtime-validation",
            "target-season-screenshot",
        ],
    }
    receipt_path = output_dir / "static-ingress-receipt.json"
    _write_new(receipt_path, receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = ingress(
            package_path=args.package,
            base_tree=args.base_tree,
            verified_base_path=args.verified_base,
            output_dir=args.output_dir,
        )
    except (
        StaticIngressError,
        policy_lift.SourceWritePolicyLiftError,
        aliases.DisplayAliasRepairError,
        mode1_batch.BatchReconciliationError,
        stale_candidates.StaleCandidateReconciliationError,
        compiler_v2.SeasonCompilerError,
        clean_audit.CleanBaseAuditError,
        package_v2.PackageValidationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"static ingress error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "season": receipt["season"]["label"],
        "state": receipt["state"],
        "package_sha256": receipt["outputs"]["package_sha256"],
        "clean_static_audit": receipt["outputs"]["clean_static_audit"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
