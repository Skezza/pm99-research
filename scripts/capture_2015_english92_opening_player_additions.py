#!/usr/bin/env python3
"""Capture dated-match players absent from the season roster snapshot.

FootballSquads' 2015/16 pages are an excellent season roster source but do not
reliably retain players who appeared in August and departed during the season.
Those people cannot be replaced by a later-season squad member when compiling
a first-fixture database.  This script identifies that gap from the already
captured match sheets and records stable biographical facts from each linked
Transfermarkt profile.  It does not modify the source roster or a PM99 file.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

try:  # Script execution places this directory on sys.path.
    from capture_2015_english92_opening_lineups import ROOT, _get
    from reconcile_2015_english92_opening_lineups import _match_player
except ModuleNotFoundError:  # Module import in tests/research shells uses root.
    from scripts.capture_2015_english92_opening_lineups import ROOT, _get
    from scripts.reconcile_2015_english92_opening_lineups import _match_player


POSITION_BY_LABEL = {
    "GK": "G", "GOALKEEPER": "G",
    "CB": "D", "LB": "D", "RB": "D", "LWB": "D", "RWB": "D", "DEFENDER": "D",
    "DM": "M", "CM": "M", "AM": "M", "LM": "M", "RM": "M", "MIDFIELDER": "M",
    "LW": "F", "RW": "F", "CF": "F", "ST": "F", "FORWARD": "F", "ATTACK": "F",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_label(page: BeautifulSoup, label: str) -> str:
    for item in page.select(".data-header__label"):
        own = item.find(string=re.compile(r"\S"), recursive=False)
        text = str(own or "").strip()
        if text.rstrip(":") != label:
            continue
        content = item.select_one(".data-header__content")
        return content.get_text(" ", strip=True) if content is not None else ""
    return ""


def _height_cm(text: str) -> int | None:
    match = re.search(r"(\d+)\s*ft\s*(\d+)\s*in", text)
    if match is None:
        return None
    return round((int(match.group(1)) * 12 + int(match.group(2))) * 2.54)


def _broad_position(profile_position: str, source_position: str) -> str:
    for candidate in (source_position, profile_position):
        upper = str(candidate).upper()
        for label, position in POSITION_BY_LABEL.items():
            if re.search(rf"\b{re.escape(label)}\b", upper):
                return position
        if "GOALKEEPER" in upper:
            return "G"
        if "BACK" in upper or "DEFENDER" in upper:
            return "D"
        if "MIDFIELD" in upper:
            return "M"
        if "WINGER" in upper or "STRIKER" in upper or "FORWARD" in upper or "ATTACK" in upper:
            return "F"
    raise ValueError(f"Could not map a broad PM99 position from {profile_position!r} / {source_position!r}")


def _profile_player(source_player: dict[str, Any], cache: Path, *, delay: float) -> dict[str, Any]:
    player_id = str(source_player["source_player_id"])
    page = BeautifulSoup(_get(str(source_player["source_url"]), cache, f"profiles/{player_id}.html", delay=delay), "html.parser")
    headline = page.select_one("h1.data-header__headline-wrapper")
    if headline is None:
        raise ValueError(f"Profile {player_id} has no headline")
    name = re.sub(r"^#\d+\s+", "", headline.get_text(" ", strip=True))
    birth = _profile_label(page, "Date of birth/Age")
    birth_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", birth)
    if birth_match is None:
        raise ValueError(f"Profile {player_id} has no date of birth")
    nationality_item = next(iter(page.select('[itemprop="nationality"] img[alt]')), None)
    nationality = str(nationality_item.get("alt") or "").strip() if nationality_item is not None else ""
    if not nationality:
        raise ValueError(f"Profile {player_id} has no nationality")
    height = _height_cm(_profile_label(page, "Height"))
    profile_position = _profile_label(page, "Position")
    return {
        "name": name,
        "birth_date": birth_match.group(1).replace("/", "-"),
        "nationality_label": nationality,
        "height_cm": height,
        "height_status": "profile-proven" if height is not None else "requires-FIFA-or-declared-position-fallback",
        "profile_position": profile_position,
        "profile_url": str(source_player["source_url"]),
    }


def _ddmmyy(date: str) -> str:
    day, month, year = date.split("-")
    return f"{day}-{month}-{year[-2:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", type=Path, default=ROOT / "upstream/.local/season-2015-16/2015-16-english-source-ledger.json")
    parser.add_argument("--lineup-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".local/season-2015-16/transfermarkt-opening-lineups-cache")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    if args.delay < 0 or args.delay > 5:
        raise SystemExit("--delay must be between 0 and 5 seconds")
    source = _load(args.source_ledger)
    lineups = _load(args.lineup_source)
    source_by_club = {str(row["club"]): row for row in source["clubs"]}
    additions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for capture in lineups["clubs"]:
        club = str(capture["club"])
        roster = list(source_by_club[club]["players"])
        for list_name in ("starting_xi", "substitutes"):
            for source_player in capture[list_name]:
                matched, _method, _candidates = _match_player(club, source_player, roster, {})
                if matched is not None:
                    continue
                key = (club, str(source_player["source_player_id"]))
                if key in seen:
                    continue
                seen.add(key)
                profile = _profile_player(source_player, args.cache_dir, delay=args.delay)
                source_position = str(source_player.get("source_position_label") or "")
                position = _broad_position(profile["profile_position"], source_position)
                additions.append({
                    "club": club, "division": str(source_by_club[club]["division"]), "list": list_name,
                    "source_player_id": str(source_player["source_player_id"]), "source_slug": str(source_player["source_slug"]),
                    "source_name": profile["name"], "display_name": str(source_player["display_name"]),
                    "shirt_number": int(source_player["source_shirt_number"]), "position": position,
                    "profile_position": profile["profile_position"], "nationality_label": profile["nationality_label"],
                    "birth_date_ddmmyy": _ddmmyy(profile["birth_date"]), "height_cm": profile["height_cm"],
                    "height_status": profile["height_status"],
                    "profile_url": profile["profile_url"],
                    "weight_status": "requires-FIFA-or-declared-position-fallback",
                })
                print(f"captured {club}: {profile['name']}")
    payload = {
        "schema_version": "pm99-2015-16-opening-lineup-additions-v1",
        "season": "2015/16",
        "purpose": "first-fixture players absent from the FootballSquads season snapshot",
        "rows": additions,
        "summary": {"addition_count": len(additions), "club_count": len({row['club'] for row in additions})},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
