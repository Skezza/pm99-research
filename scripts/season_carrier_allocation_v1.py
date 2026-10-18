#!/usr/bin/env python3
"""Allocate dated clubs to PM99's fixed country carrier families.

The PM99 carrier graph is immutable, but a country's represented clubs change
between seasons.  This authoring stage keeps every carrier inside its proven
country family, preserves a continuing club on its native carrier when an
unambiguous normalized identity exists, then assigns promoted/replacement
clubs to the remaining carriers in canonical source order.  It never changes
competition membership bytes and never requires one screenshot per carrier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier


SCHEMA = "pm99-season-carrier-allocation-v1"
SOURCE_SCHEMA = "pm99-footballsquads-season-capture-v1"
REGISTRY_SCHEMA = "pm99-fixed-foreign-carrier-registry-v1"
MIN_OPENING_SQUAD_PLAYERS = 11

COUNTRY_GROUPS = {
    "albania": "albania", "armenia": "armenia", "azerbaijan": "azerbaijan",
    "arg": "argentina", "argentina": "argentina", "austria": "austria", "belgium": "belgium",
    "belarus": "belarus", "bolivia": "bolivia", "brazil": "brazil", "bulgaria": "bulgaria", "chile": "chile",
    "colombia": "colombia", "croatia": "croatia", "czech": "czechia", "czechia": "czechia",
    "cyprus": "cyprus", "denmark": "denmark", "ecuador": "ecuador", "faroe-islands": "faroe-islands", "finland": "finland",
    "france": "france", "georgia": "georgia", "ger": "germany", "germany": "germany",
    "greece": "greece", "holland": "netherlands", "hungary": "hungary", "iceland": "iceland",
    "ireland": "ireland", "israel": "israel", "italy": "italy", "kazakhstan": "kazakhstan",
    "latvia": "latvia", "lithuania": "lithuania", "luxembourg": "luxembourg", "malta": "malta", "moldova": "moldova",
    "netherl": "netherlands", "netherlands": "netherlands", "north-macedonia": "north-macedonia",
    "northern-ireland": "northern-ireland", "english-non-league": "english-non-league",
    "norway": "norway", "paraguay": "paraguay", "peru": "peru",
    "poland": "poland", "portugal": "portugal", "romania": "romania",
    "russia": "russia", "scots": "scotland", "scotland": "scotland", "serbia": "serbia",
    "slovakia": "slovakia", "slovenia": "slovenia", "spain": "spain",
    "sweden": "sweden", "switz": "switzerland", "turkey": "turkey",
    "switzerland": "switzerland", "ukraine": "ukraine", "uruguay": "uruguay", "venezuela": "venezuela",
    "wales": "wales",
}

# These two real English clubs sit outside the otherwise contiguous carrier
# ranges inherited from the clean database.  They are not system selections:
# in seasons where they are outside the Football League they belong to the
# same dated non-league allocation lane as the 3300-series carriers.
ENGLISH_NON_LEAGUE_CARRIER_IDS = {377, 381}
SYSTEM_SELECTION_IDS = {8800, 8801, 9900, 9950, 9956}

# FootballSquads catalogues use stable short codes but labels changed over
# time.  Only the first matching code is selected for a fixed top-flight
# family; lower divisions remain source evidence, not silently promoted.
PRIMARY_COMPETITIONS = {
    "albania": ("superiore", "ntf-opening-squad"), "armenia": ("ntf-opening-squad",),
    "argentina": ("apertura", "inicial", "argprim", "argaper", "primera"),
    "austria": ("bundes", "ausbun"),
    "belgium": ("eerste", "prolge", "belpro", "proleague"),
    "azerbaijan": ("ntf-opening-squad",), "belarus": ("vysshaya", "ntf-opening-squad"),
    "bolivia": ("division-profesional", "ntf-opening-squad"), "brazil": ("campeon", "bracamp", "seriea"),
    "bulgaria": ("apfg", "first"), "chile": ("primera", "apertura", "chileprm"),
    "colombia": ("primera", "apertura", "ntf-opening-squad"), "croatia": ("prva", "1hnl", "cro1hnl", "ntf-opening-squad"), "cyprus": ("first", "ntf-opening-squad"),
    "czechia": ("gambrin", "1liga", "cze1liga", "first"),
    "denmark": ("supliga", "densuper", "superliga"),
    "ecuador": ("seriea", "primera", "ntf-opening-squad"), "faroe-islands": ("premier", "ntf-opening-squad"), "finland": ("veikkaus", "ntf-opening-squad"),
    "france": ("div1", "ligue1", "fralig1"), "georgia": ("umaglesi", "ntf-opening-squad"),
    "germany": ("bundes", "gerbun"),
    "greece": ("ethniki", "superl", "gresuper"),
    "hungary": ("borsodi", "soproni", "monicomp", "hungnb1", "otpliga", "otpbank", "nb1", "ntf-opening-squad"), "iceland": ("urvalsdeild", "ntf-opening-squad"),
    "ireland": ("prem", "ireprm"), "israel": ("ligat",), "italy": ("seriea",), "kazakhstan": ("premier",),
    "latvia": ("virsliga", "ntf-opening-squad"), "lithuania": ("alyga", "ntf-opening-squad"),
    "luxembourg": ("national-division", "ntf-opening-squad"),
    "malta": ("premier", "ntf-opening-squad"), "moldova": ("ntf-opening-squad",),
    "north-macedonia": ("ntf-opening-squad",), "northern-ireland": ("premier", "ntf-opening-squad"),
    "netherlands": ("ere", "nethere"),
    "norway": ("tippe", "eliteserien", "norelite"),
    "poland": ("ekstrak", "polekstr"),
    "portugal": ("superl", "primeira", "porprim"),
    "paraguay": ("primera", "ntf-opening-squad"), "peru": ("primera", "ntf-opening-squad"),
    "romania": ("divizia", "liga1", "ntf-opening-squad"),
    "russia": ("rfpl", "rpl", "russiapl", "premier"),
    "scotland": ("scotprm", "scotsp"), "serbia": ("superl", "ntf-opening-squad"),
    "slovakia": ("superl", "ntf-opening-squad"), "slovenia": ("prvaliga", "ntf-opening-squad"),
    "spain": ("laliga", "spalali"), "sweden": ("allsven", "swedalls"),
    "switzerland": ("superl", "switzsup"), "turkey": ("superl", "tursuper"),
    "ukraine": ("upl", "ukrainepl", "ntf-opening-squad"), "uruguay": ("primera", "uruprim", "ntf-opening-squad"),
    "venezuela": ("primera", "ntf-opening-squad"),
    "wales": ("premier",),
    "english-non-league": ("national", "confprem", "confnat", "confer", "conf", "soccerbase-august", "ntf-opening-squad"),
}


class AllocationError(ValueError):
    """A source or carrier graph cannot support deterministic allocation."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    words = "".join(character.casefold() if character.isalnum() else " " for character in text if not unicodedata.combining(character)).split()
    ignored = {"a", "ac", "afc", "as", "c", "cf", "club", "f", "fc", "fk", "rc", "sc", "sv"}
    key = "".join(word for word in words if word not in ignored)
    # Reviewed historical aliases for the two real English continuation clubs
    # whose PM99 abbreviated labels are not lexical matches for Soccerbase.
    # Keep this deliberately explicit: broad prefix matching could silently
    # bind two unrelated clubs and would undermine the continuity lock.
    return {
        "doncaster": "doncasterrovers", "doncasterr": "doncasterrovers",
        "doncasterroversfootball": "doncasterrovers",
        "hereford": "herefordunited", "herefordu": "herefordunited",
        "herefordunitedfootball": "herefordunited",
    }.get(key, key)


def _source_groups(source: Mapping[str, Any], quality_gaps: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    if source.get("schema_version") != SOURCE_SCHEMA or not isinstance(source.get("clubs"), list):
        raise AllocationError(f"source must use {SOURCE_SCHEMA}")
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in source["clubs"]:
        if not isinstance(raw, Mapping):
            raise AllocationError("source club rows must be objects")
        country_catalog = str(raw.get("country_catalog") or "")
        competition = str(raw.get("competition_catalog") or "")
        group = COUNTRY_GROUPS.get(country_catalog)
        if country_catalog == "eng" and competition in PRIMARY_COMPETITIONS["english-non-league"]:
            group = "english-non-league"
        if group is None:
            continue
        priorities = PRIMARY_COMPETITIONS.get(group, ())
        if competition not in priorities:
            continue
        players = raw.get("players")
        if not isinstance(players, list) or len(players) < MIN_OPENING_SQUAD_PLAYERS:
            if quality_gaps is not None:
                quality_gaps.append({
                    "club_name": raw.get("club_name"), "country_group": group,
                    "player_count": len(players) if isinstance(players, list) else 0,
                    "source_path": raw.get("source_path"),
                    "status": "source-club-below-opening-xi-minimum-blocked",
                })
            continue
        row = dict(raw)
        row["competition_priority"] = priorities.index(competition)
        candidates[group].append(row)
    result: dict[str, list[dict[str, Any]]] = {}
    for group, rows in candidates.items():
        # More than one credited capture may cover the same top-flight family.
        # Prefer the primary catalogue, then retain distinct supplemental
        # identities. This fills a partial source without assigning one real
        # club twice merely because two providers spell it identically.
        ordered = sorted(rows, key=lambda row: (
            int(row["competition_priority"]), str(row["source_path"]), str(row["club_name"])
        ))
        selected: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for row in ordered:
            key = _normalise(row["club_name"])
            if not key:
                raise AllocationError(f"source top flight for {group} contains a blank normalized club")
            if key in seen_names:
                continue
            seen_names.add(key)
            selected.append(row)
        result[group] = selected
    return result


def _maximum_capacity_matching(
    carriers: Sequence[Mapping[str, Any]], clubs: Sequence[Mapping[str, Any]]
) -> dict[int, int]:
    """Return a deterministic maximum-cardinality carrier-to-club matching.

    A carrier can accept a club only when the dated source fills every fixed
    roster slot.  The old first-fit pass could consume a large squad on a
    small carrier and strand a smaller squad that would otherwise fit.  A
    standard augmenting-path matching removes that order artefact.  Edge order
    prefers the carrier's continuing identity, then the smallest adequate
    squad and canonical source order; carrier order handles the most
    restrictive (largest) rosters first.
    """

    carrier_order = sorted(
        range(len(carriers)),
        key=lambda index: (-len(carriers[index].get("roster_slots") or []), int(carriers[index]["carrier_id"])),
    )
    canonical_clubs = sorted(
        range(len(clubs)),
        key=lambda index: (str(clubs[index]["source_path"]), str(clubs[index]["club_name"])),
    )
    edges: dict[int, list[int]] = {}
    for carrier_index in carrier_order:
        carrier = carriers[carrier_index]
        required = len(carrier.get("roster_slots") or [])
        baseline = carrier.get("baseline_club") or {}
        continuing_keys = {
            _normalise(baseline.get("name")), _normalise(baseline.get("full_name"))
        } - {""}
        edges[carrier_index] = sorted(
            (
                club_index for club_index in canonical_clubs
                if len(clubs[club_index].get("players") or []) >= required
            ),
            key=lambda club_index: (
                _normalise(clubs[club_index]["club_name"]) not in continuing_keys,
                len(clubs[club_index].get("players") or []),
                str(clubs[club_index]["source_path"]),
                str(clubs[club_index]["club_name"]),
            ),
        )

    def maximum(
        available_carriers: Sequence[int], unavailable_clubs: set[int]
    ) -> dict[int, int]:
        club_owner: dict[int, int] = {}

        def assign(carrier_index: int, seen_clubs: set[int]) -> bool:
            for club_index in edges[carrier_index]:
                if club_index in unavailable_clubs or club_index in seen_clubs:
                    continue
                seen_clubs.add(club_index)
                previous = club_owner.get(club_index)
                if previous is None or assign(previous, seen_clubs):
                    club_owner[club_index] = carrier_index
                    return True
            return False

        for carrier_index in available_carriers:
            assign(carrier_index, set())
        return {carrier_index: club_index for club_index, carrier_index in club_owner.items()}

    maximum_count = len(maximum(carrier_order, set()))
    locked: dict[int, int] = {}
    locked_clubs: set[int] = set()
    # Retain an unambiguous continuing identity whenever doing so cannot lower
    # the maximum number of source-complete carriers.  The feasibility check
    # prevents identity preference from recreating the old capacity gap.
    for carrier_index in sorted(carrier_order, key=lambda index: int(carriers[index]["carrier_id"])):
        carrier = carriers[carrier_index]
        baseline = carrier.get("baseline_club") or {}
        keys = {_normalise(baseline.get("name")), _normalise(baseline.get("full_name"))} - {""}
        candidates = [
            club_index for club_index in edges[carrier_index]
            if club_index not in locked_clubs and _normalise(clubs[club_index]["club_name"]) in keys
        ]
        if len(candidates) != 1:
            continue
        club_index = candidates[0]
        tentative_carriers = set(locked) | {carrier_index}
        tentative_clubs = locked_clubs | {club_index}
        remaining = [index for index in carrier_order if index not in tentative_carriers]
        if len(tentative_carriers) + len(maximum(remaining, tentative_clubs)) == maximum_count:
            locked[carrier_index] = club_index
            locked_clubs.add(club_index)
    remaining = [index for index in carrier_order if index not in locked]
    return {**locked, **maximum(remaining, locked_clubs)}


def build_allocation(*, source: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(registry.get("carriers"), list):
        raise AllocationError("registry must contain carriers")
    gaps: list[dict[str, Any]] = []
    source_groups = _source_groups(source, gaps)
    carrier_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in registry["carriers"]:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("carrier_id"), int):
            raise AllocationError("registry carrier rows must contain integer carrier_id")
        carrier_id = int(raw["carrier_id"])
        group = group_for_carrier(carrier_id)
        if carrier_id in ENGLISH_NON_LEAGUE_CARRIER_IDS:
            group = "english-non-league"
        if group is not None:
            carrier_groups[group].append(dict(raw))
    # A real fixed carrier does not cease to represent its club merely because
    # that club was relegated from the country's primary competition.  Admit
    # exact baseline identities from other captured divisions as continuing
    # clubs, but never use arbitrary lower-division teams as replacements.
    continuing_names: dict[str, set[str]] = defaultdict(set)
    for group, carriers in carrier_groups.items():
        for carrier in carriers:
            baseline = carrier.get("baseline_club") or {}
            continuing_names[group].update({
                _normalise(baseline.get("name")), _normalise(baseline.get("full_name"))
            } - {""})
    selected_names = {
        group: {_normalise(row["club_name"]) for row in rows}
        for group, rows in source_groups.items()
    }
    supplements: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in source["clubs"]:
        if not isinstance(raw, Mapping):
            continue
        country_catalog = str(raw.get("country_catalog") or "")
        competition = str(raw.get("competition_catalog") or "")
        group = COUNTRY_GROUPS.get(country_catalog)
        name = _normalise(raw.get("club_name"))
        if country_catalog == "eng" and name in continuing_names.get("english-non-league", set()):
            group = "english-non-league"
        if (
            group not in carrier_groups
            or name not in continuing_names.get(group, set())
            or name in selected_names.setdefault(group, set())
        ):
            continue
        players = raw.get("players")
        if not isinstance(players, list) or len(players) < MIN_OPENING_SQUAD_PLAYERS:
            continue
        row = dict(raw)
        row["competition_priority"] = len(PRIMARY_COMPETITIONS.get(group, ())) + 1
        supplements[group].append(row)
        selected_names[group].add(name)
    for group, rows in supplements.items():
        source_groups.setdefault(group, []).extend(sorted(
            rows, key=lambda row: (str(row["competition_catalog"]), str(row["source_path"]), str(row["club_name"]))
        ))
    assignments: list[dict[str, Any]] = []
    for group in sorted(carrier_groups):
        carriers = sorted(carrier_groups[group], key=lambda row: int(row["carrier_id"]))
        clubs = list(source_groups.get(group, []))
        matching = _maximum_capacity_matching(carriers, clubs)
        assigned_clubs = set(matching.values())
        for carrier_index, club_index in sorted(
            matching.items(), key=lambda item: int(carriers[item[0]]["carrier_id"])
        ):
            carrier = carriers[carrier_index]
            club = clubs[club_index]
            baseline = carrier.get("baseline_club") or {}
            keys = {_normalise(baseline.get("name")), _normalise(baseline.get("full_name"))} - {""}
            method = (
                "continuing-club-normalized-identity"
                if _normalise(club["club_name"]) in keys
                else "same-country-replacement-canonical-source-order"
            )
            assignments.append(_row(group, carrier, club, method))
        for carrier_index, carrier in enumerate(carriers):
            if carrier_index in matching:
                continue
            gaps.append({
                "carrier_id": int(carrier["carrier_id"]), "country_group": group,
                "status": "source-unavailable-or-insufficient-country-capacity-blocked",
            })
        for club_index, club in enumerate(clubs):
            if club_index in assigned_clubs:
                continue
            matching_native = [
                carrier for carrier in carriers
                if _normalise(club["club_name"]) in {
                    _normalise((carrier.get("baseline_club") or {}).get("name")),
                    _normalise((carrier.get("baseline_club") or {}).get("full_name")),
                } - {""}
            ]
            for native in matching_native:
                required = len(native.get("roster_slots") or [])
                if len(club.get("players") or []) < required:
                    gaps.append({
                        "available_player_count": len(club.get("players") or []),
                        "carrier_id": int(native["carrier_id"]), "club_name": club["club_name"],
                        "country_group": group, "required_player_count": required,
                        "source_path": club["source_path"],
                        "status": "source-club-below-carrier-capacity-blocked",
                    })
            gaps.append({"club_name": club["club_name"], "country_group": group, "source_path": club["source_path"], "status": "source-club-exceeds-fixed-country-capacity"})
    assignments.sort(key=lambda row: int(row["carrier_id"]))
    gaps.sort(key=lambda row: (str(row.get("country_group")), int(row.get("carrier_id", 0)), str(row.get("club_name", ""))))
    return {
        "schema_version": SCHEMA,
        "season": source.get("season"),
        "source_sha256": document_sha256(source),
        "registry_sha256": document_sha256(registry),
        "topology_policy": "fixed-country-family-preserve-continuing-then-canonical-replacement",
        "assignments": assignments,
        "gaps": gaps,
        "coverage": {
            "assignment_count": len(assignments),
            "continuing_count": sum(row["method"] == "continuing-club-normalized-identity" for row in assignments),
            "replacement_count": sum(row["method"] == "same-country-replacement-canonical-source-order" for row in assignments),
            "xi_source_eligible_count": sum(len(club.get("players") or []) >= MIN_OPENING_SQUAD_PLAYERS
                                            for clubs in source_groups.values() for club in clubs),
            "release_capacity_eligible_count": len(assignments),
            "gap_count": len(gaps),
        },
    }


def _row(group: str, carrier: Mapping[str, Any], club: Mapping[str, Any], method: str) -> dict[str, Any]:
    return {
        "carrier_id": int(carrier["carrier_id"]),
        "country_group": group,
        "club_name": club["club_name"],
        "source_selector": {key: club[key] for key in ("country_catalog", "competition_catalog", "source_path", "source_sha256")},
        "method": method,
        "roster_capacity": len(carrier.get("roster_slots") or []),
    }


def _read(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode())
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise AllocationError(f"input must be canonical JSON: {path}")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = build_allocation(source=_read(args.source), registry=_read(args.registry))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
