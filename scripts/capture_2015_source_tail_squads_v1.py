#!/usr/bin/env python3
"""Capture exact historical squads for the approved 2015 source-tail plan.

The input plan has already proved target-season league membership and unique
carrier reservations.  This step adds the missing roster evidence by accepting
only an exact (or documented-name-alias) Transfermarkt search result, pinning
its ``saison_id/2015`` squad page, and checking immutable PM99 capacity.
It creates source facts only and cannot write a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_world_manager_transfermarkt_exact_search_v6 as search_v6  # noqa: E402
from scripts import capture_2015_world_manager_transfermarkt_snapshot_v5 as snapshot_v5  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402
from scripts import capture_footballsquads_season as footballsquads  # noqa: E402
from scripts import supplement_2015_ntf_with_transfermarkt as squads  # noqa: E402


SCHEMA = "pm99-world-2015-source-tail-squad-capture-v1"
PLAN_SCHEMA = "pm99-world-2015-source-tail-replacement-plan-v1"
TARGET_STATUSES = {
    "proposed-target-membership-club-awaiting-capacity-source",
    "retain-baseline-target-membership-awaiting-capacity-source",
    "retain-declared-target-club-needs-capacity-source",
}

# These are name changes only.  Each left-hand value is the exact club title
# reserved by the target-season membership receipt; each right-hand value is
# the one exact club display name returned by the cached Transfermarkt search.
# They are deliberately local to this 2015 source-tail capture rather than a
# general fuzzy-name rule.  In particular, youth/reserve results remain
# rejected even where they share part of a club's name.
DOCUMENTED_TRANSFERMARKT_DISPLAY_ALIASES: dict[str, tuple[str, ...]] = {
    "Aragua Fútbol Club": ("Aragua FC",),
    "Aberystwyth Town F.C.": ("Aberystwyth Town",),
    "Airbus UK Broughton F.C.": ("Airbus UK Broughton",),
    "Aldershot Town F.C.": ("Aldershot Town",),
    "Bala Town F.C.": ("Bala Town",),
    "Barcelona Sporting Club": ("Barcelona SC Guayaquil",),
    "Bangor City F.C.": ("Bangor City (- 2025)",),
    "Ballinamallard United F.C.": ("Ballinamallard United FC",),
    "Bohemians 1905": ("Bohemians Prague 1905",),
    "C.A. Peñarol": ("CA Peñarol",),
    "CS Concordia Chiajna": ("Concordia Chiajna",),
    "Club Bolívar": ("Bolívar La Paz",),
    "Club Nacional de Football": ("Club Nacional",),
    "Carmarthen Town A.F.C.": ("Carmarthen Town",),
    "Connah's Quay Nomads F.C.": ("Connah's Quay Nomads",),
    "Dover Athletic F.C.": ("Dover Athletic",),
    "FC Academia Chișinău": ("Academia Chisinau",),
    "FC Astra Giurgiu": ("Astra Giurgiu (- 2024)",),
    "FC Petrolul Ploiești": ("Petrolul Ploiesti",),
    "FK Borac Čačak": ("FK Borac 1926 Cacak",),
    "FK Atlantas": ("FK Atlantas Klaipeda (-2020)",),
    "FK DAC 1904 Dunajská Streda": ("DAC Dunajska Streda",),
    "FK Klaipėdos Granitas": ("FK Klaipedos Granitas (-2015)",),
    "FO ŽP Šport Podbrezová": ("Zeleziarne Podbrezova",),
    "Haverfordwest County F.C.": ("Haverfordwest County",),
    "Llandudno F.C.": ("Llandudno FC",),
    "Montevideo Wanderers F.C.": ("Montevideo Wanderers",),
    "Newtown A.F.C.": ("Newtown AFC",),
    "Oriente Petrolero": ("Club Deportivo Oriente Petrolero",),
    "PFC Beroe Stara Zagora": ("Beroe",),
    "Port Talbot Town F.C.": ("Port Talbot Town",),
    "Rhyl F.C.": ("Rhyl FC (- 2020)",),
    "The Strongest": ("Club The Strongest",),
    "The New Saints F.C.": ("The New Saints",),
    "Tranmere Rovers F.C.": ("Tranmere Rovers",),
}

# Transfermarkt's full-text index misses a number of punctuated, accented, or
# legal-name article titles.  These are the exact queries whose retained
# search snapshots produced the corresponding reviewed display aliases above.
# A different cache key makes it impossible to confuse such a query with the
# earlier title-as-query attempt.
DOCUMENTED_TRANSFERMARKT_SEARCH_QUERIES: dict[str, str] = {
    "Aberystwyth Town F.C.": "Aberystwyth Town",
    "Airbus UK Broughton F.C.": "Airbus UK",
    "Aldershot Town F.C.": "Aldershot Town",
    "Bala Town F.C.": "Bala Town",
    "Ballinamallard United F.C.": "Ballinamallard United",
    "Bangor City F.C.": "Bangor City",
    "C.A. Peñarol": "Penarol",
    "CS Concordia Chiajna": "Concordia Chiajna",
    "Carmarthen Town A.F.C.": "Carmarthen Town",
    "Connah's Quay Nomads F.C.": "Connah's Quay Nomads",
    "Dover Athletic F.C.": "Dover Athletic",
    "FC Academia Chișinău": "Academia Chisinau",
    "FC Astra Giurgiu": "Astra Giurgiu",
    "FC Petrolul Ploiești": "Petrolul Ploiesti",
    "FK Borac Čačak": "Borac Cacak",
    "FO ŽP Šport Podbrezová": "Podbrezova",
    "Haverfordwest County F.C.": "Haverfordwest County",
    "Llandudno F.C.": "Llandudno",
    "Montevideo Wanderers F.C.": "Montevideo Wanderers",
    "Newtown A.F.C.": "Newtown AFC",
    "Port Talbot Town F.C.": "Port Talbot Town",
    "Rhyl F.C.": "Rhyl",
    "The New Saints F.C.": "The New Saints",
    "Tranmere Rovers F.C.": "Tranmere Rovers",
}

# Search did not return this club because Transfermarkt records the historic
# 2015/16 side under its older NK Inker presentation.  The fixed ID is checked
# against the dated squad page before a roster can be accepted.  The evidence
# URL exposes the club's 2015/16 fixture history under both names.
PINNED_TRANSFERMARKT_CLUB_IDENTITIES: dict[str, dict[str, str | int]] = {
    "NK Inter Zaprešić": {
        "club_id": 918,
        "display_name": "NK Inker",
        "evidence_url": "https://www.transfermarkt.com/nk-inker/spielplan/verein/918/saison_id/2015/plus/1",
        "slug": "nk-inker",
    },
}

# An exact dated FootballSquads record is permitted only as a named fallback
# after Transfermarkt has identified the correct club but its page is short.
# This has no lookup or matching heuristic: each path, target, and season are
# checked on read.  It makes the exceptional source route reproducible while
# preserving the Transfermarkt attempt in the receipt.
FOOTBALLSQUADS_CAPACITY_FALLBACKS: dict[int, dict[str, str]] = {
    3331: {
        "expected_club_name": "Tranmere Rovers",
        "source_path": "eng/2015-2016/national/tranmere.txt",
    },
}


class SourceTailSquadError(ValueError):
    """An exact dated squad cannot be established for a planned carrier."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _normalise(value: object) -> str:
    return squads._normalise(str(value or ""))


def _target(assignment: Mapping[str, Any]) -> Mapping[str, Any]:
    target = assignment.get("proposed_target") or assignment.get("target_membership")
    if not isinstance(target, Mapping):
        raise SourceTailSquadError("planned carrier has no target-season club identity")
    if not all(isinstance(target.get(key), str) and target[key].strip() for key in ("name", "article_title", "article_path")):
        raise SourceTailSquadError("planned carrier has an incomplete target-season club identity")
    return target


def _accepted_search_identity(
    *, target_title: str, links: Sequence[tuple[str, str]]
) -> tuple[str, str, str]:
    """Accept exactly one Transfermarkt club matching this source title."""

    aliases = (
        *squads.SEARCH_ALIASES.get(target_title, ()),
        *search_v6.EXTRA_DOCUMENTED_ALIASES.get(target_title, ()),
        *DOCUMENTED_TRANSFERMARKT_DISPLAY_ALIASES.get(target_title, ()),
    )
    accepted = {_normalise(value) for value in (target_title, *aliases)}
    matches = [(name, href) for name, href in links if _normalise(name) in accepted]
    hrefs = {href for _name, href in matches}
    if len(hrefs) != 1:
        raise SourceTailSquadError("no-unique-exact-or-documented-alias-transfermarkt-club-result")
    name, href = next((item for item in matches if item[1] in hrefs))
    method = (
        "exact-normalised-transfermarkt-search-display-name"
        if _normalise(name) == _normalise(target_title)
        else "documented-historical-transfermarkt-search-alias"
    )
    return name, href, method


def _search_request(*, carrier_id: int, target_title: str) -> tuple[str, str, str]:
    """Return the source URL, immutable cache key, and reviewed query term."""

    query = DOCUMENTED_TRANSFERMARKT_SEARCH_QUERIES.get(target_title, target_title)
    url = f"{squads.BASE_URL}/schnellsuche/ergebnis/schnellsuche?{urlencode({'query': query})}"
    if query == target_title:
        return url, f"search/2015/{carrier_id}.html", query
    query_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    return url, f"search/2015/{carrier_id}-query-{query_digest}.html", query


def _pinned_transfermarkt_identity(target_title: str) -> Mapping[str, str | int] | None:
    """Return one reviewed direct historical club identity, if required."""

    identity = PINNED_TRANSFERMARKT_CLUB_IDENTITIES.get(target_title)
    if identity is None:
        return None
    expected = {"club_id", "display_name", "evidence_url", "slug"}
    if set(identity) != expected or not isinstance(identity["club_id"], int):
        raise SourceTailSquadError("pinned Transfermarkt identity configuration is malformed")
    if not all(isinstance(identity[key], str) and identity[key] for key in expected - {"club_id"}):
        raise SourceTailSquadError("pinned Transfermarkt identity configuration is malformed")
    return identity


def _footballsquads_fallback(
    *, carrier_id: int, fixed_capacity: int, source_root: Path | None
) -> dict[str, Any] | None:
    """Return a reviewed full dated source only for an explicit short-page case."""

    configured = FOOTBALLSQUADS_CAPACITY_FALLBACKS.get(carrier_id)
    if configured is None:
        return None
    if source_root is None:
        raise SourceTailSquadError("approved-footballsquads-capacity-fallback-requires-source-root")
    root = source_root.expanduser().resolve()
    path = root / configured["source_path"]
    if not path.is_file():
        raise SourceTailSquadError("approved-footballsquads-capacity-fallback-source-is-missing")
    try:
        record = footballsquads._read_club_file(
            path, root=root, season_start=2015, season_label="2015/16",
        )
    except footballsquads.CaptureError as exc:
        raise SourceTailSquadError(f"approved-footballsquads-capacity-fallback-is-invalid:{exc}") from exc
    if _normalise(record["club_name"]) != _normalise(configured["expected_club_name"]):
        raise SourceTailSquadError("approved-footballsquads-capacity-fallback-has-wrong-club")
    if len(record["players"]) < fixed_capacity:
        raise SourceTailSquadError(
            f"approved-footballsquads-capacity-fallback-is-short:{len(record['players'])}/{fixed_capacity}"
        )
    return record


def _capture_one(
    *,
    assignment: Mapping[str, Any],
    search_cache: opening.SnapshotCache,
    squad_cache: opening.SnapshotCache,
    footballsquads_source_root: Path | None,
) -> dict[str, Any]:
    carrier_id = int(assignment["carrier_id"])
    target = _target(assignment)
    title = str(target["article_title"])
    pinned_identity = _pinned_transfermarkt_identity(title)
    if pinned_identity is None:
        search_url, search_key, search_query = _search_request(
            carrier_id=carrier_id, target_title=title,
        )
        search_payload = search_cache.get(search_url, search_key)
        search_name, href, identity_method = _accepted_search_identity(
            target_title=title, links=squads.SearchParserLinks(search_payload),
        )
        slug, club_id = search_v6._club_from_search_href(href)
        identity_evidence_url = None
    else:
        search_url, search_query = str(pinned_identity["evidence_url"]), None
        search_name = str(pinned_identity["display_name"])
        slug, club_id = str(pinned_identity["slug"]), int(pinned_identity["club_id"])
        identity_method = "documented-pinned-transfermarkt-historic-club-id"
        identity_evidence_url = search_url
    squad_url = f"{squads.BASE_URL}/{slug}/kader/verein/{club_id}/saison_id/2015"
    squad_payload = squad_cache.get(squad_url, f"squad/2015/{carrier_id}-{club_id}.html")
    pinned_slug, pinned_id, pinned_url = snapshot_v5._pinned_identity(squad_payload)
    if pinned_id != club_id:
        raise SourceTailSquadError("historical-squad-club-id-does-not-match-accepted-search-result")
    players = squads.parse_squad(squad_payload)
    capacity = int(assignment["fixed_roster_slot_count"])
    fallback = None
    if len(players) < capacity:
        fallback = _footballsquads_fallback(
            carrier_id=carrier_id,
            fixed_capacity=capacity,
            source_root=footballsquads_source_root,
        )
        if fallback is None:
            raise SourceTailSquadError(f"pinned-2015-squad-short:{len(players)}/{capacity}")
        players = list(fallback["players"])
    return {
        "candidate_carrier_id": carrier_id,
        "candidate_baseline_name": assignment.get("baseline_name"),
        "fixed_roster_slot_count": capacity,
        "target_membership_status": assignment.get("status"),
        "country_catalog": assignment.get("family"),
        "competition_catalog": "transfermarkt-2015-source-tail",
        "club_name": target["name"],
        "target_article_title": title,
        "target_article_path": target["article_path"],
        "source_url": (
            pinned_url if fallback is None
            else f"https://github.com/footballcsv/cache.footballsquads/blob/HEAD/{fallback['source_path']}"
        ),
        "source_season_label": "2015" if fallback is None else "2015/16",
        "source_sha256": (
            hashlib.sha256(squad_payload).hexdigest()
            if fallback is None else str(fallback["source_sha256"])
        ),
        "players": players,
        "source_identity": {
            "search_url": search_url,
            "search_query": search_query,
            "search_display_name": search_name,
            "search_identity_method": identity_method,
            "transfermarkt_club_id": pinned_id,
            "transfermarkt_slug": pinned_slug,
            **({"identity_evidence_url": identity_evidence_url} if identity_evidence_url else {}),
        },
        **({
            "capacity_fallback": {
                "source_name": "footballcsv/cache.footballsquads",
                "source_path": fallback["source_path"],
                "source_sha256": fallback["source_sha256"],
                "source_season_label": "2015/16",
                "pinned_transfermarkt_attempt_url": pinned_url,
                "pinned_transfermarkt_player_count": len(squads.parse_squad(squad_payload)),
                "reason": "Transfermarkt exact historical squad was short; reviewed exact dated FootballSquads source fills immutable capacity",
            }
        } if fallback is not None else {}),
        "capture_note": "Exact target-membership club; pinned Transfermarkt 2015 squad; immutable carrier capacity satisfied; source facts only",
    }


def capture(
    *,
    plan: Mapping[str, Any],
    search_cache: opening.SnapshotCache,
    squad_cache: opening.SnapshotCache,
    footballsquads_source_root: Path | None = None,
) -> dict[str, Any]:
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise SourceTailSquadError("source-tail plan has an unsupported schema")
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise SourceTailSquadError("source-tail plan has no assignments")
    candidates = [row for row in assignments if isinstance(row, Mapping) and row.get("status") in TARGET_STATUSES]
    carrier_ids = [int(row["carrier_id"]) for row in candidates]
    if len(carrier_ids) != len(set(carrier_ids)):
        raise SourceTailSquadError("source-tail plan repeats a carrier")
    clubs: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for assignment in sorted(candidates, key=lambda row: int(row["carrier_id"])):
        try:
            clubs.append(_capture_one(
                assignment=assignment,
                search_cache=search_cache,
                squad_cache=squad_cache,
                footballsquads_source_root=footballsquads_source_root,
            ))
        except (OSError, ValueError, opening.CaptureError, SourceTailSquadError) as exc:
            gaps.append({
                "carrier_id": int(assignment["carrier_id"]),
                "baseline_name": assignment.get("baseline_name"),
                "target_membership_status": assignment.get("status"),
                "target_article_title": (_target(assignment).get("article_title") if assignment.get("proposed_target") or assignment.get("target_membership") else None),
                "reason": str(exc),
            })
    return {
        "schema_version": SCHEMA,
        "source": {
            "title": "Pinned historical squads for the 2015 source-tail plan",
            "repository": "Transfermarkt plus explicitly reviewed dated FootballSquads capacity fallbacks",
            "retrieved_on": date.today().isoformat(),
            "license": "public factual source; search URL, pinned URL and content hash retained",
        },
        "policy": (
            "source-only; only a target-season membership reservation from the input plan is attempted; "
            "exact Transfermarkt search display name or documented alias; pinned saison_id/2015 page; "
            "capacity must satisfy the immutable carrier; no current fallback and no PM99 write"
        ),
        "coverage": {
            "planned_target_count": len(candidates),
            "capacity_complete_squad_count": len(clubs),
            "gap_count": len(gaps),
            "gap_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "clubs": clubs,
        "gaps": gaps,
        "sources": {
            "search_cache_files": [search_cache.used[key] for key in sorted(search_cache.used)],
            "squad_cache_files": [squad_cache.used[key] for key in sorted(squad_cache.used)],
        },
    }


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceTailSquadError(f"cannot read source-tail plan: {path}") from exc
    if not isinstance(value, dict):
        raise SourceTailSquadError("source-tail plan must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--footballsquads-source-root", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source receipt: {args.output}")
    try:
        plan, plan_sha = _load(args.plan)
        result = capture(
            plan=plan,
            search_cache=opening.SnapshotCache(args.cache_root / "search", offline=args.offline, delay=args.delay),
            squad_cache=opening.SnapshotCache(args.cache_root / "squads", offline=args.offline, delay=args.delay),
            footballsquads_source_root=args.footballsquads_source_root,
        )
    except (OSError, SourceTailSquadError, opening.CaptureError) as exc:
        parser.error(str(exc))
    result["sources"]["source_tail_plan_sha256"] = plan_sha
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
