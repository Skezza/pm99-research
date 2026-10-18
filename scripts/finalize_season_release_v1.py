#!/usr/bin/env python3
"""Create an immutable Pipeline V2 release binding for an existing clean game."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


BUILD_CHAIN_SCHEMA = "pm99-season-build-chain-v1"
DEFAULT_BASE = ROOT / ".local/season-pipeline-v2/pm99-base-clean"
DEFAULT_VERIFIED_BASE = ROOT / ".local/season-pipeline-v2/verified-base.json"


class FinalizeError(ValueError):
    """An existing game cannot be certified as a coherent release."""


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise FinalizeError(f"{label} must be a JSON object: {path}")
    return value


def _package_descriptor(path: Path) -> dict[str, Any]:
    value = _read(path, label="season package")
    encoded = package_v2.canonical_json_bytes(value)
    return {
        "id": "season-package",
        "canonical_sha256": package_v2.sha256_bytes(encoded),
        "canonical_size": len(encoded),
        "schema": value.get("schema_version") or value.get("schema"),
    }


def _receipt_outputs(receipt: Mapping[str, Any], *, label: str) -> dict[str, str]:
    rows = receipt.get("outputs")
    if not isinstance(rows, list) or not rows:
        raise FinalizeError(f"{label} has no output inventory")
    outputs: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FinalizeError(f"{label} contains a malformed output row")
        path, digest = row.get("path"), row.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise FinalizeError(f"{label} contains an invalid output row")
        outputs[path] = digest
    return outputs


def _assert_hashes(game: Path, outputs: Mapping[str, str], *, label: str) -> None:
    for relative, expected in outputs.items():
        path = game / relative
        actual = registry.sha256_file(path) if path.is_file() else None
        if actual != expected:
            raise FinalizeError(
                f"{label} does not match game {relative}: expected {expected}, found {actual}"
            )


def _kit_outputs(receipt: Mapping[str, Any]) -> dict[str, str]:
    archives = receipt.get("archives")
    if not isinstance(archives, Mapping):
        target = receipt.get("target")
        archives = target.get("archive_sha256_after") if isinstance(target, Mapping) else None
        if isinstance(archives, Mapping):
            outputs = {
                f"DBDAT/{name}": str(digest)
                for name, digest in archives.items()
                if name in {"MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"}
                and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
            }
            if len(outputs) != 3:
                raise FinalizeError("kit receipt does not bind all three compact archives")
            return outputs
    if not isinstance(archives, Mapping):
        raise FinalizeError("kit receipt has no archive map")
    outputs: dict[str, str] = {}
    for name in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        row = archives.get(name)
        digest = row.get("sha256_after") if isinstance(row, Mapping) else None
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise FinalizeError(f"kit receipt lacks final hash for {name}")
        outputs[f"DBDAT/{name}"] = digest
    return outputs


def _apply_transform_receipts(
    outputs: Mapping[str, str], receipt_paths: Sequence[Path],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    current = dict(outputs)
    chain_rows: list[dict[str, Any]] = []
    key_to_path = {
        "jug": "DBDAT/JUG98030.FDI",
        "eq": "DBDAT/EQ98030.FDI",
        "ent": "DBDAT/ENT98030.FDI",
    }
    for index, path in enumerate(receipt_paths, 1):
        receipt = _read(path, label=f"declared transform {index}")
        contract = receipt.get("byte_contract")
        if not isinstance(contract, Mapping):
            raise FinalizeError(f"declared transform has no byte_contract: {path}")
        before: dict[str, str] = {}
        after: dict[str, str] = {}
        for key, relative in key_to_path.items():
            before_value = contract.get(f"{key}_before_sha256")
            after_value = contract.get(f"{key}_after_sha256")
            unchanged = contract.get(f"{key}_unchanged_sha256")
            if unchanged is not None:
                if unchanged != current.get(relative):
                    raise FinalizeError(f"transform {path.name} has a broken {key.upper()} unchanged binding")
                before[relative] = str(unchanged)
                after[relative] = str(unchanged)
            elif before_value is not None or after_value is not None:
                if before_value != current.get(relative):
                    raise FinalizeError(f"transform {path.name} has a broken {key.upper()} before binding")
                if not isinstance(after_value, str) or not re.fullmatch(r"[0-9a-f]{64}", after_value):
                    raise FinalizeError(f"transform {path.name} has an invalid {key.upper()} after hash")
                before[relative] = str(before_value)
                after[relative] = after_value
                current[relative] = after_value
        if not after:
            raise FinalizeError(f"declared transform changes no recognised database file: {path}")
        chain_rows.append({
            "id": f"declared-transform-{index:02d}",
            "receipt_sha256": registry.sha256_file(path),
            "before": before,
            "after": after,
        })
    return current, chain_rows


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(path, value)


def finalize(
    *,
    season: str,
    release_id: str,
    game: Path,
    package: Path,
    compiler_receipt: Path,
    static_receipt: Path | None,
    kit_receipt: Path,
    calendar_source: Path,
    runtime_evidence: Path | None = None,
    legacy_revision: str | None = None,
    extra_receipts: Sequence[Path] = (),
    base_tree: Path = DEFAULT_BASE,
    verified_base_path: Path = DEFAULT_VERIFIED_BASE,
    base_already_verified: bool = False,
) -> dict[str, Any]:
    season = pipeline.normalise_season_id(season)
    game, package = game.resolve(), package.resolve()
    if game.is_symlink() or not game.is_dir():
        raise FinalizeError("game must be a real, non-symlink directory")
    for relative in registry.REQUIRED_GAME_FILES:
        if not (game / relative).is_file():
            raise FinalizeError(f"game is missing {relative}")

    verified_base = pipeline.read_json_file(verified_base_path)
    pipeline.validate_verified_base_descriptor(verified_base)
    if not base_already_verified:
        pipeline.verify_base_tree(tree=base_tree, verified_base=verified_base)

    package_descriptor = _package_descriptor(package)
    compiler = _read(compiler_receipt, label="compiler receipt")
    if compiler.get("season_package_sha256") != package_descriptor["canonical_sha256"]:
        raise FinalizeError("compiler receipt is not bound to the supplied canonical package")
    database_outputs = _receipt_outputs(compiler, label="compiler receipt")
    final_database_outputs, transform_rows = _apply_transform_receipts(
        database_outputs, extra_receipts,
    )
    _assert_hashes(game, final_database_outputs, label="compiler and declared transforms")

    calendar_hash = registry.sha256_file(calendar_source)
    actual_calendar_hash = registry.sha256_file(game / "MANAGPRE.EXE")
    if calendar_hash != actual_calendar_hash:
        raise FinalizeError("game executable does not match the declared season calendar")
    kit = _read(kit_receipt, label="kit receipt")
    kit_outputs = _kit_outputs(kit)
    _assert_hashes(game, kit_outputs, label="kit receipt")

    release_dir = registry.locator_path(season, release_id).parent
    if release_dir.exists():
        raise FinalizeError(f"release ID already exists and will not be overwritten: {release_dir}")
    release_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=f".{release_id}.partial-", dir=release_dir.parent))
    metadata_dir = work_dir / "metadata"

    receipt_paths = [compiler_receipt, kit_receipt, *extra_receipts]
    if static_receipt is not None:
        receipt_paths.append(static_receipt)
    artifacts = [
        pipeline.external_artifact_descriptor(
            artifact_id=f"receipt-{index:02d}", path=path, role="input"
        )
        for index, path in enumerate(receipt_paths, 1)
    ]
    base_fingerprint = verified_base["inventory"]["files_fingerprint"]
    stages = [
        pipeline.make_stage_record(
            stage_id="database",
            implementation_path=ROOT / "scripts/season_package_compiler_v2.py",
            input_fingerprints={
                "base-tree": base_fingerprint,
                "season-package": package_descriptor["canonical_sha256"],
            },
            parameters={"compiler-receipt-sha256": registry.sha256_file(compiler_receipt)},
            external_artifacts=[artifacts[0]],
        ),
        pipeline.make_stage_record(
            stage_id="kits",
            implementation_path=ROOT / "scripts/materialise_season_kit_archives_v1.py",
            input_fingerprints={
                "database": pipeline.canonical_json_sha256(final_database_outputs),
                "kit-receipt": registry.sha256_file(kit_receipt),
            },
            parameters={"outputs": kit_outputs},
        ),
        pipeline.make_stage_record(
            stage_id="calendar",
            implementation_path=ROOT / "scripts/materialise_season_calendar_v1.py",
            input_fingerprints={
                "database-and-kits": pipeline.canonical_json_sha256({**final_database_outputs, **kit_outputs}),
                "calendar-executable": calendar_hash,
            },
            parameters={"season": season},
        ),
    ]
    chain = {
        "schema_version": BUILD_CHAIN_SCHEMA,
        "season": season,
        "package_canonical_sha256": package_descriptor["canonical_sha256"],
        "stages": [
            {"id": "database", "receipt_sha256": registry.sha256_file(compiler_receipt), "outputs": database_outputs},
            *transform_rows,
            {"id": "kits", "receipt_sha256": registry.sha256_file(kit_receipt), "outputs": kit_outputs},
            {"id": "calendar", "source_sha256": calendar_hash, "outputs": {"MANAGPRE.EXE": actual_calendar_hash}},
        ],
    }
    chain_path = work_dir / "build-chain.json"
    _write(chain_path, chain)
    artifacts.append(pipeline.external_artifact_descriptor(
        artifact_id="build-chain", path=chain_path, role="input"
    ))

    output_inventory = pipeline.build_tree_inventory(game)
    manifest = pipeline.create_release_manifest(
        season=season,
        verified_base=verified_base,
        season_document=package_descriptor,
        output_inventory=output_inventory,
        external_artifacts=artifacts,
        stages=stages,
    )
    metadata_dir.mkdir()
    base_inventory_path = metadata_dir / "base.inventory.json"
    output_inventory_path = metadata_dir / "output.inventory.json"
    manifest_path = metadata_dir / "season-manifest.json"
    _write(base_inventory_path, verified_base["inventory"])
    _write(output_inventory_path, output_inventory)
    _write(manifest_path, manifest)

    attestation_path: Path | None = None
    if runtime_evidence is not None:
        summary_path = runtime_evidence / "summary.json"
        summary = _read(summary_path, label="runtime evidence summary")
        bound = summary.get("output_inventory_fingerprint")
        if summary.get("success") is True and bound == output_inventory["files_fingerprint"]:
            attestation = pipeline.create_attestation(
                release_manifest=manifest,
                output_tree=game,
                run_id=f"season-{season.replace('-', '.')}-registered-runtime",
                runtime_receipts=[{
                    "summary_sha256": registry.sha256_file(summary_path),
                    "success": True,
                    "output_inventory_fingerprint": bound,
                }],
            )
            attestation_path = metadata_dir / "attestation.json"
            _write(attestation_path, attestation)

    locator = {
        "schema_version": registry.LOCATOR_SCHEMA,
        "season": season,
        "release_id": release_id,
        "game_path": registry.relative_workspace_path(game),
        "package_path": registry.relative_workspace_path(package),
        "package_canonical_sha256": package_descriptor["canonical_sha256"],
        "compiler_receipt_path": registry.relative_workspace_path(compiler_receipt),
        "static_ingress_receipt_path": registry.relative_workspace_path(static_receipt) if static_receipt else None,
        "inventory_path": registry.relative_workspace_path(release_dir / "metadata/output.inventory.json"),
        "game_inventory_fingerprint": output_inventory["files_fingerprint"],
        "required_file_hashes": {
            relative: registry.sha256_file(game / relative)
            for relative in registry.REQUIRED_GAME_FILES
        },
        "release_manifest_path": registry.relative_workspace_path(release_dir / "metadata/season-manifest.json"),
        "attestation_path": registry.relative_workspace_path(release_dir / "metadata/attestation.json") if attestation_path else None,
        "runtime_evidence_path": registry.relative_workspace_path(runtime_evidence) if runtime_evidence else None,
        "legacy_revision": legacy_revision,
        "technical_status": "technically-verified" if attestation_path else "playable-unverified",
        "qa_status": "not-recorded",
        "editorial_status": "not-reviewed",
        "editorial_warning_count": None,
        "import_issues": [],
        "build_chain_path": registry.relative_workspace_path(release_dir / "build-chain.json"),
    }
    locator_file = work_dir / "locator.json"
    _write(locator_file, locator)
    try:
        work_dir.rename(release_dir)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return {
        "season": season,
        "release_id": release_id,
        "release_manifest_sha256": registry.sha256_file(release_dir / "metadata/season-manifest.json"),
        "technical_status": locator["technical_status"],
        "output_inventory_fingerprint": output_inventory["files_fingerprint"],
        "locator": registry.relative_workspace_path(release_dir / "locator.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--compiler-receipt", type=Path, required=True)
    parser.add_argument("--static-receipt", type=Path)
    parser.add_argument("--kit-receipt", type=Path, required=True)
    parser.add_argument("--calendar-source", type=Path, required=True)
    parser.add_argument("--runtime-evidence", type=Path)
    parser.add_argument("--legacy-revision")
    parser.add_argument("--extra-receipt", type=Path, action="append", default=[])
    parser.add_argument("--base-tree", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--verified-base", type=Path, default=DEFAULT_VERIFIED_BASE)
    args = parser.parse_args()
    result = finalize(
        season=args.season, release_id=args.release_id, game=args.game,
        package=args.package, compiler_receipt=args.compiler_receipt,
        static_receipt=args.static_receipt, kit_receipt=args.kit_receipt,
        calendar_source=args.calendar_source, runtime_evidence=args.runtime_evidence,
        legacy_revision=args.legacy_revision, extra_receipts=args.extra_receipt,
        base_tree=args.base_tree, verified_base_path=args.verified_base,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
