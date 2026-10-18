#!/usr/bin/env python3
"""Build deterministic, prioritised historical kit evidence gap queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_kit_catalogue_v1 as catalogue_v1

SCHEMA = "pm99-season-kit-gap-queue-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_queue(source_root: Path, cache_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    inputs = []
    for catalogue_path in sorted(source_root.glob("*/kit-catalogue-v1.json")):
        season_dir = catalogue_path.parent
        request_path = season_dir / "kit-catalogue-request-v1.json"
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
        request = json.loads(request_path.read_text(encoding="utf-8"))
        requested = {row["carrier_id"]: row for row in request.get("clubs") or []}
        season = season_dir.name
        inputs.append({"season": season, "catalogue_sha256": sha256_file(catalogue_path), "request_sha256": sha256_file(request_path)})
        for row in catalogue.get("rows") or []:
            status = row.get("status")
            if status not in {"blocked-missing-home-kit-fields", "blocked-no-target-season-source"}:
                continue
            queued = {
                "season": season,
                "carrier_id": row["carrier_id"],
                "club_name": row["club_name"],
                "status": status,
                "source_family": "wikipedia-exact-page-incomplete" if status == "blocked-missing-home-kit-fields" else "no-wikipedia-exact-page",
            }
            source = (requested.get(row["carrier_id"]) or {}).get("source")
            if status == "blocked-missing-home-kit-fields" and isinstance(source, dict):
                cached = catalogue_v1._read_cached_wikipedia(cache_dir, source)
                if cached is not None:
                    parsed = catalogue_v1._parse_wikipedia_home_kit(str(cached["wikitext"]))
                    queued.update({
                        "page_title": cached["page_title"],
                        "page_url": cached["page_url"],
                        "revision_id": cached["revision_id"],
                        "parse_status": parsed["status"],
                        "missing_fields": parsed.get("missing_fields") or [],
                        "invalid_fields": parsed.get("invalid_fields") or [],
                    })
            rows.append(queued)

    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        occurrences[row["club_name"]].append(row)
    for row in rows:
        row["recurring_club_gap_count"] = len(occurrences[row["club_name"]])
    rows.sort(key=lambda row: (-row["recurring_club_gap_count"], row["club_name"].casefold(), row["season"], row["carrier_id"]))

    status_counts = Counter(row["status"] for row in rows)
    family_counts = Counter(row["source_family"] for row in rows)
    signatures = Counter(tuple(row.get("missing_fields") or []) for row in rows if row["status"] == "blocked-missing-home-kit-fields")
    recurring = [
        {"club_name": club, "gap_count": len(items), "seasons": sorted(item["season"] for item in items), "source_families": sorted({item["source_family"] for item in items})}
        for club, items in occurrences.items()
    ]
    recurring.sort(key=lambda item: (-item["gap_count"], item["club_name"].casefold()))
    return {
        "schema_version": SCHEMA,
        "provenance": {"inputs": inputs},
        "policy": {
            "priority": "recurring-club-gap-count-descending-then-club-season-carrier",
            "incomplete_lane": "repair-only-from-cited-exact-revision-no-colour-inference",
            "no_page_lane": "require-alternate-credited-exact-season-evidence",
            "fallback": "none-for-continuing-clubs",
        },
        "coverage": {
            "gap_count": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
            "source_family_counts": dict(sorted(family_counts.items())),
            "recurring_club_count": sum(1 for item in recurring if item["gap_count"] > 1),
            "missing_field_signatures": [
                {"fields": list(fields), "count": count}
                for fields, count in sorted(signatures.items(), key=lambda item: (-item[1], item[0]))
            ],
        },
        "recurring_clubs": recurring,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_queue(args.source_root, args.cache_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(document))
    print(json.dumps(document["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
