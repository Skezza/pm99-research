#!/usr/bin/env python3
"""Fill short 2015 tail squads from only their opening matchday window.

This is the second, deliberately narrower source route for the 2015
source-tail plan.  It is used only after the pinned ``saison_id/2015`` squad
page identified the exact club but did not expose enough player rows for its
immutable PM99 carrier.  It retains the first domestic league XI, then named
bench players and later early-fixture appearances in source order, stopping
once the fixed carrier is full.  It never draws on the rest of the season.

Like the other source stages it emits facts and receipts only; it cannot write
a PM99 database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_source_tail_squads_v1 as tail_squads  # noqa: E402
from scripts import capture_transfermarkt_lineup_person_evidence_v1 as profiles  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402
from scripts import supplement_2015_ntf_with_transfermarkt as squads  # noqa: E402


SCHEMA = "pm99-world-2015-source-tail-opening-squad-capture-v1"
PLAN_SCHEMA = "pm99-world-2015-source-tail-replacement-plan-v1"
TAIL_SQUAD_SCHEMA = "pm99-world-2015-source-tail-squad-capture-v1"

# These are fixed source identities, not search guesses.  The dated squad
# receipt established the club ID; the competition IDs were read from that
# club's own retained 2015 schedule.  Granitas remains outside this map: its
# Transfermarkt 2015 schedule does not publish a match list, so it remains an
# explicit source gap rather than being given a different club or season.
OPENING_FIXTURE_SCOPES: dict[int, dict[str, str | int]] = {
    1402: {"article_title": "FC Petrolul Ploiești", "club_id": 9465, "competition_code": "RO1", "slug": "petrolul-ploiesti"},
    1501: {"article_title": "PFC Beroe Stara Zagora", "club_id": 6764, "competition_code": "BU1", "slug": "beroe-stara-zagora"},
    1801: {"article_title": "CS Grevenmacher", "club_id": 2230, "competition_code": "LUX1", "slug": "cs-grevenmacher"},
    2053: {"article_title": "Aberystwyth Town F.C.", "club_id": 21541, "competition_code": "WAL1", "slug": "aberystwyth-town-fc"},
    2064: {"article_title": "The New Saints F.C.", "club_id": 10734, "competition_code": "WAL1", "slug": "the-new-saints-fc"},
}


class OpeningSquadError(ValueError):
    """An early-fixture squad source cannot be bound safely."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _load(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpeningSquadError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise OpeningSquadError(f"{label} must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def _target(assignment: Mapping[str, Any]) -> Mapping[str, Any]:
    value = assignment.get("proposed_target") or assignment.get("target_membership")
    if not isinstance(value, Mapping) or not isinstance(value.get("article_title"), str):
        raise OpeningSquadError("planned tail carrier has no target article title")
    return value


def _eligible_targets(*, plan: Mapping[str, Any], tail_squad_receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise OpeningSquadError("tail plan has an unsupported schema")
    if tail_squad_receipt.get("schema_version") != TAIL_SQUAD_SCHEMA:
        raise OpeningSquadError("tail squad receipt has an unsupported schema")
    assignments = plan.get("assignments")
    gaps = tail_squad_receipt.get("gaps")
    if not isinstance(assignments, list) or not isinstance(gaps, list):
        raise OpeningSquadError("tail plan or squad receipt has no rows")
    gap_ids = {int(row["carrier_id"]) for row in gaps if isinstance(row, Mapping) and isinstance(row.get("carrier_id"), int)}
    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        if not isinstance(assignment, Mapping) or not isinstance(assignment.get("carrier_id"), int):
            continue
        carrier_id = int(assignment["carrier_id"])
        scope = OPENING_FIXTURE_SCOPES.get(carrier_id)
        if scope is None:
            continue
        if carrier_id not in gap_ids:
            raise OpeningSquadError(f"opening-fixture scope {carrier_id} is no longer a tail squad gap")
        target = _target(assignment)
        if target["article_title"] != scope["article_title"]:
            raise OpeningSquadError(f"opening-fixture scope {carrier_id} targets a different club")
        capacity = assignment.get("fixed_roster_slot_count")
        if not isinstance(capacity, int) or capacity < 11:
            raise OpeningSquadError(f"opening-fixture scope {carrier_id} has invalid fixed capacity")
        rows.append({
            "assignment": assignment,
            "carrier_id": carrier_id,
            "capacity": capacity,
            "scope": scope,
            "target": target,
        })
    return sorted(rows, key=lambda row: row["carrier_id"])


def _opening_fixtures(
    *, ref: opening.TeamRef, competition_code: str, cache: opening.SnapshotCache
) -> list[dict[str, str]]:
    """Return only league fixtures through the August opening window."""

    slug = ref.club_path.split("/")[1]
    schedule_url = f"{opening.BASE_URL}/{slug}/spielplan/verein/{ref.club_id}/saison_id/2015"
    page = BeautifulSoup(
        cache.get(schedule_url, f"opening-squad/schedule/2015/{ref.club_id}.html"), "html.parser"
    )
    rows: list[dict[str, str]] = []
    for row in page.select("tr"):
        report = row.select_one('a[href*="/spielbericht/index/spielbericht/"]')
        competition = row.select_one('a[href*="/test/spieltag/wettbewerb/"]')
        if report is None or competition is None:
            continue
        competition_match = re.search(r"/wettbewerb/([^/]+)", str(competition.get("href") or ""))
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", row.get_text(" ", strip=True))
        report_match = re.search(r"/spielbericht/(\d+)", str(report.get("href") or ""))
        if not competition_match or not date_match or not report_match:
            continue
        if competition_match.group(1) != competition_code:
            continue
        fixture_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
        if fixture_date > date(2015, 8, 31):
            continue
        rows.append({
            "date": fixture_date.isoformat(),
            "match_id": report_match.group(1),
            "report_url": urljoin(opening.BASE_URL, str(report.get("href"))),
            "schedule_url": schedule_url,
        })
    if not rows:
        raise OpeningSquadError(
            f"{ref.source_club_name}: no {competition_code} fixture in the 2015 opening window"
        )
    return sorted(rows, key=lambda row: (row["date"], int(row["match_id"])))


def _ordered_lineup_players(lineups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """First XI, first bench, later XIs and benches, deduplicated by source ID."""

    ordered: list[dict[str, Any]] = []
    for lineup_index, lineup in enumerate(lineups):
        for role, values in (("starting-xi", lineup.get("starting_xi")), ("substitute", lineup.get("substitutes"))):
            if not isinstance(values, list):
                continue
            for row in values:
                if not isinstance(row, Mapping):
                    continue
                player_id = str(row.get("source_player_id") or "").strip()
                if not player_id or any(item["source_player_id"] == player_id for item in ordered):
                    continue
                ordered.append({
                    "source_player_id": player_id,
                    "display_name": str(row.get("display_name") or "").strip(),
                    "source_url": str(row.get("source_url") or "").strip(),
                    "source_position_group": row.get("source_position_group"),
                    "selection_role": role,
                    "source_match_id": str(lineup["source_match_id"]),
                    "source_fixture_date": str(lineup["first_league_fixture_date"]),
                    "source_lineup_url": str(lineup["lineup_source_url"]),
                })
    return ordered


def _broad_position(value: object) -> str | None:
    text = str(value or "").casefold()
    if "goal" in text or text == "g":
        return "G"
    if any(token in text for token in ("back", "defend", "sweeper", "stopper")) or text == "d":
        return "D"
    if any(token in text for token in ("midfield", "wing", "half")) or text == "m":
        return "M"
    if any(token in text for token in ("forward", "attack", "striker", "centre-forward")) or text == "f":
        return "F"
    return None


def _source_player(
    *, row: Mapping[str, Any], cache: opening.SnapshotCache
) -> dict[str, Any]:
    """Turn one source-lineup identity into a minimum safe roster fact row."""

    try:
        payload = cache.get(str(row["source_url"]), f"opening-squad/profile/{row['source_player_id']}.html")
        fact = profiles._profile_facts(payload, player=row)
    except (OSError, ValueError, opening.CaptureError, profiles.PersonEvidenceError) as exc:
        fact = {
            **row,
            "published_full_name": row["display_name"],
            "published_birth_date": None,
            "published_height_cm": None,
            "published_nationality_label": None,
            "published_profile_position": None,
            "profile_status": "source-qualified-with-explicit-gaps",
            "profile_blockers": [f"profile-unavailable:{exc}"],
        }
    position = _broad_position(fact.get("published_profile_position")) or _broad_position(row.get("source_position_group"))
    nationality_label = str(fact.get("published_nationality_label") or "").strip()
    nationality = tail_squads.NATIONALITY_CODES.get(nationality_label, "UNK")
    unresolved = ["shirt_number", "weight_kg"]
    if fact.get("published_birth_date") is None:
        unresolved.append("birth_date")
    if fact.get("published_height_cm") is None:
        unresolved.append("height_cm")
    if nationality == "UNK":
        unresolved.append("nationality_code")
    if position is None:
        unresolved.append("primary_position")
    return {
        "shirt_number": None,
        "name": str(fact.get("published_full_name") or row["display_name"]),
        "nationality": nationality,
        "position": position,
        "height_cm": fact.get("published_height_cm"),
        "weight_kg": None,
        "birth_date": fact.get("published_birth_date"),
        "unresolved_fields": unresolved,
        "opening_source": {
            "fixture_date": row["source_fixture_date"],
            "lineup_url": row["source_lineup_url"],
            "match_id": row["source_match_id"],
            "player_profile_url": row["source_url"],
            "player_source_id": row["source_player_id"],
            "selection_role": row["selection_role"],
        },
    }


def _pinned_squad_players(
    *, carrier_id: int, scope: Mapping[str, str | int], source_cache_root: Path | None
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    """Read the exact short squad snapshot as a same-club capacity supplement."""

    if source_cache_root is None:
        return [], None
    club_id = int(scope["club_id"])
    relative = Path("squads") / "squad" / "2015" / f"{carrier_id}-{club_id}.html"
    path = source_cache_root / relative
    if not path.is_file():
        raise OpeningSquadError(f"pinned-short-squad-cache-is-missing:{relative}")
    payload = path.read_bytes()
    return squads.parse_squad(payload), {
        "cache_path": relative.as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source_url": f"https://www.transfermarkt.com/{scope['slug']}/kader/verein/{club_id}/saison_id/2015",
    }


def _combined_capacity_players(
    *, opening_players: Sequence[dict[str, Any]], pinned_players: Sequence[dict[str, Any]], capacity: int
) -> list[dict[str, Any]]:
    """Keep opening evidence first, then only the same-club pinned rows."""

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for player in [*opening_players, *pinned_players]:
        key = tail_squads._normalise(str(player.get("name") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(dict(player))
        if len(selected) == capacity:
            break
    return selected


def capture(
    *,
    plan: Mapping[str, Any],
    tail_squad_receipt: Mapping[str, Any],
    cache: opening.SnapshotCache,
    tail_squad_cache_root: Path | None = None,
) -> dict[str, Any]:
    clubs: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for row in _eligible_targets(plan=plan, tail_squad_receipt=tail_squad_receipt):
        carrier_id, capacity, scope = row["carrier_id"], row["capacity"], row["scope"]
        ref = opening.TeamRef(
            source_club_name=str(scope["article_title"]),
            transfermarkt_name=str(scope["article_title"]),
            club_id=int(scope["club_id"]),
            club_path=f"/{scope['slug']}/startseite/verein/{scope['club_id']}",
            identity_match_method="documented-source-tail-transfermarkt-id-and-schedule-competition",
        )
        try:
            fixtures = _opening_fixtures(ref=ref, competition_code=str(scope["competition_code"]), cache=cache)
            lineups = [opening._lineup_from_report(ref, fixture, cache) for fixture in fixtures]
            candidates = _ordered_lineup_players(lineups)
            opening_players = [_source_player(row=candidate, cache=cache) for candidate in candidates]
            pinned_players, pinned_source = _pinned_squad_players(
                carrier_id=carrier_id,
                scope=scope,
                source_cache_root=tail_squad_cache_root,
            )
            players = _combined_capacity_players(
                opening_players=opening_players,
                pinned_players=pinned_players,
                capacity=capacity,
            )
            if len(players) < capacity:
                raise OpeningSquadError(
                    f"opening-window-plus-pinned-squad-short:{len(players)}/{capacity}; fixtures={len(fixtures)}"
                )
            if any(player["position"] is None for player in players):
                raise OpeningSquadError("opening-window-player-has-no-broad-position")
        except (OSError, ValueError, opening.CaptureError, OpeningSquadError) as exc:
            gaps.append({
                "carrier_id": carrier_id,
                "target_article_title": str(scope["article_title"]),
                "reason": str(exc),
            })
            continue
        first = lineups[0]
        clubs.append({
            "candidate_carrier_id": carrier_id,
            "fixed_roster_slot_count": capacity,
            "club_name": str(row["target"]["name"]),
            "target_article_title": str(scope["article_title"]),
            "target_article_path": str(row["target"]["article_path"]),
            "country_catalog": row["assignment"].get("family"),
            "competition_catalog": "transfermarkt-2015-source-tail-opening-window",
            "source_url": str(first["lineup_source_url"]),
            "source_season_label": "2015/16 plus 2015 calendar-year leagues",
            "players": players,
            "opening_fixture": {
                "date": first["first_league_fixture_date"],
                "formation": first["formation"],
                "manager": first["declared_manager"],
                "lineup_source_style": first["lineup_source_style"],
                "lineup_source_url": first["lineup_source_url"],
                "source_match_id": first["source_match_id"],
            },
            **({"pinned_same_club_squad_source": pinned_source} if pinned_source is not None else {}),
            "capture_note": (
                "Exact historical club and domestic competition ID; first XI then published bench and later "
                "opening-window league appearances, with only the same-club pinned historical squad allowed to "
                "fill a remaining immutable capacity"
            ),
        })
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; applies only to exact target clubs still short in the pinned historical squad receipt; "
            "first domestic XI, then bench and later appearances only through 2015-08-31; stops at fixed capacity; "
            "no whole-season roster, no different club, no PM99 write"
        ),
        "source": {
            "title": "Transfermarkt published opening schedules, match reports and player profiles",
            "repository": opening.BASE_URL,
            "cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "coverage": {
            "eligible_short_squad_count": len(_eligible_targets(plan=plan, tail_squad_receipt=tail_squad_receipt)),
            "capacity_complete_opening_squad_count": len(clubs),
            "gap_count": len(gaps),
        },
        "clubs": clubs,
        "gaps": gaps,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tail-squad-receipt", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--tail-squad-cache-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source receipt: {args.output}")
    try:
        plan, plan_sha = _load(args.plan, label="tail plan")
        tail_receipt, tail_sha = _load(args.tail_squad_receipt, label="tail squad receipt")
        result = capture(
            plan=plan,
            tail_squad_receipt=tail_receipt,
            cache=opening.SnapshotCache(args.cache_root, offline=args.offline, delay=args.delay),
            tail_squad_cache_root=args.tail_squad_cache_root,
        )
    except (OSError, OpeningSquadError, opening.CaptureError) as exc:
        parser.error(str(exc))
    result["source"]["tail_plan_sha256"] = plan_sha
    result["source"]["tail_squad_receipt_sha256"] = tail_sha
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
