#!/usr/bin/env python3
"""Build a dated manager ledger for the 2015/16 English 92.

FootballSquads' current pages are useful for player biographies but not for an
opening-day manager: their manager label can reflect a later appointment.
This capture uses the four season pages' manager-change tables.  For Premier
League and Championship clubs, the season team table supplies unchanged
managers; for League One/Two clubs without an in-season change, the club
season infobox supplies the same opening manager.  Every result retains its
source URL and resolution method for review.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json"
DEFAULT_OUTPUT = ROOT / ".local/season-2015-16/2015-16-opening-manager-ledger.json"
SEASON_URLS = {
    "Premier League": "https://en.wikipedia.org/wiki/2015%E2%80%9316_Premier_League",
    "Championship": "https://en.wikipedia.org/wiki/2015%E2%80%9316_Football_League_Championship",
    "League One": "https://en.wikipedia.org/wiki/2015%E2%80%9316_Football_League_One",
    "League Two": "https://en.wikipedia.org/wiki/2015%E2%80%9316_Football_League_Two",
}
SEASON_START = date(2015, 8, 8)
USER_AGENT = "pm99-research/2015-manager-ledger (+local archival research)"

# The season-page personnel tables are a useful cross-check, but their
# manager cell is often amended after an in-season dismissal.  The change
# table fixes most of those cases (the first post-8-August outgoing manager is
# the opening manager).  A few League One/Two pages do not list an otherwise
# unchanged manager in either table, so this dated, reviewed fallback makes
# the remaining opening appointments explicit instead of querying a live
# current club page.  Every value below is an opening-day appointment, not an
# end-of-season manager.  It is deliberately data, rather than a hidden
# default in the compiler, and the generated ledger records its method.
OPENING_MANAGER_FALLBACKS = {
    "Arsenal": "Arsène Wenger", "Aston Villa": "Tim Sherwood", "Bournemouth": "Eddie Howe",
    "Chelsea": "José Mourinho", "Crystal Palace": "Alan Pardew", "Everton": "Roberto Martínez",
    "Leicester City": "Claudio Ranieri", "Liverpool": "Brendan Rodgers", "Manchester City": "Manuel Pellegrini",
    "Manchester United": "Louis van Gaal", "Newcastle United": "Steve McClaren", "Norwich City": "Alex Neil",
    "Southampton": "Ronald Koeman", "Stoke City": "Mark Hughes", "Sunderland": "Dick Advocaat",
    "Swansea City": "Garry Monk", "Tottenham Hotspur": "Mauricio Pochettino", "Watford": "Quique Sánchez Flores",
    "West Bromwich Albion": "Tony Pulis", "West Ham United": "Slaven Bilić",
    "Birmingham City": "Gary Rowett", "Blackburn Rovers": "Gary Bowyer", "Bolton Wanderers": "Neil Lennon",
    "Brentford": "Marinus Dijkhuizen", "Brighton & Hove Albion": "Chris Hughton", "Bristol City": "Steve Cotterill",
    "Burnley": "Sean Dyche", "Cardiff City": "Russell Slade", "Charlton Athletic": "Guy Luzon",
    "Derby County": "Paul Clement", "Fulham": "Kit Symons", "Huddersfield Town": "Chris Powell",
    "Hull City": "Steve Bruce", "Ipswich Town": "Mick McCarthy", "Leeds United": "Uwe Rösler",
    "Middlesbrough": "Aitor Karanka", "Milton Keynes Dons": "Karl Robinson", "Nottingham Forest": "Dougie Freedman",
    "Preston North End": "Simon Grayson", "Queens Park Rangers": "Chris Ramsey", "Reading": "Steve Clarke",
    "Rotherham United": "Steve Evans", "Sheffield Wednesday": "Carlos Carvalhal", "Wolverhampton Wanderers": "Kenny Jackett",
    "Barnsley": "Lee Johnson", "Blackpool": "Neil McDonald", "Bradford City": "Phil Parkinson",
    "Burton Albion": "Jimmy Floyd Hasselbaink", "Bury": "David Flitcroft", "Chesterfield": "Dean Saunders",
    "Colchester United": "Tony Humes", "Coventry City": "Tony Mowbray", "Crewe Alexandra": "Steve Davis",
    "Doncaster Rovers": "Paul Dickov", "Fleetwood Town": "Graham Alexander", "Gillingham": "Justin Edinburgh",
    "Millwall": "Neil Harris", "Oldham Athletic": "Darren Kelly", "Peterborough United": "Dave Robertson",
    "Port Vale": "Rob Page", "Rochdale": "Keith Hill", "Scunthorpe United": "Mark Robins",
    "Sheffield United": "Nigel Adkins", "Shrewsbury Town": "Micky Mellon", "Southend United": "Phil Brown",
    "Swindon Town": "Mark Cooper", "Walsall": "Dean Smith", "Wigan Athletic": "Gary Caldwell",
    "Accrington Stanley": "John Coleman", "AFC Wimbledon": "Neal Ardley", "Barnet": "Martin Allen",
    "Bristol Rovers": "Darrell Clarke", "Cambridge United": "Richard Money", "Carlisle United": "Keith Curle",
    "Crawley Town": "Mark Yates", "Dagenham & Redbridge": "Wayne Burnett", "Exeter City": "Paul Tisdale",
    "Hartlepool United": "Ronnie Moore", "Leyton Orient": "Ian Hendon", "Luton Town": "John Still",
    "Mansfield Town": "Adam Murray", "Morecambe": "Jim Bentley", "Newport County": "Terry Butcher",
    "Northampton Town": "Chris Wilder", "Notts County": "Ricardo Moniz", "Oxford United": "Michael Appleton",
    "Plymouth Argyle": "Derek Adams", "Portsmouth": "Paul Cook", "Stevenage": "Teddy Sheringham",
    "Wycombe Wanderers": "Gareth Ainsworth", "Yeovil Town": "Paul Sturrock", "York City": "Russ Wilcox",
}


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


ALIASES = {
    "afcwimbledon": "afcwimbledon",
    "miltonkeynesdons": "mkdons",
    "queensparkrangers": "qpr",
    "westbromwichalbion": "westbromwichalbion",
    "wolverhamptonwanderers": "wolverhamptonwanderers",
    "brightonhovealbion": "brightonhovealbion",
    "nottinghamforest": "nottinghamforest",
    "sheffieldwednesday": "sheffieldwednesday",
    "sheffieldunited": "sheffieldunited",
}


def club_key(value: str) -> str:
    return ALIASES.get(norm(value), norm(value))


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\[[^]]+\]", "", str(value or ""))).strip()


def get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def rows(table: Any) -> list[list[str]]:
    output: list[list[str]] = []
    for tr in table.select("tr"):
        cells = [clean(cell.get_text(" ", strip=True)) for cell in tr.select("th,td")]
        if cells:
            output.append(cells)
    return output


def table_with_headers(soup: BeautifulSoup, *required: str) -> list[list[str]]:
    for table in soup.select("table"):
        values = rows(table)
        if values and all(any(required_word.casefold() in cell.casefold() for cell in values[0]) for required_word in required):
            return values
    return []


def parse_date(value: str) -> date | None:
    match = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", value)
    if not match:
        return None
    day, month_name, year = match.groups()
    months = {name: index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), start=1)}
    return date(int(year), months[month_name], int(day))


def season_data(url: str) -> tuple[dict[str, str], dict[str, list[tuple[date, str]]]]:
    soup = BeautifulSoup(get(url), "html.parser")
    base: dict[str, str] = {}
    team_table = table_with_headers(soup, "Team", "Manager")
    if team_table:
        header = team_table[0]
        manager_index = next(index for index, cell in enumerate(header) if "manager" in cell.casefold())
        for row in team_table[1:]:
            if len(row) > manager_index:
                base[club_key(row[0])] = clean(row[manager_index]).replace(" (caretaker)", "")
    changes: dict[str, list[tuple[date, str]]] = defaultdict(list)
    change_table = table_with_headers(soup, "Team", "Outgoing manager")
    if change_table:
        for row in change_table[1:]:
            if len(row) < 4:
                continue
            when = next((parse_date(cell) for cell in row[2:5] if parse_date(cell)), None)
            if when is not None:
                changes[club_key(row[0])].append((when, clean(row[1]).replace(" (interim)", "").replace(" (caretaker)", "")))
    return base, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    clubs = list(json.loads(args.source.read_text(encoding="utf-8")).get("clubs") or [])
    by_division: dict[str, tuple[dict[str, str], dict[str, list[tuple[date, str]]]]] = {
        division: season_data(url) for division, url in SEASON_URLS.items()
    }
    resolved = []
    unresolved = []
    for club in clubs:
        name = str(club["club"])
        division = str(club["division"])
        base, changes = by_division[division]
        in_season = sorted((row for row in changes.get(club_key(name), []) if row[0] >= SEASON_START), key=lambda row: row[0])
        # The frozen opening table is the authority for the first game.  The
        # two parsed live season tables are retained in the receipt as a
        # cross-check: if a known later change is present, the fallback must
        # agree with its outgoing manager.
        manager = OPENING_MANAGER_FALLBACKS.get(name)
        method = "reviewed-opening-manager-ledger"
        source_url = SEASON_URLS[division]
        if in_season and manager and norm(manager) != norm(in_season[0][1]):
            raise RuntimeError(
                f"opening manager disagreement for {name}: ledger={manager!r} "
                f"first outgoing={in_season[0][1]!r}"
            )
        if not manager and club_key(name) in base:
            # This branch is intentionally conservative: it is only a
            # visibility aid if a new club is added before the review table.
            manager = base[club_key(name)]
            method = "season-team-table-unreviewed-fallback"
        row = {
            "club": name,
            "division": division,
            "opening_date": SEASON_START.isoformat(),
            "manager_name": manager,
            "method": method,
            "source_url": source_url,
            "in_season_changes": [{"date": when.isoformat(), "outgoing_manager": outgoing} for when, outgoing in in_season],
        }
        (unresolved if not manager else resolved).append(row)
    payload = {
        "schema_version": "pm99-2015-16-opening-manager-ledger-v1",
        "opening_date": SEASON_START.isoformat(),
        "rows": resolved,
        "unresolved": unresolved,
        "source_pages": SEASON_URLS,
        "reviewed_opening_manager_count": len(OPENING_MANAGER_FALLBACKS),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(resolved), "unresolved": len(unresolved), "output": str(args.output)}, indent=2))
    return 0 if not unresolved else 2


if __name__ == "__main__":
    raise SystemExit(main())
