#!/usr/bin/env python3
"""Join 2015 opening-fixture facts to dated squad sources without a PM99 write.

The Transfermarkt receipt and FootballSquads capture are independent historic
sources.  This helper only joins a club when the country-scoped
``strict_club_key`` is identical.  In particular, it does not turn an
abbreviation, a later club name, or a plausible player into a fuzzy match.

When an exact FootballSquads club is also selected by the existing source
carrier draft, its opening-XI and bench rows are linked back to the already
strict player-reconciliation rows.  Those links are source-review references,
not PM99 carrier/slot assignments and not writer instructions.
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

from scripts.audit_world_2015_source_coverage import strict_club_key  # noqa: E402
from scripts.reconcile_2015_world_source_player_facts import normalise_name  # noqa: E402


SCHEMA = "pm99-world-2015-opening-fixture-source-join-v1"
SOURCE_CAPTURE_SCHEMA = "pm99-footballsquads-season-capture-v1"
DRAFT_SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"
RECONCILIATION_SCHEMA = "pm99-world-2015-source-player-reconciliation-v1"
FIXTURE_RECEIPT_SCHEMA = "pm99-world-2015-transfermarkt-opening-fixtures-v1"
SELECTOR_FIELDS = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")


class JoinError(ValueError):
    """An input fails the hash-locked source-only join contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JoinError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise JoinError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> dict[str, str]:
    result = {field: str(value.get(field) or "") for field in SELECTOR_FIELDS}
    if not all(result.values()):
        raise JoinError("FootballSquads club/source selector is incomplete")
    return result


def _selector_key(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(_selector(value)[field] for field in SELECTOR_FIELDS)


def _strict_club_identity(value: Mapping[str, Any]) -> tuple[str, str]:
    country = str(value.get("country_catalog") or "")
    name = strict_club_key(value.get("club_name") or value.get("name"))
    if not country or not name:
        raise JoinError("club lacks a country-scoped strict name identity")
    return country, name


def _fixture_identity(value: Mapping[str, Any]) -> tuple[str, str]:
    country = str(value.get("country_catalog") or "")
    source_club = value.get("source_club")
    if not isinstance(source_club, dict):
        raise JoinError("opening-fixture receipt club lacks source_club")
    raw_name = str(source_club.get("name") or "")
    name = strict_club_key(raw_name)
    if not name and raw_name.strip():
        # ``strict_club_key`` intentionally restricts its comparison space to
        # ASCII rather than transliterating a club name.  Preserve such a
        # receipt row as an explicit non-comparable review identity instead
        # of silently inventing a transliteration (for example Cyrillic to
        # Latin) that could amount to a fuzzy map.
        name = "non-comparable-under-strict-club-key:" + raw_name.casefold()
    if not country or not name:
        raise JoinError("opening-fixture receipt club lacks a country-scoped strict name identity")
    return country, name


def _index_unique_capture_clubs(capture: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    if capture.get("schema_version") != SOURCE_CAPTURE_SCHEMA or not isinstance(capture.get("clubs"), list):
        raise JoinError("FootballSquads capture has the wrong schema")
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str]] = set()
    for raw in capture["clubs"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
            raise JoinError("FootballSquads capture has a malformed club")
        key = _strict_club_identity(raw)
        if key in indexed:
            duplicates.add(key)
        else:
            indexed[key] = raw
    # The actual overlap countries have one source row per strict identity.
    # A duplicate must remain unresolved rather than receiving an arbitrary
    # competition row.  Keep it out of the index entirely.
    for key in duplicates:
        indexed.pop(key, None)
    return indexed


def _index_draft_links(
    draft: Mapping[str, Any], *, source_capture_sha256: str
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    if draft.get("schema_version") != DRAFT_SCHEMA or not isinstance(draft.get("proposals"), list):
        raise JoinError("source carrier draft has the wrong schema")
    if draft.get("source_capture_sha256") != source_capture_sha256:
        raise JoinError("source carrier draft is not bound to this FootballSquads capture")
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for proposal in draft["proposals"]:
        if not isinstance(proposal, dict) or proposal.get("status") != "source-squad-ready":
            continue
        selector = proposal.get("source_selector")
        if not isinstance(selector, dict):
            raise JoinError("source-squad-ready draft proposal lacks a source selector")
        key = _selector_key(selector)
        if key in result:
            raise JoinError("source carrier draft has duplicate selected source selectors")
        result[key] = proposal
    return result


def _index_reconciliation_plans(
    reconciliation: Mapping[str, Any], *, source_capture_sha256: str, source_draft_sha256: str
) -> dict[int, dict[str, Any]]:
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA or not isinstance(reconciliation.get("carrier_plans"), list):
        raise JoinError("player reconciliation has the wrong schema")
    sources = reconciliation.get("sources")
    if not isinstance(sources, dict) or sources.get("source_capture_sha256") != source_capture_sha256:
        raise JoinError("player reconciliation is not bound to this FootballSquads capture")
    if sources.get("source_draft_sha256") != source_draft_sha256:
        raise JoinError("player reconciliation is not bound to this source carrier draft")
    plans: dict[int, dict[str, Any]] = {}
    for plan in reconciliation["carrier_plans"]:
        if not isinstance(plan, dict) or not isinstance(plan.get("rows"), list):
            raise JoinError("player reconciliation has a malformed carrier plan")
        carrier_id = plan.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id in plans:
            raise JoinError("player reconciliation has duplicate or malformed carrier ids")
        plans[carrier_id] = plan
    return plans


def _lineup_rows(rows: Any, *, plan: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], Counter[str]]:
    if not isinstance(rows, list):
        raise JoinError("opening fixture lineup is malformed")
    source_index: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    if plan is not None:
        for row in plan["rows"]:
            player = row.get("source_player")
            if not isinstance(player, dict):
                raise JoinError("player reconciliation row lacks a source player")
            key = normalise_name(player.get("name"))
            if key:
                source_index[key].append(row)
    result: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for source_row in rows:
        if not isinstance(source_row, dict):
            raise JoinError("opening fixture has a malformed player row")
        copied = dict(source_row)
        candidates = source_index.get(normalise_name(source_row.get("name")), [])
        if plan is None:
            status = "not-attempted-no-source-draft-and-player-plan"
            detail: dict[str, Any] = {"status": status}
        elif len(candidates) == 1:
            candidate = candidates[0]
            status = "strict-normalised-source-name-unique"
            detail = {
                "status": status,
                "source_player_name": candidate["source_player"]["name"],
                "source_squad_index": candidate["source_squad_index"],
                "player_reconciliation_row": {
                    "slot_index": candidate["slot_index"],
                    "player_carrier_id": candidate["player_carrier_id"],
                    "fifa16_status": candidate["fifa16"]["status"],
                },
                "interpretation": "source-review reference only; not a PM99 player-slot assignment",
            }
        elif not candidates:
            status = "requires-review-no-strict-source-player-name-match"
            detail = {"status": status}
        else:
            status = "requires-review-ambiguous-strict-source-player-name"
            detail = {"status": status, "candidate_source_player_names": sorted(str(row["source_player"]["name"]) for row in candidates)}
        counts[status] += 1
        copied["player_reconciliation"] = detail
        result.append(copied)
    return result, counts


def _opening_facts(fixture: Mapping[str, Any], *, plan: Mapping[str, Any] | None) -> tuple[dict[str, Any], Counter[str]]:
    required = ("date", "declared_manager", "declared_formation", "reported_match_stadium", "source_game_id", "source_status", "source_url")
    if any(field not in fixture for field in required):
        raise JoinError("opening fixture lacks required source facts")
    starting, starting_counts = _lineup_rows(fixture.get("starting_lineup"), plan=plan)
    substitutes, substitute_counts = _lineup_rows(fixture.get("substitutes"), plan=plan)
    facts = {field: fixture[field] for field in required}
    facts["source_blockers"] = list(fixture.get("source_blockers") or [])
    facts["lineup_counts"] = dict(fixture.get("lineup_counts") or {})
    facts["starting_lineup"] = starting
    facts["substitutes"] = substitutes
    facts["reported_match_stadium_interpretation"] = "fixture fact only; not a persistent club-ground or capacity claim"
    return facts, starting_counts + substitute_counts


def build_source_join(
    *,
    source_capture: Mapping[str, Any],
    source_draft: Mapping[str, Any],
    player_reconciliation: Mapping[str, Any],
    opening_fixture_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic source-only join from already loaded canonical inputs."""

    capture_sha = hashlib.sha256(canonical_json_bytes(dict(source_capture))).hexdigest()
    draft_sha = hashlib.sha256(canonical_json_bytes(dict(source_draft))).hexdigest()
    reconciliation_sha = hashlib.sha256(canonical_json_bytes(dict(player_reconciliation))).hexdigest()
    receipt_sha = hashlib.sha256(canonical_json_bytes(dict(opening_fixture_receipt))).hexdigest()
    capture_by_identity = _index_unique_capture_clubs(source_capture)
    draft_by_selector = _index_draft_links(source_draft, source_capture_sha256=capture_sha)
    plans_by_carrier = _index_reconciliation_plans(
        player_reconciliation, source_capture_sha256=capture_sha, source_draft_sha256=draft_sha
    )
    if opening_fixture_receipt.get("schema_version") != FIXTURE_RECEIPT_SCHEMA or not isinstance(opening_fixture_receipt.get("clubs"), list):
        raise JoinError("opening-fixture receipt has the wrong schema")

    clubs: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    player_status_counts: Counter[str] = Counter()
    matched = 0
    carrier_linked = 0
    exact_without_draft = 0
    incomplete = 0
    seen_receipt_identities: set[tuple[str, str]] = set()
    for receipt_club in sorted(opening_fixture_receipt["clubs"], key=lambda row: (str(row.get("country_catalog")), str((row.get("source_club") or {}).get("name")))):
        if not isinstance(receipt_club, dict):
            raise JoinError("opening-fixture receipt has a malformed club")
        identity = _fixture_identity(receipt_club)
        if identity in seen_receipt_identities:
            raise JoinError("opening-fixture receipt has duplicate strict club identities")
        seen_receipt_identities.add(identity)
        fixture = receipt_club.get("opening_fixture")
        if not isinstance(fixture, dict):
            raise JoinError("opening-fixture receipt club lacks opening_fixture")
        source_club = receipt_club["source_club"]
        footballsquads_club = capture_by_identity.get(identity)
        draft: Mapping[str, Any] | None = None
        plan: Mapping[str, Any] | None = None
        identity_record: dict[str, Any]
        carrier_reference: dict[str, Any]
        if footballsquads_club is None:
            identity_record = {
                "status": "requires-review-no-strict-footballsquads-club-identity-match",
                "country_catalog": identity[0],
                "strict_club_key": identity[1],
            }
            carrier_reference = {"status": "not-attempted-no-strict-footballsquads-club-identity-match"}
            review_queue.append({
                "kind": "unmatched-strict-club-identity",
                "country_catalog": identity[0],
                "transfermarkt_club_name": source_club.get("name"),
                "strict_club_key": identity[1],
                "action": "capture an explicit identity decision; do not fuzzy-map this club",
            })
        else:
            matched += 1
            selector = _selector(footballsquads_club)
            identity_record = {
                "status": "strict-footballsquads-club-identity-match",
                "country_catalog": identity[0],
                "strict_club_key": identity[1],
                "footballsquads_club_name": footballsquads_club["club_name"],
                "footballsquads_source_selector": selector,
            }
            draft = draft_by_selector.get(_selector_key(selector))
            if draft is None:
                exact_without_draft += 1
                carrier_reference = {
                    "status": "strict-club-match-without-selected-carrier-draft",
                    "interpretation": "no PM99 carrier or player-plan reference is created",
                }
            else:
                carrier_id = draft.get("carrier_id")
                if not isinstance(carrier_id, int):
                    raise JoinError("selected source carrier draft has a malformed carrier id")
                plan = plans_by_carrier.get(carrier_id)
                if plan is None:
                    raise JoinError(f"selected source carrier draft {carrier_id} has no strict player reconciliation plan")
                carrier_linked += 1
                carrier_reference = {
                    "status": "source-draft-and-strict-player-reconciliation-linked",
                    "draft_carrier_id": carrier_id,
                    "interpretation": "existing source-only draft reference; not a PM99 carrier assignment or writer instruction",
                }
        opening_facts, statuses = _opening_facts(fixture, plan=plan)
        player_status_counts.update(statuses)
        first_home = receipt_club.get("first_home_fixture_ground_evidence")
        if not isinstance(first_home, dict):
            raise JoinError("opening-fixture receipt club lacks first-home-fixture ground evidence")
        club = {
            "transfermarkt_source_club": {"id": source_club.get("id"), "name": source_club.get("name")},
            "country_catalog": identity[0],
            "strict_club_identity": identity_record,
            "source_draft_reference": carrier_reference,
            "opening_fixture_facts": opening_facts,
            "first_home_fixture_ground_evidence": dict(first_home),
            "ground_evidence_interpretation": "reported fixture stadium evidence only; no permanent club-ground or capacity claim",
            "compiler_disposition": "source-fact-only; no PM99 file, carrier assignment, player-slot assignment, topology, tactic-grid, ground or capacity write",
        }
        clubs.append(club)
        if fixture.get("source_status") != "source-qualified":
            incomplete += 1
            review_queue.append({
                "kind": "incomplete-opening-fixture-facts",
                "country_catalog": identity[0],
                "transfermarkt_club_name": source_club.get("name"),
                "source_blockers": list(fixture.get("source_blockers") or []),
                "action": "obtain explicit opening XI and declared formation evidence; do not infer either",
            })
    return {
        "schema_version": SCHEMA,
        "policy": "country-scoped-strict-club-identity-only; unique-normalised-source-player-name-only; source-fact-only; no-fuzzy-map; no-pm99-write; no-permanent-ground-or-capacity-claim",
        "sources": {
            "footballsquads_capture_sha256": capture_sha,
            "source_carrier_draft_sha256": draft_sha,
            "strict_player_reconciliation_sha256": reconciliation_sha,
            "transfermarkt_opening_fixture_receipt_sha256": receipt_sha,
            "transfermarkt_dataset_sha256": (opening_fixture_receipt.get("source") or {}).get("database_sha256"),
        },
        "coverage": {
            "transfermarkt_receipt_club_count": len(clubs),
            "strict_footballsquads_club_identity_match_count": matched,
            "unmatched_strict_club_identity_count": len(clubs) - matched,
            "strict_identity_matches_with_source_draft_and_player_reconciliation_count": carrier_linked,
            "strict_identity_matches_without_selected_carrier_draft_count": exact_without_draft,
            "incomplete_opening_fixture_fact_count": incomplete,
            "review_queue_count": len(review_queue),
            "lineup_player_reconciliation_status_counts": dict(sorted(player_status_counts.items())),
        },
        "clubs": clubs,
        "review_queue": sorted(review_queue, key=lambda row: (str(row["kind"]), str(row["country_catalog"]), str(row["transfermarkt_club_name"]))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--footballsquads-capture", required=True, type=Path)
    parser.add_argument("--source-draft", required=True, type=Path)
    parser.add_argument("--player-reconciliation", required=True, type=Path)
    parser.add_argument("--opening-fixture-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        capture, _ = _read_canonical(args.footballsquads_capture, label="FootballSquads capture")
        draft, _ = _read_canonical(args.source_draft, label="source carrier draft")
        reconciliation, _ = _read_canonical(args.player_reconciliation, label="player reconciliation")
        receipt, _ = _read_canonical(args.opening_fixture_receipt, label="opening-fixture receipt")
        result = build_source_join(
            source_capture=capture,
            source_draft=draft,
            player_reconciliation=reconciliation,
            opening_fixture_receipt=receipt,
        )
    except JoinError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
