#!/usr/bin/env python3
"""Capture season-specific club squads from explicit Transfermarkt leagues.

This source adapter is deliberately independent of a PM99 carrier allocation.
An input scope pins each Transfermarkt competition code to one PM99 country and
competition catalogue.  The adapter enumerates the clubs published on that
competition's exact ``saison_id`` page, then saves and hashes every historical
squad page.  It emits the canonical season-capture shape consumed by the
existing source-intake pipeline plus a separate gap receipt.

No current-club table, transfer inference, fuzzy name join, or invented player
is used.  Cached snapshots make subsequent ``--offline`` runs byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import transfermarkt_calendar_year_policy_v1 as calendar_year_policy  # noqa: E402

from scripts.capture_transfermarkt_opening_lineups_v1 import (  # noqa: E402
    BASE_URL,
    CaptureError,
    SnapshotCache,
    _competition_teams,
)
from scripts.supplement_2015_ntf_with_transfermarkt import NATIONALITY_CODES, parse_squad  # noqa: E402
from scripts import season_player_identity_v1 as identity_lib  # noqa: E402
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES as TAIL_NATIONALITY_CODES  # noqa: E402

# The old supplement covered only its missing-country batch. Historical
# capture must also recognize ordinary home-nation flags in other leagues.
NATIONALITY_CODES = {**NATIONALITY_CODES, **TAIL_NATIONALITY_CODES,
    'Norway': 'NOR', 'Sweden': 'SWE', 'Denmark': 'DEN', 'Ireland': 'IRL',
    'Republic of Ireland': 'IRL', 'Northern Ireland': 'NIR', 'Belgium': 'BEL',
    'Poland': 'POL', 'Austria': 'AUT', 'Kenya': 'KEN', 'Haiti': 'HAI',
    'Bermuda': 'BER', 'Madagascar': 'MAD', 'Philippines': 'PHI', 'Pakistan': 'PAK',
    'Guinea-Bissau': 'GNB', 'Lebanon': 'LIB', 'Zimbabwe': 'ZIM', 'Liberia': 'LBR',
    'Eritrea': 'ERI', 'Jordan': 'JOR', 'Uganda': 'UGA', 'Comoros': 'COM',
    'Isle of Man': 'IMN'}


SCHEMA = "pm99-footballsquads-season-capture-v1"
SCOPE_SCHEMA = "pm99-transfermarkt-historical-squad-scope-v1"
GAP_SCHEMA = "pm99-transfermarkt-historical-squad-gaps-v1"
SOURCE_TITLE = "Transfermarkt historical competition and squad pages"
SOURCE_URL = "https://www.transfermarkt.com"

# Transfermarkt keeps the pre-Premier-League English competitions under
# separate historical identifiers.  Scopes intentionally retain the modern
# logical league identifiers so that one scope can be replayed for every
# season; this dated alias table only changes the upstream lookup.
HISTORICAL_COMPETITION_ALIASES = {
    ("GB1", 1900, 1991): "EFD1",
    ("ENTD", 1900, 1991): "ENFD",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_scope(path: Path) -> tuple[list[dict[str, str]], str]:
    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot decode scope: {path}") from exc
    if raw != canonical_bytes(document):
        raise CaptureError("scope must be canonical JSON")
    if not isinstance(document, dict) or document.get("schema_version") != SCOPE_SCHEMA:
        raise CaptureError(f"scope must use schema {SCOPE_SCHEMA}")
    rows = document.get("competitions")
    if not isinstance(rows, list) or not rows:
        raise CaptureError("scope must contain at least one competition")
    expected = {"competition_catalog", "competition_name", "country_catalog", "source_competition_code"}
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected:
            raise CaptureError(f"scope competition {index} must contain exactly {sorted(expected)}")
        clean = {key: str(row[key]).strip() for key in expected}
        if not all(clean.values()):
            raise CaptureError(f"scope competition {index} contains a blank value")
        key = (clean["country_catalog"], clean["competition_catalog"])
        if key in seen:
            raise CaptureError(f"scope duplicates {key[0]}/{key[1]}")
        seen.add(key)
        result.append(clean)
    result.sort(key=lambda row: (row["country_catalog"], row["competition_catalog"]))
    return result, sha256_bytes(raw)


def canonical_player(row: Mapping[str, Any]) -> dict[str, Any]:
    """Translate the existing strict page parser into intake vocabulary."""

    nationality = row.get("nationality")
    if nationality == "UNK":
        nationality = None
    values = {
        "shirt_number": row.get("shirt_number"),
        "name": str(row.get("name") or "").strip(),
        "nationality": nationality,
        "position": row.get("position"),
        "height_cm": row.get("height_cm"),
        "weight_kg": row.get("weight_kg"),
        "birth_date": row.get("birth_date"),
    }
    if not values["name"] or values["position"] not in {"G", "D", "M", "F"}:
        raise CaptureError("parsed historical squad row lacks a name or supported primary position")
    unresolved_map = {
        "shirt_number": "shirt_number", "nationality": "nationality",
        "height_cm": "height_cm", "weight_kg": "weight_kg", "birth_date": "birth_date",
    }
    unresolved = [gap for field, gap in unresolved_map.items() if values[field] is None]
    result = {**values, "unresolved_fields": unresolved}
    # Optional provider-scoped identity.  Absence means unknown and adds no
    # field, so captures from before this change keep their exact shape.
    if row.get(identity_lib.IDENTITY_FIELD) is not None:
        try:
            result[identity_lib.IDENTITY_FIELD] = identity_lib.validate_source_identity(
                row[identity_lib.IDENTITY_FIELD], label=f"player {values['name']!r} source_identity"
            )
        except identity_lib.IdentityError as exc:
            raise CaptureError(str(exc)) from exc
    return result


def competition_code_candidates(code: str, season_start_year: int) -> list[str]:
    result = [code]
    for (configured, first_year, last_year), historical in HISTORICAL_COMPETITION_ALIASES.items():
        if code == configured and first_year <= season_start_year <= last_year:
            result.insert(0, historical)
    return result


def parse_squad_with_dom_fallback(payload: bytes) -> list[dict[str, Any]]:
    """Complete partially parsed tables, preserving literal person identities.

    A nonempty streaming result does not prove the table is complete. Read
    the structured outer rows too; never merge different IDs by display name.
    """

    try:
        parsed = identity_lib.collapse_rows(
            parse_squad(payload), legacy_key=lambda p: str(p['name']).casefold())
    except identity_lib.IdentityError as exc:
        raise CaptureError(str(exc)) from exc
    soup = BeautifulSoup(payload, "html.parser")
    positions = {"Goalkeeper": "G", "Defender": "D", "Midfield": "M", "Attack": "F"}
    result: list[dict[str, Any]] = []
    expected_ids = set()
    for tr in soup.select("table.items > tbody > tr"):
        cells = tr.find_all("td", recursive=False)
        anchors = tr.select("a[href*='/profil/spieler/']")
        anchor = anchors[0] if anchors else None
        if not cells or anchor is None:
            continue
        try:
            identity = identity_lib.transfermarkt_identity(
                [link.get('href') for link in anchors], label='outer squad row')
        except identity_lib.IdentityError as exc:
            raise CaptureError(str(exc)) from exc
        if identity is not None:
            expected_ids.add(identity_lib.identity_key(identity))
        name = " ".join(anchor.get_text(" ", strip=True).split())
        position = positions.get(str(cells[0].get("title") or "").strip())
        if not name or position is None:
            continue
        number_node = cells[0].select_one(".rn_nummer")
        number = number_node.get_text(" ", strip=True) if number_node else ""
        shirt = int(number) if number.isdigit() and 0 <= int(number) <= 99 else None
        flag = next((img for cell in cells[2:4] for img in cell.select("img.flaggenrahmen")), None)
        nation = str(flag.get("title") or flag.get("alt") or "").strip() if flag else ""
        player = {
            "birth_date": None, "height_cm": None, "name": name,
            "nationality": NATIONALITY_CODES.get(nation, "UNK"), "position": position,
            "shirt_number": shirt, "weight_kg": None,
        }
        try:
            identity = identity_lib.transfermarkt_identity(
                [link.get("href") for link in anchors], label=f"squad row {name!r}"
            )
            if identity is not None:
                player[identity_lib.IDENTITY_FIELD] = identity
        except identity_lib.IdentityError as exc:
            raise CaptureError(str(exc)) from exc
        result.append(player)
    if not result and not expected_ids:
        return parsed
    # Prefer the table's structured broad role and literal flag. Retain any
    # stronger secondary facts read by the legacy parser from the SAME ID.
    legacy_by_id = {identity_lib.identity_key(p[identity_lib.IDENTITY_FIELD]): p
                    for p in parsed if identity_lib.IDENTITY_FIELD in p}
    dom_ids = set()
    for player in result:
        identity = player.get(identity_lib.IDENTITY_FIELD)
        if identity is None:
            continue
        key = identity_lib.identity_key(identity)
        dom_ids.add(key)
        prior = legacy_by_id.get(key, {})
        for field in ('birth_date', 'height_cm', 'weight_kg'):
            if player.get(field) is None and prior.get(field) is not None:
                player[field] = prior[field]
    result.extend(p for p in parsed
                  if identity_lib.IDENTITY_FIELD in p
                  and identity_lib.identity_key(p[identity_lib.IDENTITY_FIELD]) not in dom_ids)
    # Unknown IDs are not evidence that this is an identified namesake.
    result.extend(p for p in parsed if identity_lib.IDENTITY_FIELD not in p)
    actual_ids = {identity_lib.identity_key(p[identity_lib.IDENTITY_FIELD])
                  for p in result if identity_lib.IDENTITY_FIELD in p}
    if expected_ids - actual_ids:
        raise CaptureError('squad parser omitted literal player rows: ' + repr(sorted(expected_ids - actual_ids)))
    try:
        rows = identity_lib.collapse_rows(result, legacy_key=lambda p: str(p["name"]).casefold())
        return sorted(rows, key=lambda p: (p['position'], p['name'], identity_lib.identity_sort_key(p)))
    except identity_lib.IdentityError as exc:
        raise CaptureError(str(exc)) from exc


def build_capture(
    *, season_start_year: int, scope: list[dict[str, str]], scope_sha256: str,
    cache: SnapshotCache, parse: Callable[[bytes], list[dict[str, Any]]] = parse_squad_with_dom_fallback,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clubs: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    calendar_routes = []
    for competition in scope:
        configured_code = competition["source_competition_code"]
        if configured_code in {*calendar_year_policy.CALENDAR_CODE_COUNTRY, "RU1"}:
            calendar_year_policy.verify_audit(ROOT)
        try:
            route = calendar_year_policy.route_provider_year(
                season_start_year, configured_code, competition["country_catalog"])
        except calendar_year_policy.RoutingError as exc:
            gaps.append({**competition, "reason": "calendar-year-routing-quarantined", "detail": str(exc)})
            continue
        provider_year = route.provider_season_id
        is_calendar_routed = provider_year != season_start_year
        if is_calendar_routed:
            calendar_routes.append(route.document())
        teams = []
        effective_code = configured_code
        errors: list[str] = []
        for candidate in competition_code_candidates(configured_code, season_start_year):
            try:
                teams = _competition_teams(
                    season_start_year=provider_year,
                    target_season_start_year=season_start_year,
                    competition_code=candidate,
                    cache=cache,
                )
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                continue
            if teams:
                effective_code = candidate
                break
        if not teams:
            gaps.append({
                **competition,
                "reason": "competition-page-unavailable-or-unparseable",
                "detail": "; ".join(errors) or "competition page returned no season-team identities",
                "attempted_source_competition_codes": competition_code_candidates(
                    configured_code, season_start_year
                ),
            })
            continue
        for team in sorted(teams, key=lambda value: (value.transfermarkt_name, value.club_id)):
            slug = team.club_path.strip("/").split("/")[0]
            url = f"{BASE_URL}/{slug}/kader/verein/{team.club_id}/saison_id/{provider_year}"
            cache_key = calendar_year_policy.cache_key(kind="squad", target_year=season_start_year,
                provider_year=provider_year, code=effective_code, club_id=team.club_id)
            try:
                payload = cache.get(url, cache_key)
                if is_calendar_routed:
                    calendar_year_policy.require_source_title(payload, provider_year=provider_year,
                        target_year=season_start_year, label="historical squad")
                players = [canonical_player(row) for row in parse(payload)]
                if not players:
                    raise CaptureError("historical squad page yielded no supported player rows")
            except Exception as exc:
                gaps.append({
                    **competition, "club_name": team.transfermarkt_name,
                    "source_club_id": team.club_id, "source_url": url,
                    "reason": "squad-source-season-title-mismatch" if is_calendar_routed else "squad-page-unavailable-or-unparseable",
                    "detail": str(exc),
                })
                continue
            club = {
                "club_name": team.transfermarkt_name,
                "competition_catalog": competition["competition_catalog"],
                "competition_name": competition["competition_name"],
                "country_catalog": competition["country_catalog"],
                "players": players,
                "source_path": cache_key,
                "source_sha256": sha256_bytes(payload),
                "source_competition_code": effective_code,
            }
            if is_calendar_routed:
                club["source_provider_season_id"] = provider_year
                club["calendar_year_routing"] = route.document()
            clubs.append(club)
    clubs.sort(key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"]))
    gaps.sort(key=lambda row: (
        row["country_catalog"], row["competition_catalog"], str(row.get("club_name") or ""), row["reason"]
    ))
    label = f"{season_start_year}/{str(season_start_year + 1)[-2:]}"
    source = {
        "license": "public factual pages; attribution, URL and content hashes retained; no page artwork redistributed",
        "repository": SOURCE_URL,
        "revision": f"content-addressed-saison-id-{season_start_year}-v1",
        "snapshots": [dict(row) for _key, row in sorted(getattr(cache, "used", {}).items())],
        "scope_sha256": scope_sha256,
        "title": SOURCE_TITLE,
        **({"calendar_year_routing_policy": calendar_year_policy.verify_audit(ROOT),
            "revision": "content-addressed-calendar-route-v1"} if calendar_routes else {}),
    }
    identified = sum(
        identity_lib.IDENTITY_FIELD in player for club in clubs for player in club["players"]
    )
    capture = {
        "clubs": clubs,
        "schema_version": SCHEMA,
        "season": {"catalog": f"{season_start_year}-{season_start_year + 1}", "label": label},
        "source": source,
        "summary": {
            "club_count": len(clubs),
            "competition_catalogs": sorted({f'{c["country_catalog"]}/{c["competition_catalog"]}' for c in clubs}),
            "country_catalogs": sorted({c["country_catalog"] for c in clubs}),
            "player_count": sum(len(c["players"]) for c in clubs),
            "player_rows_with_unresolved_facts": sum(
                bool(player["unresolved_fields"]) for club in clubs for player in club["players"]
            ),
        },
    }
    if identified:
        capture["summary"]["player_rows_with_provider_identity"] = identified
    gap_receipt = {
        "gaps": gaps,
        "schema_version": GAP_SCHEMA,
        "season": capture["season"],
        "source": source,
        "summary": {
            "captured_club_count": len(clubs), "gap_count": len(gaps),
            "scope_competition_count": len(scope),
            "uncaptured_competition_count": len({
                (g["country_catalog"], g["competition_catalog"]) for g in gaps if "club_name" not in g
            }),
        },
    }
    return capture, gap_receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--season-start-year", required=True, type=int)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gaps-output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        scope, digest = load_scope(args.scope)
        capture, gaps = build_capture(
            season_start_year=args.season_start_year, scope=scope, scope_sha256=digest,
            cache=SnapshotCache(args.cache_dir, offline=args.offline, delay=args.delay),
        )
    except (OSError, CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.gaps_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(capture))
    args.gaps_output.write_bytes(canonical_bytes(gaps))
    print(json.dumps({**capture["summary"], **gaps["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
