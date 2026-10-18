#!/usr/bin/env python3
"""Build explicit release dispositions for the remaining world carriers.

This receipt separates partial historical sources from genuine source blockers.
Partial rows preserve the deterministically selected source prefix and the
remaining native carrier tail; no person identity is invented for the tail.
No PM99 binary or database is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "pm99-world-2015-unresolved-carrier-dispositions-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(*, draft: dict[str, Any], source_capture: dict[str, Any], draft_sha256: str, capture_sha256: str) -> dict[str, Any]:
    proposals = {int(row["carrier_id"]): row for row in draft.get("proposals", [])}
    sources_by_carrier: dict[int, list[dict[str, Any]]] = defaultdict(list)
    seen_selectors: set[tuple[str, ...]] = set()
    for row in source_capture.get("clubs", []):
        if not isinstance(row, dict) or not isinstance(row.get("candidate_carrier_id"), int):
            continue
        selector = tuple(str(row.get(key) or "") for key in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))
        if not any(selector) or selector in seen_selectors:
            raise ValueError("source capture has an empty or repeated source selector")
        seen_selectors.add(selector)
        sources_by_carrier[int(row["candidate_carrier_id"])].append(row)
    rows: list[dict[str, Any]] = []
    for carrier_id in sorted(proposals):
        proposal = proposals[carrier_id]
        if proposal.get("status") == "source-squad-ready":
            continue
        status = str(proposal.get("status"))
        source_selector = proposal.get("source_selector") or {}
        selector_keys = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
        expected_fields = {key: str(source_selector.get(key)) for key in selector_keys if source_selector.get(key)}
        matching_sources = [row for row in sources_by_carrier.get(carrier_id, []) if all(str(row.get(key) or "") == value for key, value in expected_fields.items())]
        source = matching_sources[0] if len(matching_sources) == 1 else None
        if status == "undersized-source-squad":
            if source is None:
                raise ValueError(f"undersized carrier {carrier_id} has no source capture")
            players = list(source.get("players") or [])
            capacity = int(proposal.get("fixed_roster_slot_count") or 0)
            prefix_count = min(len(players), capacity)
            tail_count = capacity - prefix_count
            rows.append({
                "carrier_id": carrier_id,
                "group": proposal.get("group"),
                "baseline_name": proposal.get("baseline_name"),
                "release_disposition": "partial-sourced-prefix-preserved-native-tail",
                "source_status": "sourced-prefix",
                "fixed_roster_slot_count": capacity,
                "sourced_prefix_count": prefix_count,
                "preserved_native_tail_count": tail_count,
                "source_selector": proposal.get("source_selector"),
                "source_provenance": {"primary_source_url": source.get("source_url"), "primary_source_sha256": source.get("source_sha256"), "source_path": source.get("source_path"), "supplemental_sources": source.get("supplemental_sources", [])},
                "sourced_prefix": [{"source_index": index + 1, "name": player.get("name"), "birth_date": player.get("birth_date"), "nationality": player.get("nationality"), "position": player.get("position"), "identity_status": "source-row-only"} for index, player in enumerate(players[:prefix_count])],
                "native_tail_policy": "preserve existing carrier slots as native no-photo/unresolved identity; do not copy or invent a person",
                "next_action": "acquire a second dated squad source with enough distinct rows to fill the tail; if unavailable, retain the native tail and keep the carrier blocked",
            })
        elif status == "no-captured-source-country":
            rows.append({
                "carrier_id": carrier_id,
                "group": proposal.get("group"),
                "baseline_name": proposal.get("baseline_name"),
                "release_disposition": "genuinely-unresolved-no-dated-source",
                "source_status": "blocked-no-captured-source-country",
                "fixed_roster_slot_count": int(proposal.get("fixed_roster_slot_count") or 0),
                "sourced_prefix_count": 0,
                "preserved_native_tail_count": 0,
                "next_action": "acquire a dated 2015/16 or 2015 calendar-year squad from a stable public source, then perform an exact country-constrained carrier binding; do not assign from another country",
            })
        else:
            rows.append({
                "carrier_id": carrier_id,
                "group": proposal.get("group"),
                "baseline_name": proposal.get("baseline_name"),
                "release_disposition": "genuinely-unresolved-selector-capacity-conflict",
                "source_status": status,
                "fixed_roster_slot_count": int(proposal.get("fixed_roster_slot_count") or 0),
                "sourced_prefix_count": 0,
                "preserved_native_tail_count": 0,
                "next_action": "resolve the existing selector conflict by adding a distinct dated same-country top-competition source or explicitly approving a lower-tier source; never reuse the consumed club selector",
            })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["release_disposition"]] = counts.get(row["release_disposition"], 0) + 1
    return {"schema_version": SCHEMA, "policy": "no-PM99-write; source rows and identities remain separate; native no-photo is preserved for unresolved carrier tails", "sources": {"draft_sha256": draft_sha256, "source_capture_sha256": capture_sha256}, "coverage": {"remaining_unresolved_carrier_count": len(rows), "disposition_counts": dict(sorted(counts.items())), "remaining_unresolved_carrier_ids": [row["carrier_id"] for row in rows], "partial_sourced_prefix_carrier_count": counts.get("partial-sourced-prefix-preserved-native-tail", 0), "genuinely_blocked_carrier_count": counts.get("genuinely-unresolved-no-dated-source", 0) + counts.get("genuinely-unresolved-selector-capacity-conflict", 0)}, "dispositions": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    draft_raw, source_raw = args.draft.read_bytes(), args.source_capture.read_bytes()
    draft, source = json.loads(draft_raw), json.loads(source_raw)
    result = build(draft=draft, source_capture=source, draft_sha256=hashlib.sha256(draft_raw).hexdigest(), capture_sha256=hashlib.sha256(source_raw).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
