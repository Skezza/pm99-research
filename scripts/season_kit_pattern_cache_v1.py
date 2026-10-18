#!/usr/bin/env python3
"""Cache exact declared Commons kit layers for source-ready catalogues."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_kit_render_bindings_v1 as renderer


def requested_layers(document: dict) -> set[tuple[str, str]]:
    requested = set()
    for row in document.get("rows") or []:
        contract = row.get("render_contract") or {}
        if row.get("status") != "source-ready" or contract.get("kind") != "wikipedia-template-fields":
            continue
        fields = contract.get("fields") or {}
        for part, field in (("body", "pattern_b1"), ("left_arm", "pattern_la1"), ("right_arm", "pattern_ra1")):
            stem = str(fields.get(field) or "").strip().lstrip("_")
            if stem:
                requested.add((part, stem))
    return requested


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be between 1 and 4")
    requested = set()
    catalogues = []
    for path in sorted(args.catalogue_root.glob("*/kit-catalogue-v1.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        catalogues.append({"path": str(path), "sha256": renderer.sha256_file(path)})
        requested.update(requested_layers(document))
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(renderer._fetch_exact_layer, part, stem, args.cache_dir): (part, stem) for part, stem in sorted(requested)}
        for future in as_completed(jobs):
            part, stem = jobs[future]
            result = future.result()
            row = {"part": part, "stem": stem, "status": result.get("status"), "reason": result.get("reason")}
            if result.get("status") == "ready":
                layer = result["layer"]
                row.update({"url": layer["url"], "sha256": layer["sha256"]})
            rows.append(row)
    rows.sort(key=lambda row: (row["part"], row["stem"]))
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    receipt = {
        "schema_version": "pm99-season-kit-pattern-cache-receipt-v1",
        "policy": {"source": "exact-declared-Wikimedia-Commons-layer", "workers_maximum": 4, "redistribution": "none-source-cache-local-only"},
        "provenance": {"catalogues": catalogues},
        "coverage": {"requested_unique_layer_count": len(rows), "status_counts": dict(sorted(counts.items()))},
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(renderer.canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
