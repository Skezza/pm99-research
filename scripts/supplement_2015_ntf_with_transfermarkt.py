#!/usr/bin/env python3
"""Supplement undersized NTF season rows with dated Transfermarkt squads.

The Transfermarkt search result is accepted only through an exact or
explicitly reviewed historical-name alias.  The detailed squad URL is pinned
to ``saison_id/2015`` and its HTML is cached and hashed.  This produces source
facts for review; it does not assign PM99 data or pad a roster with invented
players.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_2015_missing_family_squads import NATIONALITY_CODES, _normalise, _position
from scripts import season_player_identity_v1 as identity_lib

SCHEMA = "pm99-footballsquads-season-capture-v1"
BASE_URL = "https://www.transfermarkt.com"

# Transfermarkt often uses a legal/historical display form.  These are
# explicit review decisions, not fuzzy acceptance.  A missing entry fails
# closed and remains unresolved in the receipt.
SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "KF Tiranë": ("KF Tirana",), "Teuta Durrës": ("KF Teuta",),
    "Pyunik Yerevan": ("FC Pyunik Yerevan",), "Slaviya Mazyr": ("Slavia Mozyr",),
    "Botev Plovdiv": ("Botev Plovdiv",), "CSKA Sofia": ("CSKA Sofia",),
    "Levski Sofia": ("Levski Sofia",), "Litex Lovech": ("PFC Litex Lovech",),
    "Lokomotiv Sofia": ("Lokomotiv Sofia",), "Slavia Sofia": ("Slavia Sofia",),
    "América Cali": ("America de Cali", "América de Cali"),
    "Los Millonarios Bogotá": ("Millonarios", "Los Millonarios"),
    "Hajduk Split": ("HNK Hajduk Split",), "AEK Larnakas": ("AEK Larnaca",),
    "Anorthosis Ammochostou": ("Anorthosis Famagusta",), "Apollon Lemesou": ("Apollon Limassol",),
    "Baník Ostrava": ("FC Banik Ostrava",), "FC Hradec Králové": ("FC Hradec Kralove",),
    "Sigma Olomouc": ("SK Sigma Olomouc",), "Slavia Praha": ("SK Slavia Prague",),
    "Zbrojovka Brno": ("FC Zbrojovka Brno",),
    "Barcelona Guayaquil": ("Barcelona SC", "Barcelona Guayaquil"),
    "El Nacional Quito": ("El Nacional",), "Emelec Guayaquil": ("Emelec",),
    "Haka Valkeakoski": ("FC Haka", "Haka Valkeakoski"),
    "Dinamo Batumi": ("Dinamo Batumi",), "Dinamo Tbilisi": ("Dinamo Tbilisi",),
    "Beitar Yerushalayim": ("Beitar Jerusalem",), "Hapoel Petah-Tikva": ("Hapoel Petah Tikva",),
    "Hapoel Tel-Aviv": ("Hapoel Tel Aviv",), "Maccabi Haifa": ("Maccabi Haifa",),
    "FK Liepāja": ("FK Liepaja",), "Skonto Rīga": ("Skonto Riga (- 2016)",),
    "Hibernians Paola": ("Hibernians FC", "Hibernians Paola"),
    "Sliema Wanderers": ("Sliema Wanderers",), "Valletta FC": ("Valletta FC",),
    "Sileks Kratovo": ("Sileks Kratovo",), "Guarani Asunción": ("Club Guarani", "Guarani Asuncion"),
    "Alianza Lima": ("Club Alianza Lima",), "Universitario de Deportes Lima": ("Universitario de Deportes",),
    "Dinamo Bucureşti": ("FC Dinamo 1948",), "Petrolul Ploieşti": ("Petrolul Ploiesti",),
    "Rapid Bucureşti": ("FC Rapid 1923",), "FC Universitatea Cluj": ("FC Universitatea Cluj",),
    "Vojvodina Novi Sad": ("FK Vojvodina Novi Sad",),
    "Dukla Banská Bystrica": ("MFK Dukla Banska Bystrica",), "Tatran Prešov": ("FC Tatran Presov",),
    "VSS Košice": ("FC VSS Kosice (2005 - 2017)",), "Olimpija Ljubljana": ("NK Olimpija Ljubljana",),
    "Rudar Velenje": ("NK Rudar Velenje",), "Caracas FC": ("Caracas FC",),
    "Zulia FC": ("Zulia FC (- 2022)",), "Caernarfon Town": ("Caernarfon Town",),
    "NK Osijek": ("NK Osijek",), "FK Jablonec": ("FK Jablonec",),
    "FC Jazz Pori": ("FC Jazz Pori",), "KÍ Klaksvík": ("KÍ Klaksvík",),
    "Víkingur Gøta": ("Víkingur Gøta",), "KR Reykjavík": ("KR Reykjavík",),
    "ÍA Akranes": ("ÍA Akranes",), "Beitar Yerushalayim": ("Beitar Jerusalem",),
    "Hapoel Petah-Tikva": ("Hapoel Petah Tikva",), "Hapoel Tel-Aviv": ("Hapoel Tel Aviv",),
    "AEK Larnakas": ("AEK Larnaca",), "Guarani Asunción": ("Club Guarani",),
    "Universitario de Deportes Lima": ("Universitario de Deportes",),
    "FC Universitatea Cluj": ("FC Universitatea Cluj",), "Inter Bratislava": ("Inter Bratislava",),
    "Slovan Bratislava": ("Slovan Bratislava",), "Spartak Trnava": ("Spartak Trnava",),
    "ND Gorica": ("ND Gorica",),
}

SEARCH_QUERIES: dict[str, str] = {
    "KF Tiranë": "KF Tirana", "Neftçi Bakı": "Neftchi Baku", "América Cali": "America de Cali",
    "Los Millonarios Bogotá": "Millonarios", "AEK Larnakas": "AEK Larnaca",
    "Barcelona Guayaquil": "Barcelona SC", "El Nacional Quito": "El Nacional",
    "Emelec Guayaquil": "Emelec", "Haka Valkeakoski": "FC Haka",
    "Beitar Yerushalayim": "Beitar Jerusalem", "Hapoel Petah-Tikva": "Hapoel Petah Tikva",
    "Hapoel Tel-Aviv": "Hapoel Tel Aviv", "Hibernians Paola": "Hibernians FC",
    "Universitario de Deportes Lima": "Universitario de Deportes", "Universitatea Cluj": "FC Universitatea Cluj",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href and "/startseite/verein/" in href:
            self.href, self.text = href, []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            item = (" ".join("".join(self.text).split()), self.href)
            if item not in self.links:
                self.links.append(item)
            self.href, self.text = None, []


class SquadParser(HTMLParser):
    """Read direct cells from Transfermarkt's ``table.items`` rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.items_depth: int | None = None
        self.row: dict[str, Any] | None = None
        self.row_depth: int | None = None
        self.cell: list[str] | None = None
        self.cell_depth: int | None = None
        self.image_title: str | None = None
        self.player_name: list[str] = []
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "table" and "items" in str(attrs_d.get("class") or "").split():
            self.items_depth = self.depth
        if tag == "tr" and self.items_depth is not None and self.row is None:
            self.row, self.row_depth = {"cells": []}, self.depth
            self.player_name = []
        if tag == "td" and self.row is not None and self.depth == (self.row_depth or -1) + 1:
            self.cell, self.cell_depth, self.image_title = [], self.depth, None
        if self.cell is not None and tag == "img":
            self.image_title = attrs_d.get("title") or attrs_d.get("alt")
        if self.cell is not None and tag == "a" and "/profil/spieler/" in str(attrs_d.get("href") or ""):
            self.player_name = []
            self._player_anchor = True
        if self.row is not None and tag == "a" and "/profil/spieler/" in str(attrs_d.get("href") or ""):
            self.row.setdefault("profile_hrefs", []).append(str(attrs_d["href"]))
        # HTMLParser does not synthesise an end tag for HTML void elements.
        # Transfermarkt emits proper self-closing image markup today, whereas
        # source fixtures (and older cached pages) may use bare ``<img>``.
        # Do not let either form corrupt the structural depth of the row.
        if tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            return
        self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # The base HTMLParser implementation calls both handlers.  Our void
        # start handler intentionally does not increase depth, so pairing it
        # with handle_endtag would decrease depth incorrectly.
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)
        if self.row is not None and self.player_name is not None:
            # Anchor text is only collected while a player link is active; the
            # flag is cleared in handle_endtag.
            if getattr(self, "_player_anchor", False):
                self.player_name.append(data)

    def handle_endtag(self, tag: str) -> None:
        self.depth -= 1
        if tag == "a" and getattr(self, "_player_anchor", False):
            self._player_anchor = False
        if tag == "td" and self.cell is not None and self.depth == self.cell_depth:
            assert self.row is not None
            self.row["cells"].append(" ".join("".join(self.cell).split()))
            self.row.setdefault("images", []).append(self.image_title)
            self.cell, self.cell_depth, self.image_title = None, None, None
        if tag == "tr" and self.row is not None and self.depth == self.row_depth:
            self.row["player_name"] = " ".join("".join(self.player_name).split())
            self.rows.append(self.row)
            self.row, self.row_depth = None, None
        if tag == "table" and self.items_depth == self.depth:
            self.items_depth = None


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PM99RE historical source audit/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _person_key(name: str) -> str:
    if "," in name:
        family, given = name.split(",", 1)
        return _normalise(given + family)
    return _normalise(name)


def parse_squad(payload: bytes) -> list[dict[str, Any]]:
    parser = SquadParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    result: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = row.get("cells") or []
        name = str(row.get("player_name") or "").strip()
        if not name or len(cells) < 4:
            continue
        # Transfermarkt's live table puts the position in its combined
        # player/position cell (index 1).  Keep the parser tolerant of the
        # small, semantically equivalent fixture/table variant where the
        # player name and position occupy separate cells.  We deliberately
        # require a recognised position rather than treating any row as a
        # player, so this does not turn headings or staff rows into players.
        position = next((parsed for cell in cells[1:] if (parsed := _position(cell)) is not None), None)
        if position is None:
            continue
        number = cells[0].strip()
        shirt = int(number) if number.isdigit() and 0 <= int(number) <= 99 else None
        unresolved = ["birth_date", "height_cm", "weight_kg"]
        if shirt is None:
            unresolved.append("shirt_number")
        nation = str((row.get("images") or [None] * 4)[3] or "").strip()
        code = NATIONALITY_CODES.get(nation, "UNK")
        if code == "UNK":
            unresolved.append("nationality_code")
        player = {"shirt_number": shirt, "name": name, "nationality": code, "position": position, "height_cm": None, "weight_kg": None, "birth_date": None, "unresolved_fields": unresolved}
        # Only a literal profile link is an identity; a row without one stays
        # unknown and keeps the legacy name-keyed collapse below.
        identity = identity_lib.transfermarkt_identity(row.get("profile_hrefs") or [], label=f"squad row {name!r}")
        if identity is not None:
            player[identity_lib.IDENTITY_FIELD] = identity
        result.append(player)
    unique = identity_lib.collapse_rows(result, legacy_key=lambda p: _person_key(p["name"]))
    return sorted(unique, key=lambda p: (p["position"], p["name"], identity_lib.identity_sort_key(p)))


def supplement(*, ntf_capture: dict[str, Any], cache_root: Path) -> dict[str, Any]:
    clubs: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    cache_root.mkdir(parents=True, exist_ok=True)
    for original in ntf_capture.get("clubs", []):
        club = dict(original)
        fixed = int(club.get("fixed_roster_slot_count") or 0)
        existing = list(club.get("players") or [])
        if len(existing) >= fixed:
            clubs.append(club)
            continue
        display = str(club.get("club_name") or "")
        aliases = SEARCH_ALIASES.get(display, ())
        search_term = SEARCH_QUERIES.get(display, display)
        query = urllib.parse.urlencode({"query": search_term})
        search_url = f"{BASE_URL}/schnellsuche/ergebnis/schnellsuche?{query}"
        try:
            search_payload = _get(search_url)
        except Exception as exc:
            unresolved.append({"candidate_carrier_id": club.get("candidate_carrier_id"), "club_name": display, "reason": "transfermarkt-search-fetch-failed", "detail": str(exc)})
            clubs.append(club)
            continue
        accepted = {_normalise(value) for value in aliases}
        matches = [(name, href) for name, href in SearchParserLinks(search_payload) if _normalise(name) in accepted]
        if len({href for _, href in matches}) != 1:
            unresolved.append({"candidate_carrier_id": club.get("candidate_carrier_id"), "club_name": display, "reason": "no-unique-explicit-transfermarkt-club-result"})
            clubs.append(club)
            continue
        tm_name, href = matches[0]
        parts = href.strip("/").split("/")
        try:
            slug, _, _, club_id = parts[-4], parts[-3], parts[-2], parts[-1]
            int(club_id)
        except (IndexError, ValueError):
            unresolved.append({"candidate_carrier_id": club.get("candidate_carrier_id"), "club_name": display, "reason": "malformed-transfermarkt-club-result"})
            clubs.append(club)
            continue
        detail_url = f"{BASE_URL}/{slug}/kader/verein/{club_id}/saison_id/2015"
        try:
            detail_payload = _get(detail_url)
        except Exception as exc:
            unresolved.append({"candidate_carrier_id": club.get("candidate_carrier_id"), "club_name": display, "reason": "transfermarkt-squad-fetch-failed", "source_url": detail_url, "detail": str(exc)})
            clubs.append(club)
            continue
        tm_players = parse_squad(detail_payload)
        existing_keys = {_person_key(str(row.get("name") or "")) for row in existing}
        added = [row for row in tm_players if _person_key(row["name"]) not in existing_keys]
        combined = existing + added
        club["players"] = sorted(combined, key=lambda p: (p["position"], p["name"]))
        digest_value = sha256_bytes(detail_payload)
        source_path = Path(f"{club['country_catalog']}/{club['candidate_carrier_id']}-{_normalise(tm_name)}.html")
        full_path = cache_root / source_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(detail_payload)
        club["supplemental_sources"] = [{"source_name": "Transfermarkt detailed squad 15/16", "source_url": detail_url, "source_path": source_path.as_posix(), "source_sha256": digest_value, "search_url": search_url, "search_result_name": tm_name, "added_player_row_count": len(added)}]
        club["supplement_status"] = "capacity-complete-second-source" if len(combined) >= fixed else "still-undersized-after-second-source"
        if len(combined) < fixed:
            unresolved.append({"candidate_carrier_id": club.get("candidate_carrier_id"), "club_name": display, "reason": "still-undersized-after-second-source", "source_url": detail_url, "player_count": len(combined), "fixed_roster_slot_count": fixed})
        clubs.append(club)
    clubs.sort(key=lambda c: (str(c.get("country_catalog")), str(c.get("club_name"))))
    captured = sum(1 for c in clubs if len(c.get("players") or []) >= int(c.get("fixed_roster_slot_count") or 0))
    return {"schema_version": SCHEMA, "source": {"title": "National Football Teams plus Transfermarkt historical squad pages", "repository": "mixed-content-addressed-public-sources", "revision": "2015-dated-pages-content-addressed-v2", "license": "source-specific public factual captures; URL and content hash retained", "retrieved_on": date.today().isoformat()}, "season": {"catalog": "2015-world-ntf-plus-transfermarkt", "label": "2015/16 plus 2015 calendar-year leagues"}, "clubs": clubs, "unresolved_supplements": unresolved, "summary": {"club_count": len(clubs), "player_count": sum(len(c.get("players") or []) for c in clubs), "capacity_complete_count": captured, "supplement_attempt_count": sum(1 for c in clubs if c.get("supplemental_sources")), "still_unresolved_count": len(unresolved)}}


def SearchParserLinks(payload: bytes) -> list[tuple[str, str]]:
    parser = SearchParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return parser.links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ntf-capture", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    capture = json.loads(args.ntf_capture.read_text(encoding="utf-8"))
    result = supplement(ntf_capture=capture, cache_root=args.cache_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
