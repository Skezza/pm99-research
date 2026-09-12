#!/usr/bin/env python3
"""Capture FK Klaipėdos Granitas from Lithuanian FA opening match sheets.

Transfermarkt retains the club identity but no 2015 schedule or squad rows.
The Lithuanian FA instead publishes the two opening 2015 A Lyga match sheets
with named first teams, benches and player profiles.  This source-only adapter
uses those two exact sheets, keeps the first XI ahead of the bench and second
fixture, and stops at the fixed 18-player carrier capacity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_opening_lineups_v1 as cache_lib  # noqa: E402


SCHEMA = "pm99-world-2015-lff-opening-squad-capture-v1"
PLAN_SCHEMA = "pm99-world-2015-source-tail-replacement-plan-v1"
TARGET_CARRIER_ID = 2253
TARGET_TITLE = "FK Klaipėdos Granitas"
TARGET_CAPACITY = 18

# In the first fixture Granitas is away (right table column); in the second it
# is home (left table column).  These are published 2015 match URLs, not a
# competition scrape or a team-name search.
MATCHES: tuple[dict[str, str | int], ...] = (
    {
        "date": "2015-03-01",
        "name_cell_index": 4,
        "shirt_cell_index": 3,
        "url": "https://lietuvosfutbolas.lt/rungtynes/fk-kauno-zalgiris-klaipedos-granitas-81625/",
    },
    {
        "date": "2015-03-08",
        "name_cell_index": 0,
        "shirt_cell_index": 1,
        "url": "https://lietuvosfutbolas.lt/rungtynes/klaipedos-granitas-fk-zalgiris-81642/",
    },
)

# The LFF records are authoritative for opening match sheets, but seven older
# player profiles deliberately publish a blank ``Pozicija`` field. This exact
# historical squad view states its competition and ``2015/2015`` season and
# supplies only those missing broad G/D/M/F groups. It is not used to choose a
# player, club membership, or an opening XI.
FOOTBALLTY_2015_SQUAD_URL = "https://footballty.com/team/granitas-klaip-da/"
FOOTBALLTY_CACHE_KEY = "position-source/footballty-granitas-2015.html"
# LFF's historical profile display shortens this one surname; the same named
# player is listed in the Granitas 2015 A Lyga roster with its published full
# Lithuanian spelling.  Keep this review explicit rather than applying a
# generic suffix transformation.
FOOTBALLTY_NAME_ALIASES = {"zigmantas-jesipov-1209": "Zigmantas Jesipovas"}

NATIONALITIES = {
    "Azerbaidžanas": "AZE", "Baltarusija": "BLR", "Brazil": "BRA", "Brazilija": "BRA",
    "Gruzija": "GEO", "Japonija": "JPN", "Kroatija": "CRO", "Lietuva": "LTU",
    "Lenkija": "POL", "Rusija": "RUS", "Ukraina": "UKR",
}
POSITIONS = {
    "Vartininkas": "G", "Gynėjas": "D", "Saugas": "M", "Puolėjas": "F",
}


class LffOpeningSquadError(ValueError):
    """The official opening-match source cannot establish a safe roster."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LffOpeningSquadError(f"cannot read tail plan: {path}") from exc
    if not isinstance(value, dict):
        raise LffOpeningSquadError("tail plan must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def _validate_target(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise LffOpeningSquadError("tail plan has an unsupported schema")
    for row in plan.get("assignments") or []:
        if not isinstance(row, Mapping) or row.get("carrier_id") != TARGET_CARRIER_ID:
            continue
        target = row.get("proposed_target") or row.get("target_membership")
        if not isinstance(target, Mapping) or target.get("article_title") != TARGET_TITLE:
            raise LffOpeningSquadError("Granitas plan target changed")
        if row.get("fixed_roster_slot_count") != TARGET_CAPACITY:
            raise LffOpeningSquadError("Granitas fixed carrier capacity changed")
        return {"assignment": dict(row), "target": dict(target)}
    raise LffOpeningSquadError("Granitas carrier is absent from tail plan")


def _match_players(payload: bytes, *, match: Mapping[str, str | int]) -> list[dict[str, Any]]:
    """Read target-side XI then bench from one published LFF match table."""

    soup = BeautifulSoup(payload, "html.parser")
    table = soup.select_one("table.teams")
    if table is None:
        raise LffOpeningSquadError("official match page has no lineup table")
    name_index, shirt_index = int(match["name_cell_index"]), int(match["shirt_cell_index"])
    rows: list[dict[str, Any]] = []
    for role, selector in (("starting-xi", "tr.firstteam"), ("substitute", "tr.bench")):
        for row in table.select(selector):
            cells = row.select("td")
            if len(cells) <= max(name_index, shirt_index):
                continue
            anchor = cells[name_index].select_one('a[href^="/zaidejai/"]')
            if anchor is None:
                continue
            url_path = str(anchor.get("href") or "")
            identifier = url_path.strip("/").split("/")[-1]
            # LFF appends role labels such as ``(G)`` and captain ``(C)`` to
            # the rendered lineup name. They are presentation metadata, not
            # part of the source player's legal/display name.
            name = re.sub(r"\s+\(([CG])\)$", "", anchor.get_text(" ", strip=True))
            name = " ".join(name.split())
            shirt = cells[shirt_index].get_text(" ", strip=True)
            if not name or not identifier or not shirt.isdigit():
                continue
            rows.append({
                "name": name,
                "player_id": identifier,
                "player_url": "https://lietuvosfutbolas.lt" + url_path,
                "role": role,
                "shirt_number": int(shirt),
            })
    if len(rows) < 11:
        raise LffOpeningSquadError("official match page has fewer than eleven target-side starters")
    return rows


def _normalise(value: object) -> str:
    """Compare documented spelling/diacritic variants without selecting a player."""

    text = str(value or "").casefold()
    replacements = str.maketrans({
        "ą": "a", "č": "c", "ę": "e", "ė": "e", "į": "i", "š": "s", "ų": "u", "ū": "u", "ž": "z",
    })
    return "".join(char for char in text.translate(replacements) if char.isalnum())


def _footballty_2015_positions(
    *, candidates: Sequence[Mapping[str, Any]], cache: cache_lib.SnapshotCache
) -> dict[str, str]:
    """Read broad positions from the declared 2015 Granitas squad section.

    This requires an exact candidate-name match inside the ``A Lyga /
    2015/2015`` squad section. A match elsewhere on the page (for example a
    transfer-history row) cannot qualify a position.
    """

    payload = cache.get(FOOTBALLTY_2015_SQUAD_URL, FOOTBALLTY_CACHE_KEY)
    page = BeautifulSoup(payload, "html.parser")
    section = page.select_one('section[data-scroll-section="lineup"]')
    if section is None:
        raise LffOpeningSquadError("secondary 2015 position source has no squad section")
    section_text = section.get_text(" ", strip=True)
    if "A Lyga" not in section_text or "2015/2015" not in section_text:
        raise LffOpeningSquadError("secondary position source is not its declared 2015 A Lyga squad")
    result: dict[str, str] = {}
    for candidate in candidates:
        key = str(candidate["player_id"])
        name = FOOTBALLTY_NAME_ALIASES.get(key, str(candidate["name"]))
        rows = []
        for row in section.select("players-list-item"):
            published_names = {
                _normalise(anchor.get_text(" ", strip=True)) for anchor in row.select("a")
            }
            if _normalise(name) in published_names:
                rows.append(row)
        if len(rows) != 1:
            raise LffOpeningSquadError(
                f"secondary 2015 position source has {len(rows)} exact rows for {name!r}"
            )
        groups = re.findall(r"(?<![A-Za-z])([GDMF])(?![A-Za-z])", rows[0].get_text(" ", strip=True))
        if len(groups) != 1:
            raise LffOpeningSquadError(
                f"secondary 2015 position source has an ambiguous broad position for {name!r}"
            )
        result[key] = groups[0]
    return result


def _profile_player(
    *, candidate: Mapping[str, Any], cache: cache_lib.SnapshotCache
) -> dict[str, Any]:
    player_id = str(candidate["player_id"])
    payload = cache.get(str(candidate["player_url"]), f"players/{player_id}.html")
    page = BeautifulSoup(payload, "html.parser")
    information: dict[str, str] = {}
    for item in page.select(".playerInfo2 li"):
        label = item.select_one("b")
        if label is None:
            continue
        key = label.get_text(" ", strip=True)
        value = item.get_text(" ", strip=True)[len(key):].strip(" :-")
        information[key] = value
    position_label = information.get("Pozicija", "")
    nationality_label = information.get("Pilietybė", "")
    position = POSITIONS.get(position_label)
    nationality = NATIONALITIES.get(nationality_label, "UNK")
    unresolved = ["birth_date", "height_cm", "weight_kg"]
    if position is None:
        unresolved.append("primary_position")
    if nationality == "UNK":
        unresolved.append("nationality_code")
    return {
        "shirt_number": int(candidate["shirt_number"]),
        "name": str(candidate["name"]),
        "nationality": nationality,
        "position": position,
        "height_cm": None,
        "weight_kg": None,
        "birth_date": None,
        "unresolved_fields": unresolved,
        "opening_source": {
            "fixture_date": str(candidate["fixture_date"]),
            "lineup_url": str(candidate["lineup_url"]),
            "player_profile_url": str(candidate["player_url"]),
            "player_source_id": player_id,
            "selection_role": str(candidate["role"]),
        },
    }


def capture(*, plan: Mapping[str, Any], cache: cache_lib.SnapshotCache) -> dict[str, Any]:
    target = _validate_target(plan)
    candidates: list[dict[str, Any]] = []
    for index, match in enumerate(MATCHES):
        payload = cache.get(str(match["url"]), f"matches/{match['date']}.html")
        for row in _match_players(payload, match=match):
            if any(existing["player_id"] == row["player_id"] for existing in candidates):
                continue
            candidates.append({
                **row,
                "fixture_date": match["date"],
                "lineup_url": match["url"],
                "fixture_order": index,
            })
    if len(candidates) < TARGET_CAPACITY:
        raise LffOpeningSquadError(
            f"two official opening match sheets provide only {len(candidates)}/{TARGET_CAPACITY} unique players"
        )
    selected = candidates[:TARGET_CAPACITY]
    players = [_profile_player(candidate=row, cache=cache) for row in selected]
    missing_positions = [candidate for candidate, player in zip(selected, players) if player["position"] is None]
    if missing_positions:
        position_overrides = _footballty_2015_positions(candidates=missing_positions, cache=cache)
        for candidate, player in zip(selected, players):
            if player["position"] is not None:
                continue
            player["position"] = position_overrides[str(candidate["player_id"])]
            player["unresolved_fields"].remove("primary_position")
            player["opening_source"]["position_source_url"] = FOOTBALLTY_2015_SQUAD_URL
            player["opening_source"]["position_source_season"] = "2015/2015 A Lyga"
    if any(player["position"] is None for player in players):
        raise LffOpeningSquadError("official profile has an unmapped published position")
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; exact planned Granitas carrier; first match XI then bench and second opening match "
            "appearances; stops at immutable capacity; player profile fields absent from the official page are explicit gaps; "
            "a declared 2015 squad-category source supplies only broad positions when the official profile publishes none"
        ),
        "source": {
            "title": (
                "Lithuanian Football Federation published 2015 match reports and player profiles; "
                "Footballty 2015 A Lyga squad categories only for blank official position fields"
            ),
            "repository": "https://lietuvosfutbolas.lt",
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "club": {
            "candidate_carrier_id": TARGET_CARRIER_ID,
            "fixed_roster_slot_count": TARGET_CAPACITY,
            "club_name": target["target"]["name"],
            "target_article_title": TARGET_TITLE,
            "target_article_path": target["target"]["article_path"],
            "country_catalog": target["assignment"].get("family"),
            "competition_catalog": "lff-2015-a-lyga-opening-window",
            "source_url": str(MATCHES[0]["url"]),
            "source_season_label": "2015",
            "players": players,
            "opening_fixture": {"date": MATCHES[0]["date"], "lineup_source_url": MATCHES[0]["url"]},
        },
        "coverage": {"capacity_complete": True, "player_count": len(players)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source receipt: {args.output}")
    try:
        plan, plan_sha = _load(args.plan)
        result = capture(
            plan=plan,
            cache=cache_lib.SnapshotCache(args.cache_root, offline=args.offline, delay=args.delay),
        )
    except (OSError, LffOpeningSquadError, cache_lib.CaptureError) as exc:
        parser.error(str(exc))
    result["source"]["tail_plan_sha256"] = plan_sha
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
