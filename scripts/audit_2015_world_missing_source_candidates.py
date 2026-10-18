#!/usr/bin/env python3
"""Audit exact, dated source candidates for the foreign-carrier source gaps.

The output is a source receipt only.  It never assigns a PM99 carrier to a
club, allocates a roster, or writes any game input.  A candidate is admitted
only when the preserved PM99 family and the captured source club have the
same *strict* normalised name.  In particular, no similarity score or
capacity-first substitution is used here.

The receipt joins three already-captured inputs:

* FootballSquads historic club squads (the dated source of full roster facts);
* the FIFA 16 player and FUT snapshots (a dated player-fact/rating candidate);
* the dated Transfermarkt opening-fixture receipt (manager, XI, formation and
  reported-stadium facts).

These are independent evidence lanes.  Even an exact candidate remains a
review item when its FootballSquads selector is already consumed by another
carrier in the existing source draft, or when it has fewer players than the
fixed PM99 slot count.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_world_2015_source_coverage import strict_club_key  # noqa: E402
from scripts.prepare_2015_world_fifa16_carrier_allocation import (  # noqa: E402
    FUT_LEAGUES,
    group_for_carrier,
    normalise,
)
from scripts.prepare_2015_world_source_carrier_drafts import (  # noqa: E402
    GROUP_TO_SOURCE_COMPETITIONS,
    GROUP_TO_SOURCE_COUNTRY,
)


SCHEMA = "pm99-world-2015-missing-source-candidates-v1"
SOURCE_CAPTURE_SCHEMA = "pm99-footballsquads-season-capture-v1"
TRANSFERMARKT_SCHEMA = "pm99-world-2015-transfermarkt-opening-fixtures-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {path}")
    return value


def _file_receipt(path: Path, *, role: str, data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    receipt: dict[str, Any] = {"path": str(path), "sha256": sha256_file(path), "role": role}
    if data is not None:
        receipt["schema_version"] = data.get("schema_version")
        receipt["season"] = data.get("season")
        if isinstance(data.get("source"), dict):
            receipt["declared_source"] = data["source"]
    return receipt


def _csv_rows(path: Path, label: str) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"{label} has no header")
            return [dict(row) for row in reader], list(reader.fieldnames)
    except OSError as exc:
        raise ValueError(f"cannot read {label}: {path}") from exc


def _selector(club: Mapping[str, Any]) -> dict[str, str]:
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    result = {field: str(club.get(field) or "") for field in fields}
    if not all(result.values()):
        raise ValueError("FootballSquads club has an incomplete source selector")
    return result


def _club_source_candidate(
    club: Mapping[str, Any], *, slots: int, used_by: list[int]
) -> dict[str, Any]:
    selector = _selector(club)
    players = club.get("players")
    if not isinstance(players, list):
        raise ValueError("FootballSquads club has no player list")
    return {
        "source_selector": selector,
        "source_club_name": str(club["club_name"]),
        "source_player_row_count": len(players),
        "capacity_sufficient": len(players) >= slots,
        "selector_already_used_by_carrier_ids": used_by,
        "eligible_for_direct_gap_closure": len(players) >= slots and not used_by,
        "source_date": "2015/16 capture (hybrid also includes a 2015 calendar-year lane)",
    }


def _fifa_candidate(
    *,
    label: str,
    league: str,
    stats_rows: list[Mapping[str, str]],
    fut_rows: list[Mapping[str, str]],
    slots: int,
) -> dict[str, Any]:
    player_ids = sorted(str(row.get("player_id") or "") for row in stats_rows)
    page_urls = sorted({str(row.get("page_url") or "") for row in stats_rows if row.get("page_url")})
    return {
        "fut_club_name": label,
        "fut_league": league,
        "fut_source_row_count": len(fut_rows),
        "fifa16_stats_row_count": len(stats_rows),
        "fifa16_player_ids": player_ids,
        "fifa16_player_page_urls": page_urls,
        "capacity_sufficient": len(stats_rows) >= slots,
        "eligible_for_direct_gap_closure": False,
        "source_date": "FIFA 16 snapshot (declared season 16/year 2016); player facts are candidate evidence only",
    }


def _transfermarkt_candidate(club: Mapping[str, Any]) -> dict[str, Any]:
    fixture = club.get("opening_fixture")
    if not isinstance(fixture, dict):
        raise ValueError("Transfermarkt club has no opening fixture")
    return {
        "source_club": club.get("source_club"),
        "country_name": club.get("country_name"),
        "competition": club.get("competition"),
        "opening_fixture": {
            "source_game_id": fixture.get("source_game_id"),
            "date": fixture.get("date"),
            "source_url": fixture.get("source_url"),
            "declared_manager": fixture.get("declared_manager"),
            "declared_formation": fixture.get("declared_formation"),
            "reported_match_stadium": fixture.get("reported_match_stadium"),
            "lineup_counts": fixture.get("lineup_counts"),
        },
        "home_fixture_ground_evidence": club.get("first_home_fixture_ground_evidence"),
        "eligible_for_direct_gap_closure": False,
        "source_date": "2015 opening domestic fixture receipt",
    }


def _inventory(
    *,
    fs_path: Path,
    fs_data: Mapping[str, Any],
    stats_path: Path,
    stats_rows: list[Mapping[str, str]],
    stats_fields: list[str],
    fut_path: Path,
    fut_rows: list[Mapping[str, str]],
    fut_fields: list[str],
    fifa16_ea_meta_path: Path | None,
    fifa16_ea_meta: Mapping[str, Any] | None,
    tm_path: Path,
    tm_data: Mapping[str, Any],
) -> dict[str, Any]:
    fs_clubs = fs_data.get("clubs")
    if not isinstance(fs_clubs, list):
        raise ValueError("FootballSquads capture has no clubs")
    fs_countries = Counter(str(row.get("country_catalog") or "") for row in fs_clubs)
    fs_competitions = Counter(
        f"{row.get('country_catalog')}/{row.get('competition_catalog')}" for row in fs_clubs
    )
    fs_players = sum(len(row.get("players") or []) for row in fs_clubs if isinstance(row, dict))
    stats_clubs = {str(row.get("club") or "") for row in stats_rows if row.get("club")}
    fut_clubs = {str(row.get("CLUB") or "") for row in fut_rows if row.get("CLUB")}
    tm_clubs = tm_data.get("clubs")
    if not isinstance(tm_clubs, list):
        raise ValueError("Transfermarkt receipt has no clubs")
    tm_countries = Counter(str(row.get("country_catalog") or "") for row in tm_clubs)
    inventory = {
        "footballsquads": {
            **_file_receipt(fs_path, role="dated-full-squad-source", data=fs_data),
            "club_count": len(fs_clubs),
            "player_row_count": fs_players,
            "countries": dict(sorted(fs_countries.items())),
            "competition_catalogs": dict(sorted(fs_competitions.items())),
            "capture_source": fs_data.get("source"),
            "captured_input_files": (
                fs_data.get("source", {}).get("inputs", [])
                if isinstance(fs_data.get("source"), dict)
                else []
            ),
        },
        "fifa16_player_stats": {
            **_file_receipt(stats_path, role="dated-player-facts-and-rating-candidate"),
            "row_count": len(stats_rows),
            "club_count": len(stats_clubs),
            "declared_seasons": dict(sorted(Counter(str(row.get("season") or "") for row in stats_rows).items())),
            "declared_years": dict(sorted(Counter(str(row.get("year") or "") for row in stats_rows).items())),
            "fields": stats_fields,
            "source_page_url_count": len({row.get("page_url") for row in stats_rows if row.get("page_url")}),
        },
        "fifa16_fut": {
            **_file_receipt(fut_path, role="dated-league-and-club-candidate"),
            "row_count": len(fut_rows),
            "club_count": len(fut_clubs),
            "league_count": len({row.get("LEAGUE") for row in fut_rows if row.get("LEAGUE")}),
            "leagues": dict(sorted(Counter(str(row.get("LEAGUE") or "") for row in fut_rows).items())),
            "fields": fut_fields,
            "declared_load_dates": sorted({str(row.get("LOADDATE") or "") for row in fut_rows if row.get("LOADDATE")}),
        },
        "transfermarkt_opening_fixture_receipt": {
            **_file_receipt(tm_path, role="dated-manager-XI-formation-ground-source", data=tm_data),
            "club_count": len(tm_clubs),
            "countries": dict(sorted(tm_countries.items())),
            "summary": tm_data.get("summary"),
            "capture_source": tm_data.get("source"),
        },
    }
    if fifa16_ea_meta_path is not None and fifa16_ea_meta is not None:
        inventory["fifa16_ea_player_meta"] = {
            **_file_receipt(fifa16_ea_meta_path, role="dated-FIFA16-player-identity-alias-candidate"),
            "player_count": len(fifa16_ea_meta.get("players") or []) if isinstance(fifa16_ea_meta.get("players"), list) else 0,
            "captured_at_utc": fifa16_ea_meta.get("captured_at_utc"),
            "source_url": fifa16_ea_meta.get("source_url"),
            "declared_source_sha256": fifa16_ea_meta.get("source_sha256"),
        }
    return inventory


def build_receipt(
    *,
    registry: Mapping[str, Any],
    source_draft: Mapping[str, Any],
    fs_data: Mapping[str, Any],
    stats_rows: list[Mapping[str, str]],
    fut_rows: list[Mapping[str, str]],
    tm_data: Mapping[str, Any],
    fs_path: Path,
    stats_path: Path,
    fut_path: Path,
    tm_path: Path,
    fifa16_ea_meta_path: Path | None = None,
    fifa16_ea_meta: Mapping[str, Any] | None = None,
    registry_path: Path | None = None,
    source_draft_path: Path | None = None,
) -> dict[str, Any]:
    if fs_data.get("schema_version") != SOURCE_CAPTURE_SCHEMA:
        raise ValueError("FootballSquads capture schema is not supported")
    if tm_data.get("schema_version") != TRANSFERMARKT_SCHEMA:
        raise ValueError("Transfermarkt receipt schema is not supported")
    proposals = source_draft.get("proposals")
    carriers = registry.get("carriers")
    if not isinstance(proposals, list) or not isinstance(carriers, list):
        raise ValueError("registry/draft has no carrier list")
    draft_by_id = {int(row["carrier_id"]): row for row in proposals}
    blocked_ids = {
        carrier_id for carrier_id, row in draft_by_id.items() if row.get("status") != "source-squad-ready"
    }
    if len(blocked_ids) != 149:
        raise ValueError(f"expected 149 source gaps, found {len(blocked_ids)}")

    fs_index: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for club in fs_data["clubs"]:
        if not isinstance(club, dict):
            raise ValueError("FootballSquads capture has malformed club")
        selector = _selector(club)
        fs_index[(selector["country_catalog"], selector["competition_catalog"], strict_club_key(selector["club_name"]))].append(club)
    used_by: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(list)
    for row in proposals:
        if row.get("status") == "source-squad-ready" and isinstance(row.get("source_selector"), dict):
            selector = row["source_selector"]
            used_by[tuple(str(selector.get(field) or "") for field in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))].append(int(row["carrier_id"]))
    for rows in used_by.values():
        rows.sort()

    stats_index: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in stats_rows:
        key = normalise(row.get("club"))
        if key:
            stats_index[key].append(row)
    fut_index: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in fut_rows:
        key = normalise(row.get("CLUB"))
        league = str(row.get("LEAGUE") or "")
        if key and league:
            fut_index[(league, key)].append(row)

    tm_index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for club in tm_data["clubs"]:
        if not isinstance(club, dict):
            raise ValueError("Transfermarkt receipt has malformed club")
        source_club = club.get("source_club")
        if isinstance(source_club, dict):
            tm_index[(str(club.get("country_catalog") or ""), strict_club_key(source_club.get("name")))].append(club)

    records: list[dict[str, Any]] = []
    family_summary: dict[str, dict[str, Any]] = {}
    for carrier in sorted(carriers, key=lambda row: int(row["carrier_id"])):
        carrier_id = int(carrier["carrier_id"])
        if carrier_id not in blocked_ids:
            continue
        draft = draft_by_id[carrier_id]
        group = group_for_carrier(carrier_id)
        baseline_name = str((carrier.get("baseline_club") or {}).get("name") or "")
        slots = len(carrier.get("roster_slots") or [])
        source_country = GROUP_TO_SOURCE_COUNTRY.get(str(group or ""))
        competitions = sorted(GROUP_TO_SOURCE_COMPETITIONS.get(str(group or ""), set()))
        strict_key = strict_club_key(baseline_name)
        fifa_key = normalise(baseline_name)

        fs_candidates = []
        if source_country and competitions:
            for competition in competitions:
                for club in fs_index.get((source_country, competition, strict_key), []):
                    selector = _selector(club)
                    key = tuple(selector[field] for field in ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"))
                    fs_candidates.append(_club_source_candidate(club, slots=slots, used_by=used_by.get(key, [])))

        fifa_candidates = []
        for league in FUT_LEAGUES.get(str(group or ""), ()):
            rows = fut_index.get((league, fifa_key), [])
            if rows:
                fifa_candidates.append(_fifa_candidate(label=str(rows[0].get("CLUB") or ""), league=league, stats_rows=stats_index.get(fifa_key, []), fut_rows=rows, slots=slots))

        tm_candidates = []
        if source_country:
            tm_candidates = [_transfermarkt_candidate(club) for club in tm_index.get((source_country, strict_key), [])]

        evidence = []
        if any(row["eligible_for_direct_gap_closure"] for row in fs_candidates):
            evidence.append("exact-footballsquads-capacity-ready")
        elif any(row["capacity_sufficient"] for row in fs_candidates):
            evidence.append("exact-footballsquads-capacity-ready-but-selector-conflict")
        if any(row["capacity_sufficient"] for row in fifa_candidates):
            evidence.append("exact-fifa16-capacity-ready")
        elif fifa_candidates:
            evidence.append("exact-fifa16-player-candidate-undersized")
        if tm_candidates:
            evidence.append("exact-transfermarkt-opening-fixture-evidence")
        if not evidence:
            evidence.append("no-exact-dated-source-candidate")

        direct = any(row["eligible_for_direct_gap_closure"] for row in fs_candidates)
        status = "direct-exact-footballsquads-candidate" if direct else (
            "exact-source-candidate-needs-review" if fs_candidates or fifa_candidates or tm_candidates else "unresolved"
        )
        record = {
            "carrier_id": carrier_id,
            "group": group,
            "baseline_name": baseline_name,
            "fixed_roster_slot_count": slots,
            "existing_gap_status": draft.get("status"),
            "strict_name_key": strict_key,
            "fifa_name_key": fifa_key,
            "source_country_catalog": source_country,
            "source_competition_catalogs": competitions,
            "candidate_status": status,
            "evidence": evidence,
            "footballsquads_exact_candidates": fs_candidates,
            "fifa16_exact_candidates": fifa_candidates,
            "transfermarkt_exact_candidates": tm_candidates,
            "guardrail": "Exact source evidence only; no carrier assignment, roster-slot mapping, membership inference or PM99 write.",
        }
        records.append(record)
        summary = family_summary.setdefault(str(group or "unclassified"), {"blocked_carrier_count": 0, "blocked_slot_count": 0, "candidate_carrier_count": 0, "direct_exact_source_carrier_count": 0, "unresolved_carrier_count": 0})
        summary["blocked_carrier_count"] += 1
        summary["blocked_slot_count"] += slots
        summary["candidate_carrier_count"] += int(status != "unresolved")
        summary["direct_exact_source_carrier_count"] += int(direct)
        summary["unresolved_carrier_count"] += int(status == "unresolved")

    candidate_count = sum(row["candidate_status"] != "unresolved" for row in records)
    direct_count = sum(row["candidate_status"] == "direct-exact-footballsquads-candidate" for row in records)
    unresolved = [row["carrier_id"] for row in records if row["candidate_status"] == "unresolved"]
    return {
        "schema_version": SCHEMA,
        "season": "2015/16",
        "policy": "exact-preserved-family-name-join-only; read-only-source-receipt; no-fuzzy-carrier-assignment",
        "inputs": {
            "registry": {"path": str(registry_path or "<in-memory>"), "sha256": hashlib.sha256(canonical_bytes(dict(registry))).hexdigest()},
            "source_draft": {"path": str(source_draft_path or "<in-memory>"), "sha256": hashlib.sha256(canonical_bytes(dict(source_draft))).hexdigest()},
        },
        "inventory": _inventory(fs_path=fs_path, fs_data=fs_data, stats_path=stats_path, stats_rows=stats_rows, stats_fields=list(stats_rows[0].keys()) if stats_rows else [], fut_path=fut_path, fut_rows=fut_rows, fut_fields=list(fut_rows[0].keys()) if fut_rows else [], fifa16_ea_meta_path=fifa16_ea_meta_path, fifa16_ea_meta=fifa16_ea_meta, tm_path=tm_path, tm_data=tm_data),
        "gap_scope": {
            "fixed_carrier_count": len(carriers),
            "source_ready_carrier_count": len(carriers) - len(records),
            "foreign_source_gap_carrier_count": len(records),
            "foreign_source_gap_slot_count": sum(int(row["fixed_roster_slot_count"]) for row in records),
            "existing_gap_status_counts": dict(sorted(Counter(str(row["existing_gap_status"]) for row in records).items())),
        },
        "candidate_summary": {
            "exact_source_candidate_carrier_count": candidate_count,
            "direct_exact_source_candidate_carrier_count": direct_count,
            "unresolved_carrier_count": len(unresolved),
            "unresolved_carrier_ids": unresolved,
            "families": {key: family_summary[key] for key in sorted(family_summary)},
        },
        "records": records,
        "guardrails": [
            "FootballSquads candidates retain the exact source selector and source hash from the capture.",
            "FIFA16 candidates retain the exact club/league labels, player IDs and player-page URLs from the snapshots.",
            "Transfermarkt candidates retain the exact dated fixture, source URL, manager, formation and reported stadium facts.",
            "A candidate is not a release-ledger row: managers, grounds, kits, portraits, ratings reconciliation and PM99 slot identity remain separate decisions.",
            "The unresolved remainder is explicit and must not be filled from another country family or by fuzzy matching.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-draft", type=Path, required=True)
    parser.add_argument("--footballsquads", type=Path, required=True)
    parser.add_argument("--fifa16-player-stats", type=Path, required=True)
    parser.add_argument("--fifa16-fut", type=Path, required=True)
    parser.add_argument("--fifa16-ea-meta", type=Path, required=True)
    parser.add_argument("--transfermarkt-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry = _read_json(args.registry, "registry")
        source_draft = _read_json(args.source_draft, "source draft")
        fs_data = _read_json(args.footballsquads, "FootballSquads capture")
        tm_data = _read_json(args.transfermarkt_receipt, "Transfermarkt receipt")
        stats_rows, _stats_fields = _csv_rows(args.fifa16_player_stats, "FIFA16 player stats")
        fut_rows, _fut_fields = _csv_rows(args.fifa16_fut, "FIFA16 FUT snapshot")
        fifa16_ea_meta = _read_json(args.fifa16_ea_meta, "FIFA16 EA player metadata")
        result = build_receipt(registry=registry, source_draft=source_draft, fs_data=fs_data, stats_rows=stats_rows, fut_rows=fut_rows, tm_data=tm_data, fs_path=args.footballsquads, stats_path=args.fifa16_player_stats, fut_path=args.fifa16_fut, tm_path=args.transfermarkt_receipt, fifa16_ea_meta_path=args.fifa16_ea_meta, fifa16_ea_meta=fifa16_ea_meta, registry_path=args.registry, source_draft_path=args.source_draft)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"output": str(args.output), **result["candidate_summary"], **result["gap_scope"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
