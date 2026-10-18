#!/usr/bin/env python3
"""Materialise safe opening-fixture facts as blocked fixed-carrier ledger rows.

This is deliberately the last source/package boundary before any future
compiler.  It accepts only a hash-locked source join whose club and player
links were exact, and emits a valid V2 fixed-carrier *blocked* ledger.  It
does not write PM99 files, select a permanent ground/capacity, apply a kit or
portrait, relink a manager, or claim that a fixed slot is ready for runtime
write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


JOIN_SCHEMA = "pm99-world-2015-opening-fixture-source-join-v1"
RECONCILIATION_SCHEMA = "pm99-world-2015-source-player-reconciliation-v1"
REPORT_SCHEMA = "pm99-world-2015-opening-fixture-ledger-materialisation-report-v1"
SOURCE_IDS = {
    "capture": "footballsquads-2015-world-hybrid",
    "join": "opening-fixture-source-join",
    "reconciliation": "strict-player-reconciliation",
    "receipt": "transfermarkt-opening-fixture-receipt",
    "registry": "fixed-carrier-registry",
}
REQUIRED_RATING_VALUES = (
    "rating", "sprint_speed", "stamina", "aggression", "short_pass",
    "stand_tackle", "heading", "finishing", "dribbling", "gk_handling",
)
POSITION_TO_PROVISIONAL_ROLE = {"G": [0], "D": [4], "M": [9], "F": [12]}


class MaterialisationError(ValueError):
    """The source join cannot safely form a fixed-carrier review ledger."""


def canonical_json_bytes(value: Any) -> bytes:
    return ledger.canonical_json_bytes(value)


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        return ledger.read_canonical_json(path, label=label)
    except ledger.WorldLedgerError as exc:
        raise MaterialisationError(str(exc)) from exc


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _validate_inputs(
    *, registry: Mapping[str, Any], base_ledger: Mapping[str, Any], source_join: Mapping[str, Any], reconciliation: Mapping[str, Any]
) -> None:
    try:
        ledger.validate_registry(registry)
        ledger.validate_ledger(registry=registry, ledger=base_ledger)
    except ledger.WorldLedgerError as exc:
        raise MaterialisationError(str(exc)) from exc
    if base_ledger["sources"] or base_ledger["carrier_updates"]:
        raise MaterialisationError("materialisation accepts an empty, hash-locked base ledger only")
    if source_join.get("schema_version") != JOIN_SCHEMA or not isinstance(source_join.get("clubs"), list):
        raise MaterialisationError("opening-fixture source join has the wrong schema")
    sources = source_join.get("sources")
    if not isinstance(sources, dict):
        raise MaterialisationError("opening-fixture source join has no source hashes")
    if sources.get("strict_player_reconciliation_sha256") != _sha(reconciliation):
        raise MaterialisationError("opening-fixture source join is not bound to this strict player reconciliation")
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA or not isinstance(reconciliation.get("carrier_plans"), list):
        raise MaterialisationError("strict player reconciliation has the wrong schema")


def _plan_index(reconciliation: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for plan in reconciliation["carrier_plans"]:
        if not isinstance(plan, dict) or not isinstance(plan.get("carrier_id"), int) or not isinstance(plan.get("rows"), list):
            raise MaterialisationError("strict player reconciliation has a malformed carrier plan")
        if plan["carrier_id"] in result:
            raise MaterialisationError("strict player reconciliation has duplicate carrier plans")
        result[plan["carrier_id"]] = plan
    return result


def _source_rows(*, registry_sha: str, source_join: Mapping[str, Any]) -> list[dict[str, str]]:
    source_hashes = source_join["sources"]
    # The join itself is the provenance document for the exact two-source
    # identity decision. Its hash is added by the caller because this function
    # operates on loaded JSON values.
    output = [
        {
            "id": SOURCE_IDS["capture"],
            "title": "FootballSquads 2015 world hybrid: dated squad/player facts",
            "kind": "squad",
            "content_sha256": str(source_hashes["footballsquads_capture_sha256"]),
        },
        {
            "id": SOURCE_IDS["reconciliation"],
            "title": "Strict FootballSquads-to-FIFA16 player reconciliation: candidate facts and ratings",
            "kind": "ratings",
            "content_sha256": str(source_hashes["strict_player_reconciliation_sha256"]),
        },
        {
            "id": SOURCE_IDS["receipt"],
            "title": "Transfermarkt 2015 opening-fixture receipt: manager, XI, bench, shirt, formation and stadium facts",
            "kind": "manager",
            "content_sha256": str(source_hashes["transfermarkt_opening_fixture_receipt_sha256"]),
        },
        {
            "id": SOURCE_IDS["registry"],
            "title": "Approved PM99 fixed-carrier registry: structural IDs only",
            "kind": "other",
            "content_sha256": registry_sha,
        },
    ]
    return sorted(output, key=lambda row: row["id"])


def _lineup_candidates(club: Mapping[str, Any], *, plan: Mapping[str, Any]) -> list[tuple[dict[str, Any], Mapping[str, Any]]]:
    facts = club.get("opening_fixture_facts")
    if not isinstance(facts, dict):
        raise MaterialisationError("source-join club lacks opening fixture facts")
    rows_by_slot: dict[int, Mapping[str, Any]] = {}
    for row in plan["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("slot_index"), int):
            raise MaterialisationError("strict player reconciliation plan has malformed player rows")
        rows_by_slot[row["slot_index"]] = row
    result: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    seen_slots: set[int] = set()
    for lane in ("starting_lineup", "substitutes"):
        source_rows = facts.get(lane)
        if not isinstance(source_rows, list):
            raise MaterialisationError("opening fixture has malformed lineup facts")
        for fixture_player in source_rows:
            if not isinstance(fixture_player, dict):
                raise MaterialisationError("opening fixture has malformed player facts")
            reference = fixture_player.get("player_reconciliation")
            if not isinstance(reference, dict) or reference.get("status") != "strict-normalised-source-name-unique":
                continue
            row_reference = reference.get("player_reconciliation_row")
            if not isinstance(row_reference, dict) or not isinstance(row_reference.get("slot_index"), int):
                raise MaterialisationError("strict player reference lacks a fixed slot index")
            slot_index = row_reference["slot_index"]
            plan_row = rows_by_slot.get(slot_index)
            if plan_row is None or plan_row.get("player_carrier_id") != row_reference.get("player_carrier_id"):
                raise MaterialisationError("opening-fixture player reference does not match the strict reconciliation plan")
            if slot_index in seen_slots:
                raise MaterialisationError("opening fixture references one fixed slot more than once")
            seen_slots.add(slot_index)
            result.append((fixture_player, plan_row))
    return result


def _blocked_player(*, fixture_player: Mapping[str, Any], plan_row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    source_player = plan_row.get("source_player")
    fifa = plan_row.get("fifa16")
    if not isinstance(source_player, dict) or not isinstance(fifa, dict):
        raise MaterialisationError("strict player reconciliation row lacks source/fifa facts")
    values = fifa.get("fifa16_values")
    if not isinstance(values, dict) or any(key not in values or not isinstance(values[key], int) for key in REQUIRED_RATING_VALUES):
        return None, "missing-complete-fifa16-rating-candidate"
    if not isinstance(fifa.get("fifa16_player_id"), int):
        return None, "missing-unique-fifa16-player-identity"
    position = source_player.get("position")
    if position not in POSITION_TO_PROVISIONAL_ROLE:
        return None, "invalid-footballsquads-broad-position"
    shirt = fixture_player.get("shirt_number")
    try:
        shirt_number = int(str(shirt))
    except (TypeError, ValueError):
        return None, "invalid-opening-fixture-shirt-number"
    if not 0 <= shirt_number <= 99:
        return None, "invalid-opening-fixture-shirt-number"
    required_facts = ("birth_date", "nationality", "height_cm", "weight_kg")
    if any(not source_player.get(key) for key in required_facts):
        return None, "incomplete-footballsquads-player-facts"
    if not isinstance(source_player["height_cm"], int) or not isinstance(source_player["weight_kg"], int):
        return None, "invalid-footballsquads-player-facts"
    ratings = {
        "quality": values["rating"], "speed": values["sprint_speed"], "stamina": values["stamina"],
        "aggression": values["aggression"], "passing": values["short_pass"], "tackling": values["stand_tackle"],
        "heading": values["heading"], "shooting": values["finishing"], "dribbling": values["dribbling"],
        "handling": values["gk_handling"],
    }
    return {
        "slot_index": int(plan_row["slot_index"]),
        "player_carrier_id": int(plan_row["player_carrier_id"]),
        "person_id": f"fifa16-player-{fifa['fifa16_player_id']}",
        "name": str(source_player["name"]),
        "facts": {
            "birth_date": source_player["birth_date"],
            "nationality": source_player["nationality"],
            "height_cm": source_player["height_cm"],
            "weight_kg": source_player["weight_kg"],
            "primary_position": position,
            "fine_roles": POSITION_TO_PROVISIONAL_ROLE[position],
            "shirt_number": shirt_number,
        },
        "ratings": ratings,
        "source_ids": sorted([SOURCE_IDS["capture"], SOURCE_IDS["join"], SOURCE_IDS["reconciliation"], SOURCE_IDS["receipt"]]),
        "portrait": {"status": "unresolved"},
    }, None


def build_materialised_ledger(
    *, registry: Mapping[str, Any], base_ledger: Mapping[str, Any], source_join: Mapping[str, Any], reconciliation: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a valid blocked ledger and a complete materialisation report."""

    _validate_inputs(registry=registry, base_ledger=base_ledger, source_join=source_join, reconciliation=reconciliation)
    registry_sha = _sha(registry)
    join_sha = _sha(source_join)
    plan_by_carrier = _plan_index(reconciliation)
    registry_by_carrier = {int(row["carrier_id"]): row for row in registry["carriers"]}
    source_hashes = source_join["sources"]
    required_hashes = ("footballsquads_capture_sha256", "transfermarkt_opening_fixture_receipt_sha256")
    if any(not isinstance(source_hashes.get(key), str) or len(source_hashes[key]) != 64 for key in required_hashes):
        raise MaterialisationError("opening-fixture source join is missing required input hashes")

    candidate_players: list[tuple[int, dict[str, Any]]] = []
    skipped_players: list[dict[str, Any]] = []
    carrier_contexts: list[tuple[int, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
    for club in source_join["clubs"]:
        if not isinstance(club, dict):
            raise MaterialisationError("opening-fixture source join has a malformed club")
        reference = club.get("source_draft_reference")
        if not isinstance(reference, dict) or reference.get("status") != "source-draft-and-strict-player-reconciliation-linked":
            continue
        carrier_id = reference.get("draft_carrier_id")
        if not isinstance(carrier_id, int) or carrier_id not in registry_by_carrier:
            raise MaterialisationError("source join references an unknown fixed carrier")
        plan = plan_by_carrier.get(carrier_id)
        if plan is None:
            raise MaterialisationError("source join references a carrier without a strict player reconciliation plan")
        identity = club.get("strict_club_identity")
        if not isinstance(identity, dict) or identity.get("status") != "strict-footballsquads-club-identity-match":
            raise MaterialisationError("source-draft-linked club lacks a strict FootballSquads identity match")
        carrier_contexts.append((carrier_id, club, plan, registry_by_carrier[carrier_id]))
        for fixture_player, plan_row in _lineup_candidates(club, plan=plan):
            player, reason = _blocked_player(fixture_player=fixture_player, plan_row=plan_row)
            if player is None:
                skipped_players.append({
                    "carrier_id": carrier_id,
                    "slot_index": int(plan_row["slot_index"]),
                    "player_carrier_id": int(plan_row["player_carrier_id"]),
                    "player_name": plan_row["source_player"].get("name"),
                    "reason": reason,
                })
            else:
                candidate_players.append((carrier_id, player))

    # A shared JUG record is one write surface. If it belongs to more than one
    # fixed carrier, its historical identity needs an all-owner review before a
    # package compiler could safely act. Also keep two distinct fixed JUG IDs
    # from receiving one FIFA identity merely because names collided.
    owners: dict[int, list[int]] = defaultdict(list)
    for carrier in registry["carriers"]:
        for slot in carrier["roster_slots"]:
            owners[int(slot["player_carrier_id"])].append(int(carrier["carrier_id"]))
    fifa_people: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for carrier_id, player in candidate_players:
        fifa_people[str(player["person_id"])].append((carrier_id, player))
    filtered: list[tuple[int, dict[str, Any]]] = []
    for carrier_id, player in candidate_players:
        reasons: list[str] = []
        if len(owners[int(player["player_carrier_id"])]) != 1:
            reasons.append("shared-fixed-jug-carrier-requires-all-owner-review")
        if len(fifa_people[str(player["person_id"])]) != 1:
            reasons.append("fifa16-person-identity-reused-across-different-fixed-jug-carriers")
        if reasons:
            skipped_players.append({
                "carrier_id": carrier_id,
                "slot_index": int(player["slot_index"]),
                "player_carrier_id": int(player["player_carrier_id"]),
                "player_name": player["name"],
                "reason": ";".join(sorted(reasons)),
            })
        else:
            filtered.append((carrier_id, player))
    players_by_carrier: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for carrier_id, player in filtered:
        players_by_carrier[carrier_id].append(player)
    for players in players_by_carrier.values():
        players.sort(key=lambda row: int(row["slot_index"]))

    updates: list[dict[str, Any]] = []
    for carrier_id, club, _plan, registry_carrier in sorted(carrier_contexts):
        fixture = club["opening_fixture_facts"]
        source_club = club.get("transfermarkt_source_club")
        if not isinstance(source_club, dict) or not str(source_club.get("name") or "").strip():
            raise MaterialisationError("source-join club lacks the Transfermarkt source club name")
        source_status = fixture.get("source_status")
        blockers = {
            "2015-club-ground-and-capacity-source-required",
            "2015-era-kit-source-required",
            "2015-portrait-or-no-photo-decision-required",
            "foreign-competition-membership-preserve-only",
            "foreign-mode1-manager-entity-link-write-not-proven",
            "foreign-mode1-role-position-and-shirt-number-write-not-proven",
            "source-only-ledger-row-not-a-pm99-write-authorisation",
        }
        if source_status != "source-qualified":
            blockers.add("opening-fixture-source-incomplete")
        materialised_slots = {int(row["slot_index"]) for row in players_by_carrier.get(carrier_id, [])}
        fixed_slots = {int(row["slot_index"]) for row in registry_carrier["roster_slots"]}
        if materialised_slots != fixed_slots:
            blockers.add("fixed-roster-slots-without-complete-strict-opening-fixture-and-rating-evidence")
        updates.append({
            "carrier_id": carrier_id,
            "status": "blocked",
            "club": {
                "identity_key": f"source-club-carrier-{carrier_id}",
                "name": str(source_club["name"]),
                "full_name": str(source_club["name"]),
                "ground_name": "Unresolved 2015 ground",
                "seated_capacity": 0,
                "source_ids": sorted([SOURCE_IDS["capture"], SOURCE_IDS["join"], SOURCE_IDS["receipt"]]),
            },
            "manager": {
                "carrier_id": int(registry_carrier["baseline_club"]["active_manager_carrier_id"]),
                "person_id": f"review-manager-carrier-{int(registry_carrier['baseline_club']['active_manager_carrier_id'])}",
                "name": str(fixture.get("declared_manager") or "Unresolved 2015 manager"),
                "source_ids": sorted([SOURCE_IDS["join"], SOURCE_IDS["receipt"], SOURCE_IDS["registry"]]),
            },
            "kit": {
                "status": "unresolved",
                "reason": "No approved 2015/16 era-specific kit source is attached; inherited PM99 art must not be retained.",
            },
            "players": players_by_carrier.get(carrier_id, []),
            "blockers": sorted(blockers),
        })

    output = dict(base_ledger)
    output["sources"] = _source_rows(registry_sha=registry_sha, source_join=source_join) + [{
        "id": SOURCE_IDS["join"],
        "title": "Hash-locked strict FootballSquads/Transfermarkt opening-fixture source join",
        "kind": "other",
        "content_sha256": join_sha,
    }]
    output["sources"].sort(key=lambda row: row["id"])
    output["carrier_updates"] = updates
    try:
        ledger.validate_ledger(registry=registry, ledger=output)
    except ledger.WorldLedgerError as exc:
        raise MaterialisationError(f"materialised ledger is invalid: {exc}") from exc

    reason_counts = Counter(str(row["reason"]) for row in skipped_players)
    # ``candidate_players`` was counted before shared-JUG/person filtering;
    # the source-join count remains the authoritative exact-link total.
    source_coverage = source_join.get("coverage") or {}
    report = {
        "schema_version": REPORT_SCHEMA,
        "result": "blocked-fixed-carrier-ledger-materialised",
        "registry_sha256": registry_sha,
        "base_ledger_sha256": _sha(base_ledger),
        "opening_fixture_source_join_sha256": join_sha,
        "strict_player_reconciliation_sha256": _sha(reconciliation),
        "write_policy": "source-and-package-level-output-only; no PM99 file is read or written; blocked rows are not write authorisations",
        "coverage": {
            "strict_source_join_linked_carrier_count": len(updates),
            "source_qualified_linked_carrier_count": sum(
                int(club["opening_fixture_facts"].get("source_status") == "source-qualified")
                for _, club, _, _ in carrier_contexts
            ),
            "strict_opening_fixture_player_link_count": int(
                (source_coverage.get("lineup_player_reconciliation_status_counts") or {}).get("strict-normalised-source-name-unique", 0)
            ),
            "rating-complete-fixed-slot-candidate_count": len(candidate_players),
            "ledger_ready_fixed_slot_count": len(filtered),
            "ledger_ready_fixed_carrier_count": len(players_by_carrier),
            "blocked_carrier_row_count": len(updates),
            "blocked_player_row_count": sum(len(update["players"]) for update in updates),
            "deferred_player_row_count": len(skipped_players),
        },
        "deferred_player_rows_by_reason": dict(sorted(reason_counts.items())),
        "deferred_player_rows": sorted(skipped_players, key=lambda row: (int(row["carrier_id"]), int(row["slot_index"]), str(row["reason"]))),
        "remaining_blockers": [
            "Every carrier remains blocked: no permanent ground/capacity source, kit source or portrait/no-photo decision is supplied.",
            "The named fixture manager is a source fact only; mapping it to an immutable PM99 ENT carrier is not proven.",
            "Foreign mode-1 role, shirt, opening-XI and tactic-grid write paths remain unproven.",
            "No foreign competition membership, topology or roster ownership may change.",
        ],
    }
    return output, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--base-ledger", required=True, type=Path)
    parser.add_argument("--opening-fixture-source-join", required=True, type=Path)
    parser.add_argument("--player-reconciliation", required=True, type=Path)
    parser.add_argument("--output-ledger", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args(argv)
    registry, _ = _read_canonical(args.registry, label="fixed-carrier registry")
    base_ledger, _ = _read_canonical(args.base_ledger, label="empty world ledger")
    source_join, _ = _read_canonical(args.opening_fixture_source_join, label="opening-fixture source join")
    reconciliation, _ = _read_canonical(args.player_reconciliation, label="strict player reconciliation")
    try:
        output, report = build_materialised_ledger(
            registry=registry, base_ledger=base_ledger, source_join=source_join, reconciliation=reconciliation
        )
    except MaterialisationError as exc:
        parser.error(str(exc))
    ledger.write_canonical_json(args.output_ledger, output)
    ledger.write_canonical_json(args.output_report, report)
    print(json.dumps(report["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
