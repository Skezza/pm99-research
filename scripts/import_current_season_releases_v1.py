#!/usr/bin/env python3
"""Inventory the 26 current playable games without changing their bytes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
LEGACY_REVISIONS = {
    "2000-01": "r1", "2001-02": "r2", "2002-03": "r5", "2003-04": "r3",
    "2004-05": "r3", "2005-06": "r3", "2006-07": "r3", "2007-08": "r1",
    "2008-09": "r1", "2009-10": "r2", "2010-11": "r3", "2011-12": "r1",
    "2012-13": "r1", "2013-14": "r1", "2014-15": "r2", "2016-17": "r2",
    "2017-18": "r1", "2018-19": "r3", "2019-20": "r3", "2020-21": "r2",
    "2021-22": "r3", "2022-23": "r2", "2023-24": "r3", "2024-25": "r3",
    "2025-26": "r3",
}
RUNTIME_EVIDENCE_TAGS = {
    "2001-02": "post1999_2001_02_stoke_lineup_20260907_r3",
}
EVIDENCE_SUFFIX = {"2004-05": "r2", "2014-15": "r2"}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object: {path}")
    return value


def _runtime_evidence(season: str) -> Path | None:
    tag = RUNTIME_EVIDENCE_TAGS.get(season)
    if tag is None:
        key = season.replace("-", "_")
        tag = f"post1999_{key}_stoke_lineup_20260907_{EVIDENCE_SUFFIX.get(season, 'final1')}"
    path = ROOT / "upstream/pm99-runner/docs/artifacts/pm99_runner" / tag
    return path if path.is_dir() else None


def _paths(season: str) -> tuple[Path, Path, Path | None, Path | None, str | None]:
    if season == "2015-16":
        # Pipeline V2 correctly rejects symlink roots.  Bind the locator to the
        # immutable target rather than the convenience release symlink.
        game = (ROOT / ".local/releases/pm99-2015-16-world").resolve()
        package = ROOT / ".local/season-workspace-v1/2015-16-final-build/season-package.effective.json"
        compiler = ROOT / ".local/season-workspace-v1/2015-16-final-build/database-compiler-receipt.json"
        return game, package, compiler if compiler.is_file() else None, None, None
    revision = LEGACY_REVISIONS[season]
    game = ROOT / ".local/season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game"
    ingress = ROOT / ".local/season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    compiler = ingress / "compiler-receipt.json"
    static = ingress / "static-ingress-receipt.json"
    candidates = [
        ROOT / ".local/season-worldwide-merged-v1" / season / revision / "strict-season-package.json",
        ingress / "season-package.reconciled.json",
        ingress / "season-package.source-writable.json",
        ingress / "season-package.alias-bound.json",
    ]
    package = next(path for path in candidates if path.is_file())
    if compiler.is_file():
        expected = _read(compiler).get("season_package_sha256")
        for candidate in candidates:
            if candidate.is_file() and registry.canonical_document_sha256(candidate) == expected:
                package = candidate
                break
    return game, package, compiler if compiler.is_file() else None, static if static.is_file() else None, revision


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(pipeline.canonical_json_bytes(value) + b"\n")
    temporary.replace(path)


def import_release(season: str, release_id: str, *, refresh: bool = False) -> dict[str, Any]:
    existing_path = registry.locator_path(season, release_id)
    if not refresh and existing_path.is_file():
        existing = _read(existing_path)
        inventory_path = ROOT / str(existing.get("inventory_path") or "")
        if (
            existing.get("schema_version") == registry.LOCATOR_SCHEMA
            and existing.get("season") == season
            and existing.get("release_id") == release_id
            and inventory_path.is_file()
        ):
            issues = existing.get("import_issues") or []
            return {
                "season": season,
                "release_id": release_id,
                "technical_status": existing.get("technical_status"),
                "issue_count": len(issues),
                "issues": issues,
                "game_inventory_fingerprint": existing.get("game_inventory_fingerprint"),
                "reused": True,
            }
    game, package, compiler, static, revision = _paths(season)
    release_dir = registry.locator_path(season, release_id).parent
    inventory_path = release_dir / "imported-game.inventory.json"
    inventory = pipeline.build_tree_inventory(game)
    _write_json(inventory_path, inventory)
    required_hashes = {
        relative: registry.sha256_file(game / relative)
        for relative in registry.REQUIRED_GAME_FILES
        if (game / relative).is_file()
    }
    issues: list[dict[str, Any]] = []
    missing = [relative for relative in registry.REQUIRED_GAME_FILES if not (game / relative).is_file()]
    for relative in missing:
        issues.append({"code": "required-file-missing", "detail": relative})
    package_hash = registry.canonical_document_sha256(package)
    if compiler is None:
        issues.append({"code": "compiler-receipt-missing", "detail": "compiler receipt unavailable"})
    else:
        receipt = _read(compiler)
        if receipt.get("season_package_sha256") != package_hash:
            issues.append({
                "code": "compiler-package-mismatch",
                "detail": "no retained package matches the compiler receipt",
                "compiler_sha256": receipt.get("season_package_sha256"),
                "package_sha256": package_hash,
            })
        for row in receipt.get("outputs") or []:
            path = game / str(row.get("path") or "")
            actual = registry.sha256_file(path) if path.is_file() else None
            if actual != row.get("sha256"):
                issues.append({
                    "code": "compiler-output-mismatch",
                    "detail": str(row.get("path") or "unknown output"),
                    "compiler_sha256": row.get("sha256"),
                    "runtime_sha256": actual,
                })
    evidence = _runtime_evidence(season)
    locator = {
        "schema_version": registry.LOCATOR_SCHEMA,
        "season": season,
        "release_id": release_id,
        "game_path": registry.relative_workspace_path(game),
        "package_path": registry.relative_workspace_path(package),
        "package_canonical_sha256": package_hash,
        "compiler_receipt_path": registry.relative_workspace_path(compiler) if compiler else None,
        "static_ingress_receipt_path": registry.relative_workspace_path(static) if static else None,
        "inventory_path": registry.relative_workspace_path(inventory_path),
        "game_inventory_fingerprint": inventory["files_fingerprint"],
        "required_file_hashes": required_hashes,
        "release_manifest_path": None,
        "attestation_path": None,
        "runtime_evidence_path": registry.relative_workspace_path(evidence) if evidence else None,
        "legacy_revision": revision,
        "technical_status": "inconsistent" if issues else "playable-unverified",
        "editorial_warning_count": 0,
        "imported_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "import_issues": issues,
    }
    _write_json(registry.locator_path(season, release_id), locator)
    return {
        "season": season,
        "release_id": release_id,
        "technical_status": locator["technical_status"],
        "issue_count": len(issues),
        "issues": issues,
        "game_inventory_fingerprint": inventory["files_fingerprint"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", nargs="?", default="all")
    parser.add_argument("--refresh", action="store_true", help="rehash releases already imported")
    args = parser.parse_args()
    catalog = registry.load_catalog()
    seasons = list(catalog) if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    results = [
        import_release(season, catalog[season]["release_id"], refresh=args.refresh)
        for season in seasons
    ]
    summary = {
        "schema_version": "pm99-current-season-release-import-v1",
        "season_count": len(results),
        "playable_unverified_count": sum(row["technical_status"] == "playable-unverified" for row in results),
        "inconsistent_count": sum(row["technical_status"] == "inconsistent" for row in results),
        "seasons": results,
    }
    _write_json(registry.LOCAL_ROOT / "import-report.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
