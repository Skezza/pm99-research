#!/usr/bin/env python3
"""Integrate dated NTF captures into the fixed-carrier source package.

This is a source/package operation only.  It combines the existing
FootballSquads capture with the content-addressed National Football Teams
capture, replaces only the explicitly carrier-bound missing-family draft rows,
and runs the existing player/FIFA reconciliation.  It never writes PM99
binary/database assets.  NTF appearance lists that cannot fill an immutable
carrier are retained as ``undersized-source-squad`` and remain unresolved;
they are never padded with invented players.
"""

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

from scripts.reconcile_2015_world_source_player_facts import (
    _read_fifa_rows,
    build_reconciliation,
)


SCHEMA = "pm99-world-2015-ntf-integrated-source-package-v1"
CAPTURE_SCHEMA = "pm99-footballsquads-season-capture-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_canonical(path: Path, label: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise ValueError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def integrate(*, registry: dict[str, Any], base_capture: dict[str, Any], base_draft: dict[str, Any], ntf_capture: dict[str, Any], fifa_csv: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if base_capture.get("schema_version") != CAPTURE_SCHEMA or ntf_capture.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("both captures must use the FootballSquads capture schema")
    if base_draft.get("schema_version") != DRAFT_SCHEMA:
        raise ValueError("base draft has the wrong schema")
    if base_draft.get("source_capture_sha256") != digest(base_capture):
        raise ValueError("base draft is not bound to the supplied base capture")
    if not isinstance(registry.get("carriers"), list) or not isinstance(base_draft.get("proposals"), list):
        raise ValueError("registry/draft are missing their carrier lists")

    base_clubs = [dict(club) for club in base_capture.get("clubs", [])]
    ntf_clubs = [dict(club) for club in ntf_capture.get("clubs", [])]
    if not base_clubs or not ntf_clubs:
        raise ValueError("both captures must contain clubs")
    selectors: set[tuple[str, str, str, str, str]] = set()
    for club in base_clubs + ntf_clubs:
        selector = tuple(str(club.get(key) or "") for key in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))
        if not all(selector):
            raise ValueError("capture has incomplete source selector")
        if selector in selectors:
            raise ValueError(f"duplicate source selector: {selector}")
        selectors.add(selector)
    # The FootballSquads hybrid legitimately contains repeated historical
    # club names across competition captures.  The newly acquired candidates
    # must nevertheless be one-to-one within their country family.
    ntf_identities = [(str(club["country_catalog"]), str(club["club_name"]).casefold()) for club in ntf_clubs]
    if len(ntf_identities) != len(set(ntf_identities)):
        raise ValueError("NTF capture reuses a country-scoped club identity")
    base_identities = {(str(club["country_catalog"]), str(club["club_name"]).casefold()) for club in base_clubs}
    reused_identities = sorted(set(ntf_identities) & base_identities)
    if reused_identities:
        raise ValueError(f"NTF capture reuses a base country-scoped club identity: {reused_identities[0]}")

    carrier_ids = {int(row["carrier_id"]) for row in registry["carriers"]}
    ntf_by_carrier: dict[int, dict[str, Any]] = {}
    for club in ntf_clubs:
        carrier_id = club.get("candidate_carrier_id")
        if not isinstance(carrier_id, int) or carrier_id in ntf_by_carrier:
            raise ValueError("NTF capture must contain one unique integer candidate_carrier_id per club")
        if carrier_id not in carrier_ids:
            raise ValueError(f"NTF capture candidate carrier is absent from registry: {carrier_id}")
        ntf_by_carrier[carrier_id] = club

    # Preserve the existing 451-carrier draft exactly except for explicit NTF
    # carrier candidates.  A short NTF table is source evidence, not a reason
    # to fill the tail of a PM99 roster with an unrelated player.
    proposals: list[dict[str, Any]] = []
    replaced: set[int] = set()
    for original in base_draft["proposals"]:
        proposal = dict(original)
        carrier_id = int(proposal["carrier_id"])
        club = ntf_by_carrier.get(carrier_id)
        if club is not None:
            fixed = int(proposal["fixed_roster_slot_count"])
            player_count = len(club.get("players") or [])
            if str(proposal.get("group") or "") != str(club["country_catalog"]):
                raise ValueError(f"NTF carrier {carrier_id} crosses country family: {proposal.get('group')} vs {club['country_catalog']}")
            proposal.update({
                "group": str(proposal.get("group") or club["country_catalog"]),
                "source_country_catalog": club["country_catalog"],
                "source_competition_catalogs": [club["competition_catalog"]],
                "source_selector": {key: club[key] for key in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")},
                "source_club_name": club["club_name"],
                "source_player_row_count": player_count,
                "allocation_method": "explicit-ntf-carrier-catalogue-binding",
                "status": "source-squad-ready" if player_count >= fixed else "undersized-source-squad",
                "source_note": "NTF appearance table; not guaranteed to be a complete registration list",
            })
            replaced.add(carrier_id)
        proposals.append(proposal)
    if replaced != set(ntf_by_carrier):
        raise ValueError("some NTF candidate carriers were absent from the base draft")
    proposals.sort(key=lambda row: int(row["carrier_id"]))

    integrated_capture = {
        "schema_version": CAPTURE_SCHEMA,
        "source": {
            "title": "FootballSquads plus National Football Teams historical source capture",
            "repository": "mixed-content-addressed-public-sources",
            "revision": "2015-dated-pages-content-addressed-v1",
            "license": "source-specific public factual captures; URL and content hash retained",
            "inputs": {"footballsquads_capture_sha256": digest(base_capture), "ntf_capture_sha256": digest(ntf_capture)},
        },
        "season": {"catalog": "2015-world-hybrid-plus-ntf", "label": "2015/16 plus 2015 calendar-year leagues"},
        "clubs": sorted(base_clubs + ntf_clubs, key=lambda club: (str(club["country_catalog"]), str(club["competition_catalog"]), str(club["club_name"]), str(club["source_path"]))),
        "summary": {
            "club_count": len(base_clubs) + len(ntf_clubs),
            "player_count": sum(len(club.get("players") or []) for club in base_clubs + ntf_clubs),
            "base_footballsquads_club_count": len(base_clubs),
            "ntf_club_count": len(ntf_clubs),
            "country_catalogs": sorted({str(club["country_catalog"]) for club in base_clubs + ntf_clubs}),
        },
    }
    integrated_draft = {
        "schema_version": DRAFT_SCHEMA,
        "policy": "existing-carriers-only; preserve-country-family-and-roster-capacity; no-topology-write",
        "registry_sha256": digest(registry),
        "source_capture_sha256": digest(integrated_capture),
        "coverage": {
            "carrier_count": len(proposals),
            "status_counts": dict(sorted(Counter(str(row.get("status")) for row in proposals).items())),
            "ntf_bound_carrier_count": len(replaced),
            "ntf_source_ready_carrier_count": sum(1 for row in proposals if int(row["carrier_id"]) in replaced and row.get("status") == "source-squad-ready"),
            "source_squad_ready_slot_count": sum(int(row["fixed_roster_slot_count"]) for row in proposals if row.get("status") == "source-squad-ready"),
        },
        "proposals": proposals,
    }

    fifa_rows, fifa_sha = _read_fifa_rows(fifa_csv)
    reconciliation = build_reconciliation(
        registry=registry,
        draft=integrated_draft,
        source_capture=integrated_capture,
        fifa_rows=fifa_rows,
        fifa_sha256=fifa_sha,
    )
    role_counts = Counter()
    role_by_group: dict[str, Counter[str]] = defaultdict(Counter)
    ntf_plan_count = 0
    proposal_by_carrier = {int(row["carrier_id"]): row for row in integrated_draft["proposals"]}
    for plan in reconciliation["carrier_plans"]:
        is_ntf = str(plan["source_selector"].get("competition_catalog")) == "national-football-teams-2015-1"
        ntf_plan_count += int(is_ntf)
        for row in plan["rows"]:
            role = str(row["source_player"].get("position") or "UNRESOLVED")
            role_counts[role] += 1
            role_by_group[str(proposal_by_carrier[int(plan["carrier_id"])].get("group") or "unclassified")][role] += 1
    unresolved = [
        {"carrier_id": int(row["carrier_id"]), "group": row.get("group"), "baseline_name": row.get("baseline_name"), "status": row.get("status"), "reason": "source-squad-unavailable-or-insufficient-capacity" if row.get("status") == "undersized-source-squad" else str(row.get("status"))}
        for row in proposals if row.get("status") != "source-squad-ready"
    ]
    # Keep the player receipt consumable by the existing asset/portrait lanes;
    # identify this package integration in an additive field rather than
    # replacing the established reconciliation schema.
    reconciliation["integration_receipt_schema"] = SCHEMA
    reconciliation["policy"] = "fixed-existing-carriers-and-slots-only; NTF capacity is never padded; FIFA ratings remain explicit fallback-required when unmatched; no-fdi-pkf-or-bmp-write"
    reconciliation["coverage"].update({
        "total_registry_carriers": len(registry["carriers"]),
        "integrated_source_ready_carriers": len(reconciliation["carrier_plans"]),
        "integrated_source_ready_slot_count": sum(int(plan["fixed_roster_slot_count"]) for plan in reconciliation["carrier_plans"]),
        "ntf_source_ready_carriers_in_reconciliation": ntf_plan_count,
        "remaining_unresolved_carrier_count": len(unresolved),
        "remaining_unresolved_carrier_ids": [row["carrier_id"] for row in unresolved],
        "remaining_unresolved_carriers": unresolved,
        "role_demand": dict(sorted(role_counts.items())),
        "role_demand_by_group": {group: dict(sorted(counts.items())) for group, counts in sorted(role_by_group.items())},
        "ratings_fallback_policy": "existing FIFA16 reconciliation statuses are retained; fallback-required means no unambiguous FIFA row and no rating is invented",
    })
    reconciliation["sources"]["integrated_source_draft_sha256"] = digest(integrated_draft)
    reconciliation["sources"]["ntf_capture_sha256"] = digest(ntf_capture)
    return integrated_capture, integrated_draft, reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--base-capture", required=True, type=Path)
    parser.add_argument("--base-draft", required=True, type=Path)
    parser.add_argument("--ntf-capture", required=True, type=Path)
    parser.add_argument("--fifa16-player-csv", required=True, type=Path)
    parser.add_argument("--integrated-capture-output", required=True, type=Path)
    parser.add_argument("--integrated-draft-output", required=True, type=Path)
    parser.add_argument("--reconciliation-output", required=True, type=Path)
    args = parser.parse_args()
    registry, _ = read_canonical(args.registry, "registry")
    base_capture, _ = read_canonical(args.base_capture, "base capture")
    base_draft, _ = read_canonical(args.base_draft, "base draft")
    ntf_capture, _ = read_canonical(args.ntf_capture, "NTF capture")
    capture, draft, reconciliation = integrate(registry=registry, base_capture=base_capture, base_draft=base_draft, ntf_capture=ntf_capture, fifa_csv=args.fifa16_player_csv)
    for path, value in ((args.integrated_capture_output, capture), (args.integrated_draft_output, draft), (args.reconciliation_output, reconciliation)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
    print(json.dumps({"integrated_capture": capture["summary"], "draft": draft["coverage"], "reconciliation": reconciliation["coverage"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
