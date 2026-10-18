#!/usr/bin/env python3
"""Create a reviewable 2015/16 foreign-carrier allocation from local FIFA data.

This is intentionally a *source allocation* tool, not a PM99 writer.  It
keeps every PM99 EQ carrier in its existing country/league group and proposes
a distinct FIFA 16 club from the corresponding published FUT league.  It does
not infer a new division, alter a country, or write a roster row.

The report is useful because the original 1998 club identity is not a safe
key for a 2015 club.  A new or relegated club is allowed to occupy any
existing carrier in the same preserved group.  The output makes every such
proposal explicit for review before it becomes a season ledger row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "pm99-world-fifa16-carrier-allocation-v1"

# The ranges are existing PM99 carrier families, identified from the fixed
# registry rather than guessed from record order.  They are deliberately
# country/league *labels* for source selection only: no output field implies a
# PM99 competition or membership mutation.
GROUP_RANGES: tuple[tuple[str, range], ...] = (
    ("spain", range(1, 100)),
    ("italy", range(200, 300)),
    ("germany", range(400, 500)),
    ("france", range(500, 600)),
    ("portugal", range(600, 700)),
    ("serbia", range(700, 750)),
    ("russia", range(750, 800)),
    ("netherlands", range(800, 850)),
    ("belgium", range(850, 900)),
    ("croatia", range(900, 950)),
    ("sweden", range(950, 1000)),
    ("turkey", range(1000, 1050)),
    ("poland", range(1050, 1100)),
    ("switzerland", range(1100, 1150)),
    ("austria", range(1150, 1200)),
    ("denmark", range(1200, 1250)),
    ("scotland", range(1250, 1300)),
    ("greece", range(1300, 1350)),
    ("norway", range(1350, 1400)),
    ("romania", range(1400, 1450)),
    ("czechia", range(1450, 1500)),
    ("bulgaria", range(1500, 1550)),
    ("slovakia", range(1550, 1600)),
    ("slovenia", range(1600, 1650)),
    ("cyprus", range(1650, 1700)),
    ("hungary", range(1700, 1750)),
    ("ukraine", range(1750, 1800)),
    ("luxembourg", range(1800, 1850)),
    ("ireland", range(1850, 1900)),
    ("northern-ireland", range(1900, 1950)),
    ("iceland", range(1950, 2000)),
    ("finland", range(2000, 2050)),
    ("wales", range(2050, 2100)),
    ("israel", range(2100, 2150)),
    ("malta", range(2150, 2200)),
    ("faroe-islands", range(2200, 2250)),
    ("lithuania", range(2250, 2300)),
    ("albania", range(2400, 2450)),
    ("georgia", range(2500, 2550)),
    ("moldova", range(2550, 2600)),
    ("bolivia", range(2600, 2650)),
    ("ecuador", range(2650, 2700)),
    ("belarus", range(2700, 2750)),
    ("peru", range(2750, 2800)),
    ("brazil", range(2800, 2850)),
    ("uruguay", range(2900, 2950)),
    ("venezuela", range(2950, 3000)),
    ("chile", range(3000, 3050)),
    ("colombia", range(3100, 3150)),
    ("paraguay", range(3200, 3250)),
    ("english-non-league", range(3300, 3400)),
    ("latvia", range(4000, 4025)),
    ("armenia", range(4025, 4050)),
    ("north-macedonia", range(4050, 4075)),
    ("belarus", range(4075, 4100)),
    ("kazakhstan", range(4100, 4125)),
    ("azerbaijan", range(4125, 4150)),
    ("argentina", range(9000, 9100)),
)

# This is the published FIFA 16 FUT league field.  A group absent from this
# map is deliberately reported as unresolved; it is never filled from a club
# in a different country merely to improve a percentage.
FUT_LEAGUES: dict[str, tuple[str, ...]] = {
    "spain": ("Liga BBVA",),
    "italy": ("Serie A",),
    "germany": ("Bundesliga", "2. Bundesliga"),
    "france": ("Ligue 1",),
    "portugal": ("Primeira Liga",),
    "russia": ("Russian League",),
    "netherlands": ("Eredivisie",),
    "belgium": ("Pro League",),
    "sweden": ("Allsvenskan",),
    "turkey": ("Süper Lig",),
    "poland": ("Ekstraklasa",),
    "switzerland": ("Raiffeisen SL",),
    "austria": ("A. Bundesliga",),
    "denmark": ("Superliga",),
    "scotland": ("Scottish Prem",),
    "greece": ("Hellas Liga",),
    "norway": ("Tippeligaen",),
    "ukraine": ("Ukrayina Liha",),
    "ireland": ("Airtricity League",),
    "brazil": ("Liga do Brasil",),
    "argentina": ("Primera División",),
    "chile": ("Camp. Scotiabank",),
    "colombia": ("Liga Postobón",),
    "english-non-league": ("Football League", "Football League 2"),
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character.casefold() for character in text if character.isalnum())


def group_for_carrier(carrier_id: int) -> str | None:
    for name, bounds in GROUP_RANGES:
        if carrier_id in bounds:
            return name
    return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def resolve_stats_club(
    *,
    fifa_club: str,
    stats_by_club: dict[str, list[dict[str, str]]],
    stats_labels: dict[str, str],
) -> tuple[str | None, str]:
    """Link FUT's abbreviated club label to the detailed FIFA stats label.

    FIFA's two published files use variants such as ``PSG`` versus ``Paris
    Saint-Germain``.  This is a reviewable source-file join, not a historic
    club-placement decision: ambiguous or weak matches are returned as no
    match instead of inventing a squad.
    """

    key = normalise(fifa_club)
    if key in stats_by_club:
        return key, "exact-normalised-label"
    scored = sorted(
        (
            (SequenceMatcher(a=key, b=stats_key).ratio(), stats_key)
            for stats_key in stats_by_club
        ),
        reverse=True,
    )
    if not scored:
        return None, "no-stats-club"
    best_score, best_key = scored[0]
    next_score = scored[1][0] if len(scored) > 1 else 0.0
    # The margin makes abbreviations deterministic but prevents a generic
    # label such as United from attaching to an arbitrary club.
    if best_score >= 0.68 and best_score - next_score >= 0.06:
        return best_key, f"review-fuzzy-label:{best_score:.3f}:{stats_labels[best_key]}"
    return None, "ambiguous-or-weak-stats-label"


def build_report(*, registry: dict[str, Any], stats: list[dict[str, str]], fut: list[dict[str, str]]) -> dict[str, Any]:
    stats_by_club: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in stats:
        key = normalise(row.get("club"))
        if key:
            stats_by_club[key].append(row)
    stats_labels = {key: str(rows[0].get("club") or "") for key, rows in stats_by_club.items()}

    fut_by_league: dict[str, dict[str, str]] = defaultdict(dict)
    for row in fut:
        club = str(row.get("CLUB") or "").strip()
        league = str(row.get("LEAGUE") or "").strip()
        key = normalise(club)
        if club and league and key:
            # The FUT CSV repeats player rows.  One canonical club label per
            # normalised key is enough for a source allocation proposal.
            fut_by_league[league].setdefault(key, club)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    out_of_scope: list[int] = []
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        group = group_for_carrier(carrier_id)
        if group is None:
            out_of_scope.append(carrier_id)
        else:
            groups[group].append(carrier)

    assignments: list[dict[str, Any]] = []
    group_summary: list[dict[str, Any]] = []
    used_stats_clubs: set[str] = set()
    for group, carriers in sorted(groups.items()):
        leagues = FUT_LEAGUES.get(group, ())
        pool: dict[str, str] = {}
        for league in leagues:
            pool.update(fut_by_league.get(league, {}))
        source_links = {
            key: resolve_stats_club(fifa_club=label, stats_by_club=stats_by_club, stats_labels=stats_labels)
            for key, label in pool.items()
        }
        remaining = {
            key for key, (stats_key, _method) in source_links.items()
            if stats_key is not None and stats_key not in used_stats_clubs
        }

        # Preserve a still-valid club identity where possible.  The rest are
        # deterministically allocated by usable roster depth then name.  This
        # is a review order, not an opening-table order claim.
        ordered = sorted(carriers, key=lambda row: int(row["carrier_id"]))
        for carrier in ordered:
            baseline = normalise(carrier["baseline_club"].get("name"))
            candidate_key = baseline if baseline in remaining else None
            if candidate_key is None and remaining:
                candidate_key = min(
                    remaining,
                    key=lambda key: (-len(stats_by_club[source_links[key][0]]), pool[key].casefold()),
                )
            slots = len(carrier["roster_slots"])
            if candidate_key is None:
                assignments.append({
                    "carrier_id": int(carrier["carrier_id"]),
                    "group": group,
                    "baseline_name": carrier["baseline_club"].get("name"),
                    "fixed_slot_count": slots,
                    "status": "unresolved",
                    "reason": "no-distinct-fifa16-club-remains-in-this-preserved-country-group",
                })
                continue
            remaining.remove(candidate_key)
            stats_key, stats_match_method = source_links[candidate_key]
            assert stats_key is not None
            used_stats_clubs.add(stats_key)
            candidate_rows = stats_by_club[stats_key]
            assignments.append({
                "carrier_id": int(carrier["carrier_id"]),
                "group": group,
                "baseline_name": carrier["baseline_club"].get("name"),
                "fixed_slot_count": slots,
                "status": "candidate" if len(candidate_rows) >= slots else "undersized-source-squad",
                "fifa16_club": pool[candidate_key],
                "fifa16_stats_club": stats_labels[stats_key],
                "fifa16_stats_match": stats_match_method,
                "fifa16_player_row_count": len(candidate_rows),
                "source_leagues": list(leagues),
            })
        group_summary.append({
            "group": group,
            "carrier_count": len(carriers),
            "fifa16_leagues": list(leagues),
            "fifa16_distinct_club_count": len(pool),
            "unallocated_fifa16_clubs": [pool[key] for key in sorted(remaining)],
        })

    status_counts = Counter(str(row["status"]) for row in assignments)
    return {
        "schema_version": SCHEMA,
        "policy": "existing-pm99-carriers-only; no country, league-size, promotion, relegation, draw-pool or membership write",
        "sources": {
            "registry_sha256": hashlib.sha256(canonical_bytes(registry)).hexdigest(),
            "fifa16_player_stats_sha256": None,
            "fifa16_fut_source_sha256": None,
        },
        "coverage": {
            "foreign_carrier_count": len(registry["carriers"]),
            "assigned_carrier_count": len(assignments),
            "status_counts": dict(sorted(status_counts.items())),
            "unmapped_carrier_ids": out_of_scope,
        },
        "groups": group_summary,
        "assignments": sorted(assignments, key=lambda row: int(row["carrier_id"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--player-stats-csv", required=True, type=Path)
    parser.add_argument("--fut-source-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    stats = read_csv(args.player_stats_csv)
    fut = read_csv(args.fut_source_csv)
    report = build_report(registry=registry, stats=stats, fut=fut)
    report["sources"]["fifa16_player_stats_sha256"] = sha256(args.player_stats_csv)
    report["sources"]["fifa16_fut_source_sha256"] = sha256(args.fut_source_csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report))
    print(json.dumps(report["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
