#!/usr/bin/env python3
"""Run a selected immutable season set through no-overwrite static ingress.

This is a static-only orchestration command.  It never modifies a source
package, previous candidate, or release tree.  Each requested season gets its
own fresh child directory and the batch writes one final canonical matrix of
clean-static passes and explicit blockers.  A pass is not a playable release:
the underlying ingress receipt retains the runtime and historical-content
gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_static_ingress_v1 as static_ingress  # noqa: E402


SCHEMA = "pm99-season-static-ingress-batch-receipt-v1"
SEASON_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}$")


class StaticIngressBatchError(ValueError):
    """The batch request cannot create an isolated static matrix."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise StaticIngressBatchError(f"refusing to replace existing output: {path}")
    payload = package_v2.canonical_json_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def run_batch(
    *, package_root: Path, base_tree: Path, verified_base_path: Path,
    output_root: Path, seasons: Sequence[str],
) -> dict[str, Any]:
    package_root = package_root.resolve()
    base_tree = base_tree.resolve()
    verified_base_path = verified_base_path.resolve()
    output_root = output_root.resolve()
    selected = sorted(set(seasons))
    if not selected or any(SEASON_RE.fullmatch(season) is None for season in selected):
        raise StaticIngressBatchError("seasons must be one or more YYYY-YY identifiers")
    if output_root.exists() or output_root.is_symlink():
        raise StaticIngressBatchError(f"output root must be new: {output_root}")
    if not output_root.parent.is_dir() or output_root.parent.is_symlink():
        raise StaticIngressBatchError(
            f"output root parent must be an existing non-symlink directory: {output_root.parent}"
        )
    package_paths = {
        season: package_root / season / "draft-season-package.json" for season in selected
    }
    missing = [f"{season}: {path}" for season, path in package_paths.items() if not path.is_file()]
    if missing:
        raise StaticIngressBatchError("missing draft packages: " + "; ".join(missing))
    if not base_tree.is_dir() or base_tree.is_symlink():
        raise StaticIngressBatchError(f"base tree must be a non-symlink directory: {base_tree}")
    if not verified_base_path.is_file() or verified_base_path.is_symlink():
        raise StaticIngressBatchError(f"verified base must be a non-symlink file: {verified_base_path}")

    output_root.mkdir()
    rows: list[dict[str, Any]] = []
    for season in selected:
        package_path = package_paths[season]
        child = output_root / season
        try:
            receipt = static_ingress.ingress(
                package_path=package_path,
                base_tree=base_tree,
                verified_base_path=verified_base_path,
                output_dir=child,
            )
        except Exception as exc:  # Every underlying error is sealed in the matrix.
            rows.append({
                "season": season,
                "input_package_sha256": _sha256(package_path),
                "state": "blocked-before-clean-static-ingress",
                "release_eligible": False,
                "output_directory": child.name if child.exists() else None,
                "error": str(exc),
            })
            continue
        rows.append({
            "season": season,
            "input_package_sha256": _sha256(package_path),
            "state": receipt["state"],
            "release_eligible": False,
            "output_directory": child.name,
            "static_ingress_receipt_sha256": _sha256(child / "static-ingress-receipt.json"),
            "clean_static_audit_sha256": _sha256(child / "clean-static-audit.json"),
        })

    pass_count = sum(row["state"] == static_ingress.STATE for row in rows)
    result = {
        "schema_version": SCHEMA,
        "state": "static-ingress-batch-complete-not-playable",
        "release_eligible": False,
        "inputs": {
            "package_root": str(package_root),
            "base_tree": str(base_tree),
            "verified_base_path": str(verified_base_path),
            "verified_base_sha256": _sha256(verified_base_path),
        },
        "summary": {
            "requested_season_count": len(selected),
            "clean_static_pass_count": pass_count,
            "blocked_count": len(rows) - pass_count,
        },
        "seasons": rows,
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
    _write_new(output_root / "static-ingress-batch-receipt.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--season", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_batch(
            package_root=args.package_root,
            base_tree=args.base_tree,
            verified_base_path=args.verified_base,
            output_root=args.output_root,
            seasons=args.season,
        )
    except (StaticIngressBatchError, OSError, ValueError) as exc:
        print(f"static ingress batch error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if result["summary"]["blocked_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
