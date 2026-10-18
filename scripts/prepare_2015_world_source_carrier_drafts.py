#!/usr/bin/env python3
"""Allocate captured 2015 squads to the existing foreign PM99 carriers.

This is a reproducible *content-source draft*, not a topology writer.  A
carrier stays in its existing PM99 country family and its roster capacity is
immutable.  The output merely chooses a distinct, sufficiently large historic
squad from the same captured country for editorial completion (ground,
manager, kit, portraits and ratings remain separate facts).
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
from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier  # noqa: E402


SCHEMA = "pm99-world-2015-source-carrier-drafts-v1"
SOURCE_SCHEMA = "pm99-footballsquads-season-capture-v1"

# These labels identify the existing foreign carrier *families* already
# present in the PM99 base registry.  They select a source-country directory;
# the output has no country/division/competition field and cannot mutate one.
GROUP_TO_SOURCE_COUNTRY = {
    "argentina": "arg",
    "austria": "austria",
    "belgium": "belgium",
    "brazil": "brazil",
    "chile": "chile",
    "denmark": "denmark",
    "english-non-league": "eng",
    "france": "france",
    "germany": "ger",
    "greece": "greece",
    "hungary": "hungary",
    "ireland": "ireland",
    "italy": "italy",
    "netherlands": "netherl",
    "norway": "norway",
    "poland": "poland",
    "portugal": "portugal",
    "russia": "russia",
    "scotland": "scots",
    "spain": "spain",
    "sweden": "sweden",
    "switzerland": "switz",
    "turkey": "turkey",
    "ukraine": "ukraine",
}

# Membership comes from this captured competition directory.  This does not
# imply PM99 has a writable league field: it prevents a same-country source
# from silently supplying a Segunda club to a La Liga carrier.  If fixed PM99
# capacity is smaller than the real competition, omissions stay explicit.
GROUP_TO_SOURCE_COMPETITIONS = {
    "argentina": {"primera"}, "austria": {"bundes"}, "belgium": {"prolge"},
    "brazil": {"seriea"}, "chile": {"clausura"}, "denmark": {"supliga"},
    "english-non-league": {"national"}, "france": {"ligue1"}, "germany": {"bundes"},
    "greece": {"superl"}, "hungary": {"hungnb1"}, "ireland": {"prem"},
    "italy": {"seriea"}, "netherlands": {"ere"}, "norway": {"tippe"},
    "poland": {"ekstrak"}, "portugal": {"primeira"}, "russia": {"rfpl"},
    "scotland": {"scotprm"}, "spain": {"laliga"}, "sweden": {"allsven"},
    "switzerland": {"superl"}, "turkey": {"superl"}, "ukraine": {"upl"},
}


class DraftError(ValueError):
    """A registry or captured historic source is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DraftError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise DraftError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _club_selector(club: Mapping[str, Any]) -> dict[str, str]:
    fields = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
    result = {field: str(club.get(field) or "") for field in fields}
    if not all(result.values()):
        raise DraftError("captured club has incomplete source selector")
    return result


def build_drafts(*, registry: Mapping[str, Any], source_capture: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(registry.get("carriers"), list):
        raise DraftError("registry has no carrier list")
    if source_capture.get("schema_version") != SOURCE_SCHEMA or not isinstance(source_capture.get("clubs"), list):
        raise DraftError("source capture is not a FootballSquads capture")
    clubs_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for club in source_capture["clubs"]:
        if not isinstance(club, dict) or not isinstance(club.get("players"), list):
            raise DraftError("source capture has malformed club rows")
        selector = _club_selector(club)
        row = dict(club)
        row["_selector"] = selector
        row["_name_key"] = strict_club_key(row["club_name"])
        clubs_by_country[selector["country_catalog"]].append(row)
    for country in clubs_by_country:
        clubs_by_country[country].sort(key=lambda club: (str(club["club_name"]).casefold(), str(club["source_path"])))

    proposals: list[dict[str, Any]] = []
    used_selectors: set[tuple[str, str, str, str, str]] = set()
    used_club_identities: set[tuple[str, str]] = set()
    group_summary: dict[str, Counter[str]] = defaultdict(Counter)
    for carrier in sorted(registry["carriers"], key=lambda row: int(row["carrier_id"])):
        if not isinstance(carrier, dict):
            raise DraftError("registry contains a malformed carrier")
        carrier_id = int(carrier["carrier_id"])
        group = group_for_carrier(carrier_id)
        slot_count = len(carrier.get("roster_slots") or [])
        baseline_name = str((carrier.get("baseline_club") or {}).get("name") or "")
        source_country = GROUP_TO_SOURCE_COUNTRY.get(str(group or ""))
        source_competitions = GROUP_TO_SOURCE_COMPETITIONS.get(str(group or ""))
        base = {
            "carrier_id": carrier_id,
            "group": group,
            "baseline_name": baseline_name,
            "fixed_roster_slot_count": slot_count,
            "topology_policy": "preserve-existing-carrier-and-roster-slot-count",
        }
        if source_country is None or source_competitions is None:
            proposals.append({**base, "status": "no-captured-source-country"})
            group_summary[str(group or "unclassified")]["no-captured-source-country"] += 1
            continue
        pool = [
            club for club in clubs_by_country.get(source_country, [])
            if (
                str(club["competition_catalog"]) in source_competitions
                and tuple(club["_selector"].values()) not in used_selectors
                and (source_country, str(club["_name_key"])) not in used_club_identities
                and len(club["players"]) >= slot_count
            )
        ]
        if not pool:
            proposals.append({
                **base,
                "source_country_catalog": source_country,
                "source_competition_catalogs": sorted(source_competitions),
                "status": "no-distinct-captured-top-competition-squad-with-required-capacity",
            })
            group_summary[str(group)]["no-distinct-captured-top-competition-squad-with-required-capacity"] += 1
            continue
        baseline_key = strict_club_key(baseline_name)
        exact = [club for club in pool if club["_name_key"] == baseline_key and baseline_key]
        chosen = exact[0] if exact else min(
            pool,
            key=lambda club: (-len(club["players"]), str(club["club_name"]).casefold(), str(club["source_path"])),
        )
        selector = chosen["_selector"]
        selector_tuple = tuple(selector.values())
        used_selectors.add(selector_tuple)
        used_club_identities.add((source_country, str(chosen["_name_key"])))
        method = "same-normalised-club-name" if chosen in exact else "deterministic-capacity-first-same-country-top-competition"
        proposals.append({
            **base,
            "source_country_catalog": source_country,
            "source_competition_catalogs": sorted(source_competitions),
            "status": "source-squad-ready",
            "allocation_method": method,
            "source_selector": selector,
            "source_club_name": chosen["club_name"],
            "source_player_row_count": len(chosen["players"]),
            "remaining_editorial_work": [
                "manager-source-and-identity",
                "ground-and-capacity-source",
                "ratings-reconciliation",
                "historical-tactical-role-selection",
                "era-kit-decision",
                "portrait-or-native-no-photo-decision",
            ],
        })
        group_summary[str(group)]["source-squad-ready"] += 1
    status_counts = Counter(str(row["status"]) for row in proposals)
    return {
        "schema_version": SCHEMA,
        "policy": "existing-carriers-only; preserve-country-family-and-roster-capacity; no-topology-write",
        "registry_sha256": hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest(),
        "source_capture_sha256": hashlib.sha256(canonical_json_bytes(dict(source_capture))).hexdigest(),
        "coverage": {
            "carrier_count": len(proposals),
            "status_counts": dict(sorted(status_counts.items())),
            "source_squad_ready_slot_count": sum(
                int(row["fixed_roster_slot_count"]) for row in proposals if row["status"] == "source-squad-ready"
            ),
            "groups": {key: dict(sorted(value.items())) for key, value in sorted(group_summary.items())},
        },
        "proposals": proposals,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        registry, _ = _read_canonical(args.registry, label="registry")
        source_capture, _ = _read_canonical(args.source_capture, label="source capture")
        result = build_drafts(registry=registry, source_capture=source_capture)
    except (OSError, DraftError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
