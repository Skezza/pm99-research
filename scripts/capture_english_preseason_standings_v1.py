#!/usr/bin/env python3
"""Capture hash-bound English prior-season tables for the rating policy.

The historical game starts before its target season's first fixtures.  This
tool therefore uses the four completed English league tables from the previous
season as a small, reproducible editorial input.  It never treats the target
season's eventual finish as a preseason fact.

Raw CSV files are retained in a caller-owned cache.  The compact canonical
output retains the source URL, raw SHA-256 and the calculated table used by
the rating layer, so an offline rebuild has the same input and an online
refresh is explicit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "pm99-english-preseason-standings-v1"
SOURCE_ID = "football-data-co-uk-england-results-csv-v1"
SOURCE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/{division}.csv"
DIVISIONS = ("E0", "E1", "E2", "E3")
EXPECTED_CLUB_COUNTS = {"E0": 20, "E1": 24, "E2": 24, "E3": 24}
SEASON_RE = re.compile(r"^(19|20)(\d{2})-(\d{2})$")


class PreseasonStandingsError(ValueError):
    """The source result data cannot safely establish a completed table."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _season_parts(season: str) -> tuple[int, str]:
    match = SEASON_RE.fullmatch(season)
    if match is None:
        raise PreseasonStandingsError("season must be YYYY-YY")
    start_year = int(match.group(1) + match.group(2))
    end_suffix = int(match.group(3))
    if (start_year + 1) % 100 != end_suffix:
        raise PreseasonStandingsError("season end must be the year after its start")
    previous_start = start_year - 1
    return previous_start, f"{previous_start % 100:02d}{start_year % 100:02d}"


def _normalise(value: object) -> str:
    return "".join(character.casefold() for character in str(value or "") if character.isalnum())


def _read_cached_or_download(*, path: Path, url: str, allow_network: bool) -> bytes:
    if path.is_file():
        data = path.read_bytes()
        if data:
            return data
    if not allow_network:
        raise PreseasonStandingsError(f"source cache missing and network is disabled: {path}")
    request = urllib.request.Request(url, headers={"User-Agent": "pm99-season-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
    except OSError as exc:
        raise PreseasonStandingsError(f"could not download {url}") from exc
    if not data:
        raise PreseasonStandingsError(f"download returned no data: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _integer(value: object, *, row_number: int, field: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise PreseasonStandingsError(f"CSV row {row_number} has invalid {field}") from exc


def _standing(*, raw: bytes, division: str, allow_curtailed: bool = False) -> tuple[list[dict[str, Any]], str]:
    try:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Older Football-Data exports contain Windows smart punctuation
            # in referee/team notes.  Result columns remain plain text.
            text = raw.decode("cp1252")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise PreseasonStandingsError(f"{division} CSV cannot be read") from exc
    required = {"Div", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
    if not rows or any(not required.issubset(set(row)) for row in rows):
        raise PreseasonStandingsError(f"{division} CSV lacks required result columns")
    values: dict[str, dict[str, int | str]] = {}
    completed = 0
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("Div") or "").strip() != division:
            continue
        home = str(row.get("HomeTeam") or "").strip()
        away = str(row.get("AwayTeam") or "").strip()
        if not home or not away or home == away:
            raise PreseasonStandingsError(f"{division} CSV row {row_number} has invalid teams")
        result = str(row.get("FTR") or "").strip().upper()
        # A current/incomplete season may include future unplayed fixtures. A
        # previous season must still produce the expected full table below.
        if result not in {"H", "D", "A"}:
            continue
        home_goals = _integer(row.get("FTHG"), row_number=row_number, field="FTHG")
        away_goals = _integer(row.get("FTAG"), row_number=row_number, field="FTAG")
        for name in (home, away):
            values.setdefault(name, {"club": name, "played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "points": 0})
        home_row, away_row = values[home], values[away]
        for club_row, scored, conceded in ((home_row, home_goals, away_goals), (away_row, away_goals, home_goals)):
            club_row["played"] = int(club_row["played"]) + 1
            club_row["goals_for"] = int(club_row["goals_for"]) + scored
            club_row["goals_against"] = int(club_row["goals_against"]) + conceded
        if result == "H":
            home_row["won"] = int(home_row["won"]) + 1
            away_row["lost"] = int(away_row["lost"]) + 1
            home_row["points"] = int(home_row["points"]) + 3
        elif result == "A":
            away_row["won"] = int(away_row["won"]) + 1
            home_row["lost"] = int(home_row["lost"]) + 1
            away_row["points"] = int(away_row["points"]) + 3
        else:
            for club_row in (home_row, away_row):
                club_row["drawn"] = int(club_row["drawn"]) + 1
                club_row["points"] = int(club_row["points"]) + 1
        completed += 1
    expected_maximum = EXPECTED_CLUB_COUNTS[division]
    # Bury's expunged 2019/20 League Two season is the important real-world
    # exception: the completed result feed has 23 clubs and a 23-team
    # round-robin, not a malformed 24-team table.  Retain that fact rather
    # than inventing a twenty-fourth result row.
    if not 20 <= len(values) <= expected_maximum:
        raise PreseasonStandingsError(
            f"{division} has {len(values)} completed clubs; expected 20..{expected_maximum}"
        )
    expected_matches = len(values) * (len(values) - 1)
    curtailed = completed != expected_matches
    if curtailed and not allow_curtailed:
        raise PreseasonStandingsError(
            f"{division} has {completed} completed fixtures; expected {expected_matches}"
        )
    if curtailed:
        if any(int(row["played"]) < 20 for row in values.values()):
            raise PreseasonStandingsError(f"{division} curtailed result feed has too little completed play")
        # The English Football League ended the affected 2019/20 divisions
        # by points per game.  Sort by cross-products to avoid float drift;
        # use the normal table tiebreakers only after PPG.
        from functools import cmp_to_key

        def compare(left: Mapping[str, int | str], right: Mapping[str, int | str]) -> int:
            left_ppg = int(left["points"]) * int(right["played"])
            right_ppg = int(right["points"]) * int(left["played"])
            for a, b in (
                (left_ppg, right_ppg),
                (int(left["goals_for"]) - int(left["goals_against"]), int(right["goals_for"]) - int(right["goals_against"])),
                (int(left["goals_for"]), int(right["goals_for"])),
            ):
                if a != b:
                    return -1 if a > b else 1
            return -1 if _normalise(left["club"]) < _normalise(right["club"]) else int(_normalise(left["club"]) > _normalise(right["club"]))

        table = sorted(values.values(), key=cmp_to_key(compare))
        method = "curtailed-final-table-points-per-game"
    else:
        table = sorted(
            values.values(),
            key=lambda row: (
                -int(row["points"]),
                -(int(row["goals_for"]) - int(row["goals_against"])),
                -int(row["goals_for"]),
                _normalise(row["club"]),
            ),
        )
        method = "completed-fixture-results-to-final-table"
    result = []
    for rank, row in enumerate(table, start=1):
        result.append({
            "rank": rank,
            "club": str(row["club"]),
            "played": int(row["played"]),
            "won": int(row["won"]),
            "drawn": int(row["drawn"]),
            "lost": int(row["lost"]),
            "goals_for": int(row["goals_for"]),
            "goals_against": int(row["goals_against"]),
            "goal_difference": int(row["goals_for"]) - int(row["goals_against"]),
            "points": int(row["points"]),
        })
    return result, method


def capture(*, season: str, cache_dir: Path, allow_network: bool) -> dict[str, Any]:
    previous_start, source_code = _season_parts(season)
    competitions = []
    for division in DIVISIONS:
        url = SOURCE_URL.format(season_code=source_code, division=division)
        cache_path = cache_dir / f"{previous_start}-{previous_start + 1}" / f"{division}.csv"
        raw = _read_cached_or_download(path=cache_path, url=url, allow_network=allow_network)
        standing, table_method = _standing(
            raw=raw, division=division, allow_curtailed=previous_start == 2019,
        )
        competitions.append({
            "division": division,
            "source_url": url,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "table_method": table_method,
            "standing": standing,
        })
    return {
        "schema_version": SCHEMA,
        "target_season": season,
        "previous_season": f"{previous_start}-{(previous_start + 1) % 100:02d}",
        "source": {"id": SOURCE_ID, "method": "completed-fixture-results-to-final-table"},
        "competitions": competitions,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = capture(season=args.season, cache_dir=args.cache_dir, allow_network=args.allow_network)
    except (OSError, PreseasonStandingsError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(value))
    print(json.dumps({"season": args.season, "competition_count": len(value["competitions"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
