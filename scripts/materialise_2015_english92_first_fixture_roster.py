#!/usr/bin/env python3
"""Materialise a dated first-fixture roster source for the 2015/16 compiler.

The published season roster is retained as the base.  Players named in an
opening league match but absent from that snapshot are appended from the
reviewable additions ledger, with their match-day shirt numbers.  This avoids
the historically false outcome where an opening XI points at somebody who is
not in the compiled club roster.
"""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_NATIONALITY_TO_PM99 = {
    "antigua and barbuda": "XXX", "argentina": "ARG", "barbados": "XXX", "belgium": "BEL",
    "brazil": "BRA", "bulgaria": "BUL", "costa rica": "CRC", "cote divoire": "CIV",
    "croatia": "CRO", "curacao": "XXX", "cyprus": "XXX", "czech republic": "CZE", "dr congo": "COD",
    "egypt": "EGY", "england": "ENG", "finland": "FIN", "france": "FRA", "greece": "GRE",
    "grenada": "XXX", "guadeloupe": "FRA", "guinea": "GUI", "guinea bissau": "GUI", "iceland": "ISL",
    "ireland": "IRL", "italy": "ITA", "jamaica": "JAM", "jersey": "ENG", "mali": "MLI",
    "mauritania": "XXX", "mexico": "MEX", "montserrat": "XXX", "netherlands": "NED", "nigeria": "NGA",
    "northern ireland": "NIR", "norway": "NOR", "poland": "POL", "portugal": "POR", "romania": "ROU",
    "scotland": "SCO", "sierra leone": "SLE", "spain": "ESP", "st kitts nevis": "XXX", "sweden": "SWE",
    "switzerland": "SUI", "the gambia": "GAM", "tunisia": "TUN", "uganda": "UGA", "uruguay": "URU", "wales": "WAL",
}
DEFAULT_WEIGHT_KG = {"G": 82, "D": 75, "M": 72, "F": 75}
DEFAULT_HEIGHT_CM = {"G": 188, "D": 180, "M": 175, "F": 180}


def _normalise(value: str) -> str:
    text = str(value or "").translate(str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o", "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fifa_physical(path: Path) -> dict[str, Any]:
    exact: dict[tuple[str, str], tuple[int, int, str]] = {}
    by_dob: dict[str, list[tuple[str, int, int, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = _normalise(str(row.get("name") or row.get("short_name") or ""))
            date = str(row.get("birthdate") or row.get("dob") or "")
            if not name or not date:
                continue
            try:
                height = int(float(str(row.get("height") or row.get("height_cm") or "")))
                weight = int(float(str(row.get("weight") or row.get("weight_kg") or "")))
            except ValueError:
                continue
            physical = (height, weight, str(row.get("nationality") or ""))
            exact[(name, date)] = physical
            by_dob[date].append((name, *physical))
    return {"exact": exact, "by_dob": by_dob}


def _iso_dob(ddmmyy: str) -> str:
    day, month, year = str(ddmmyy).split("-")
    return f"{1900 + int(year) if int(year) >= 20 else 2000 + int(year):04d}-{int(month):02d}-{int(day):02d}"


def _resolve_fifa_physical(index: dict[str, Any], name: str, birth_date: str) -> tuple[tuple[int, int, str] | None, str | None]:
    key = (_normalise(name), birth_date)
    direct = index["exact"].get(key)
    if direct is not None:
        return direct, "FIFA16-exact-name-and-dob"
    ranked = [
        (SequenceMatcher(a=key[0], b=candidate_name).ratio(), height, weight, nationality)
        for candidate_name, height, weight, nationality in index["by_dob"].get(birth_date, [])
    ]
    ranked.sort(reverse=True)
    if not ranked or ranked[0][0] < 0.78 or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08):
        return None, None
    _ratio, height, weight, nationality = ranked[0]
    return (height, weight, nationality), "FIFA16-dob-and-strict-name-alias"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", type=Path, default=ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json")
    parser.add_argument("--additions", required=True, type=Path)
    parser.add_argument("--fifa16", type=Path, default=ROOT / ".local/season-2015-16/fifa16-player-stats.csv")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = _load(args.source_ledger)
    additions = _load(args.additions)
    fifa = _fifa_physical(args.fifa16)
    rows_by_club: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in additions["rows"]:
        rows_by_club[str(row["club"])].append(row)
    output_clubs: list[dict[str, Any]] = []
    added = 0
    fallback_weight = 0
    fallback_height = 0
    unknown_nationality = 0
    for club in source["clubs"]:
        updated = dict(club)
        players = [dict(row) for row in club["players"]]
        existing = {_normalise(str(row["name"])) for row in players}
        additions_for_club = sorted(rows_by_club[str(club["club"])], key=lambda row: (row["list"] != "starting_xi", int(row["shirt_number"]), row["source_name"]))
        for addition in additions_for_club:
            name = str(addition["source_name"])
            if _normalise(name) in existing:
                continue
            position = str(addition["position"])
            fifa_row, fifa_method = _resolve_fifa_physical(fifa, name, _iso_dob(str(addition["birth_date_ddmmyy"])))
            height = int(addition["height_cm"]) if addition.get("height_cm") else (fifa_row[0] if fifa_row else DEFAULT_HEIGHT_CM[position])
            weight = fifa_row[1] if fifa_row else DEFAULT_WEIGHT_KG[position]
            if not addition.get("height_cm") and not fifa_row:
                fallback_height += 1
            if not fifa_row:
                fallback_weight += 1
            nationality = PROFILE_NATIONALITY_TO_PM99.get(_normalise(str(addition["nationality_label"])), "XXX")
            if nationality == "XXX":
                unknown_nationality += 1
            players.append({
                "shirt_number": int(addition["shirt_number"]), "name": name, "nationality": nationality,
                "position": position, "height_cm": height, "weight_kg": weight,
                "birth_date_ddmmyy": str(addition["birth_date_ddmmyy"]),
                "first_fixture_source": {
                    "source_player_id": addition["source_player_id"], "source_slug": addition["source_slug"],
                    "profile_url": addition["profile_url"], "snapshot_list": addition["list"],
                    "height_status": addition["height_status"] if addition.get("height_cm") else (fifa_method or "declared-position-fallback"),
                    "weight_status": fifa_method or "declared-position-fallback",
                    "nationality_label": addition["nationality_label"],
                    "nationality_status": "PM99-supported-map" if nationality != "XXX" else "PM99-unsupported-preserved-as-XXX",
                },
            })
            existing.add(_normalise(name))
            added += 1
        updated["players"] = players
        output_clubs.append(updated)
    output = dict(source)
    output.update({
        "schema_version": "pm99-2015-16-first-fixture-enriched-roster-v1",
        "snapshot": "FootballSquads season roster enriched with first 2015/16 league-fixture players and dated shirt numbers",
        "clubs": output_clubs,
        "first_fixture_additions": {"count": added, "weight_fallback_count": fallback_weight, "height_fallback_count": fallback_height, "unsupported_nationality_count": unknown_nationality},
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["first_fixture_additions"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
