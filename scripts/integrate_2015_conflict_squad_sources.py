#!/usr/bin/env python3
"""Bind exact conflict-source captures into a source-only 2015 package."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconcile_2015_world_source_player_facts import _read_fifa_rows, build_reconciliation

CAPTURE_SCHEMA = "pm99-footballsquads-season-capture-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"
SOURCE_COUNTRY_BY_GROUP = {"english-non-league": "eng"}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def integrate(*, registry: dict[str, Any], base_capture: dict[str, Any], base_draft: dict[str, Any], conflict_capture: dict[str, Any], fifa_csv: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if base_capture.get("schema_version") != CAPTURE_SCHEMA or conflict_capture.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("captures must use the canonical squad schema")
    if base_draft.get("schema_version") != DRAFT_SCHEMA:
        raise ValueError("draft has the wrong schema")
    base_selectors = {tuple(str(club.get(k) or "") for k in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")) for club in base_capture.get("clubs", [])}
    clubs = [dict(c) for c in base_capture.get("clubs", [])]
    conflict_by_id: dict[int, dict[str, Any]] = {}
    for club in conflict_capture.get("clubs", []):
        selector = tuple(str(club.get(k) or "") for k in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))
        if not all(selector) or selector in base_selectors or int(club["candidate_carrier_id"]) in conflict_by_id:
            raise ValueError("conflict capture has an incomplete, duplicate, or reused selector")
        conflict_by_id[int(club["candidate_carrier_id"])] = club
        clubs.append(dict(club))
    proposals: list[dict[str, Any]] = []
    for original in base_draft["proposals"]:
        proposal = dict(original)
        carrier_id = int(proposal["carrier_id"])
        club = conflict_by_id.get(carrier_id)
        if club is not None:
            expected_country = SOURCE_COUNTRY_BY_GROUP.get(str(proposal.get("group") or ""), str(proposal.get("group") or ""))
            if expected_country != str(club["country_catalog"]):
                raise ValueError(f"country mismatch for carrier {carrier_id}")
            if len(club.get("players") or []) < int(proposal["fixed_roster_slot_count"]):
                raise ValueError(f"conflict source does not meet capacity for carrier {carrier_id}")
            proposal.update({"source_country_catalog": club["country_catalog"], "source_competition_catalogs": [club["competition_catalog"]], "source_selector": {k: club[k] for k in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")}, "source_club_name": club["club_name"], "source_player_row_count": len(club["players"]), "allocation_method": "explicit-transfermarkt-conflict-carrier-binding", "status": "source-squad-ready", "source_note": "Pinned exact 2015 Transfermarkt squad; alternate source retained alongside base capture"})
        proposals.append(proposal)
    proposals.sort(key=lambda row: int(row["carrier_id"]))
    capture = {"schema_version": CAPTURE_SCHEMA, "source": {"title": "FootballSquads plus NTF plus exact Transfermarkt conflict captures", "repository": "mixed-content-addressed-public-sources", "revision": "2015-dated-pages-content-addressed-v3", "license": "source-specific public factual captures; URL and content hash retained", "inputs": {"base_capture_sha256": digest(base_capture), "conflict_capture_sha256": digest(conflict_capture)}}, "season": {"catalog": "2015-world-hybrid-plus-ntf-plus-conflicts", "label": "2015/16 plus 2015 calendar-year leagues"}, "clubs": sorted(clubs, key=lambda c: (str(c["country_catalog"]), str(c["competition_catalog"]), str(c["club_name"]), str(c["source_path"]))), "summary": {"club_count": len(clubs), "player_count": sum(len(c.get("players") or []) for c in clubs), "base_club_count": len(base_capture.get("clubs", [])), "conflict_club_count": len(conflict_by_id)}}
    draft = {"schema_version": DRAFT_SCHEMA, "policy": "existing-carriers-only; preserve-country-family-and-roster-capacity; exact-conflict-sources-only; no-topology-write", "registry_sha256": digest(registry), "source_capture_sha256": digest(capture), "coverage": {"carrier_count": len(proposals), "status_counts": dict(sorted(Counter(str(r.get("status")) for r in proposals).items())), "conflict_source_ready_carrier_count": len(conflict_by_id), "source_squad_ready_slot_count": sum(int(r["fixed_roster_slot_count"]) for r in proposals if r.get("status") == "source-squad-ready")}, "proposals": proposals}
    fifa_rows, fifa_sha = _read_fifa_rows(fifa_csv)
    reconciliation = build_reconciliation(registry=registry, draft=draft, source_capture=capture, fifa_rows=fifa_rows, fifa_sha256=fifa_sha)
    reconciliation["conflict_integration"] = {"capture_sha256": digest(capture), "source_ready_conflict_carriers": sorted(conflict_by_id), "policy": "exact carrier/country/source binding; no fuzzy assignment; no invented ratings"}
    return capture, draft, reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--base-capture", required=True, type=Path)
    parser.add_argument("--base-draft", required=True, type=Path)
    parser.add_argument("--conflict-capture", required=True, type=Path)
    parser.add_argument("--fifa16-player-csv", required=True, type=Path)
    parser.add_argument("--integrated-capture-output", required=True, type=Path)
    parser.add_argument("--integrated-draft-output", required=True, type=Path)
    parser.add_argument("--reconciliation-output", required=True, type=Path)
    args = parser.parse_args()
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    capture, draft, reconciliation = integrate(registry=load(args.registry), base_capture=load(args.base_capture), base_draft=load(args.base_draft), conflict_capture=load(args.conflict_capture), fifa_csv=args.fifa16_player_csv)
    for path, value in ((args.integrated_capture_output, capture), (args.integrated_draft_output, draft), (args.reconciliation_output, reconciliation)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
    print(json.dumps({"capture": capture["summary"], "draft": draft["coverage"], "reconciliation": reconciliation["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
