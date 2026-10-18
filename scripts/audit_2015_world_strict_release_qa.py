#!/usr/bin/env python3
"""Adversarially audit the strict 2015 world V2 package graph."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = "pm99-world-2015-strict-release-qa-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build(*, package: dict[str, Any], projection: dict[str, Any], draft: dict[str, Any], candidate: dict[str, Any], dispositions: dict[str, Any], ownership: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def require(code: str, condition: bool, detail: Any) -> None:
        if not condition:
            failures.append({"code": code, "detail": detail})

    clubs = {int(row["carrier_id"]): row for row in package.get("clubs", [])}
    players = {int(row["carrier_id"]): row for row in package.get("players", [])}
    managers = {str(row["id"]): row for row in package.get("managers", [])}
    proposals = {int(row["carrier_id"]): row for row in draft.get("proposals", [])}
    candidate_clubs = {int(row["carrier_id"]): row for row in candidate.get("carrier_drafts", [])}
    disp_rows = {int(row["carrier_id"]): row for row in dispositions.get("dispositions", [])}
    source_ids = {carrier for carrier, row in proposals.items() if row.get("status") == "source-squad-ready"}
    partial_ids = {carrier for carrier, row in disp_rows.items() if row.get("release_disposition") == "partial-sourced-prefix-preserved-native-tail"}
    blocked_ids = set(proposals) - source_ids - partial_ids
    proof_sets: dict[str, set[int]] = defaultdict(set)
    for carrier, club in clubs.items():
        proof_sets[str((club.get("proof") or {}).get("artifact_id"))].add(carrier)

    require("carrier-set", len(clubs) == 451 and set(clubs) == set(proposals), {"package": len(clubs), "draft": len(proposals)})
    require("source-category", proof_sets["world-2015-source-candidate"] == source_ids, {"expected": len(source_ids), "actual": len(proof_sets["world-2015-source-candidate"])})
    require("partial-category", proof_sets["world-2015-partial-source-dispositions"] == partial_ids, {"expected": len(partial_ids), "actual": len(proof_sets["world-2015-partial-source-dispositions"])})
    require("preserved-category", proof_sets["world-mode1-runtime-contract"] == blocked_ids, {"expected": len(blocked_ids), "actual": len(proof_sets["world-mode1-runtime-contract"])})

    for carrier in sorted(source_ids):
        expected = str(candidate_clubs[carrier]["club"]["source_club_name"])
        require("source-club-name", clubs[carrier].get("name") == expected, {"carrier_id": carrier, "expected": expected, "actual": clubs[carrier].get("name")})
        require("source-club-full-name", clubs[carrier].get("full_name") == expected, {"carrier_id": carrier, "expected": expected, "actual": clubs[carrier].get("full_name")})
    for carrier in sorted(partial_ids):
        expected = str((disp_rows[carrier].get("source_selector") or {}).get("club_name"))
        require("partial-club-name", clubs[carrier].get("name") == expected, {"carrier_id": carrier, "expected": expected, "actual": clubs[carrier].get("name")})
        require("partial-club-full-name", clubs[carrier].get("full_name") == expected, {"carrier_id": carrier, "expected": expected, "actual": clubs[carrier].get("full_name")})

    package_player_rows = package.get("players", [])
    require("unique-player-ids", len(players) == len(package_player_rows) == len({row.get("id") for row in package_player_rows}) == len({row.get("person_id") for row in package_player_rows}), {"player_count": len(package_player_rows), "unique_carriers": len(players)})
    club_roster_ids = [player_id for club in clubs.values() for player_id in club.get("roster_player_ids", [])]
    require("v11-player-and-roster-counts", len(package_player_rows) == 9354 and len(club_roster_ids) == 9390 and len(set(club_roster_ids)) == 9354, {"roster_refs": len(club_roster_ids), "players": len(package_player_rows), "unique_roster_refs": len(set(club_roster_ids))})

    # V11 deliberately rejects appended/recycled playable-club carriers.  The
    # 37 allocation requests fail open to the original compact donor: 36 are
    # exact native shared references and one is a single invalid-role native
    # row.  Verify this from the source allocation graph, not merely counts.
    fallback_rows: list[dict[str, int]] = []
    for candidate_club in candidate.get("carrier_drafts", []):
        team = int(candidate_club["carrier_id"])
        for source_player in candidate_club.get("players", []):
            graph = source_player.get("compiler_graph") or {}
            if graph.get("operation") != "mode1-recycle":
                continue
            allocation = graph.get("allocation") or {}
            fallback_rows.append({
                "team": team,
                "slot": int(source_player["slot_index"]),
                "target": int(source_player["player_carrier_id"]),
                "donor": int(allocation["old_shared_mode1_carrier_id"]),
            })
    require("v11-source-fallback-count", len(fallback_rows) == 37, len(fallback_rows))
    fallback_donors = {row["donor"] for row in fallback_rows}
    for row in fallback_rows:
        roster = clubs[row["team"]].get("roster_player_ids", [])
        expected_id = f"player-{row['donor']}"
        require("v11-fallback-slot", row["slot"] < len(roster) and roster[row["slot"]] == expected_id, {**row, "actual": roster[row["slot"]] if row["slot"] < len(roster) else None})
        donor_player = players.get(row["donor"])
        require("v11-fallback-whole-record-preserve", donor_player is not None and donor_player.get("policy") == "preserve-existing-mode1", row)
    shared_declarations = [
        (carrier, player_id)
        for carrier, club in clubs.items()
        for player_id in club.get("shared_preserve_player_ids", [])
    ]
    require("v11-declared-shared-ref-count", len(shared_declarations) == 36, len(shared_declarations))
    for carrier, player_id in shared_declarations:
        require("v11-shared-ref-in-roster", player_id in clubs[carrier].get("roster_player_ids", []), {"carrier_id": carrier, "player_id": player_id})
        player = next((row for row in package_player_rows if row.get("id") == player_id), None)
        require("v11-shared-ref-cross-owner-preserve", player is not None and player.get("club_id") != f"club-{carrier}" and player.get("policy") == "preserve-existing-mode1", {"carrier_id": carrier, "player_id": player_id})
    require("v11-no-clone-or-recycle-fields", not any("mode0_clone_carrier_id" in row or "recycle_from_mode1_carrier_id" in row or "append_from_carrier_id" in row for row in package_player_rows), None)
    require("v11-projection-fallback-counts", (projection.get("coverage") or {}).get("recycle_fallback_slot_count") == 37 and (projection.get("coverage") or {}).get("shared_native_preserve_slot_count") == 36 and (projection.get("coverage") or {}).get("recycle_edge_count") == 0, projection.get("coverage"))

    ownership_artifact = next((row for row in package.get("artifacts", []) if row.get("id") == "world-2015-person-ownership-decisions"), None)
    require("ownership-artifact", ownership_artifact is not None and ownership_artifact.get("sha256") == digest(ownership), ownership_artifact)
    require("ownership-decision-count", len(ownership.get("decisions", [])) == 36, len(ownership.get("decisions", [])))
    for decision in ownership.get("decisions", []):
        retained = decision["retained"]
        retained_player = players.get(int(retained["player_carrier_id"]))
        require("ownership-retained", retained_player is not None and retained_player.get("club_id") == f"club-{retained['team_carrier_id']}" and (retained_player.get("proof") or {}).get("artifact_id") == "world-2015-source-candidate", retained)
        for displaced in decision["displaced"]:
            displaced_player = players.get(int(displaced["player_carrier_id"]))
            require("ownership-displaced", displaced_player is not None and displaced_player.get("club_id") == f"club-{displaced['team_carrier_id']}" and (displaced_player.get("proof") or {}).get("artifact_id") == "world-2015-person-ownership-decisions" and displaced.get("disposition") == "preserve-native-carrier-row", displaced)

    # Recompute which dated manager writes are graph-safe. A shared manager
    # entity is writable only when every owner has the same dated name.
    metadata_by_carrier = {int(row["carrier_id"]): row for row in metadata.get("rows", [])}
    owners: dict[str, list[int]] = defaultdict(list)
    for carrier, club in clubs.items():
        owners[str(club["manager_id"])].append(carrier)
    safe_manager_values: dict[str, str] = {}
    for manager_id, carrier_ids in owners.items():
        values = [(metadata_by_carrier.get(carrier) or {}).get("manager", {}).get("value") for carrier in carrier_ids]
        if values and all(values) and len(set(values)) == 1:
            safe_manager_values[manager_id] = str(values[0])
    metadata_artifact = next((row for row in package.get("artifacts", []) if row.get("sha256") == digest(metadata)), None)
    require("metadata-dispositions-consumed", metadata_artifact is not None, {"expected_sha256": digest(metadata)})
    write_managers = {manager_id: row for manager_id, row in managers.items() if row.get("policy") == "write"}
    require("manager-safe-write-set", set(write_managers) == set(safe_manager_values), {"expected": len(safe_manager_values), "actual": len(write_managers), "missing": sorted(set(safe_manager_values) - set(write_managers))[:20], "unexpected": sorted(set(write_managers) - set(safe_manager_values))[:20]})
    for manager_id, expected in safe_manager_values.items():
        actual = managers.get(manager_id) or {}
        require("manager-name", actual.get("policy") == "write" and actual.get("name") == expected, {"manager_id": manager_id, "expected": expected, "actual": actual.get("name"), "policy": actual.get("policy")})

    require("projection-result", projection.get("result") == "strict-package-emitted", projection.get("result"))
    return {
        "schema_version": SCHEMA,
        "result": "pass" if not failures else "fail",
        "sources": {"package_sha256": digest(package), "projection_sha256": digest(projection), "draft_sha256": digest(draft), "candidate_sha256": digest(candidate), "dispositions_sha256": digest(dispositions), "ownership_sha256": digest(ownership), "metadata_sha256": digest(metadata)},
        "coverage": {"carrier_count": len(clubs), "source_carrier_count": len(source_ids), "partial_carrier_count": len(partial_ids), "preserved_carrier_count": len(blocked_ids), "player_count": len(package_player_rows), "roster_reference_count": len(club_roster_ids), "shared_reference_count": len(club_roster_ids) - len(set(club_roster_ids)), "source_fallback_count": len(fallback_rows), "unique_player_carrier_count": len(players), "ownership_decision_count": len(ownership.get("decisions", [])), "safe_manager_write_count": len(safe_manager_values), "actual_manager_write_count": len(write_managers), "failure_count": len(failures)},
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "projection", "draft", "candidate", "dispositions", "ownership", "metadata"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build(**{name: load(getattr(args, name)) for name in ("package", "projection", "draft", "candidate", "dispositions", "ownership", "metadata")})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
