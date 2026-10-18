#!/usr/bin/env python3
"""Apply small source-cited corrections to a materialised manager layer."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    layer_raw, override_raw = args.layer.read_bytes(), args.overrides.read_bytes()
    result, overrides = copy.deepcopy(json.loads(layer_raw)), json.loads(override_raw)
    if result.get("schema_version") != "pm99-season-manager-layer-v1":
        parser.error("unsupported manager layer schema")
    season_value = result.get("season")
    season = season_value.get("label") if isinstance(season_value, dict) else season_value
    if overrides.get("schema_version") != "pm99-english-manager-overrides-v1" or overrides.get("season") != season:
        parser.error("override schema or season mismatch")
    rows = {row["club"]: row for row in result.get("rows") or []}
    applied = []
    for correction in overrides.get("corrections") or []:
        club = str(correction.get("club") or "")
        row = rows.get(club)
        if row is None:
            parser.error(f"manager override club is absent: {club}")
        expected = str(correction.get("expected_incorrect_manager") or "")
        if expected and row.get("manager_name") != expected:
            parser.error(f"manager override stale for {club}: {row.get('manager_name')!r}")
        manager = str(correction.get("manager_name") or "").strip()
        source_url = str(correction.get("source_url") or "").strip()
        if not manager or not source_url:
            parser.error(f"manager override is incomplete: {club}")
        row["manager_name"] = manager
        row["source_url"] = source_url
        row["resolution_method"] = "source-cited-editorial-correction"
        row["source_snapshot_sha256"] = hashlib.sha256(override_raw).hexdigest()
        applied.append({"club": club, "manager_name": manager, "source_url": source_url,
                        "reason": correction.get("reason")})
    audit = {"schema_version": "pm99-english-manager-override-audit-v1", "season": season,
             "input_layer_sha256": hashlib.sha256(layer_raw).hexdigest(),
             "overrides_sha256": hashlib.sha256(override_raw).hexdigest(), "applied": applied}
    for path, value in ((args.output, result), (args.output_audit, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
    print(json.dumps({"applied_correction_count": len(applied)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
