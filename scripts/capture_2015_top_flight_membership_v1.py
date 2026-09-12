#!/usr/bin/env python3
"""Capture the actual 2015 top-flight club membership for source-tail repair.

The PM99 foreign carrier layout is fixed, but several legacy carrier labels
belong to clubs that were not in their country's top division in 2015.  This
tool supplies the missing decision input: a content-addressed record of the
clubs published in each target-season league article.  It does *not* select a
carrier, collect a squad, or write a database.

The receipt deliberately retains the raw MediaWiki API response and its hash.
That makes a later carrier choice reviewable and keeps source collection apart
from the PM99 binary writer.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA = "pm99-world-2015-top-flight-membership-v1"
API_URL = "https://en.wikipedia.org/w/api.php"


@dataclass(frozen=True)
class League:
    """One country family and its target-season top-flight source page."""

    family: str
    country_catalog: str
    page_title: str
    season_label: str
    expected_team_count: int
    section_id: str = "Teams"
    excluded_article_titles: tuple[str, ...] = ()
    competition_scope: str = "top-flight"


# This is a public-source catalogue, not a carrier allocation table.  The
# names have been checked against the target-season article titles and are
# deliberately explicit rather than being guessed from a current URL.
LEAGUES: tuple[League, ...] = (
    League("bolivia", "bolivia", "2015–16 Liga de Fútbol Profesional Boliviano", "2015/16", 12),
    League("bulgaria", "bulgaria", "2015–16 A Group", "2015/16", 10),
    League("croatia", "croatia", "2015–16 Croatian First Football League", "2015/16", 10),
    League("czechia", "czechia", "2015–16 Czech First League", "2015/16", 16),
    League("ecuador", "ecuador", "2015 Campeonato Ecuatoriano de Fútbol Serie A", "2015", 12),
    League("english-non-league", "eng", "2015–16 National League", "2015/16", 24, "National_League", (), "national"),
    League("english-non-league", "eng", "2015–16 National League", "2015/16", 22, "National_League_North", (), "national-north"),
    League("english-non-league", "eng", "2015–16 National League", "2015/16", 22, "National_League_South", (), "national-south"),
    League("finland", "finland", "2015 Veikkausliiga", "2015", 12),
    League("kazakhstan", "kazakhstan", "2015 Kazakhstan Premier League", "2015", 12),
    League("lithuania", "lithuania", "2015 A Lyga", "2015", 10),
    League("luxembourg", "luxembourg", "2015–16 Luxembourg National Division", "2015/16", 14, "Teams", ("Stade du Thillenberg",)),
    League("moldova", "moldova", "2015–16 Moldovan National Division", "2015/16", 10),
    League("northern-ireland", "northern-ireland", "2015–16 NIFL Premiership", "2015/16", 12, "Teams", ("Seaview (football ground)",)),
    League("romania", "romania", "2015–16 Liga I", "2015/16", 14),
    League("serbia", "serbia", "2015–16 Serbian SuperLiga", "2015/16", 16),
    League("slovakia", "slovakia", "2015–16 Slovak First Football League", "2015/16", 12),
    League("slovenia", "slovenia", "2015–16 Slovenian PrvaLiga", "2015/16", 10),
    League("uruguay", "uruguay", "2015–16 Campeonato Uruguayo Primera División", "2015/16", 16),
    League("venezuela", "venezuela", "2015 Venezuelan Primera División season", "2015", 20),
    League("wales", "wales", "2015–16 Welsh Premier League", "2015/16", 12),
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class MembershipParseError(ValueError):
    """The cached source page has no unambiguous team-membership table."""


class _TeamTableParser(HTMLParser):
    """Extract the first column of the first Club/Team wikitable in Teams."""

    def __init__(self, *, section_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self._in_teams = False
        self._teams_complete = False
        self._table_depth: int | None = None
        self._candidate_table = False
        self._team_columns: list[int] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None
        self._cell_text: list[str] = []
        self._anchor: dict[str, str] | None = None
        self._rows: list[list[dict[str, Any]]] = []
        self._depth = 0
        self._section_id = section_id

    @staticmethod
    def _attrs(attrs: Iterable[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        if tag == "h2" and values.get("id") == self._section_id:
            self._in_teams = True
        elif tag == "h2" and self._in_teams:
            self._in_teams, self._teams_complete = False, True

        if self._in_teams and not self._teams_complete and tag == "table" and self._table_depth is None:
            if "wikitable" in values.get("class", "").split():
                self._table_depth = self._depth
                self._candidate_table = False
                self._rows = []
        if self._table_depth is not None and tag == "tr":
            self._row = []
        if self._row is not None and tag in {"th", "td"}:
            self._cell = {"anchors": []}
            self._cell_text = []
        if self._cell is not None and tag == "a":
            href = values.get("href", "")
            if href.startswith("/wiki/") and not href.startswith("/wiki/File:"):
                self._anchor = {"href": html.unescape(href), "title": html.unescape(values.get("title", ""))}
        self._depth += 1

    def handle_data(self, value: str) -> None:
        if self._cell is not None:
            self._cell_text.append(value)
        if self._anchor is not None:
            self._anchor.setdefault("text", "")
            self._anchor["text"] += value

    def handle_endtag(self, tag: str) -> None:
        self._depth -= 1
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join(self._anchor.get("text", "").split())
            if self._anchor["text"]:
                assert self._cell is not None
                self._cell["anchors"].append(self._anchor)
            self._anchor = None
        if tag in {"th", "td"} and self._cell is not None:
            self._cell["text"] = " ".join("".join(self._cell_text).split())
            assert self._row is not None
            self._row.append(self._cell)
            self._cell, self._cell_text = None, []
        if tag == "tr" and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None
        if tag == "table" and self._table_depth == self._depth:
            if self._rows:
                self._team_columns = [
                    index
                    for index, cell in enumerate(self._rows[0])
                    if cell.get("text", "").casefold()
                    in {"club", "team", "home club", "licensed club(s)"}
                ]
                self._candidate_table = bool(self._team_columns)
            if self._candidate_table:
                self._in_teams, self._teams_complete = False, True
            self._table_depth = None

    def membership(self) -> list[dict[str, str]]:
        if not self._candidate_table or len(self._rows) < 2:
            raise MembershipParseError("Teams section has no Club/Team membership table")
        result: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        assert self._team_columns
        for row in self._rows[1:]:
            for index in self._team_columns:
                if len(row) <= index or not row[index].get("anchors"):
                    continue
                for anchor in row[index]["anchors"]:
                    name = str(anchor.get("text") or "").strip()
                    title = str(anchor.get("title") or name).strip()
                    href = str(anchor.get("href") or "").strip()
                    if not name or not href or (name, href) in seen:
                        continue
                    seen.add((name, href))
                    result.append({"name": name, "article_title": title, "article_path": href})
        if len(result) < 2:
            raise MembershipParseError("membership table has fewer than two clubs")
        return result


def parse_membership(
    api_payload: bytes, *, section_id: str = "Teams"
) -> tuple[str, int, list[dict[str, str]]]:
    try:
        value = json.loads(api_payload.decode("utf-8"))
        parsed = value["parse"]
        title = str(parsed["title"])
        page_id = int(parsed["pageid"])
        rendered = str(parsed["text"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MembershipParseError("MediaWiki parse response is malformed") from exc
    parser = _TeamTableParser(section_id=section_id)
    parser.feed(rendered)
    return title, page_id, parser.membership()


def api_url(page_title: str) -> str:
    query = urllib.parse.urlencode(
        {"action": "parse", "page": page_title, "prop": "text", "format": "json", "formatversion": "2"}
    )
    return f"{API_URL}?{query}"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PM99RE historical source research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _cache_path(league: League) -> Path:
    safe_title = "".join(char if char.isalnum() else "-" for char in league.page_title).strip("-")
    while "--" in safe_title:
        safe_title = safe_title.replace("--", "-")
    return Path("wikipedia-top-flight-membership-2015") / league.family / f"{safe_title}-{league.competition_scope}.json"


def _legacy_cache_path(league: League) -> Path:
    """Locate the pre-scope cache layout without making a duplicate request."""

    safe_title = "".join(char if char.isalnum() else "-" for char in league.page_title).strip("-")
    while "--" in safe_title:
        safe_title = safe_title.replace("--", "-")
    return Path("wikipedia-top-flight-membership-2015") / league.family / f"{safe_title}.json"


def capture(
    *,
    leagues: Iterable[League],
    cache_root: Path,
    retrieved_on: str,
    fetch: Callable[[str], bytes] = _get,
    delay_seconds: float = 0.0,
) -> dict[str, Any]:
    if not retrieved_on:
        raise ValueError("retrieved_on is required")
    selected = tuple(leagues)
    cache_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for league in sorted(selected, key=lambda item: item.family):
        url = api_url(league.page_title)
        relative = _cache_path(league)
        destination = cache_root / relative
        legacy_relative = _legacy_cache_path(league)
        legacy_destination = cache_root / legacy_relative
        try:
            if destination.is_file():
                payload, used_relative = destination.read_bytes(), relative
            elif league.competition_scope == "top-flight" and legacy_destination.is_file():
                payload, used_relative = legacy_destination.read_bytes(), legacy_relative
            else:
                payload, used_relative = fetch(url), relative
            title, page_id, teams = parse_membership(payload, section_id=league.section_id)
            excluded = set(league.excluded_article_titles)
            teams = [row for row in teams if row["article_title"] not in excluded]
            if len(teams) != league.expected_team_count:
                raise MembershipParseError(
                    f"expected {league.expected_team_count} clubs, found {len(teams)}"
                )
        except (OSError, MembershipParseError, urllib.error.URLError, TimeoutError) as exc:
            unresolved.append({"family": league.family, "page_title": league.page_title, "reason": str(exc)})
            continue
        if not destination.is_file() and used_relative == relative:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            if delay_seconds:
                time.sleep(delay_seconds)
        records.append({
            "family": league.family,
            "country_catalog": league.country_catalog,
            "season_label": league.season_label,
            "competition_scope": league.competition_scope,
            "source_section_id": league.section_id,
            "source_page_title": title,
            "source_page_id": page_id,
            "source_url": url,
            "source_path": used_relative.as_posix(),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "team_count": len(teams),
            "teams": teams,
            "excluded_non_team_article_titles": list(league.excluded_article_titles),
            "source_policy": "published target-season top-flight Teams table; source-only, no carrier allocation",
        })
    return {
        "schema_version": SCHEMA,
        "season": "2015/16 plus 2015 calendar-year leagues",
        "source": {
            "title": "Wikipedia target-season top-flight membership",
            "repository": "https://en.wikipedia.org",
            "retrieved_on": retrieved_on,
            "license": "CC BY-SA; raw response URL and content hash retained",
        },
        "policy": "source-only; retain actual target-season membership before any fixed-carrier selection; no PM99 write",
        "leagues": records,
        "unresolved": unresolved,
        "summary": {
            "requested_family_count": len(selected),
            "captured_family_count": len(records),
            "unresolved_family_count": len(unresolved),
            "team_count": sum(row["team_count"] for row in records),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", action="append", choices=[league.family for league in LEAGUES])
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args(argv)
    wanted = set(args.family or [league.family for league in LEAGUES])
    selected = tuple(league for league in LEAGUES if league.family in wanted)
    result = capture(
        leagues=selected,
        cache_root=args.cache_root,
        retrieved_on=args.retrieved_on,
        delay_seconds=args.delay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if not result["unresolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
