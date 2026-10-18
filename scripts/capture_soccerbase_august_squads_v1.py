#!/usr/bin/env python3
"""Capture deterministic August squads from Soccerbase league match sheets.

An explicit Soccerbase tournament-season id enumerates the dated clubs. For
each club, only league match sheets from its first fixture through 31 August
are used. Starters precede named substitutes, then later first appearances.
Team, match and player pages are URL-bound, cached and hashed. A player who
does not appear on those August sheets is not inferred into the squad.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_ntf_historical_carrier_squads_v1 import Cache
from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes

BASE = "https://www.soccerbase.com"
SCHEMA = "pm99-footballsquads-season-capture-v1"
GAP_SCHEMA = "pm99-soccerbase-august-squad-gaps-v1"
POSITION = {"G": "G", "D": "D", "M": "M", "F": "F"}
NATIONALITY = {
    "England": "ENG", "Ireland": "IRL", "Northern Ireland": "NIR",
    "Scotland": "SCO", "Wales": "WAL",
}


def _id(href: str, name: str) -> int | None:
    value = parse_qs(urlparse(href).query).get(name)
    return int(value[0]) if value and value[0].isdigit() else None


def tournament_teams(payload: bytes) -> list[tuple[str, int]]:
    soup = BeautifulSoup(payload, "html.parser")
    table = soup.select_one("table.table")
    if table is None:
        raise ValueError("tournament page has no standings table")
    result: list[tuple[str, int]] = []
    for anchor in table.select("a[href*='team_id=']"):
        team_id = _id(anchor.get("href", ""), "team_id")
        name = " ".join(anchor.get_text(" ", strip=True).split())
        if team_id is not None and name and (name, team_id) not in result:
            result.append((name, team_id))
    if not result:
        raise ValueError("tournament standings has no teams")
    return result


def august_games(payload: bytes, *, competition: str, start_year: int) -> tuple[str, list[tuple[date, int, str]]]:
    soup = BeautifulSoup(payload, "html.parser")
    heading = soup.select_one("h1")
    club_name = " ".join((heading.get_text(" ", strip=True) if heading else "").split())
    club_name = re.sub(r"\s+(results|fixtures).*$", "", club_name, flags=re.I).strip().rstrip(".")
    games: list[tuple[date, int, str]] = []
    for row in soup.select("tr.match[id^='tgc']"):
        tournament_cell = row.select_one("td.tournament")
        tournament_link = tournament_cell.select_one("a") if tournament_cell else None
        competition_name = " ".join((tournament_link.get_text(" ", strip=True)
                                      if tournament_link else "").split())
        hidden = row.select_one("td.dateTime span.hide")
        if competition_name != competition or hidden is None:
            continue
        match = re.search(r"(\d{4}-\d{2}-\d{2})", hidden.get_text(" ", strip=True))
        game_id = row.get("id", "")[3:]
        if not match or not game_id.isdigit():
            continue
        game_date = date.fromisoformat(match.group(1))
        if game_date.year == start_year and game_date.month == 8:
            home = row.select_one("td.homeTeam a[href*='team_id=']")
            away = row.select_one("td.awayTeam a[href*='team_id=']")
            side = "teamA" if home and str(_id(home.get("href", ""), "team_id")) in payload.decode(errors="ignore") else ""
            # The caller determines its side from the explicit team id.
            games.append((game_date, int(game_id), side))
    return club_name, sorted(games)


def match_players(payload: bytes, *, team_id: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(payload, "html.parser")
    score = soup.select_one("div.gameInfo p.score")
    if score is None:
        return []
    sides: dict[str, int | None] = {"teamA": None, "teamB": None}
    # Soccerbase match fragments do not put team ids in the score; lineup
    # player ownership is recovered by checking which side contains a player
    # link also present in the team's results player filter. The capture caller
    # therefore supplies a side marker separately when parsing a game.
    for side in ("teamA", "teamB"):
        column = soup.select_one(f"div.lineup div.{side}")
        if column is not None:
            column["data-side"] = side
    return []


def side_players(payload: bytes, *, side: str) -> list[tuple[int, str, str | None, bool]]:
    soup = BeautifulSoup(payload, "html.parser")
    column = soup.select_one(f"div.lineup div.{side}")
    if column is None:
        return []
    result: list[tuple[int, str, str | None, bool]] = []
    for index, anchor in enumerate(column.select("a[href*='player_id=']")):
        player_id = _id(anchor.get("href", ""), "player_id")
        if player_id is None or any(row[0] == player_id for row in result):
            continue
        label = " ".join(anchor.get_text(" ", strip=True).split())
        pos = re.search(r"\(([GDMF])\)", anchor.parent.get_text(" ", strip=True))
        result.append((player_id, label, POSITION.get(pos.group(1)) if pos else None, index < 11))
    return result


def player_profile(payload: bytes, *, fallback_name: str, fallback_position: str | None) -> dict[str, Any]:
    soup = BeautifulSoup(payload, "html.parser")
    heading = soup.select_one("h1")
    name = " ".join((heading.get_text(" ", strip=True) if heading else fallback_name).split())
    name = re.sub(r"^\d+\.\s*", "", name)
    text = " ".join(soup.get_text(" ", strip=True).split())
    born = re.search(r"Born\s+(\d{2})\s+([A-Z][a-z]{2}),\s+(\d{4})", text)
    months = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
    birth_date = f"{born.group(3)}-{months[born.group(2)]:02d}-{int(born.group(1)):02d}" if born else None
    nationality_name = (re.search(r"Nationality\s+([^|]+?)\s+Date Signed", text) or [None, None])[1]
    nationality = NATIONALITY.get(nationality_name.strip()) if nationality_name else None
    height = re.search(r"Height\s+[^()]*\((\d\.\d{2})m\)", text)
    weight = re.search(r"Weight\s+[^()]*\(([\d.]+)kg\)", text)
    position_text = soup.select_one("table.playerInfo") or soup.select_one("table")
    position_match = re.search(r"\b(Goalkeeper|Defender|Midfielder|Forward)\b", position_text.get_text(" ", strip=True) if position_text else "")
    pos_map = {"Goalkeeper": "G", "Defender": "D", "Midfielder": "M", "Forward": "F"}
    position = pos_map.get(position_match.group(1)) if position_match else fallback_position
    height_cm = round(float(height.group(1)) * 100) if height else None
    weight_kg = round(float(weight.group(1))) if weight else None
    # Source pages occasionally contain clearly corrupt measurements. Preserve
    # the page hash but treat values outside the canonical intake domain as an
    # explicit unresolved fact rather than emitting an invalid or invented one.
    if height_cm is not None and not 120 <= height_cm <= 230:
        height_cm = None
    if weight_kg is not None and not 40 <= weight_kg <= 140:
        weight_kg = None
    row = {"birth_date": birth_date, "height_cm": height_cm,
           "name": name, "nationality": nationality, "position": position,
           "shirt_number": None, "weight_kg": weight_kg}
    row["unresolved_fields"] = [
        ("primary_position" if key == "position" else key)
        for key in ("shirt_number", "nationality", "position", "height_cm", "weight_kg", "birth_date")
        if row[key] is None
    ]
    return row


def career_covers(payload: bytes, *, club_name: str, cutoff: date) -> bool:
    """Verify that a Soccerbase career spell covers the requested cutoff."""

    def parse(value: str) -> date | None:
        match = re.fullmatch(r"(\d{2}) ([A-Z][a-z]{2}), (\d{2})", value)
        if not match:
            return None
        year = int(match.group(3))
        year += 1900 if year >= 50 else 2000
        months = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
        return date(year, months[match.group(2)], int(match.group(1)))

    wanted = re.sub(r"[^a-z0-9]", "", club_name.casefold())
    soup = BeautifulSoup(payload, "html.parser")
    for tr in soup.select("tr"):
        cells = [" ".join(cell.get_text(" ", strip=True).split()) for cell in tr.select("th,td")]
        if len(cells) < 3 or re.sub(r"[^a-z0-9]", "", cells[0].casefold()) != wanted:
            continue
        start, end = parse(cells[1]), parse(cells[2])
        if start is not None and start <= cutoff and (end is None or cutoff <= end):
            return True
    return False


def capture(*, tournament_id: int, season_id: int, start_year: int, competition: str, cache: Cache,
            registered_players: Mapping[int, Sequence[int]] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    tournament_url = f"{BASE}/tournaments/tournament.sd?tourn_id={tournament_id}"
    tournament = cache.get(tournament_url, f"tournament/{tournament_id}.html")
    clubs, gaps = [], []
    match_cache: dict[int, bytes] = {}
    profile_cache: dict[int, dict[str, Any]] = {}
    for table_name, team_id in tournament_teams(tournament):
        team_url = f"{BASE}/teams/team.sd?season_id={season_id}&team_id={team_id}&teamTabs=results"
        team_payload = cache.get(team_url, f"team/{team_id}.html")
        club_name, games = august_games(team_payload, competition=competition, start_year=start_year)
        # Determine the club's home/away side from its own result row.
        team_soup = BeautifulSoup(team_payload, "html.parser")
        ordered: list[tuple[int, str, str | None, bool, date, int]] = []
        for game_date, game_id, _unused in games:
            row = team_soup.select_one(f"tr#tgc{game_id}")
            home = row.select_one("td.homeTeam a[href*='team_id=']") if row else None
            side = "teamA" if home and _id(home.get("href", ""), "team_id") == team_id else "teamB"
            if game_id not in match_cache:
                url = f"{BASE}/matches/additional_information.sd?id_game={game_id}"
                try:
                    match_cache[game_id] = cache.get(url, f"match/{game_id}.html")
                except Exception as exc:
                    gaps.append({
                        "club_name": club_name or table_name, "game_date": game_date.isoformat(),
                        "game_id": game_id, "reason": "august-match-sheet-unavailable",
                        "source_url": url, "detail": str(exc), "team_id": team_id,
                    })
                    continue
            for player_id, label, position, starter in side_players(match_cache[game_id], side=side):
                ordered.append((player_id, label, position, starter, game_date, game_id))
        # All opening-fixture starters first, then every player's first dated
        # August appearance in match/lineup order.
        first_game = games[0][1] if games else None
        ordered.sort(key=lambda row: (not (row[5] == first_game and row[3]), row[4], row[5]))
        unique: list[tuple[int, str, str | None]] = []
        for player_id, label, position, _starter, _date, _game in ordered:
            if not any(row[0] == player_id for row in unique):
                unique.append((player_id, label, position))
        players = []
        for player_id, label, position in unique:
            if player_id not in profile_cache:
                url = f"{BASE}/players/player.sd?player_id={player_id}"
                payload = cache.get(url, f"player/{player_id}.html")
                profile_cache[player_id] = player_profile(payload, fallback_name=label, fallback_position=position)
            players.append(profile_cache[player_id])
        # Explicitly declared capacity fillers are accepted only when their
        # own Soccerbase career table proves membership on 31 August. This is
        # useful for registered reserve/youth players who did not appear on a
        # league match sheet; it is never inferred from a whole-season list.
        for player_id in (registered_players or {}).get(team_id, ()):
            if any(row[0] == player_id for row in unique):
                continue
            url = f"{BASE}/players/player.sd?player_id={player_id}"
            payload = cache.get(url, f"player/{player_id}.html")
            if not career_covers(payload, club_name=club_name or table_name, cutoff=date(start_year, 8, 31)):
                gaps.append({"club_name": club_name or table_name, "player_id": player_id,
                             "reason": "declared-registered-player-career-does-not-cover-cutoff",
                             "source_url": url, "team_id": team_id})
                continue
            profile_cache[player_id] = player_profile(payload, fallback_name=str(player_id), fallback_position=None)
            players.append(profile_cache[player_id])
            unique.append((player_id, profile_cache[player_id]["name"], profile_cache[player_id]["position"]))
        if len(players) < 11:
            gaps.append({"club_name": club_name or table_name, "player_count": len(players), "reason": "august-match-sheets-below-xi", "team_id": team_id})
        source_hash = hashlib.sha256(canonical_bytes({"games": [row[1] for row in games], "players": [row[0] for row in unique], "team_id": team_id})).hexdigest()
        clubs.append({"club_name": club_name or table_name, "competition_catalog": "soccerbase-august",
                      "competition_name": competition, "country_catalog": "english-non-league", "players": players,
                      "source_path": f"soccerbase/team/{team_id}/august", "source_sha256": source_hash})
    label = f"{start_year}/{str(start_year + 1)[-2:]}"
    source = {"license": "public factual match sheets; attribution, URLs and hashes retained", "repository": BASE,
              "revision": f"content-addressed-august-{start_year}-v1", "snapshots": sorted(cache.used, key=lambda row: row["cache_path"]),
              "title": "Soccerbase August league match sheets"}
    result = {"clubs": sorted(clubs, key=lambda row: row["club_name"]), "schema_version": SCHEMA,
              "season": {"catalog": f"{start_year}-{start_year+1}", "label": label}, "source": source}
    result["summary"] = {"club_count": len(clubs), "competition_catalogs": ["english-non-league/soccerbase-august"],
                         "country_catalogs": ["english-non-league"], "player_count": sum(len(row["players"]) for row in clubs),
                         "player_rows_with_unresolved_facts": sum(bool(p["unresolved_fields"]) for row in clubs for p in row["players"])}
    receipt = {"gaps": gaps, "schema_version": GAP_SCHEMA, "season": result["season"], "source": source,
               "summary": {"captured_club_count": len(clubs), "gap_count": len(gaps)}}
    return result, receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament-id", type=int, required=True); parser.add_argument("--season-id", type=int, required=True)
    parser.add_argument("--season-start-year", type=int, required=True); parser.add_argument("--competition", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gaps-output", type=Path, required=True); parser.add_argument("--offline", action="store_true")
    parser.add_argument("--registered-player", action="append", default=[], metavar="TEAM_ID:PLAYER_ID")
    parser.add_argument("--delay", type=float, default=.2); args = parser.parse_args(argv)
    registered: dict[int, list[int]] = {}
    for value in args.registered_player:
        try:
            team_id, player_id = (int(item) for item in value.split(":"))
        except (ValueError, TypeError):
            parser.error(f"invalid --registered-player {value!r}; expected TEAM_ID:PLAYER_ID")
        registered.setdefault(team_id, []).append(player_id)
    result, gaps = capture(tournament_id=args.tournament_id, season_id=args.season_id, start_year=args.season_start_year,
                           competition=args.competition, cache=Cache(args.cache_dir, offline=args.offline, delay=args.delay),
                           registered_players=registered)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(canonical_bytes(result)); args.gaps_output.write_bytes(canonical_bytes(gaps))
    print(json.dumps({**result["summary"], **gaps["summary"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
