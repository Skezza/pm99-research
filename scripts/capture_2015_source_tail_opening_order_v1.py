#!/usr/bin/env python3
"""Order the 2015 source-tail season squads from their domestic opening window.

Each source-tail club already has a hash-bound dated squad.  This step uses
the exact Transfermarkt club IDs retained by that capture, reads only their
own 2015 schedule, then prioritises first-league-XI players, first benches,
and later domestic opening fixtures.  A pinned dated season roster can fill a
remaining immutable carrier capacity, but that fallback is labelled rather
than hidden.  It cannot write a PM99 database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_source_tail_squads_v1 as tail_squads  # noqa: E402
from scripts import capture_transfermarkt_lineup_person_evidence_v1 as person_profiles  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-world-2015-source-tail-opening-order-capture-v1"
PACKAGE_SCHEMAS = {
    "pm99-world-2015-source-tail-package-v1",
    "pm99-world-2015-source-tail-package-v2",
}

# These are the exact competition codes observed in every selected club's
# cached 2015 schedule.  Split calendar-year leagues retain both published
# stages so the earliest domestic fixture, rather than a hand-picked stage,
# determines the opening window.  Cup codes are deliberately absent.
DOMESTIC_COMPETITIONS: dict[str, tuple[str, ...]] = {
    "bolivia": ("B1AP",),
    "bulgaria": ("BU1",),
    "croatia": ("KR1",),
    "czechia": ("TS1",),
    "ecuador": ("ECPE", "ECSE"),
    "english-non-league": ("CNAT",),
    "finland": ("FI1",),
    "kazakhstan": ("KAS1",),
    "lithuania": ("LI1",),
    "luxembourg": ("LUX1",),
    "moldova": ("MOL1",),
    "northern-ireland": ("NIR1",),
    "romania": ("RO1",),
    "serbia": ("SER1",),
    "slovakia": ("SLO1",),
    "slovenia": ("SL1",),
    "uruguay": ("URU1", "URUC"),
    "venezuela": ("VZ1A", "VZ1C"),
    "wales": ("WAL1",),
}

# Three chronologically first domestic reports form a defined opening window.
# This preserves an August/opening squad approach without silently reaching
# into a later-season match simply because a fixed PM99 carrier has more slots.
MAX_OPENING_FIXTURES = 3
MAX_OPENING_REPORT_ATTEMPTS = 6

# Transfermarkt publishes the dated 2015 squad pages for these four calendar
# clubs, but their matching historical schedules contain no domestic fixture
# rows at all.  Do not manufacture a first XI.  These exact source receipts
# may use their published squad-number sequence solely to fill the immutable
# roster carrier, with the evidence downgrade retained in the output.
SOURCE_NUMBER_ORDER_EXCEPTION_CARRIER_IDS = {2601, 2602, 2603, 2953}


class OpeningOrderError(ValueError):
    """A dated squad cannot be joined safely to opening-fixture evidence."""


def _profile_position_group(label: object) -> str | None:
    """Map a published profile position to the four explicit PM99 groups."""

    value = str(label or "").casefold()
    if "goalkeeper" in value:
        return "G"
    if any(token in value for token in ("back", "defender", "sweeper")):
        return "D"
    if "midfield" in value:
        return "M"
    if any(token in value for token in ("forward", "striker", "winger", "attack")):
        return "F"
    return None


def _profile_player_addition(
    *, lineup_player: Mapping[str, Any], cache: opening.SnapshotCache
) -> dict[str, Any]:
    """Capture a profile-backed fact row only when a dated squad lacks an XI player."""

    source_id = str(lineup_player.get("source_player_id") or "").strip()
    source_url = str(lineup_player.get("source_url") or "").strip()
    if not source_id or not source_url:
        raise OpeningOrderError("opening-lineup player lacks its profile identity")
    try:
        payload = cache.get(source_url, f"profile/{source_id}.html")
        facts = person_profiles._profile_facts(payload, player=dict(lineup_player))
    except (OSError, opening.CaptureError, person_profiles.PersonEvidenceError) as exc:
        raise OpeningOrderError(f"cannot capture profile facts for opening-lineup player {source_id}") from exc
    nationality = tail_squads.NATIONALITY_CODES.get(str(facts.get("published_nationality_label") or ""))
    position = _profile_position_group(facts.get("published_profile_position"))
    name = str(facts.get("published_full_name") or "").strip()
    if not name or nationality is None or position is None:
        raise OpeningOrderError(
            f"opening-lineup profile {source_id} lacks a usable name, nationality or broad position"
        )
    birth_date = facts.get("published_birth_date")
    height_cm = facts.get("published_height_cm")
    unresolved = ["shirt_number", "weight_kg"]
    if birth_date is None:
        unresolved.append("birth_date")
    if height_cm is None:
        unresolved.append("height_cm")
    return {
        "birth_date": birth_date,
        "height_cm": height_cm,
        "name": name,
        "nationality": nationality,
        "position": position,
        "shirt_number": None,
        "unresolved_fields": unresolved,
        "weight_kg": None,
        "source_profile": {
            "source_player_id": source_id,
            "source_url": source_url,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "published_nationality_label": facts["published_nationality_label"],
            "published_profile_position": facts["published_profile_position"],
            "fact_origin": "opening-lineup-profile-addition",
        },
    }


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpeningOrderError(f"cannot read source-tail package: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise OpeningOrderError("source-tail package must be canonical JSON")
    if value.get("schema_version") not in PACKAGE_SCHEMAS:
        raise OpeningOrderError("source-tail package has an unsupported schema")
    return value, hashlib.sha256(raw).hexdigest()


def _schedule_fixtures(
    *, club: Mapping[str, Any], cache: opening.SnapshotCache
) -> tuple[opening.TeamRef, list[dict[str, str]]]:
    identity = club.get("source_identity")
    if not isinstance(identity, Mapping):
        raise OpeningOrderError("pinned source club lacks its exact Transfermarkt identity")
    club_id, slug = identity.get("transfermarkt_club_id"), identity.get("transfermarkt_slug")
    if not isinstance(club_id, int) or not isinstance(slug, str) or not slug:
        raise OpeningOrderError("pinned source club has an invalid Transfermarkt identity")
    country = str(club.get("country_catalog") or "")
    domestic_codes = DOMESTIC_COMPETITIONS.get(country)
    if domestic_codes is None:
        raise OpeningOrderError(f"no reviewed domestic competition codes for {country!r}")
    carrier_id = club.get("candidate_carrier_id")
    if not isinstance(carrier_id, int):
        raise OpeningOrderError("pinned source club lacks a carrier id")
    source_saison_id = identity.get("transfermarkt_saison_id", 2015)
    if not isinstance(source_saison_id, int) or source_saison_id not in {2014, 2015}:
        raise OpeningOrderError("pinned source club has an invalid historical Transfermarkt selector")
    selector_suffix = "" if source_saison_id == 2015 else f"-selector-{source_saison_id}"
    schedule_url = (
        f"{opening.BASE_URL}/{slug}/spielplan/verein/{club_id}/saison_id/{source_saison_id}"
    )
    page = BeautifulSoup(
        cache.get(
            schedule_url, f"schedule/2015/{carrier_id}-{club_id}{selector_suffix}.html",
        ), "html.parser"
    )
    fixtures: list[dict[str, str]] = []
    observed_codes: set[str] = set()
    for row in page.select("tr"):
        report = row.select_one('a[href*="/spielbericht/index/spielbericht/"]')
        competition = row.select_one('a[href*="/test/spieltag/wettbewerb/"]')
        if report is None or competition is None:
            continue
        code_match = re.search(r"/wettbewerb/([^/]+)", str(competition.get("href") or ""))
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", row.get_text(" ", strip=True))
        report_match = re.search(r"/spielbericht/(\d+)", str(report.get("href") or ""))
        if code_match is None or date_match is None or report_match is None:
            continue
        code = code_match.group(1)
        observed_codes.add(code)
        if code not in domestic_codes:
            continue
        fixture_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat()
        fixtures.append({
            "date": fixture_date,
            "match_id": report_match.group(1),
            "report_url": urljoin(opening.BASE_URL, str(report.get("href"))),
            "schedule_url": schedule_url,
            "source_competition_code": code,
        })
    if not fixtures:
        raise OpeningOrderError(
            f"no reviewed domestic fixtures for {club['club_name']!r}; observed {sorted(observed_codes)}"
        )
    ref = opening.TeamRef(
        source_club_name=str(club["club_name"]),
        transfermarkt_name=str(identity.get("search_display_name") or club["club_name"]),
        club_id=club_id,
        club_path=f"/{slug}/startseite/verein/{club_id}",
        identity_match_method="exact-pinned-2015-source-tail-club-id",
    )
    return ref, sorted(fixtures, key=lambda row: (row["date"], int(row["match_id"])))


def _index_source_players(players: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for player in players:
        name = str(player.get("name") or "").strip()
        key = tail_squads._normalise(name)
        if not key:
            raise OpeningOrderError("dated squad has an unnamed player")
        if key in result:
            raise OpeningOrderError(f"dated squad has duplicate normalised player {name!r}")
        result[key] = dict(player)
    return result


def _source_player_ids(
    *, club: Mapping[str, Any], source_squad_cache_root: Path
) -> dict[str, dict[str, Any]]:
    """Join the original dated squad's profile IDs back to its player facts.

    Match reports often shorten a display name to a surname.  A surname match
    would be unsafe, so use the stable Transfermarkt player ID from the exact
    cached squad page whenever that primary receipt came from Transfermarkt.
    """

    source_url = str(club.get("source_url") or "")
    source_sha256 = str(club.get("source_sha256") or "")
    identity = club.get("source_identity")
    carrier_id = club.get("candidate_carrier_id")
    if not source_url.startswith("https://www.transfermarkt."):
        # A separately attributed FootballSquads capacity fallback has no
        # compatible Transfermarkt player-ID page.  Its names remain exact
        # normalised joins, never loose surname matching.
        return {}
    if not isinstance(identity, Mapping) or not isinstance(carrier_id, int):
        raise OpeningOrderError("Transfermarkt dated squad lacks a stable cache identity")
    club_id = identity.get("transfermarkt_club_id")
    if not isinstance(club_id, int):
        raise OpeningOrderError("Transfermarkt dated squad lacks its club id")
    source_saison_id = identity.get("transfermarkt_saison_id", 2015)
    if not isinstance(source_saison_id, int) or source_saison_id not in {2014, 2015}:
        raise OpeningOrderError("Transfermarkt dated squad has an invalid historical selector")
    selector_suffix = "" if source_saison_id == 2015 else f"-selector-{source_saison_id}"
    path = source_squad_cache_root / f"squad/2015/{carrier_id}-{club_id}{selector_suffix}.html"
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise OpeningOrderError(f"missing exact cached dated squad: {path}") from exc
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != source_sha256:
        raise OpeningOrderError(
            f"cached dated squad hash differs from source receipt for {club['club_name']!r}"
        )
    stored_ids: dict[str, dict[str, Any]] = {}
    for player in club["players"]:
        source_id = str(player.get("source_player_id") or "").strip()
        if not source_id:
            continue
        if source_id in stored_ids:
            raise OpeningOrderError(f"dated squad repeats source player ID {source_id}")
        stored_ids[source_id] = dict(player)
    if len(stored_ids) == len(club["players"]):
        return stored_ids
    players_by_name = _index_source_players(club["players"])
    result: dict[str, dict[str, Any]] = {}
    for anchor in BeautifulSoup(payload, "html.parser").select('a[href*="/profil/spieler/"]'):
        profile_match = re.search(r"/profil/spieler/(\d+)", str(anchor.get("href") or ""))
        if profile_match is None:
            continue
        key = tail_squads._normalise(anchor.get_text(" ", strip=True))
        player = players_by_name.get(key)
        if player is None:
            continue
        source_id = profile_match.group(1)
        prior = result.get(source_id)
        if prior is not None and prior != player:
            raise OpeningOrderError(f"dated squad reuses player ID {source_id} for distinct player facts")
        result[source_id] = player
    if not result:
        raise OpeningOrderError(f"cached dated squad has no joinable player IDs for {club['club_name']!r}")
    return result


def _capacity_roster(
    *,
    source_players: Sequence[Mapping[str, Any]],
    lineups: Sequence[Mapping[str, Any]],
    capacity: int,
    source_players_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    profile_player_factory: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Select XI then bench from each earliest fixture, before tagged source remainder."""

    by_id = dict(source_players_by_id or {})
    has_dated_squad_profile_ids = bool(by_id)
    indexed = {} if has_dated_squad_profile_ids else _index_source_players(source_players)

    def player_key(player: Mapping[str, Any]) -> str:
        source_id = str(player.get("source_player_id") or "").strip()
        return f"source-id:{source_id}" if source_id else f"name:{tail_squads._normalise(player.get('name'))}"
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fixture in lineups:
        for role, lineup_players in (("starting-xi", fixture.get("starting_xi")), ("substitute", fixture.get("substitutes"))):
            if not isinstance(lineup_players, list):
                continue
            for lineup_player in lineup_players:
                if not isinstance(lineup_player, Mapping):
                    continue
                name = str(lineup_player.get("display_name") or "").strip()
                key = tail_squads._normalise(name)
                source_id = str(lineup_player.get("source_player_id") or "")
                match_method = ""
                source_player = by_id.get(source_id) if has_dated_squad_profile_ids else indexed.get(key)
                if source_player is not None:
                    match_method = (
                        "exact-transfermarkt-player-id"
                        if has_dated_squad_profile_ids else "exact-normalised-source-name"
                    )
                if source_player is None:
                    # For a non-Transfermarkt dated fallback, the full profile
                    # slug is still an exact name bridge; a report's one-word
                    # display label alone is never accepted.
                    slug_key = tail_squads._normalise(lineup_player.get("source_slug"))
                    source_player = indexed.get(slug_key) if slug_key else None
                    if source_player is not None:
                        match_method = "exact-profile-slug-to-source-name"
                if source_player is None and source_id and profile_player_factory is not None:
                    source_player = profile_player_factory(lineup_player)
                    by_id[source_id] = source_player
                    match_method = "opening-lineup-profile-addition"
                if source_player is None:
                    join_kind = "Transfermarkt player ID" if has_dated_squad_profile_ids else "exact normalised name"
                    raise OpeningOrderError(
                        f"published opening-lineup player {name!r} has no {join_kind} in the pinned dated squad"
                    )
                source_key = player_key(source_player)
                if source_key in seen:
                    continue
                selected.append({
                    **source_player,
                    "opening_source": {
                        "fixture_date": fixture["first_league_fixture_date"],
                        "lineup_url": fixture["lineup_source_url"],
                        "match_id": fixture["source_match_id"],
                        "player_profile_url": lineup_player.get("source_url"),
                        "player_source_id": lineup_player.get("source_player_id"),
                        "player_match_method": match_method,
                        "selection_role": role,
                    },
                })
                seen.add(source_key)
                if len(selected) >= capacity:
                    return selected, 0
    fallback_count = 0
    for player in source_players:
        key = player_key(player)
        if key in seen:
            continue
        selected.append({
            **dict(player),
            "opening_source": {
                "selection_role": "pinned-season-capacity-remainder",
                "reason": "not named in the published domestic opening fixtures needed to fill immutable carrier capacity",
            },
        })
        seen.add(key)
        fallback_count += 1
        if len(selected) >= capacity:
            return selected, fallback_count
    raise OpeningOrderError(f"dated squad could not fill immutable capacity {len(selected)}/{capacity}")


def _source_number_order_exception(*, club: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """Return the declared degraded selection where no domestic reports exist."""

    carrier_id = club.get("candidate_carrier_id")
    identity = club.get("source_identity")
    capacity = club.get("fixed_roster_slot_count")
    if (
        carrier_id not in SOURCE_NUMBER_ORDER_EXCEPTION_CARRIER_IDS
        or not isinstance(identity, Mapping)
        or identity.get("transfermarkt_saison_id") != 2014
        or not isinstance(capacity, int)
    ):
        raise OpeningOrderError(reason)
    players = club.get("players")
    if not isinstance(players, list):
        raise OpeningOrderError("source-number exception has no dated squad players")
    ordered = sorted(
        (dict(player) for player in players if isinstance(player, Mapping)),
        key=lambda player: (
            player.get("shirt_number") is None,
            int(player["shirt_number"]) if isinstance(player.get("shirt_number"), int) else 999,
            str(player.get("name") or ""),
            str(player.get("source_player_id") or ""),
        ),
    )[:capacity]
    if len(ordered) != capacity:
        raise OpeningOrderError("source-number exception cannot fill immutable capacity")
    for player in ordered:
        player["opening_source"] = {
            "selection_role": "published-dated-squad-number-order-exception",
            "reason": "exact historical Transfermarkt schedule publishes no domestic fixture report; no first XI was inferred",
            "player_source_id": player.get("source_player_id"),
            "player_match_method": "exact-dated-squad-source-player-id",
        }
    return {
        "candidate_carrier_id": carrier_id,
        "fixed_roster_slot_count": capacity,
        "country_catalog": club["country_catalog"],
        "competition_catalog": "transfermarkt-2015-source-tail-number-ordered-exception",
        "club_name": club["club_name"],
        "target_article_title": club["target_article_title"],
        "target_article_path": club["target_article_path"],
        "source_season_label": club["source_season_label"],
        "source_url": club["source_url"],
        "source_sha256": club.get("source_sha256"),
        "players": ordered,
        "opening_fixtures": [],
        "skipped_opening_reports": [],
        "opening_lineup_evidence_gap": reason,
        "selection": {
            "policy": (
                "published dated-squad shirt-number sequence only; exact historical source schedule has no domestic "
                "fixture reports, so no first XI, bench, formation or manager is claimed"
            ),
            "pinned_season_capacity_remainder_count": 0,
            "published_opening_lineup_player_count": 0,
            "opening_profile_player_addition_count": 0,
            "published_dated_squad_number_order_exception_count": capacity,
        },
        "source_identity": dict(identity),
    }


def _capture_one(
    *, club: Mapping[str, Any], cache: opening.SnapshotCache, source_squad_cache_root: Path
) -> dict[str, Any]:
    try:
        ref, fixtures = _schedule_fixtures(club=club, cache=cache)
    except OpeningOrderError as exc:
        return _source_number_order_exception(club=club, reason=str(exc))
    capacity = club.get("fixed_roster_slot_count")
    if not isinstance(capacity, int) or capacity < 11:
        raise OpeningOrderError("source club has an invalid immutable capacity")
    lineups: list[dict[str, Any]] = []
    skipped_reports: list[dict[str, str]] = []
    for fixture in fixtures[:MAX_OPENING_REPORT_ATTEMPTS]:
        if len(lineups) >= MAX_OPENING_FIXTURES:
            break
        try:
            lineup = opening._lineup_from_report(ref, fixture, cache)
        except opening.CaptureError as exc:
            skipped_reports.append({
                "date": fixture["date"], "match_id": fixture["match_id"],
                "lineup_source_url": fixture["report_url"], "reason": str(exc),
            })
            continue
        lineup["source_competition_code"] = fixture["source_competition_code"]
        lineups.append(lineup)
    if not lineups:
        raise OpeningOrderError("no source-qualified reports in the domestic opening window")
    profile_additions: dict[str, dict[str, Any]] = {}

    def profile_addition(lineup_player: Mapping[str, Any]) -> Mapping[str, Any]:
        source_id = str(lineup_player.get("source_player_id") or "")
        existing = profile_additions.get(source_id)
        if existing is not None:
            return existing
        captured = _profile_player_addition(lineup_player=lineup_player, cache=cache)
        profile_additions[source_id] = captured
        return captured

    selected, fallback_count = _capacity_roster(
        source_players=club["players"], lineups=lineups, capacity=capacity,
        source_players_by_id=_source_player_ids(
            club=club, source_squad_cache_root=source_squad_cache_root,
        ),
        profile_player_factory=profile_addition,
    )
    return {
        "candidate_carrier_id": club["candidate_carrier_id"],
        "fixed_roster_slot_count": capacity,
        "country_catalog": club["country_catalog"],
        "competition_catalog": "transfermarkt-2015-source-tail-domestic-opening-window",
        "club_name": club["club_name"],
        "target_article_title": club["target_article_title"],
        "target_article_path": club["target_article_path"],
        "source_season_label": club["source_season_label"],
        "source_url": club["source_url"],
        "source_sha256": club.get("source_sha256"),
        "players": selected,
        "opening_fixtures": [
            {
                "date": fixture["first_league_fixture_date"],
                "lineup_source_url": fixture["lineup_source_url"],
                "match_id": fixture["source_match_id"],
                "source_competition_code": fixture["source_competition_code"],
                "source_status": fixture["source_status"],
                "source_blockers": fixture["source_blockers"],
            }
            for fixture in lineups
        ],
        "skipped_opening_reports": skipped_reports,
        "selection": {
            "policy": (
                "first domestic XI, then its published bench, then later domestic opening fixtures; "
                "only a labelled pinned dated-season roster remainder may fill immutable capacity"
            ),
            "pinned_season_capacity_remainder_count": fallback_count,
            "published_opening_lineup_player_count": capacity - fallback_count,
            "opening_profile_player_addition_count": sum(
                1 for player in selected
                if isinstance(player.get("source_profile"), Mapping)
            ),
        },
        "source_identity": club["source_identity"],
    }


def capture(
    *, package: Mapping[str, Any], package_sha256: str, cache: opening.SnapshotCache,
    source_squad_cache_root: Path,
) -> dict[str, Any]:
    clubs = package.get("clubs")
    if not isinstance(clubs, list):
        raise OpeningOrderError("source-tail package has no clubs")
    selected = [
        club for club in clubs
        if isinstance(club, Mapping)
        and (club.get("source_package") or {}).get("route") == "pinned-historic-season-squad"
    ]
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for club in sorted(selected, key=lambda row: int(row["candidate_carrier_id"])):
        try:
            rows.append(_capture_one(
                club=club, cache=cache, source_squad_cache_root=source_squad_cache_root,
            ))
        except (OSError, ValueError, opening.CaptureError, OpeningOrderError) as exc:
            failures.append({
                "candidate_carrier_id": club.get("candidate_carrier_id"),
                "club_name": club.get("club_name"),
                "reason": str(exc),
            })
    remainder_count = sum(row["selection"]["pinned_season_capacity_remainder_count"] for row in rows)
    source_number_exception_count = sum(
        row["selection"].get("published_dated_squad_number_order_exception_count", 0)
        for row in rows
    )
    return {
        "schema_version": SCHEMA,
        "policy": "source-only; exact historic Transfermarkt club IDs; reviewed domestic schedule codes; no PM99 write",
        "source": {
            "title": "Transfermarkt published 2015 domestic schedules and opening match reports",
            "repository": opening.BASE_URL,
            "source_tail_package_sha256": package_sha256,
            "domestic_competition_codes": {key: list(value) for key, value in sorted(DOMESTIC_COMPETITIONS.items())},
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "coverage": {
            "eligible_pinned_season_squad_count": len(selected),
            "capacity_complete_opening_order_count": len(rows),
            "gap_count": len(failures),
            "pinned_season_capacity_remainder_player_count": remainder_count,
            "published_dated_squad_number_order_exception_player_count": source_number_exception_count,
        },
        "clubs": rows,
        "gaps": failures,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tail-package", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument(
        "--source-squad-cache-root", required=True, type=Path,
        help="cached dated Transfermarkt squad receipt root; read-only and hash-checked",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source receipt: {args.output}")
    try:
        package, package_sha = _load(args.source_tail_package)
        result = capture(
            package=package,
            package_sha256=package_sha,
            cache=opening.SnapshotCache(args.cache_root, offline=args.offline, delay=args.delay),
            source_squad_cache_root=args.source_squad_cache_root,
        )
    except (OSError, OpeningOrderError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
