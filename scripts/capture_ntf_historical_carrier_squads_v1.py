#!/usr/bin/env python3
"""Backfill unresolved fixed-carrier squads from exact NTF season indexes.

National Football Teams is used only where a season's primary squad captures
leave a country-family carrier gap. Club identity must match the exact season
index by a reviewed alias or an exact normalized native/full carrier name.
Every index and club page is cached and hashed; failures remain explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_2015_missing_family_squads import (  # noqa: E402
    ALIASES, BASE_URL, CALENDAR_YEAR_COUNTRIES, COUNTRIES, _get, _normalise,
    parse_league_links, parse_squad_page,
)
from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes  # noqa: E402

SCHEMA = "pm99-footballsquads-season-capture-v1"
GAP_SCHEMA = "pm99-ntf-historical-carrier-squad-gaps-v1"
SOURCE_COUNTRIES = {
    **COUNTRIES,
    "english-non-league": (59, "England"),
    "hungary": (84, "Hungary"),
    "serbia": (271, "Yugoslavia"),
}

# Exact historical display forms observed in the content-addressed 2000
# indexes. They supplement the older 2015 alias ledger; none is a fuzzy join.
HISTORICAL_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("faroe-islands", "Gotu"): ("GÍ Gøta",),
    ("moldova", "Constructorul"): ("Constructorul Chişinău",),
    ("romania", "Nat.Bucarest"): ("Național Bucureşti",),
    ("slovakia", "Chemlon H."): ("HFC Humenné",),
    ("slovakia", "Kosice"): ("1.FC Košice",),
    ("slovakia", "Bardejov"): ("JAS Bardejov",),
    ("hungary", "Ferencvaros"): ("Ferencvárosi TC",),
    ("hungary", "VAC Zollner"): ("Vác VLSE",),
    ("hungary", "Ujpesti Dozsa"): ("Újpest FC",),
    ("hungary", "Kispest"): ("Kispest Honvéd",),
    ("hungary", "Vasutas"): ("BVSC Budapest",),
    ("hungary", "DVSC Epona"): ("Debreceni VSC",),
    ("hungary", "MTK"): ("MTK Hungária Budapest",),
    ("hungary", "Vasas CV"): ("Vasas Budapest",),
    ("hungary", "Csepel"): ("Csepel SC",),
    ("serbia", "Obilic"): ("Obilić Beograd",),
    # Exact 2000/01 England index labels for abbreviated PM99 carriers.
    ("english-non-league", "Doncaster R."): ("Doncaster Rovers",),
    ("english-non-league", "Hereford U."): ("Hereford United",),
    ("english-non-league", "Altrincham"): ("Altrincham FC",),
    ("english-non-league", "Gateshead"): ("Gateshead FC",),
    ("english-non-league", "Hayes"): ("Hayes FC",),
    ("english-non-league", "Morecambe"): ("Morecambe FC",),
    ("english-non-league", "Rushden & D."): ("Rushden & Diamonds FC",),
    ("english-non-league", "Southport"): ("Southport FC",),
    ("english-non-league", "Woking"): ("Woking FC",),
    ("english-non-league", "Barrow"): ("Barrow AFC",),
    ("english-non-league", "Bishop A."): ("Bishop Auckland FC",),
    ("english-non-league", "Buxton"): ("Buxton FC",),
    ("english-non-league", "Chorley"): ("Chorley FC",),
    ("english-non-league", "Colwyn B."): ("Colwyn Bay FC",),
}


class Cache:
    blocked_hosts: dict[str, int] = {}

    def __init__(self, root: Path, *, offline: bool, delay: float, stop_on_http_block: bool = False) -> None:
        self.root, self.offline, self.delay = root, offline, delay
        self.stop_on_http_block = stop_on_http_block
        self.used: list[dict[str, str]] = []

    def get(self, url: str, key: str) -> bytes:
        path = self.root / key
        receipt_path = path.with_suffix(path.suffix + ".source.json")
        receipt: dict[str, Any] | None = None
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                receipt = None
        reusable = path.is_file() and receipt is not None and receipt.get("url") == url
        if reusable:
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != receipt.get("sha256"):
                raise ValueError(f"cached snapshot hash mismatch: {path}")
        elif self.offline:
            raise ValueError(f"offline URL-bound snapshot missing: {path}")
        else:
            host = urlparse(url).netloc
            if self.stop_on_http_block and host in self.blocked_hosts:
                raise ValueError(f'source host paused after HTTP {self.blocked_hosts[host]}; cached evidence only')
            try:
                payload = _get(url)
            except HTTPError as exc:
                if self.stop_on_http_block and exc.code in (401, 403, 405, 429, 503):
                    self.blocked_hosts[host] = exc.code
                raise
            finally:
                # Failed requests must be rate-limited too. Otherwise a
                # provider refusal turns a slow capture into a tight loop.
                if self.delay:
                    time.sleep(self.delay)
            if len(payload) < 1000:
                raise ValueError("source response is implausibly small")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            receipt_path.write_bytes(canonical_bytes({
                "sha256": hashlib.sha256(payload).hexdigest(), "url": url,
            }))
        self.used.append({"cache_path": key, "sha256": hashlib.sha256(payload).hexdigest(), "url": url})
        return payload


def canonical_player(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: row.get(key) for key in ("shirt_number", "name", "nationality", "position", "height_cm", "weight_kg", "birth_date")}
    if result["nationality"] == "UNK":
        result["nationality"] = None
    result["unresolved_fields"] = [key for key in ("shirt_number", "nationality", "height_cm", "weight_kg", "birth_date") if result[key] is None]
    return result


def capture(*, registry: Mapping[str, Any], allocation: Mapping[str, Any], season_start_year: int, cache: Cache,
            countries: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    by_carrier = {int(row["carrier_id"]): row for row in registry["carriers"]}
    targets = [row for row in allocation["gaps"] if "carrier_id" in row and row.get("country_group") in SOURCE_COUNTRIES]
    if countries is not None:
        targets = [row for row in targets if row.get("country_group") in countries]
    clubs: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for family in sorted({str(row["country_group"]) for row in targets}):
        country_id, country_slug = SOURCE_COUNTRIES[family]
        candidates = [str(season_start_year), f"{season_start_year}_1"] if family in CALENDAR_YEAR_COUNTRIES else [f"{season_start_year}_1", str(season_start_year)]
        indexed: list[tuple[str, bytes, list[tuple[str, str]], str]] = []
        for suffix in candidates:
            url = f"{BASE_URL}/leagues/{country_id}/{suffix}/{country_slug}.html"
            try:
                payload = cache.get(url, f"index/{family}/{suffix}.html")
                indexed.append((suffix, payload, parse_league_links(payload), url))
            except Exception as exc:
                gaps.append({"country_group": family, "reason": "country-index-fetch-failed", "source_url": url, "detail": str(exc)})
        if not indexed or not max(indexed, key=lambda row: len(row[2]))[2]:
            for target in sorted((row for row in targets if row["country_group"] == family), key=lambda row: int(row["carrier_id"])):
                carrier = by_carrier[int(target["carrier_id"])]
                gaps.append({
                    "carrier_id": int(target["carrier_id"]), "country_group": family,
                    "baseline_name": carrier["baseline_club"]["name"],
                    "reason": "country-index-has-no-season-clubs",
                })
            continue
        suffix, _payload, links, _url = max(indexed, key=lambda row: len(row[2]))
        by_name: dict[str, list[tuple[str, str]]] = {}
        for display, href in links:
            by_name.setdefault(_normalise(display), []).append((display, href))
        for gap in sorted((row for row in targets if row["country_group"] == family), key=lambda row: int(row["carrier_id"])):
            carrier = by_carrier[int(gap["carrier_id"])]
            baseline = carrier["baseline_club"]
            accepted = (set(ALIASES.get((family, str(baseline["name"])), ())) |
                        set(HISTORICAL_ALIASES.get((family, str(baseline["name"])), ())) |
                        {str(baseline["name"]), str(baseline["full_name"])})
            matches = [item for name in accepted for item in by_name.get(_normalise(name), [])]
            unique = {href: display for display, href in matches}
            if len(unique) != 1:
                gaps.append({"carrier_id": int(gap["carrier_id"]), "country_group": family, "baseline_name": baseline["name"],
                             "reason": "no-unique-exact-season-index-club", "match_count": len(unique)})
                continue
            href, display = next(iter(unique.items()))
            url = href if href.startswith("http") else BASE_URL + href
            if url in used_urls:
                gaps.append({"carrier_id": int(gap["carrier_id"]), "country_group": family, "reason": "source-club-reused"})
                continue
            used_urls.add(url)
            try:
                payload = cache.get(url, f"club/{family}/{gap['carrier_id']}.html")
                match = re.search(r"/(\d{4}_[12])/", href)
                page_season = f"{season_start_year}/{str(season_start_year + 1)[-2:]}" if match and match.group(1).endswith("_1") else str(season_start_year)
                players = [canonical_player(row) for row in parse_squad_page(payload, country_name=country_slug.replace("_", " "), season_label=page_season)]
                if not players:
                    raise ValueError(f"no player rows for page season {page_season}")
            except Exception as exc:
                gaps.append({"carrier_id": int(gap["carrier_id"]), "country_group": family, "club_name": display,
                             "reason": "club-page-unavailable-or-no-season-players", "detail": str(exc), "source_url": url})
                continue
            clubs.append({"club_name": display, "competition_catalog": "ntf-opening-squad", "competition_name": "National Football Teams historical season appearances",
                          "country_catalog": family, "players": players, "source_path": f"club/{family}/{gap['carrier_id']}.html",
                          "source_sha256": hashlib.sha256(payload).hexdigest()})
    clubs.sort(key=lambda row: (row["country_catalog"], row["club_name"], row["source_path"]))
    gaps.sort(key=lambda row: (str(row.get("country_group")), int(row.get("carrier_id", 0)), row["reason"]))
    label = f"{season_start_year}/{str(season_start_year + 1)[-2:]}"
    source = {"license": "public factual pages; attribution, URLs and hashes retained", "repository": BASE_URL,
              "revision": f"content-addressed-season-{season_start_year}-v1", "snapshots": sorted(cache.used, key=lambda row: row["cache_path"]),
              "title": "National Football Teams historical club pages"}
    result = {"clubs": clubs, "schema_version": SCHEMA, "season": {"catalog": f"{season_start_year}-{season_start_year+1}", "label": label},
              "source": source, "summary": {"club_count": len(clubs), "competition_catalogs": sorted({f'{c["country_catalog"]}/ntf-opening-squad' for c in clubs}),
              "country_catalogs": sorted({c["country_catalog"] for c in clubs}), "player_count": sum(len(c["players"]) for c in clubs),
              "player_rows_with_unresolved_facts": sum(bool(p["unresolved_fields"]) for c in clubs for p in c["players"])}}
    receipt = {"gaps": gaps, "schema_version": GAP_SCHEMA, "season": result["season"], "source": source,
               "summary": {"captured_club_count": len(clubs), "gap_count": len(gaps), "target_carrier_count": len(targets)}}
    return result, receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--allocation", type=Path, required=True)
    parser.add_argument("--season-start-year", type=int, required=True); parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--gaps-output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true"); parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--country", action="append", default=[])
    args = parser.parse_args(argv)
    registry, allocation = json.loads(args.registry.read_text()), json.loads(args.allocation.read_text())
    result, gaps = capture(registry=registry, allocation=allocation, season_start_year=args.season_start_year,
                           cache=Cache(args.cache_dir, offline=args.offline, delay=args.delay),
                           countries=set(args.country) if args.country else None)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.gaps_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result)); args.gaps_output.write_bytes(canonical_bytes(gaps))
    print(json.dumps({**result["summary"], **gaps["summary"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
