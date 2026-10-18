#!/usr/bin/env python3
"""Adapt canonical opening evidence to the English mode-0 authoring layers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-english-opening-manager-layer-adapter-v1"
PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
RECONCILIATION_SCHEMA = "pm99-transfermarkt-opening-lineup-reconciliation-v1"
MANAGER_SCHEMA = "pm99-opening-manager-ledger-v1"
SNAPSHOT_POLICY = "at-club-on-first-league-fixture-date-exclude-later-arrivals"
ENGLISH_COMPETITIONS = {"faprem", "engprem", "prem", "premier", "champ", "championship", "flcham", "d1", "lge1", "league1", "flone", "d2", "lge2", "league2", "fltwo", "d3"}


class LayerAdapterError(ValueError):
    """The evidence chain is stale or structurally ambiguous."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(row.get(key) or "").strip() for key in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise LayerAdapterError("source selector is incomplete")
    return result  # type: ignore[return-value]


def _index(rows: object, selector_field: str, label: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not isinstance(rows, list):
        raise LayerAdapterError(f"{label} rows must be a list")
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(selector_field), dict):
            raise LayerAdapterError(f"{label} has a malformed row")
        key = _selector(row[selector_field])
        if key in result:
            raise LayerAdapterError(f"{label} duplicates {key}")
        result[key] = row
    return result


def _season(preallocation: Mapping[str, Any]) -> dict[str, str]:
    season = preallocation.get("season")
    if not isinstance(season, Mapping):
        raise LayerAdapterError("preallocation has no season object")
    label = str(season.get("label") or "")
    if not re.fullmatch(r"(?:19|20)\d{2}/\d{2}", label):
        raise LayerAdapterError("preallocation season label must be YYYY/YY")
    return dict(season)  # type: ignore[return-value]


def _infer_formation(players: list[dict[str, Any]]) -> str | None:
    positions = [str((row.get("facts") or {}).get("position") or "").upper() for row in players]
    if len(positions) != 11 or positions.count("G") != 1 or any(value not in {"G", "D", "M", "F"} for value in positions):
        return None
    counts = [positions.count(position) for position in ("D", "M", "F")]
    if sum(counts) != 10:
        return None
    # Historical squad sources use broad D/M/F position groups rather than
    # match-specific roles.  A side with six players labelled D did not
    # literally have to use a six-man defensive band.  Project impossible
    # (>5) broad-group counts onto the nearest conventional PM99 formation;
    # tie order is fixed, so the inference remains deterministic and visible.
    supported = (
        (4, 4, 2), (4, 3, 3), (3, 5, 2), (5, 3, 2),
        (4, 5, 1), (5, 4, 1), (3, 4, 3), (5, 2, 3),
    )
    projected = min(supported, key=lambda row: (sum(abs(a - b) for a, b in zip(counts, row)), supported.index(row)))
    return "-".join(str(value) for value in projected)


def materialise(
    *, preallocation: Mapping[str, Any], preallocation_sha256: str,
    reconciliation: Mapping[str, Any], reconciliation_sha256: str,
    managers: Mapping[str, Any], managers_sha256: str, squad_limit: int = 25,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if preallocation.get("schema_version") != PREALLOCATION_SCHEMA:
        raise LayerAdapterError(f"preallocation must have schema {PREALLOCATION_SCHEMA}")
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA:
        raise LayerAdapterError(f"reconciliation must have schema {RECONCILIATION_SCHEMA}")
    if managers.get("schema_version") != MANAGER_SCHEMA:
        raise LayerAdapterError(f"manager ledger must have schema {MANAGER_SCHEMA}")
    if not 11 <= squad_limit <= 25:
        raise LayerAdapterError("squad_limit must be between 11 and 25")
    sources = preallocation.get("sources") or {}
    if sources.get("opening_reconciliation_sha256") != reconciliation_sha256:
        raise LayerAdapterError("preallocation is not bound to this reconciliation")
    reconciliation_sources = reconciliation.get("sources") or {}
    if sources.get("opening_lineup_sha256") != reconciliation_sources.get("lineup_capture_sha256"):
        raise LayerAdapterError("preallocation and reconciliation target different lineup captures")
    manager_sources = managers.get("sources") or {}
    if manager_sources.get("opening_lineup_receipt_sha256") != sources.get("opening_lineup_sha256"):
        raise LayerAdapterError("manager ledger targets a different lineup capture")
    if manager_sources.get("squad_source_capture_sha256") != sources.get("source_capture_sha256"):
        raise LayerAdapterError("manager ledger targets a different squad capture")

    season = _season(preallocation)
    preallocation_by_club = _index(preallocation.get("source_clubs"), "selector", "preallocation")
    reconciliation_by_club = _index(reconciliation.get("clubs"), "source_selector", "reconciliation")
    managers_by_club = _index(managers.get("managers"), "source_selector", "manager ledger")
    opening_rows: list[dict[str, Any]] = []
    manager_rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    english_keys = sorted(key for key in preallocation_by_club if key[0] == "eng" and key[1] in ENGLISH_COMPETITIONS)
    for key in english_keys:
        club = preallocation_by_club[key]
        reconciliation_row = reconciliation_by_club.get(key)
        manager = managers_by_club.get(key)
        players = list(club.get("players") or [])
        xi_players = [row for row in players if isinstance(row, dict) and isinstance(row.get("opening_xi_order"), int)]
        xi_players.sort(key=lambda row: row["opening_xi_order"])
        names = [str((row.get("facts") or {}).get("name") or "").strip() for row in players[:squad_limit]]
        xi_names = [str((row.get("facts") or {}).get("name") or "").strip() for row in xi_players]
        reasons: list[str] = []
        if not club.get("opening_xi_complete") or len(xi_players) != 11 or [row["opening_xi_order"] for row in xi_players] != list(range(1, 12)) or any(not value for value in xi_names):
            reasons.append("opening-xi-is-not-complete-and-ordered")
        # A published August squad can legitimately be smaller than twenty.
        # The hard contract is an ordered, unique first XI plus every further
        # source player that fits the fixed carrier capacity, not an invented
        # twentieth player.
        if len(names) < 11 or len(set(names)) != len(names) or any(not value for value in names):
            reasons.append("opening-squad-is-not-at-least-eleven-unique-players")
        if reconciliation_row is None:
            reasons.append("opening-reconciliation-row-missing")
        formation = str((reconciliation_row or {}).get("formation") or "").strip()
        method = "source"
        if not formation:
            formation = _infer_formation(xi_players) or ""
            method = "deterministic-inference-from-sourced-xi"
        if not re.fullmatch(r"[1-9](?:-[1-9])+", formation) or sum(map(int, formation.split("-"))) != 10:
            reasons.append("formation-cannot-be-sourced-or-deterministically-inferred")
        fixture_date = str((reconciliation_row or {}).get("first_league_fixture_date") or club.get("opening_fixture_date") or "").strip()
        source_url = str((reconciliation_row or {}).get("lineup_source_url") or "").strip()
        if not fixture_date or not source_url:
            reasons.append("fixture-date-or-source-url-missing")
        if reasons:
            gaps.append({"club": key[2], "source_selector": dict(club["selector"]), "lane": "opening", "reasons": sorted(set(reasons))})
        else:
            opening_rows.append({
                "club": key[2], "first_xi": xi_names, "opening_squad": names,
                "squad_snapshot_policy": SNAPSHOT_POLICY, "formation": formation,
                "formation_method": method, "fixture_date": fixture_date,
                "source_url": source_url, "source_match_id": str((reconciliation_row or {}).get("source_match_id") or club.get("opening_source_match_id") or ""),
            })
        if manager is None:
            gaps.append({"club": key[2], "source_selector": dict(club["selector"]), "lane": "manager", "reasons": ["dated-opening-manager-is-unresolved"]})
        else:
            evidence = manager.get("evidence") or {}
            manager_rows.append({
                "club": key[2], "manager_name": str(manager.get("manager_name") or "").strip(),
                "source_url": str(evidence.get("source_url") or "").strip(),
                "fixture_date": str(manager.get("opening_fixture_date") or "").strip(),
                "resolution_method": str(manager.get("resolution_method") or ""),
                "source_snapshot_sha256": str(evidence.get("source_snapshot_sha256") or ""),
            })

    openings = {"schema_version": "pm99-season-opening-layer-v1", "season": season, "clubs": opening_rows}
    manager_layer = {"schema_version": "pm99-season-manager-layer-v1", "season": season, "rows": manager_rows}
    audit = {
        "schema_version": SCHEMA, "season": season,
        "sources": {"preallocation_sha256": preallocation_sha256, "reconciliation_sha256": reconciliation_sha256, "manager_ledger_sha256": managers_sha256},
        "coverage": {"english_source_club_count": len(english_keys), "opening_layer_club_count": len(opening_rows), "manager_layer_club_count": len(manager_rows), "gap_count": len(gaps)},
        "gaps": gaps,
        "opening_layer_sha256": _digest_bytes(canonical_json_bytes(openings)),
        "manager_layer_sha256": _digest_bytes(canonical_json_bytes(manager_layer)),
    }
    return openings, manager_layer, audit


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise LayerAdapterError(f"input must be a JSON object: {path}")
    return value, _digest_bytes(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preallocation", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--manager-ledger", type=Path, required=True)
    parser.add_argument("--squad-limit", type=int, default=25)
    parser.add_argument("--output-openings", type=Path, required=True)
    parser.add_argument("--output-managers", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    preallocation, preallocation_sha = _read(args.preallocation)
    reconciliation, reconciliation_sha = _read(args.reconciliation)
    managers, managers_sha = _read(args.manager_ledger)
    openings, manager_layer, audit = materialise(
        preallocation=preallocation, preallocation_sha256=preallocation_sha,
        reconciliation=reconciliation, reconciliation_sha256=reconciliation_sha,
        managers=managers, managers_sha256=managers_sha, squad_limit=args.squad_limit,
    )
    for path, value in ((args.output_openings, openings), (args.output_managers, manager_layer), (args.output_audit, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
