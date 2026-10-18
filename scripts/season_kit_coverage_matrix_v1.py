#!/usr/bin/env python3
"""Build a hash-bound coverage matrix for season kit capture and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "pm99-season-kit-coverage-matrix-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_matrix(source_root: Path, render_root: Path, historical_root: Path | None = None) -> dict[str, Any]:
    labels = {path.parent.name for path in source_root.glob("*/kit-catalogue-v1.json")} | {path.parent.name for path in render_root.glob("*/kit-render-receipt-v1.json")}
    if historical_root is not None:
        labels |= {path.parent.name for path in historical_root.glob("*/current.json")}
    labels = sorted(labels)
    rows = []
    for label in labels:
        catalogue_path = source_root / label / "kit-catalogue-v1.json"
        capture_path = source_root / label / "kit-source-capture-v1.json"
        binding_path = render_root / label / "kit-render-bindings-v1.json"
        receipt_path = render_root / label / "kit-render-receipt-v1.json"
        row: dict[str, Any] = {"season": label}
        if catalogue_path.is_file() and capture_path.is_file():
            catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            row["capture"] = capture["coverage"]
            row["catalogue"] = catalogue["coverage"]
            row["catalogue_sha256"] = digest(catalogue_path)
            row["capture_sha256"] = digest(capture_path)
            if historical_root is not None:
                current_path = historical_root / label / "current.json"
                if not current_path.is_file():
                    row["immutable_input_status"] = "missing-current-pointer"
                else:
                    current_bytes = current_path.read_bytes()
                    current = json.loads(current_bytes)
                    expected = ((current.get("artifacts") or {}).get("allocation") or {}).get("sha256")
                    provenance = capture.get("provenance") or {}
                    matched = (
                        current.get("schema_version") == "pm99-historical-squad-backfill-current-v1"
                        and provenance.get("historical_revision_id") == current.get("revision_id")
                        and provenance.get("historical_current_sha256") == hashlib.sha256(current_bytes).hexdigest()
                        and provenance.get("historical_allocation_file_sha256") == expected
                    )
                    row["immutable_input_status"] = "current-pointer-hash-verified" if matched else "stale-or-unverified-current-pointer"
        else:
            row["capture_status"] = "missing"
        if binding_path.is_file() and receipt_path.is_file():
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if catalogue_path.is_file() and binding.get("kit_catalogue_sha256") != hashlib.sha256(canonical_json_bytes(json.loads(catalogue_path.read_text(encoding="utf-8")))).hexdigest():
                raise ValueError(f"{label}: render binding targets a stale catalogue")
            row["render"] = receipt["coverage"]
            row["binding_sha256"] = digest(binding_path)
            row["render_receipt_sha256"] = digest(receipt_path)
            row["integrator_ready_binding_count"] = len(binding.get("clubs") or [])
        else:
            row["render_status"] = "missing"
        rows.append(row)
    return {"schema_version": SCHEMA, "coverage": {"season_count": len(rows), "captured_season_count": sum("catalogue" in row for row in rows), "rendered_season_count": sum("render" in row for row in rows), "immutable_verified_season_count": sum(row.get("immutable_input_status") == "current-pointer-hash-verified" for row in rows), "source_ready_club_count": sum((row.get("catalogue", {}).get("status_counts", {}).get("source-ready", 0)) for row in rows), "bound_club_count": sum((row.get("render", {}).get("bound_club_count", 0)) for row in rows), "artifact_count": sum((row.get("render", {}).get("artifact_count", 0)) for row in rows)}, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--render-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, help="verify capture provenance against immutable current.json")
    args = parser.parse_args()
    matrix = build_matrix(args.source_root, args.render_root, args.historical_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(matrix))
    print(json.dumps(matrix["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
