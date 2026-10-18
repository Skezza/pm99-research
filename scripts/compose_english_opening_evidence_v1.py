#!/usr/bin/env python3
"""Bind newer English lineup/manager overlays into a squad preallocation.

The historical capture programme deliberately keeps whole-season squads,
opening-match lineups and manager evidence as separate immutable documents.
This stage composes them without changing any input.  A player present in the
sourced first XI but absent from the whole-season squad is retained as a
minimal source-backed row; secondary facts remain explicit gaps.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-english-opening-evidence-composition-v1"
PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
RECONCILIATION_SCHEMA = "pm99-transfermarkt-opening-lineup-reconciliation-v1"
MANAGER_SCHEMA = "pm99-opening-manager-ledger-v1"
LINEUP_SCHEMAS = {
    "pm99-transfermarkt-opening-lineup-source-v1",
    "pm99-composed-opening-lineup-source-v1",
}
ENGLISH_COMPETITIONS = {
    "faprem", "prem", "premier", "champ", "championship", "flcham",
    "d1", "lge1", "league1", "flone", "d2", "lge2", "league2",
    "fltwo", "d3",
}


class CompositionError(ValueError):
    """The evidence documents cannot be composed without ambiguity."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise CompositionError(f"input must be a JSON object: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(
        str(row.get(key) or "").strip()
        for key in ("country_catalog", "competition_catalog", "club_name")
    )
    if not all(result):
        raise CompositionError("source selector is incomplete")
    return result  # type: ignore[return-value]


def source_position(row: Mapping[str, Any]) -> str | None:
    direct = str(row.get("source_position") or "").strip().upper()
    if direct in {"G", "D", "M", "F"}:
        return direct
    text = str(row.get("source_position_group") or "").casefold()
    if "goal" in text:
        return "G"
    if "defen" in text or "back" in text:
        return "D"
    if "mid" in text:
        return "M"
    if any(word in text for word in ("forward", "attack", "striker")):
        return "F"
    return None


def _lineup_index(lineups: list[Mapping[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for document in lineups:
        if document.get("schema_version") not in LINEUP_SCHEMAS:
            raise CompositionError("lineup source schema is unsupported")
        rows = document.get("clubs")
        if not isinstance(rows, list):
            raise CompositionError("lineup source clubs must be a list")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("source_selector"), Mapping):
                raise CompositionError("lineup source row is malformed")
            result.setdefault(selector(row["source_selector"]), []).append(row)
    return result


def _choose_lineup(
    candidates: list[dict[str, Any]], reconciliation: Mapping[str, Any]
) -> dict[str, Any] | None:
    match_id = str(reconciliation.get("source_match_id") or "")
    exact = [row for row in candidates if str(row.get("source_match_id") or "") == match_id]
    choices = exact or candidates
    if not choices:
        return None
    signatures = {digest(row) for row in choices}
    if len(signatures) > 1 and not exact:
        raise CompositionError("multiple lineup rows exist without a matching source match ID")
    return choices[-1]


def _new_player(source: Mapping[str, Any], index: int) -> dict[str, Any]:
    name = str(source.get("display_name") or source.get("source_name") or "").strip()
    if not name:
        raise CompositionError("opening-XI source player has no display name")
    position = source_position(source)
    facts = {
        "shirt_number": source.get("source_shirt_number"),
        "name": name,
        "nationality": None,
        "position": position,
        "height_cm": None,
        "weight_kg": None,
        "birth_date": None,
        "unresolved_fields": [
            field
            for field, value in (
                ("shirt_number", source.get("source_shirt_number")),
                ("nationality", None),
                ("primary_position", position),
                ("height_cm", None),
                ("weight_kg", None),
                ("birth_date", None),
            )
            if value is None
        ],
    }
    identity = {
        "source_player_id": str(source.get("source_player_id") or ""),
        "source_url": str(source.get("source_url") or ""),
        "facts": facts,
    }
    return {
        "source_row_index": index,
        "source_row_sha256": digest(identity),
        "facts": facts,
        "opening_xi_origin": "sourced-first-fixture-lineup",
        "opening_source_player_id": identity["source_player_id"],
        "proof": {
            "grade": "source-captured",
            "source_url": identity["source_url"],
        },
    }


def compose(
    *, preallocation: Mapping[str, Any], reconciliation: Mapping[str, Any],
    managers: Mapping[str, Any], lineup_documents: list[Mapping[str, Any]],
    input_hashes: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if preallocation.get("schema_version") != PREALLOCATION_SCHEMA:
        raise CompositionError(f"preallocation must use {PREALLOCATION_SCHEMA}")
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA:
        raise CompositionError(f"reconciliation must use {RECONCILIATION_SCHEMA}")
    if managers.get("schema_version") != MANAGER_SCHEMA:
        raise CompositionError(f"manager ledger must use {MANAGER_SCHEMA}")

    result_preallocation = copy.deepcopy(dict(preallocation))
    result_reconciliation = copy.deepcopy(dict(reconciliation))
    result_managers = copy.deepcopy(dict(managers))
    source_clubs = result_preallocation.get("source_clubs")
    reconciliation_rows = result_reconciliation.get("clubs")
    manager_rows = result_managers.get("managers")
    if not isinstance(source_clubs, list) or not isinstance(reconciliation_rows, list) or not isinstance(manager_rows, list):
        raise CompositionError("one or more evidence row collections are malformed")

    clubs_by_key = {
        selector(row["selector"]): row
        for row in source_clubs
        if isinstance(row, dict) and isinstance(row.get("selector"), Mapping)
    }
    reconciliation_by_key = {
        selector(row["source_selector"]): row
        for row in reconciliation_rows
        if isinstance(row, dict) and isinstance(row.get("source_selector"), Mapping)
    }
    managers_by_key = {
        selector(row["source_selector"]): row
        for row in manager_rows
        if isinstance(row, dict) and isinstance(row.get("source_selector"), Mapping)
    }
    lineups_by_key = _lineup_index(lineup_documents)
    english_keys = sorted(
        key for key in clubs_by_key
        if key[0] == "eng" and key[1] in ENGLISH_COMPETITIONS
    )

    added_players = 0
    removed_duplicate_squad_rows = 0
    completed_xis = 0
    gaps: list[dict[str, Any]] = []
    for key in english_keys:
        club = clubs_by_key[key]
        reconciled = reconciliation_by_key.get(key)
        manager = managers_by_key.get(key)
        lineup = _choose_lineup(lineups_by_key.get(key, []), reconciled or {})
        if lineup is None:
            gaps.append({"club": key[2], "lane": "opening", "reason": "lineup-source-missing"})
            continue
        if reconciled is None:
            # A later source overlay can supply a complete XI after the older
            # reconciliation was frozen. The composer performs the same exact
            # name/source-id joins below and records the new reconciliation;
            # it does not need a placeholder row to have existed beforehand.
            reconciled = {"source_selector": copy.deepcopy(lineup["source_selector"])}
            reconciliation_rows.append(reconciled)
            reconciliation_by_key[key] = reconciled
        starters = lineup.get("starting_xi")
        if not isinstance(starters, list) or len(starters) != 11:
            gaps.append({"club": key[2], "lane": "opening", "reason": "source-first-xi-is-not-eleven"})
            continue
        if manager is None or not str(manager.get("manager_name") or "").strip():
            gaps.append({"club": key[2], "lane": "manager", "reason": "dated-manager-missing"})

        players = club.get("players")
        if not isinstance(players, list):
            raise CompositionError(f"club has no player rows: {key[2]}")
        for player in players:
            if isinstance(player, dict):
                player.pop("opening_xi_order", None)
                player.pop("opening_xi_origin", None)

        ordered: list[dict[str, Any]] = []
        remaining = [row for row in players if isinstance(row, dict)]
        next_source_row_index = max(
            (
                int(row.get("source_row_index"))
                for row in remaining
                if isinstance(row.get("source_row_index"), int)
            ),
            default=-1,
        ) + 1
        for order, source_player in enumerate(starters, 1):
            if not isinstance(source_player, Mapping):
                raise CompositionError("lineup starter is malformed")
            source_id = str(source_player.get("source_player_id") or "")
            name = str(source_player.get("display_name") or source_player.get("source_name") or "").strip()
            matches = [
                row for row in remaining
                if source_id and str(row.get("opening_source_player_id") or "") == source_id
            ]
            if not matches:
                matches = [
                    row for row in remaining
                    if str((row.get("facts") or {}).get("name") or "").strip().casefold() == name.casefold()
                ]
            if len(matches) > 1:
                raise CompositionError(f"opening player matches multiple squad rows: {key[2]} / {name}")
            if matches:
                player = matches[0]
                remaining.remove(player)
                facts = player.get("facts")
                if isinstance(facts, dict) and not facts.get("position") and source_position(source_player):
                    facts["position"] = source_position(source_player)
                    unresolved = facts.get("unresolved_fields")
                    if isinstance(unresolved, list):
                        facts["unresolved_fields"] = [value for value in unresolved if value != "primary_position"]
            else:
                player = _new_player(source_player, next_source_row_index)
                next_source_row_index += 1
                added_players += 1
            player["opening_xi_order"] = order
            player["opening_xi_origin"] = "sourced-first-fixture-lineup"
            player["opening_source_player_id"] = source_id
            ordered.append(player)
        unique_remaining: list[dict[str, Any]] = []
        seen_names = {
            str((player.get("facts") or {}).get("name") or "").strip().casefold()
            for player in ordered
        }
        for player in remaining:
            player.pop("opening_source_player_id", None)
            name_key = str((player.get("facts") or {}).get("name") or "").strip().casefold()
            if name_key and name_key in seen_names:
                removed_duplicate_squad_rows += 1
                continue
            if name_key:
                seen_names.add(name_key)
            unique_remaining.append(player)
        club["players"] = ordered + unique_remaining
        club["opening_fixture_date"] = str(lineup.get("first_league_fixture_date") or "")
        club["opening_source_match_id"] = str(lineup.get("source_match_id") or "")
        club["opening_xi_complete"] = True
        club["opening_xi_player_count"] = 11
        club["opening_xi_blockers"] = []
        reconciled["starting_xi"] = copy.deepcopy(starters)
        reconciled["starting_xi_reconciled"] = True
        reconciled["unresolved_first_fixture_players"] = []
        reconciled["first_league_fixture_date"] = str(lineup.get("first_league_fixture_date") or "")
        reconciled["lineup_source_url"] = str(lineup.get("lineup_source_url") or "")
        reconciled["source_match_id"] = str(lineup.get("source_match_id") or "")
        completed_xis += 1

    lineup_bundle_sha = digest({"lineup_source_sha256": input_hashes["lineup_sources"]})
    result_reconciliation.setdefault("sources", {})["lineup_capture_sha256"] = lineup_bundle_sha
    result_preallocation.setdefault("sources", {})["opening_lineup_sha256"] = lineup_bundle_sha
    result_preallocation["sources"]["opening_reconciliation_sha256"] = digest(result_reconciliation)
    result_managers["sources"] = {
        **dict(result_managers.get("sources") or {}),
        "opening_lineup_receipt_sha256": lineup_bundle_sha,
        "squad_source_capture_sha256": result_preallocation["sources"].get("source_capture_sha256"),
    }
    audit = {
        "schema_version": SCHEMA,
        "season": result_preallocation.get("season"),
        "inputs": dict(input_hashes),
        "coverage": {
            "english_club_count": len(english_keys),
            "completed_opening_xi_count": completed_xis,
            "dated_manager_count": sum(key in managers_by_key for key in english_keys),
            "added_opening_player_count": added_players,
            "removed_duplicate_squad_row_count": removed_duplicate_squad_rows,
            "gap_count": len(gaps),
        },
        "gaps": gaps,
        "outputs": {
            "preallocation_sha256": digest(result_preallocation),
            "reconciliation_sha256": digest(result_reconciliation),
            "manager_ledger_sha256": digest(result_managers),
        },
    }
    return result_preallocation, result_reconciliation, result_managers, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preallocation", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--manager-ledger", type=Path, required=True)
    parser.add_argument("--lineup-source", type=Path, action="append", required=True)
    parser.add_argument("--output-preallocation", type=Path, required=True)
    parser.add_argument("--output-reconciliation", type=Path, required=True)
    parser.add_argument("--output-manager-ledger", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()

    preallocation, preallocation_sha = read_json(args.preallocation)
    reconciliation, reconciliation_sha = read_json(args.reconciliation)
    managers, manager_sha = read_json(args.manager_ledger)
    lineup_pairs = [read_json(path) for path in args.lineup_source]
    documents = [document for document, _ in lineup_pairs]
    hashes = {
        "preallocation_sha256": preallocation_sha,
        "reconciliation_sha256": reconciliation_sha,
        "manager_ledger_sha256": manager_sha,
        "lineup_sources": [
            {"path": str(path), "sha256": sha}
            for path, (_, sha) in zip(args.lineup_source, lineup_pairs)
        ],
    }
    outputs = compose(
        preallocation=preallocation, reconciliation=reconciliation,
        managers=managers, lineup_documents=documents, input_hashes=hashes,
    )
    for path, value in zip(
        (
            args.output_preallocation, args.output_reconciliation,
            args.output_manager_ledger, args.output_audit,
        ),
        outputs,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
    print(json.dumps(outputs[-1]["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
