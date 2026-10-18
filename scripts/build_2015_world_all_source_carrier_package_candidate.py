#!/usr/bin/env python3
"""Build one all-source-squad-ready, source-only world package candidate.

Every source-squad-ready carrier receives every reconciled immutable roster
row. Opening-fixture facts are attached only to the 77 exact links; the other
225 carriers receive an explicit metadata blocker, not invented manager or
stadium facts. The final receipt applies the deterministic editorial rating
policy while preserving ambiguous identities for manual resolution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts.apply_2015_world_editorial_fallback_ratings import build_editorial_fallback_receipt, canonical_json_bytes
from scripts.audit_world_2015_source_coverage import strict_club_key


RAW_SCHEMA = "pm99-world-2015-full-fixed-roster-carrier-drafts-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"
RECON_SCHEMA = "pm99-world-2015-source-player-reconciliation-v1"
JOIN_SCHEMA = "pm99-world-2015-opening-fixture-source-join-v1"
ASSET_SCHEMA = "pm99-world-2015-asset-dispositions-v1"
ASSET_CANDIDATE_SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"
RECYCLE_SCHEMA = "pm99-world-2015-recycle-role-demand-v1"
RECYCLE_ALLOCATION_SCHEMA = "pm99-world-2015-mode1-recycle-allocation-v1"
RATING_FIELDS = ("rating", "sprint_speed", "stamina", "aggression", "short_pass", "stand_tackle", "heading", "finishing", "dribbling", "gk_handling")


class AllCarrierCandidateError(ValueError):
    pass


def _read(path: Path, label: str, *, canonical: bool = True) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes(); value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllCarrierCandidateError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or (canonical and raw != canonical_json_bytes(value)):
        raise AllCarrierCandidateError(f"{label} must be a canonical JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _asset_index(value: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    if value.get("schema_version") not in {ASSET_SCHEMA, ASSET_CANDIDATE_SCHEMA} or not isinstance(value.get("clubs"), list):
        raise AllCarrierCandidateError("asset dispositions have the wrong schema")
    result = {}
    for club in value["clubs"]:
        if not isinstance(club, dict) or not isinstance(club.get("carrier_id"), int) or club["carrier_id"] in result:
            raise AllCarrierCandidateError("asset dispositions have malformed carrier ids")
        result[club["carrier_id"]] = club
    return result


def _asset(asset: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    for value in asset.get("players") or []:
        if isinstance(value, dict) and value.get("slot_index") == row.get("slot_index") and value.get("player_carrier_id") == row.get("player_carrier_id"):
            portrait = value.get("portrait") if isinstance(value.get("portrait"), Mapping) else value
            return {
                "status": portrait.get("status"),
                "reason": portrait.get("reason") or portrait.get("source_policy"),
                "action": portrait.get("action") or "no-write",
                "source_url": portrait.get("source_url"),
            }
    return {"status": "native-no-photo-review-required", "reason": "no asset disposition for fixed source row", "action": "no-write", "source_url": None}


def _rating(row: Mapping[str, Any]) -> dict[str, Any]:
    fifa = row.get("fifa16") if isinstance(row.get("fifa16"), dict) else {}
    values = fifa.get("fifa16_values")
    if isinstance(values, dict) and all(isinstance(values.get(field), int) for field in RATING_FIELDS):
        return {"status": "fifa16-complete-candidate", "fifa16_match_status": fifa.get("status"), "fifa16_player_id": fifa.get("fifa16_player_id"), "fifa16_name": fifa.get("fifa16_name"), "values": dict(values)}
    if fifa.get("status") == "fifa16-ambiguous-name":
        # The FootballSquads roster identity remains exact through its club,
        # date of birth and nationality facts. FIFA is only a ratings lookup;
        # candidates lacking that DOB must not block the roster identity.
        return {"status": "editorial-fallback-required", "fifa16_match_status": fifa.get("status"), "candidate_fifa16_player_ids": list(fifa.get("candidate_fifa16_player_ids") or []), "reason": "FIFA16 candidates do not share the FootballSquads DOB; deterministic editorial rating fallback required", "identity_basis": "FootballSquads-club-DOB-nationality; FIFA-candidates-retained-as-nonmatching-rating-provenance"}
    return {"status": "editorial-fallback-required", "fifa16_match_status": fifa.get("status"), "reason": "no complete unique FIFA16 rating candidate; deterministic editorial fallback required"}


def _physical_medians(selected: list[Mapping[str, Any]], plans: Mapping[int, Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    """Deterministic competition/position medians for omitted source physique."""
    samples: dict[tuple[str, str, str], list[int]] = {}
    global_samples: dict[tuple[str, str], list[int]] = {}
    for proposal in selected:
        competition = str(proposal["source_selector"]["competition_catalog"])
        for row in plans[int(proposal["carrier_id"])]["rows"]:
            source = row["source_player"]; position = str(source["position"])
            for field in ("height_cm", "weight_kg"):
                value = source.get(field)
                if isinstance(value, int):
                    samples.setdefault((competition, position, field), []).append(value)
                    global_samples.setdefault((position, field), []).append(value)
    result: dict[tuple[str, str, str], int] = {}
    for key, values in samples.items(): result[key] = int(statistics.median(sorted(values)))
    for (position, field), values in global_samples.items(): result.setdefault(("*", position, field), int(statistics.median(sorted(values))))
    return result


def _player_facts_disposition(source: Mapping[str, Any], *, competition: str, medians: Mapping[tuple[str, str, str], int]) -> dict[str, Any]:
    fallbacks = {}
    position = str(source["position"])
    for field in ("height_cm", "weight_kg"):
        if not isinstance(source.get(field), int):
            value = medians.get((competition, position, field), medians.get(("*", position, field)))
            if not isinstance(value, int): raise AllCarrierCandidateError(f"missing physical fallback median for {competition}/{position}/{field}")
            fallbacks[field] = {"value": value, "basis": "deterministic-source-squad-median", "scope": f"{competition}/{position}", "source_field": "missing-in-FootballSquads"}
    return {"status": "physical-editorial-fallback-applied" if fallbacks else "source-complete-or-preserve-only", "physical_fallbacks": fallbacks, "shirt_number_policy": "preserve-existing-mode1; missing FootballSquads shirt number is not a release blocker", "birth_date_status": "review-required" if not source.get("birth_date") else "source-present"}


def _expected_recycle_allocation_count(source_ready_carrier_count: int) -> int | None:
    return {302: 29, 317: 30, 362: 32, 372: 36}.get(source_ready_carrier_count)


def build_candidate(*, source_draft: Mapping[str, Any], reconciliation: Mapping[str, Any], opening_join: Mapping[str, Any], assets: Mapping[str, Any], recycle: Mapping[str, Any], recycle_allocation: Mapping[str, Any] | None = None, source_hashes: Mapping[str, str]) -> dict[str, Any]:
    if source_draft.get("schema_version") != DRAFT_SCHEMA or reconciliation.get("schema_version") not in {RECON_SCHEMA, "pm99-world-2015-ntf-integrated-source-package-v1"}:
        raise AllCarrierCandidateError("source draft or player reconciliation has the wrong schema")
    if opening_join.get("schema_version") != JOIN_SCHEMA:
        raise AllCarrierCandidateError("opening-fixture join has the wrong schema")
    if recycle.get("schema_version") != RECYCLE_SCHEMA or recycle.get("result") != "pass-for-selected-carriers" or recycle.get("runtime_unqualified_required_role_codes"):
        raise AllCarrierCandidateError("allocation-specific recycle-role audit is not qualified")
    plans = {int(row["carrier_id"]): row for row in reconciliation.get("carrier_plans") or [] if isinstance(row, dict)}
    selected = [row for row in source_draft.get("proposals") or [] if isinstance(row, dict) and row.get("status") == "source-squad-ready"]
    if not selected or len(plans) < len(selected):
        raise AllCarrierCandidateError("source-ready carriers lack complete player plans")
    physical_medians = _physical_medians(selected, plans)
    fixture_by_carrier = {int(c["source_draft_reference"]["draft_carrier_id"]): c for c in opening_join.get("clubs") or [] if isinstance(c, dict) and isinstance(c.get("source_draft_reference"), dict) and c["source_draft_reference"].get("status") == "source-draft-and-strict-player-reconciliation-linked"}
    asset_by_carrier = _asset_index(assets)
    recycle_by_slot = {
        (int(demand["recycle_team_carrier_id"]), int(demand["slot_index"])): demand
        for demand in recycle.get("demands") or []
        if isinstance(demand, dict)
    }
    allocation_by_target: dict[tuple[int, int], Mapping[str, Any]] = {}
    allocation_source_replacements: dict[tuple[int, int], int] = {}
    if recycle_allocation is not None:
        if recycle_allocation.get("schema_version") != RECYCLE_ALLOCATION_SCHEMA or recycle_allocation.get("result") != "allocated-selected-carriers":
            raise AllCarrierCandidateError("mode1 recycle allocation is not qualified")
        expected_allocations = _expected_recycle_allocation_count(len(selected))
        if expected_allocations is not None and recycle_allocation.get("allocation_count") != expected_allocations:
            raise AllCarrierCandidateError(f"mode1 recycle allocation count must be {expected_allocations} for {len(selected)} source-ready carriers")
        for allocation in recycle_allocation.get("allocations") or []:
            if not isinstance(allocation, dict): raise AllCarrierCandidateError("malformed recycle allocation")
            target = (int(allocation["recycle_team_carrier_id"]), int(allocation["recycle_team_slot_index"]))
            if target in allocation_by_target: raise AllCarrierCandidateError("duplicate recycle allocation target")
            allocation_by_target[target] = allocation
            source_id = int(allocation["mode0_source_player_carrier_id"]); source_team = int(allocation["mode0_source_team_carrier_id"])
            key = (source_team, source_id)
            if key in allocation_source_replacements: raise AllCarrierCandidateError("duplicate mode0 recycle source")
            allocation_source_replacements[key] = int(allocation["appended_mode0_clone_carrier_id"])
    rows = []
    rating_counts: Counter[str] = Counter()
    physical_fallback_count = 0
    missing_dob_rows: list[dict[str, Any]] = []
    for proposal in sorted(selected, key=lambda row: int(row["carrier_id"])):
        cid = int(proposal["carrier_id"]); plan = plans.get(cid)
        if plan is None or len(plan.get("rows") or []) != int(proposal["fixed_roster_slot_count"]):
            raise AllCarrierCandidateError(f"carrier {cid} has no complete strict player plan")
        fixture_club = fixture_by_carrier.get(cid); asset_club = asset_by_carrier.get(cid, {}); competition = str(proposal["source_selector"]["competition_catalog"])
        fixture = (fixture_club or {}).get("opening_fixture_facts") or {}
        opening_by_slot = {}
        for lane in ("starting_lineup", "substitutes"):
            for item in fixture.get(lane) or []:
                ref = item.get("player_reconciliation") if isinstance(item, dict) else None
                if isinstance(ref, dict) and ref.get("status") == "strict-normalised-source-name-unique":
                    slot = (ref.get("player_reconciliation_row") or {}).get("slot_index")
                    if isinstance(slot, int): opening_by_slot[slot] = {"lineup_role": lane, "fixture_player": dict(item)}
        players = []
        for player in sorted(plan["rows"], key=lambda value: int(value["slot_index"])):
            disposition = _rating(player); rating_counts[str(disposition["status"])] += 1
            facts_disposition = _player_facts_disposition(player["source_player"], competition=competition, medians=physical_medians)
            physical_fallback_count += len(facts_disposition["physical_fallbacks"])
            if facts_disposition["birth_date_status"] == "review-required":
                missing_dob_rows.append({"carrier_id": cid, "slot_index": int(player["slot_index"]), "player_carrier_id": int(player["player_carrier_id"]), "source_player_name": player["source_player"]["name"], "reason": "FootballSquads-birth-date-missing; source-or-editorial-fallback-review-required"})
            slot = int(player["slot_index"])
            recycle_demand = recycle_by_slot.get((cid, slot)); allocation = allocation_by_target.get((cid, slot))
            final_player_carrier_id = int(player["player_carrier_id"])
            if allocation is not None:
                if final_player_carrier_id != int(allocation["old_shared_mode1_carrier_id"]): raise AllCarrierCandidateError(f"recycle target {cid}/{slot} no longer has expected shared carrier")
                final_player_carrier_id = int(allocation["new_foreign_player_carrier_id"])
            final_player_carrier_id = allocation_source_replacements.get((cid, final_player_carrier_id), final_player_carrier_id)
            graph = {"operation": "mode1-core-in-place", "runtime_status": "proven-core-path"}
            if recycle_demand is not None or allocation is not None:
                graph = {"operation": "mode1-recycle", "runtime_status": "qualified-allocation-specific-role", "retained_team_carrier_id": recycle_demand["retained_team_carrier_id"] if recycle_demand else allocation["mode0_source_team_carrier_id"], "required_primary_fine_role_code": recycle_demand["required_primary_fine_role_code"] if recycle_demand else allocation["required_primary_fine_role_code"], "runtime_qualified": recycle_demand["runtime_qualified"] if recycle_demand else True, "allocation": {key: allocation[key] for key in ("old_shared_mode1_carrier_id", "new_foreign_player_carrier_id", "mode0_source_player_carrier_id", "mode0_source_team_carrier_id", "appended_mode0_clone_carrier_id")} if allocation else None}
            players.append({"slot_index": slot, "player_carrier_id": final_player_carrier_id, "player_family": player.get("player_family"), "immutable_row_flag": player.get("immutable_row_flag"), "source_squad_index": player.get("source_squad_index"), "source_player": dict(player["source_player"]), "player_facts_disposition": facts_disposition, "rating_disposition": disposition, "portrait_disposition": _asset(asset_club, player), "opening_fixture_presence": opening_by_slot.get(slot, {"status": "not-in-strictly-reconciled-opening-xi-or-bench"}), "compiler_graph": graph})
        blockers = {"2015-club-ground-and-capacity-source-required", "2015-era-kit-source-required", "portrait-source-or-no-photo-decision-required"}
        if fixture_club is None:
            blockers.add("2015-manager-source-required")
        elif fixture.get("source_status") != "source-qualified":
            blockers.add("opening-fixture-source-incomplete")
        if any(p["rating_disposition"]["status"] == "editorial-fallback-required" for p in players): blockers.add("player-rating-editorial-fallback-required")
        if any(p["player_facts_disposition"]["birth_date_status"] == "review-required" for p in players): blockers.add("player-birth-date-source-or-editorial-fallback-review-required")
        kit = dict(asset_club.get("kit") or {"status": "blocked-no-reviewed-2015-kit", "action": "no-write", "reason": "no asset disposition supplied"})
        rows.append({"carrier_id": cid, "status": "blocked", "stage_status": "source-package-candidate; compiler-disabled-until-blockers-clear", "preserved_constraints": ["foreign-competition-membership-preserve-only"], "club": {"strict_identity": (fixture_club or {}).get("strict_club_identity") or {"country_catalog": proposal["source_country_catalog"], "strict_club_key": strict_club_key(proposal["source_club_name"]), "status": "dated-footballsquads-source-club"}, "source_club_name": proposal["source_club_name"], "source_selector": proposal["source_selector"], "ground_policy": "no permanent ground or capacity claim", "fixture_ground_evidence": (fixture_club or {}).get("first_home_fixture_ground_evidence")}, "manager": {"name": fixture.get("declared_manager"), "metadata_status": "fixture-source-fact" if fixture_club else "unavailable-no-dated-manager-source"}, "opening_fixture": {"status": fixture.get("source_status") if fixture_club else "metadata-unavailable", "date": fixture.get("date"), "formation": fixture.get("declared_formation"), "stadium": fixture.get("reported_match_stadium")}, "kit_disposition": kit, "players": players, "runtime_contract": {"mode1_core_fields": "proven-core-path; no generic-unproven blocker", "allocation_specific_recycle_roles": {"result": recycle["result"], "recycle_demand_count": recycle["recycle_demand_count"], "required_role_counts": recycle["required_role_counts"], "runtime_qualified_role_codes": recycle["runtime_qualified_role_codes"], "unresolved_duplicate_slot_count": recycle["unresolved_duplicate_slot_count"]}}, "blockers": sorted(blockers)})
    final_ids = [player["player_carrier_id"] for row in rows for player in row["players"]]
    if len(set(final_ids)) != len(final_ids): raise AllCarrierCandidateError("recycle allocation left duplicate final player carrier ids")
    raw = {"schema_version": RAW_SCHEMA, "policy": "all-source-squad-ready-full-fixed-roster-candidate; strict-reconciliation-only; deterministic-physical-fallback-for-missing-source-values; allocated-recycle-ids-exclusive; no-pm99-write", "stage_status": "source-package-candidate; compiler-disabled-until-blockers-clear", "preserved_constraints": ["foreign-competition-membership-preserve-only"], "sources": dict(source_hashes), "coverage": {"strict_linked_carrier_count": len(rows), "fixed_roster_slot_count": sum(len(row["players"]) for row in rows), "unique_final_player_carrier_id_count": len(set(final_ids)), "rating_disposition_counts": dict(sorted(rating_counts.items())), "physical_editorial_fallback_value_count": physical_fallback_count, "birth_date_source_or_editorial_fallback_review_rows": missing_dob_rows}, "carrier_drafts": rows}
    result = build_editorial_fallback_receipt(full_roster_draft=raw)
    blocker_counts = Counter(blocker for row in result["carrier_drafts"] for blocker in row["blockers"])
    result["stage_status"] = raw["stage_status"]
    result["preserved_constraints"] = raw["preserved_constraints"]
    result["compiler_graph"] = {"mode1_core_in_place_slot_count": sum(1 for row in result["carrier_drafts"] for player in row["players"] if player["compiler_graph"]["operation"] == "mode1-core-in-place"), "mode1_recycle_edge_count": len(recycle_by_slot), "recycle_edges": [dict(value) for _, value in sorted(recycle_by_slot.items())], "audit_result": recycle["result"]}
    result["coverage"]["blocker_counts"] = dict(sorted(blocker_counts.items()))
    result["coverage"]["preserved_constraint_counts"] = {"foreign-competition-membership-preserve-only": len(result["carrier_drafts"])}
    result["coverage"]["physical_editorial_fallback_value_count"] = physical_fallback_count
    result["coverage"]["birth_date_source_or_editorial_fallback_review_rows"] = missing_dob_rows
    result["coverage"]["unique_final_player_carrier_id_count"] = len(set(final_ids))
    result["coverage"]["mode1_recycle_allocation_count"] = len(allocation_by_target)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-draft", required=True, type=Path); parser.add_argument("--player-reconciliation", required=True, type=Path); parser.add_argument("--opening-fixture-source-join", required=True, type=Path); parser.add_argument("--asset-dispositions", required=True, type=Path); parser.add_argument("--recycle-role-audit", required=True, type=Path); parser.add_argument("--recycle-allocation", type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    draft, draft_sha = _read(args.source_draft, "source carrier draft"); recon, recon_sha = _read(args.player_reconciliation, "player reconciliation"); join, join_sha = _read(args.opening_fixture_source_join, "opening fixture source join"); assets, assets_sha = _read(args.asset_dispositions, "asset dispositions", canonical=False); recycle, recycle_sha = _read(args.recycle_role_audit, "recycle role audit", canonical=False)
    allocation, allocation_sha = _read(args.recycle_allocation, "recycle allocation", canonical=False) if args.recycle_allocation else (None, None)
    try:
        result = build_candidate(source_draft=draft, reconciliation=recon, opening_join=join, assets=assets, recycle=recycle, recycle_allocation=allocation, source_hashes={"source_draft_sha256": draft_sha, "strict_player_reconciliation_sha256": recon_sha, "opening_fixture_source_join_sha256": join_sha, "asset_dispositions_sha256": assets_sha, "recycle_role_audit_sha256": recycle_sha, **({"mode1_recycle_allocation_sha256": allocation_sha} if allocation_sha else {})})
    except AllCarrierCandidateError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(canonical_json_bytes(result)); print(json.dumps(result["coverage"], sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
