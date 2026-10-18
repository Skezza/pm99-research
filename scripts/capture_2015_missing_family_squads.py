#!/usr/bin/env python3
"""Capture dated 2015/16 historical club pages for missing PM99 families.

This is a source-only acquisition step.  It never allocates a player carrier
and never writes PM99 data.  The source catalogue is deliberately explicit:
each club is selected by a country-scoped 2015/16 National Football Teams
league index and an exact, reviewed display-name alias.  A page hash is kept
with every capture so a later review can reproduce the evidence.

National Football Teams reports players who appeared for the club in the
season, rather than a complete registration list.  Missing physical facts
and shirt numbers are therefore retained as unresolved fields; a capture is
not automatically source-ready for a fixed PM99 carrier.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.request
import unicodedata
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SCHEMA = "pm99-footballsquads-season-capture-v1"
SEASON_LABEL = "2015/16"
SEASON_CATALOG = "2015-2016"
BASE_URL = "https://www.national-football-teams.com"

# NTF's country identifiers are part of the URL and make the country scope
# machine-checkable.  These are not inferred from a club name.
COUNTRIES: dict[str, tuple[int, str]] = {
    "serbia": (164, "Serbia"), "croatia": (47, "Croatia"),
    "romania": (151, "Romania"), "czechia": (50, "Czechia"),
    "bulgaria": (31, "Bulgaria"), "slovakia": (168, "Slovakia"),
    "slovenia": (169, "Slovenia"), "cyprus": (49, "Cyprus"),
    "wales": (205, "Wales"), "israel": (91, "Israel"),
    "malta": (117, "Malta"), "lithuania": (108, "Lithuania"),
    "albania": (2, "Albania"), "georgia": (70, "Georgia"),
    "luxembourg": (109, "Luxembourg"), "northern-ireland": (137, "Northern_Ireland"),
    "moldova": (122, "Moldova"), "bolivia": (25, "Bolivia"),
    "ecuador": (56, "Ecuador"), "peru": (145, "Peru"),
    "uruguay": (198, "Uruguay"), "venezuela": (203, "Venezuela"),
    "colombia": (43, "Colombia"), "paraguay": (144, "Paraguay"),
    "latvia": (102, "Latvia"), "armenia": (10, "Armenia"),
    "north-macedonia": (111, "North_Macedonia"),
    "kazakhstan": (96, "Kazakhstan"), "azerbaijan": (14, "Azerbaijan"),
    "finland": (66, "Finland"), "iceland": (85, "Iceland"),
    "faroe-islands": (64, "Faroe_Islands"), "belarus": (19, "Belarus"),
}

# NTF uses ``2015`` for calendar-year competitions and ``2015_1`` for the
# European split-year campaign.  Keeping this distinction prevents a URL that
# merely looks close to 2015/16 from being treated as the requested season.
CALENDAR_YEAR_COUNTRIES = {
    "colombia", "ecuador", "peru", "uruguay", "venezuela", "paraguay",
    "bolivia", "latvia", "lithuania", "finland", "iceland", "faroe-islands",
    "belarus", "kazakhstan",
}

# Explicit aliases are the only join between a PM99 historical baseline name
# and an external club page.  Values are exact normalized NTF display names;
# do not replace this with fuzzy matching.  The short table covers the
# highest-priority missing families first; absent entries are audited as
# unresolved rather than guessed.
ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("serbia", "Red Star"): ("Crvena Zvezda Beograd",),
    ("serbia", "Partizán"): ("Partizan Beograd",),
    ("serbia", "Vojvodina"): ("Vojvodina Novi Sad",),
    ("serbia", "Becej"): ("OFK Bečej 1918",),
    ("croatia", "Hajduk Split"): ("Hajduk Split",),
    ("croatia", "Croatia Zag."): ("Dinamo Zagreb",),
    ("croatia", "Osijek"): ("NK Osijek",),
    ("croatia", "Varteks"): ("Varteks Varaždin",),
    ("romania", "Steaua B."): ("Steaua Bucureşti",),
    ("romania", "Petrolul"): ("Petrolul Ploieşti",),
    ("romania", "Universitatea"): ("Universitatea Cluj",),
    ("romania", "D.Bucarest"): ("Dinamo Bucureşti",),
    ("romania", "G. Bistrita"): ("Gloria Bistriţa",),
    ("romania", "R. Bucarest"): ("Rapid Bucureşti",),
    ("romania", "Nat.Bucarest"): ("FC Naţional Bucureşti",),
    ("romania", "Arges Pitesti"): ("FC Argeş Piteşti",),
    ("czechia", "Hradec Kral."): ("FC Hradec Králové",),
    ("czechia", "Sparta Prague"): ("Sparta Praha",),
    ("czechia", "Slavia Prague"): ("Slavia Praha",),
    ("czechia", "Sigma Olomouc"): ("Sigma Olomouc",),
    ("czechia", "Jablonec N."): ("FK Jablonec",),
    ("czechia", "Boby Brno"): ("Zbrojovka Brno",),
    ("czechia", "Banik Ostrava"): ("Baník Ostrava",),
    ("bulgaria", "Lok. Sofia"): ("Lokomotiv Sofia",),
    ("bulgaria", "Levski Sofia"): ("Levski Sofia",),
    ("bulgaria", "Botev Plovdiv"): ("Botev Plovdiv",),
    ("bulgaria", "Slavia Sofia"): ("Slavia Sofia",),
    ("bulgaria", "CSKA Sofía"): ("CSKA Sofia",),
    ("bulgaria", "Litex Lovech"): ("Litex Lovech",),
    ("slovakia", "S. Bratislava"): ("Slovan Bratislava",),
    ("slovakia", "Inter Bratislava"): ("Inter Bratislava",),
    ("slovakia", "Kosice"): ("VSS Košice",),
    ("slovakia", "Spartak Trnava"): ("Spartak Trnava",),
    ("slovakia", "Dukla Banska"): ("Dukla Banská Bystrica",),
    ("slovakia", "Tartan Presov"): ("Tatran Prešov",),
    ("slovakia", "Bardejov"): ("Partizán Bardejov",),
    ("slovenia", "Mura"): ("NŠ Mura",),
    ("slovenia", "Olimpia"): ("Olimpija Ljubljana",),
    ("slovenia", "Maribor B."): ("NK Maribor B",),
    ("slovenia", "Gorica"): ("ND Gorica",),
    ("slovenia", "Rudar Velenje"): ("Rudar Velenje",),
    ("cyprus", "Anorthosis"): ("Anorthosis Ammochostou",),
    ("cyprus", "Apoel Nic."): ("APOEL Lefkosias",),
    ("cyprus", "Omonia"): ("Omonia Lefkosias",),
    ("cyprus", "AEK Larnaca"): ("AEK Larnakas",),
    ("cyprus", "Apollon L."): ("Apollon Lemesou",),
    ("wales", "Bangor City"): ("Bangor City",),
    ("wales", "Afan Lido"): ("Afan Lido",),
    ("wales", "Barry Town"): ("Barry Town United",),
    ("wales", "Newton"): ("Newtown AFC",),
    ("wales", "Conwy Utd"): ("Conwy Borough",),
    ("wales", "Caernarfon"): ("Caernarfon Town",),
    ("wales", "Connah's Quay"): ("Connah's Quay Nomads",),
    ("wales", "Aberyswyth Town"): ("Aberystwyth Town",),
    ("israel", "M.Tel Aviv"): ("Maccabi Tel-Aviv",),
    ("israel", "Maccabi Haifa"): ("Maccabi Haifa",),
    ("israel", "Beitar"): ("Beitar Yerushalayim",),
    ("israel", "H.Tel Aviv"): ("Hapoel Tel-Aviv",),
    ("israel", "Hap. Petach"): ("Hapoel Petah-Tikva",),
    ("malta", "Valletta"): ("Valletta FC",),
    ("malta", "Hibernians"): ("Hibernians Paola",),
    ("malta", "Sliema"): ("Sliema Wanderers",),
    ("albania", "Teuta"): ("Teuta Durrës",),
    ("albania", "P. Tirana"): ("KF Tiranë",),
    ("georgia", "Dinamo Tbilisi"): ("Dinamo Tbilisi",),
    ("georgia", "Dinamo Batumi"): ("Dinamo Batumi",),
    ("moldova", "Constructorul"): ("Constructorul",),
    ("bolivia", "Bolívar"): ("Bolívar La Paz",),
    ("bolivia", "The Strongest"): ("The Strongest La Paz",),
    ("bolivia", "Oriente Petrol."): ("Oriente Petrolero Santa Cruz",),
    ("uruguay", "Peñarol"): ("CA Peñarol",),
    ("uruguay", "Nacional"): ("Nacional Montevideo",),
    ("uruguay", "Wanderers"): ("Montevideo Wanderers",),
    ("colombia", "A. de Cali"): ("América Cali",),
    ("colombia", "Nacional Medellín"): ("Atlético Nacional Medellín",),
    ("colombia", "Millonarios"): ("Los Millonarios Bogotá",),
    ("ecuador", "El Nacional"): ("El Nacional Quito",),
    ("ecuador", "Emelec"): ("Emelec Guayaquil",),
    ("ecuador", "Barc. Guayaquil"): ("Barcelona Guayaquil",),
    ("peru", "Universitario"): ("Universitario de Deportes Lima",),
    ("peru", "Alianza Lima"): ("Alianza Lima",),
    ("peru", "Sporting Cristal"): ("Sporting Cristal Lima",),
    ("uruguay", "Peñarol"): ("CA Peñarol",),
    ("uruguay", "Nacional"): ("Nacional Montevideo",),
    ("uruguay", "Wanderers"): ("Montevideo Wanderers",),
    ("venezuela", "Caracas F.C"): ("Caracas FC",),
    ("venezuela", "Atlético Zulia"): ("Zulia FC",),
    ("paraguay", "O. Asunción"): ("Olimpia Asunción",),
    ("paraguay", "Cerro Porteño"): ("Cerro Porteño Asunción",),
    ("paraguay", "Guaraní"): ("Guarani Asunción",),
    ("latvia", "Skonto Riga"): ("Skonto Rīga",),
    ("latvia", "Met. Liepaja"): ("FK Liepāja",),
    ("lithuania", "Zalguiris"): ("Žalgiris Vilnius",),
    ("finland", "TPV"): ("TPV Tampere",),
    ("finland", "Haka"): ("Haka Valkeakoski",),
    ("finland", "Jazz"): ("FC Jazz Pori",),
    ("finland", "HJK Helsinki"): ("HJK Helsinki",),
    ("iceland", "KR Reykjavik"): ("KR Reykjavík",),
    ("iceland", "Akranes"): ("ÍA Akranes",),
    ("faroe-islands", "KI"): ("KÍ Klaksvík",),
    ("faroe-islands", "Gotu"): ("Víkingur Gøta",),
    ("belarus", "Dinamo Minsk"): ("Dynama Minsk",),
    ("belarus", "Mozyr"): ("Slaviya Mazyr",),
    ("kazakhstan", "Lantana"): ("Lantana",),
    ("armenia", "Pyunic"): ("Pyunik Yerevan",),
    ("north-macedonia", "Sileks"): ("Sileks Kratovo",),
    ("azerbaijan", "Neftchi"): ("Neftçi Bakı",),
    ("luxembourg", "Grevenmacher"): ("CS Grevenmacher",),
    ("luxembourg", "Jeunesse"): ("Jeunesse Esch-sur-Alzette",),
    ("luxembourg", "Avenir Beggen"): ("Avenir Beggen",),
    ("northern-ireland", "Linfield"): ("Linfield Belfast",),
    ("northern-ireland", "Crusaders"): ("Crusaders Belfast",),
    ("northern-ireland", "Glenavon"): ("Glenavon Lurgan",),
    ("northern-ireland", "Portadown"): ("Portadown FC",),
    ("northern-ireland", "Glentoran"): ("Glentoran Belfast",),
    ("northern-ireland", "Cliftonville"): ("Cliftonville FC",),
    ("northern-ireland", "Ards"): ("Ards Newtonards",),
}

NATIONALITY_CODES = {
    "Serbia": "SRB", "Croatia": "CRO", "Romania": "ROU", "Czechia": "CZE",
    "Bulgaria": "BUL", "Slovakia": "SVK", "Slovenia": "SVN", "Cyprus": "CYP",
    "Wales": "WAL", "Israel": "ISR", "Malta": "MLT", "Albania": "ALB",
    "Georgia": "GEO", "Moldova": "MDA", "Bolivia": "BOL", "Ecuador": "ECU",
    "Peru": "PER", "Uruguay": "URU", "Venezuela": "VEN", "Colombia": "COL",
    "Paraguay": "PAR", "Latvia": "LVA", "Armenia": "ARM", "North Macedonia": "MKD",
    "Kazakhstan": "KAZ", "Azerbaijan": "AZE", "Finland": "FIN", "Iceland": "ISL",
    "Faroe Islands": "FRO", "Belarus": "BLR", "Bosnia & Herzegovina": "BIH",
    "Montenegro": "MNE", "North Macedonia": "MKD", "Brazil": "BRA", "Argentina": "ARG",
    "Nigeria": "NGA", "Ghana": "GHA", "France": "FRA", "Germany": "GER",
    "Italy": "ITA", "Netherlands": "NED", "Spain": "ESP", "Portugal": "POR",
    "Turkey": "TUR", "Russia": "RUS", "Ukraine": "UKR", "England": "ENG",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)


class _LeagueParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "a" and (href := attrs_d.get("href")) and "/club/" in href:
            self._href, self._link_text = href, []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            value = (" ".join("".join(self._link_text).split()), self._href)
            if value not in self.links:
                self.links.append(value)
            self._href, self._link_text = None, []


class _SquadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._athlete = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "tr":
            self._athlete = d.get("itemprop") == "athlete"
            self._row = [] if self._athlete else None
        elif self._athlete and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._athlete and tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._athlete and self._row is not None:
            self.rows.append(self._row)
            self._row, self._athlete = None, False


def parse_league_links(payload: bytes) -> list[tuple[str, str]]:
    parser = _LeagueParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return parser.links


def _position(value: str) -> str | None:
    value = value.lower()
    if "goalkeeper" in value:
        return "G"
    if any(token in value for token in ("back", "defender", "sweeper", "stopper")):
        return "D"
    if any(token in value for token in ("midfield", "wing", "half")):
        return "M"
    if any(token in value for token in ("forward", "striker", "attacker", "offensive")):
        return "F"
    return None


def parse_squad_page(payload: bytes, *, country_name: str, season_label: str = SEASON_LABEL) -> list[dict[str, Any]]:
    parser = _SquadParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    players: list[dict[str, Any]] = []
    for row in parser.rows:
        if len(row) < 8 or row[5] != season_label:
            continue
        name, dob, nationality, raw_position = row[1], row[2], row[3], row[4]
        position = _position(raw_position)
        if not name or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dob) or position is None:
            continue
        nationality = html.unescape(nationality).strip()
        code = NATIONALITY_CODES.get(nationality, "UNK")
        unresolved = ["shirt_number", "height_cm", "weight_kg"]
        if code == "UNK":
            unresolved.append("nationality_code")
        players.append({
            "shirt_number": None,
            "name": re.sub(r"\s*,\s*", ", ", name),
            "nationality": code,
            "position": position,
            "height_cm": None,
            "weight_kg": None,
            "birth_date": dob,
            "unresolved_fields": unresolved,
        })
    # NTF can expose a player twice when a page contains multiple tables.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for player in players:
        unique[(player["name"], player["birth_date"])] = player
    return sorted(unique.values(), key=lambda p: (p["position"], p["name"]))


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PM99RE historical source audit/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _draft_targets(draft_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    result = []
    for proposal in payload.get("proposals", []):
        if proposal.get("status") == "source-squad-ready":
            continue
        family = proposal.get("group")
        if family in COUNTRIES:
            result.append({"carrier_id": int(proposal["carrier_id"]), "family": family, "baseline_name": proposal["baseline_name"], "fixed_roster_slot_count": int(proposal["fixed_roster_slot_count"])})
    return sorted(result, key=lambda x: x["carrier_id"])


def capture(*, draft_path: Path, cache_root: Path, countries: set[str] | None = None) -> dict[str, Any]:
    targets = _draft_targets(draft_path)
    if countries is not None:
        targets = [target for target in targets if target["family"] in countries]
    cache_root.mkdir(parents=True, exist_ok=True)
    clubs: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for family in sorted({target["family"] for target in targets}):
        country_id, country_slug = COUNTRIES[family]
        index_path_value = "2015" if family in CALENDAR_YEAR_COUNTRIES else "2015_1"
        source_season_label = "2015" if family in CALENDAR_YEAR_COUNTRIES else SEASON_LABEL
        index_url = f"{BASE_URL}/leagues/{country_id}/{index_path_value}/{country_slug}.html"
        try:
            index_payload = _get(index_url)
        except Exception as exc:  # network failure is an auditable source gap
            for target in [x for x in targets if x["family"] == family]:
                unresolved.append({**target, "reason": "country-index-fetch-failed", "detail": str(exc)})
            continue
        index_path = cache_root / family / "_league_2015_1.html"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(index_payload)
        indexes.append({"family": family, "url": index_url, "source_path": index_path.relative_to(cache_root).as_posix(), "source_sha256": _sha256_bytes(index_payload), "club_link_count": len(parse_league_links(index_payload))})
        links = parse_league_links(index_payload)
        by_name: dict[str, list[tuple[str, str]]] = {}
        for display, href in links:
            by_name.setdefault(_normalise(display), []).append((display, href))
        for target in [x for x in targets if x["family"] == family]:
            aliases = ALIASES.get((family, target["baseline_name"]), ())
            matches = [item for alias in aliases for item in by_name.get(_normalise(alias), [])]
            if not aliases:
                unresolved.append({**target, "reason": "no-reviewed-country-club-alias"})
                continue
            if not matches:
                unresolved.append({**target, "reason": "no-exact-2015-country-index-club"})
                continue
            if len({href for _, href in matches}) != 1:
                unresolved.append({**target, "reason": "ambiguous-exact-country-club-alias", "matches": matches})
                continue
            display, href = matches[0]
            url = href if href.startswith("http") else BASE_URL + href
            if url in used_urls:
                unresolved.append({**target, "reason": "source-club-reused-by-another-carrier", "source_url": url})
                continue
            used_urls.add(url)
            try:
                payload = _get(url)
            except Exception as exc:
                unresolved.append({**target, "reason": "club-page-fetch-failed", "source_url": url, "detail": str(exc)})
                continue
            source_path = Path(f"{family}/{target['carrier_id']}-{_normalise(display)}.html")
            full_path = cache_root / source_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(payload)
            players = parse_squad_page(payload, country_name=country_slug.replace("_", " "), season_label=source_season_label)
            if not players:
                unresolved.append({**target, "reason": "club-page-has-no-dated-2015-16-player-rows", "source_url": url, "source_sha256": _sha256_bytes(payload)})
                continue
            clubs.append({
                "country_catalog": family,
                "competition_catalog": "national-football-teams-2015-1",
                "club_name": display,
                "competition_name": f"National Football Teams historical club page ({SEASON_LABEL})",
                "source_path": source_path.as_posix(),
                "source_sha256": _sha256_bytes(payload),
                "source_url": url,
                "source_season_label": source_season_label,
                "players": players,
                "capture_note": "NTF appearance table; not guaranteed to be a complete registration list",
                "candidate_carrier_id": target["carrier_id"],
                "candidate_baseline_name": target["baseline_name"],
                "fixed_roster_slot_count": target["fixed_roster_slot_count"],
            })
    clubs.sort(key=lambda x: (x["country_catalog"], x["club_name"]))
    return {
        "schema_version": SCHEMA,
        "source": {"title": "National Football Teams historical club pages", "repository": BASE_URL, "revision": "2015-dated-pages-content-addressed-v1", "license": "public web factual source; URL and content hash retained", "retrieved_on": date.today().isoformat()},
        "season": {"catalog": SEASON_CATALOG, "label": SEASON_LABEL},
        "source_indexes": indexes,
        "clubs": clubs,
        "unresolved_carriers": unresolved,
        "summary": {
            "club_count": len(clubs),
            "player_count": sum(len(club["players"]) for club in clubs),
            "target_carrier_count": len(targets),
            "captured_target_carrier_count": len({club["candidate_carrier_id"] for club in clubs}),
            "unresolved_target_carrier_count": len(unresolved),
            "country_catalogs": sorted({club["country_catalog"] for club in clubs}),
            "unresolved_reason_counts": {reason: sum(1 for item in unresolved if item["reason"] == reason) for reason in sorted({item["reason"] for item in unresolved})},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--country", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = capture(draft_path=args.draft, cache_root=args.cache_root, countries=set(args.country) if args.country else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(result))
    print(json.dumps({"output": str(args.output), **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
