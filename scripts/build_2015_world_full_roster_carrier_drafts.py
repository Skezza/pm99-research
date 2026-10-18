#!/usr/bin/env python3
"""Build full fixed-roster, source-only drafts for strict 2015 fixture links.

This promotes the 77 source-draft links certified by the opening-fixture join
from XI/bench evidence to every immutable roster row in their corresponding
strict player-reconciliation plan.  The output is a package-review receipt;
it has no PM99 writer and no claim that an unresolved source candidate can be
written to a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


SCHEMA = "pm99-world-2015-full-fixed-roster-carrier-drafts-v1"
JOIN_SCHEMA = "pm99-world-2015-opening-fixture-source-join-v1"
RECONCILIATION_SCHEMA = "pm99-world-2015-source-player-reconciliation-v1"
ASSET_SCHEMA = "pm99-world-2015-asset-dispositions-v1"
RATING_FIELDS = (
    "rating", "sprint_speed", "stamina", "aggression", "short_pass",
    "stand_tackle", "heading", "finishing", "dribbling", "gk_handling",
)


class FullRosterDraftError(ValueError):
    """A source input cannot safely form a deterministic full-roster draft."""


def canonical_json_bytes(value: Any) -> bytes:
    return ledger.canonical_json_bytes(value)


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        return ledger.read_canonical_json(path, label=label)
    except ledger.WorldLedgerError as exc:
        raise FullRosterDraftError(str(exc)) from exc


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _plans(reconciliation: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA or not isinstance(reconciliation.get("carrier_plans"), list):
        raise FullRosterDraftError("strict player reconciliation has the wrong schema")
    result: dict[int, Mapping[str, Any]] = {}
    for plan in reconciliation["carrier_plans"]:
        if not isinstance(plan, dict) or not isinstance(plan.get("carrier_id"), int) or not isinstance(plan.get("rows"), list):
            raise FullRosterDraftError("strict player reconciliation has malformed carrier plans")
        if plan["carrier_id"] in result:
            raise FullRosterDraftError("strict player reconciliation has duplicate carrier plans")
        result[plan["carrier_id"]] = plan
    return result


def _asset_index(dispositions: Mapping[str, Any] | None) -> tuple[dict[int, Mapping[str, Any]], str | None]:
    if dispositions is None:
        return {}, None
    if dispositions.get("schema_version") != ASSET_SCHEMA or not isinstance(dispositions.get("clubs"), list):
        raise FullRosterDraftError("asset dispositions have the wrong schema")
    result: dict[int, Mapping[str, Any]] = {}
    for club in dispositions["clubs"]:
        if not isinstance(club, dict) or not isinstance(club.get("carrier_id"), int):
            raise FullRosterDraftError("asset dispositions contain a malformed club")
        if club["carrier_id"] in result:
            raise FullRosterDraftError("asset dispositions have duplicate carrier ids")
        result[club["carrier_id"]] = club
    return result, _sha(dispositions)


def _opening_player_index(club: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    facts = club.get("opening_fixture_facts")
    if not isinstance(facts, dict):
        raise FullRosterDraftError("source join club lacks opening fixture facts")
    result: dict[int, dict[str, Any]] = {}
    for lane in ("starting_lineup", "substitutes"):
        rows = facts.get(lane)
        if not isinstance(rows, list):
            raise FullRosterDraftError("source join fixture lineup is malformed")
        for row in rows:
            if not isinstance(row, dict):
                raise FullRosterDraftError("source join fixture has a malformed player")
            reference = row.get("player_reconciliation")
            if not isinstance(reference, dict) or reference.get("status") != "strict-normalised-source-name-unique":
                continue
            fixed = reference.get("player_reconciliation_row")
            if not isinstance(fixed, dict) or not isinstance(fixed.get("slot_index"), int):
                raise FullRosterDraftError("strict opening player reference lacks its slot")
            slot = int(fixed["slot_index"])
            if slot in result:
                raise FullRosterDraftError("source join maps multiple fixture players to one fixed slot")
            result[slot] = {"lineup_role": lane, "fixture_player": dict(row)}
    return result


def _rating_disposition(row: Mapping[str, Any]) -> dict[str, Any]:
    fifa = row.get("fifa16")
    if not isinstance(fifa, dict):
        raise FullRosterDraftError("reconciliation player row lacks FIFA disposition")
    values = fifa.get("fifa16_values")
    if isinstance(values, dict) and all(isinstance(values.get(field), int) for field in RATING_FIELDS):
        return {
            "status": "fifa16-complete-candidate",
            "fifa16_match_status": fifa.get("status"),
            "fifa16_player_id": fifa.get("fifa16_player_id"),
            "fifa16_name": fifa.get("fifa16_name"),
            "values": dict(values),
        }
    return {
        "status": "editorial-fallback-required",
        "fifa16_match_status": fifa.get("status"),
        "reason": "no complete uniquely reconciled FIFA16 rating candidate; do not infer or average a rating",
    }


def _asset_disposition(
    *, asset_club: Mapping[str, Any] | None, row: Mapping[str, Any]
) -> dict[str, Any]:
    if asset_club is not None and isinstance(asset_club.get("players"), list):
        for item in asset_club["players"]:
            if isinstance(item, dict) and item.get("slot_index") == row.get("slot_index") and item.get("player_carrier_id") == row.get("player_carrier_id"):
                return {"status": item.get("status"), "reason": item.get("reason"), "action": item.get("action"), "source_url": item.get("source_url")}
    fifa = row.get("fifa16") if isinstance(row.get("fifa16"), dict) else {}
    url = fifa.get("fifa16_headshot_url")
    if url:
        return {"status": "pending-source-materialisation", "reason": "identity-safe FIFA16 URL exists but no reviewed asset disposition was supplied", "action": "no-write", "source_url": url}
    return {"status": "native-no-photo-review-required", "reason": "no reviewed asset disposition or identity-safe FIFA16 URL", "action": "no-write", "source_url": None}


def build_full_roster_drafts(
    *, source_join: Mapping[str, Any], reconciliation: Mapping[str, Any], asset_dispositions: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Materialise all strict-linked fixed roster rows with explicit fallbacks."""

    if source_join.get("schema_version") != JOIN_SCHEMA or not isinstance(source_join.get("clubs"), list):
        raise FullRosterDraftError("opening-fixture source join has the wrong schema")
    sources = source_join.get("sources")
    if not isinstance(sources, dict) or sources.get("strict_player_reconciliation_sha256") != _sha(reconciliation):
        raise FullRosterDraftError("opening-fixture source join is not bound to this strict player reconciliation")
    plans = _plans(reconciliation)
    assets, asset_sha = _asset_index(asset_dispositions)
    drafts: list[dict[str, Any]] = []
    seen: set[int] = set()
    rating_counts: Counter[str] = Counter()
    asset_counts: Counter[str] = Counter()
    for club in sorted(source_join["clubs"], key=lambda row: int((row.get("source_draft_reference") or {}).get("draft_carrier_id") or 0)):
        if not isinstance(club, dict):
            raise FullRosterDraftError("opening-fixture source join has a malformed club")
        reference = club.get("source_draft_reference")
        if not isinstance(reference, dict) or reference.get("status") != "source-draft-and-strict-player-reconciliation-linked":
            continue
        carrier_id = reference.get("draft_carrier_id")
        if not isinstance(carrier_id, int) or carrier_id in seen:
            raise FullRosterDraftError("opening-fixture source join has duplicate or malformed draft carrier references")
        seen.add(carrier_id)
        plan = plans.get(carrier_id)
        if plan is None:
            raise FullRosterDraftError(f"linked carrier {carrier_id} has no strict player reconciliation plan")
        fixture = club.get("opening_fixture_facts")
        identity = club.get("strict_club_identity")
        source_club = club.get("transfermarkt_source_club")
        if not isinstance(fixture, dict) or not isinstance(identity, dict) or not isinstance(source_club, dict):
            raise FullRosterDraftError("linked source-join club has incomplete provenance")
        opening_by_slot = _opening_player_index(club)
        asset_club = assets.get(carrier_id)
        players: list[dict[str, Any]] = []
        source_unresolved = 0
        for row in sorted(plan["rows"], key=lambda item: int(item.get("slot_index") or 0)):
            if not isinstance(row, dict) or not isinstance(row.get("source_player"), dict):
                raise FullRosterDraftError(f"carrier {carrier_id} has malformed strict player row")
            rating = _rating_disposition(row)
            asset = _asset_disposition(asset_club=asset_club, row=row)
            rating_counts[str(rating["status"])] += 1
            asset_counts[str(asset["status"])] += 1
            source_unresolved += int(bool(row["source_player"].get("unresolved_fields")))
            opening = opening_by_slot.get(int(row["slot_index"]))
            players.append({
                "slot_index": int(row["slot_index"]),
                "player_carrier_id": int(row["player_carrier_id"]),
                "player_family": row.get("player_family"),
                "immutable_row_flag": row.get("immutable_row_flag"),
                "source_squad_index": row.get("source_squad_index"),
                "source_player": dict(row["source_player"]),
                "rating_disposition": rating,
                "portrait_disposition": asset,
                "opening_fixture_presence": opening if opening is not None else {"status": "not-in-strictly-reconciled-opening-xi-or-bench"},
            })
        blockers = {
            "2015-club-ground-and-capacity-source-required",
            "2015-era-kit-source-required",
            "2015-manager-entity-link-write-not-proven",
            "foreign-competition-membership-preserve-only",
            "foreign-mode1-role-position-shirt-and-tactics-write-not-proven",
            "source-only-full-roster-draft-not-a-pm99-write-authorisation",
        }
        if fixture.get("source_status") != "source-qualified":
            blockers.add("opening-fixture-source-incomplete")
        if source_unresolved:
            blockers.add("footballsquads-player-facts-incomplete")
        if any(player["rating_disposition"]["status"] != "fifa16-complete-candidate" for player in players):
            blockers.add("player-rating-editorial-fallback-required")
        if any(player["portrait_disposition"]["status"] not in {"native-no-photo", "approved-crop-candidate"} for player in players):
            blockers.add("portrait-source-or-no-photo-decision-required")
        kit = dict((asset_club or {}).get("kit") or {
            "status": "blocked-no-reviewed-2015-kit",
            "reason": "no asset disposition supplied; a reviewed era kit is required",
            "action": "no-write",
        })
        if kit.get("status") != "approved-era-kit":
            blockers.add("2015-era-kit-source-required")
        # No current input can clear all source/write blockers. Keeping this
        # calculation explicit makes a later approved kit/portrait amendment
        # auditable instead of changing status by convention.
        status = "complete" if not blockers else "blocked"
        drafts.append({
            "carrier_id": carrier_id,
            "status": status,
            "club": {
                "strict_identity": dict(identity),
                "transfermarkt_source_club": dict(source_club),
                "reported_opening_match_stadium": fixture.get("reported_match_stadium"),
                "reported_opening_match_stadium_interpretation": fixture.get("reported_match_stadium_interpretation"),
                "first_home_fixture_ground_evidence": dict(club.get("first_home_fixture_ground_evidence") or {}),
                "ground_policy": "fixture-stadium evidence only; no permanent club-ground or capacity claim",
            },
            "manager": {
                "name": fixture.get("declared_manager"),
                "source_status": fixture.get("source_status"),
                "source_url": fixture.get("source_url"),
                "policy": "dated fixture manager fact only; no PM99 ENT relink or write claim",
            },
            "opening_fixture": {
                "date": fixture.get("date"), "declared_formation": fixture.get("declared_formation"),
                "source_game_id": fixture.get("source_game_id"), "source_status": fixture.get("source_status"),
                "source_blockers": list(fixture.get("source_blockers") or []),
                "lineup_counts": dict(fixture.get("lineup_counts") or {}), "source_url": fixture.get("source_url"),
            },
            "kit_disposition": kit,
            "players": players,
            "blockers": sorted(blockers),
        })
    status_counts = Counter(str(row["status"]) for row in drafts)
    return {
        "schema_version": SCHEMA,
        "policy": "strict-club-and-player-reconciliation-only; full-fixed-roster-source-draft; explicit-editorial-fallbacks; no-pm99-write; no-permanent-ground-or-capacity-claim",
        "sources": {
            "opening_fixture_source_join_sha256": _sha(source_join),
            "strict_player_reconciliation_sha256": _sha(reconciliation),
            "asset_dispositions_sha256": asset_sha,
            "footballsquads_capture_sha256": sources.get("footballsquads_capture_sha256"),
            "transfermarkt_opening_fixture_receipt_sha256": sources.get("transfermarkt_opening_fixture_receipt_sha256"),
        },
        "coverage": {
            "strict_linked_carrier_count": len(drafts),
            "fixed_roster_slot_count": sum(len(row["players"]) for row in drafts),
            "carrier_status_counts": dict(sorted(status_counts.items())),
            "rating_disposition_counts": dict(sorted(rating_counts.items())),
            "portrait_disposition_counts": dict(sorted(asset_counts.items())),
            "compiler_package_ready_carrier_count": status_counts["complete"],
            "compiler_package_blocked_carrier_count": status_counts["blocked"],
        },
        "carrier_drafts": drafts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opening-fixture-source-join", required=True, type=Path)
    parser.add_argument("--player-reconciliation", required=True, type=Path)
    parser.add_argument("--asset-dispositions", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    source_join, _ = _read_canonical(args.opening_fixture_source_join, label="opening-fixture source join")
    reconciliation, _ = _read_canonical(args.player_reconciliation, label="strict player reconciliation")
    assets = None
    if args.asset_dispositions is not None:
        assets, _ = _read_canonical(args.asset_dispositions, label="asset dispositions")
    try:
        result = build_full_roster_drafts(source_join=source_join, reconciliation=reconciliation, asset_dispositions=assets)
    except FullRosterDraftError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
