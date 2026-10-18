#!/usr/bin/env python3
"""Finalize the 25 post-1999 registered releases that use the batch pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import finalize_season_release_v1 as finalizer  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts.import_current_season_releases_v1 import LEGACY_REVISIONS  # noqa: E402


EVIDENCE_SUFFIX = {
    "2000-01": "r2", "2001-02": "r3", "2002-03": "r3",
    "2004-05": "coordfix1", "2007-08": "retry2", "2013-14": "retry2",
}


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _runtime_evidence(season: str) -> Path | None:
    if season == "2004-05":
        tag = "post1999_2004_05_calendar-dayfix-817_20260909"
    else:
        tag = f"post1999_{season.replace('-', '_')}_stoke_lineup_20260907_{EVIDENCE_SUFFIX.get(season, 'final1')}"
    path = ROOT / "upstream/pm99-runner/docs/artifacts/pm99_runner" / tag
    return path if path.is_dir() else None


def _compiler_root(season: str) -> Path:
    if season == "2017-18":
        return ROOT / ".local/season-static-ingress-v1/2017-18-worldwide-source-backed-qa2"
    return ROOT / ".local/season-quality-ingress-v1" / season / "qa1"


def _package_for_receipt(root: Path, receipt: dict[str, object]) -> Path:
    expected = receipt.get("season_package_sha256")
    candidates = [
        root / "season-package.reconciled.json",
        root / "season-package.alias-bound.json",
        root / "season-package.source-writable.json",
    ]
    matches = [
        path for path in candidates
        if path.is_file() and registry.canonical_document_sha256(path) == expected
    ]
    if not matches:
        raise ValueError(f"no retained package matches compiler receipt in {root}")
    return matches[0]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(pipeline.canonical_json_bytes(value) + b"\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", nargs="?", default="all")
    parser.add_argument("--release-label", default="quality-bound-20260913-r1")
    args = parser.parse_args()
    seasons = sorted(LEGACY_REVISIONS) if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    if "2015-16" in seasons:
        seasons.remove("2015-16")

    verified = pipeline.read_json_file(finalizer.DEFAULT_VERIFIED_BASE)
    pipeline.verify_base_tree(tree=finalizer.DEFAULT_BASE, verified_base=verified)
    results = []
    for season in seasons:
        revision = LEGACY_REVISIONS[season]
        root = _compiler_root(season)
        compiler_path = root / "compiler-receipt.json"
        compiler = _read(compiler_path)
        package = _package_for_receipt(root, compiler)
        game = ROOT / ".local/season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game"
        kit = ROOT / ".local/season-kit-runtime-overlays-v1" / season / "v5/receipt.json"
        calendar = ROOT / ".local/calendar-v1" / season / "MANAGPRE.EXE"
        static = root / "static-ingress-receipt.json"
        result = finalizer.finalize(
            season=season, release_id=args.release_label, game=game,
            package=package, compiler_receipt=compiler_path,
            static_receipt=static if static.is_file() else None,
            kit_receipt=kit, calendar_source=calendar,
            runtime_evidence=_runtime_evidence(season), legacy_revision=revision,
            base_already_verified=True,
        )
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)

    catalog = registry.load_catalog()
    for result in results:
        catalog[result["season"]] = {
            "season": result["season"],
            "release_id": result["release_id"],
            "release_manifest_sha256": result["release_manifest_sha256"],
        }
    proposal = {
        "schema_version": registry.CATALOG_SCHEMA,
        "seasons": [catalog[season] for season in sorted(catalog)],
    }
    output = registry.LOCAL_ROOT / "preferred-catalog-proposal.json"
    _write(output, proposal)
    print(json.dumps({"finalized_count": len(results), "catalog_proposal": registry.relative_workspace_path(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
