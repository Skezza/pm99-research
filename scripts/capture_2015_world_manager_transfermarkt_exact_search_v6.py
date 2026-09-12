#!/usr/bin/env python3
"""Extend the 2015 manager evidence with exact historical Transfermarkt links.

This pass retries only clubs still unresolved after the pinned-squad V5 pass.
It is intentionally limited to the original source-candidate carriers and
accepts a Transfermarkt search result only when its display name is an exact
normalised match for the declared club name or a pre-existing documented
historical alias.  It then pins the returned club's ``saison_id/2015`` squad
page and reads its manager history at 2015-09-01.

It is source-only and fail-closed.  A search ambiguity, historical-squad
failure, manager-tenure ambiguity or non-PM99 display spelling becomes a
receipt gap; it does not select a current/native manager or alter a database.
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

from scripts import capture_2015_world_manager_transfermarkt_snapshot_v5 as v5
from scripts import capture_opening_manager_history_supplements_v1 as history
from scripts import capture_transfermarkt_opening_lineups_v1 as opening
from scripts import supplement_2015_ntf_with_transfermarkt as squads


SCHEMA = "pm99-world-2015-transfermarkt-exact-search-manager-history-v6"

# These are reviewed 2015 first-team display-name variants observed in the
# immutable search snapshots written by this command.  They are deliberately
# carrier-specific through the declared source club name: no similarity score
# or country-crossing name match is allowed.  Ambiguous results (for example
# Argentina's Arsenal) remain gaps rather than being added here.
EXTRA_DOCUMENTED_ALIASES: dict[str, tuple[str, ...]] = {
    "Partizan Beograd": ("FK Partizan Belgrade",),
    "Lugano": ("FC Lugano",), "Luzern": ("FC Luzern",),
    "SV Mattersburg": ("SV Mattersburg (-2020)",),
    "Rosenborg": ("Rosenborg BK",), "Aalesund": ("Aalesunds FK",),
    "Lillestrøm": ("Lillestrøm SK",), "Vålerenga": ("Vålerenga Fotball Elite",),
    "Diósgyor": ("Diósgyőri VTK",), "MTK": ("MTK Budapest",),
    "Újpest": ("Újpest FC",), "Videoton": ("Videoton FC Fehérvár",),
    "Dundalk": ("Dundalk FC",), "Cork City": ("Cork City FC",),
    "Bohemians": ("Bohemian Football Club",), "Drogheda United": ("Drogheda United FC",),
    "Limerick": ("Limerick FC",), "Galway United": ("Galway United FC",),
    "Longford Town": ("Longford Town FC",), "Žalgiris Vilnius": ("FK Zalgiris Vilnius",),
    "Flamengo": ("CR Flamengo",), "Palmeiras": ("Sociedade Esportiva Palmeiras",),
    "Grêmio": ("Grêmio Foot-Ball Porto Alegrense",),
    "Corinthians": ("Sport Club Corinthians Paulista",),
    "Cruzeiro": ("Cruzeiro Esporte Clube",), "Colo-Colo": ("CSD Colo-Colo",),
    "Altrincham": ("Altrincham FC",), "Guiseley": ("Guiseley AFC",),
    "Gateshead": ("Gateshead FC",), "Eastleigh": ("Eastleigh FC",),
    "Wrexham": ("Wrexham AFC",), "Southport": ("Southport FC",),
    "Boreham Wood": ("Boreham Wood FC",), "Macclesfield Town": ("Macclesfield Town (- 2020)",),
    "Woking": ("Woking FC",), "San Lorenzo": ("CA San Lorenzo de Almagro",),
    "Crucero del Norte": ("CM Crucero del Norte",), "Lanús": ("CA Lanús",),
    "Rosario Central": ("CA Rosario Central",), "Atlético Rafaela": ("AMSD Atlético de Rafaela",),
    "Independiente": ("CA Independiente",), "Huracán": ("CA Huracán",),
    "Vélez Sarsfield": ("CA Vélez Sarsfield",), "Argentinos Juniors": ("AA Argentinos Juniors",),
    "Quilmes": ("Quilmes AC",),
}

# PM99 names are CP1252.  These two manager-history display names are Latin
# but contain Central-European letters outside that code page.  The retained
# form is an explicit source-linked Latin spelling, never automatic character
# loss; the original published display name remains in the receipt.
DOCUMENTED_PM99_LATIN_MANAGER_SPELLINGS = {
    (1704, "Balázs Bekő"): "Balazs Beko",
    (1709, "Tamás Pető"): "Tamas Peto",
}


class ExactSearchManagerError(ValueError):
    """The strict search source could not establish one historical manager."""


def canonical_json_bytes(value: Any) -> bytes:
    return v5.canonical_json_bytes(value)


def _normalise(value: object) -> str:
    return squads._normalise(str(value or ""))


def _accepted_search_identity(club_name: str, links: Sequence[tuple[str, str]]) -> tuple[str, str, str]:
    """Return one exact/pre-reviewed-alias Transfermarkt search result."""

    aliases = (*squads.SEARCH_ALIASES.get(club_name, ()), *EXTRA_DOCUMENTED_ALIASES.get(club_name, ()))
    accepted = {_normalise(value) for value in (club_name, *aliases)}
    matches = [(name, href) for name, href in links if _normalise(name) in accepted]
    unique = {(name, href) for name, href in matches}
    hrefs = {href for _name, href in unique}
    if len(hrefs) != 1:
        raise ExactSearchManagerError("no-unique-exact-or-documented-alias-transfermarkt-club-result")
    name, href = next(iter(unique))
    method = (
        "exact-normalised-transfermarkt-search-display-name"
        if _normalise(name) == _normalise(club_name)
        else "documented-historical-transfermarkt-search-alias"
    )
    return name, href, method


def _club_from_search_href(href: str) -> tuple[str, int]:
    parts = href.strip("/").split("/")
    try:
        slug, lane, _label, raw_id = parts[-4:]
        club_id = int(raw_id)
    except (IndexError, ValueError) as exc:
        raise ExactSearchManagerError("malformed-transfermarkt-club-search-result") from exc
    if lane != "startseite" or not slug or club_id <= 0:
        raise ExactSearchManagerError("malformed-transfermarkt-club-search-result")
    return slug, club_id


def _pm99_manager_name(carrier_id: int, published_name: str) -> tuple[str, str]:
    if v5._safe_manager_name(published_name):
        return published_name, "published-transfermarkt-display-name"
    spelling = DOCUMENTED_PM99_LATIN_MANAGER_SPELLINGS.get((carrier_id, published_name))
    if spelling and v5._safe_manager_name(spelling):
        return spelling, "documented-pm99-latin-spelling-for-published-transfermarkt-name"
    raise ExactSearchManagerError("published manager display name requires a reviewed PM99 Latin spelling")


def _prior_attempted_carriers(prior: Mapping[str, Any], *, candidate_sha: str, wikipedia_sha: str) -> set[int]:
    if prior.get("schema_version") != v5.SCHEMA:
        raise ExactSearchManagerError("prior pinned-squad manager receipt has an unsupported schema")
    sources = prior.get("sources")
    if not isinstance(sources, Mapping):
        raise ExactSearchManagerError("prior pinned-squad manager receipt has no source binding")
    if sources.get("source_candidate_sha256") != candidate_sha:
        raise ExactSearchManagerError("prior pinned-squad manager receipt targets a different source candidate")
    if sources.get("multilingual_wikipedia_history_sha256") != wikipedia_sha:
        raise ExactSearchManagerError("prior pinned-squad manager receipt targets a different Wikipedia receipt")
    result: set[int] = set()
    for key in ("rows", "gaps"):
        values = prior.get(key)
        if not isinstance(values, list):
            raise ExactSearchManagerError("prior pinned-squad manager receipt has no rows or gaps")
        for row in values:
            if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
                raise ExactSearchManagerError("prior pinned-squad manager receipt has a malformed row")
            result.add(int(row["carrier_id"]))
    return result


def capture(
    *,
    candidate: Mapping[str, Any],
    candidate_sha: str,
    multilingual_history: Mapping[str, Any],
    multilingual_history_sha: str,
    prior_snapshot_history: Mapping[str, Any],
    search_cache: opening.SnapshotCache,
    historical_squad_cache: opening.SnapshotCache,
    manager_history_cache: opening.SnapshotCache,
) -> dict[str, Any]:
    candidates = v5._candidate_index(candidate)
    unresolved = v5._unresolved_scope(multilingual_history, candidate_sha256=candidate_sha)
    prior = _prior_attempted_carriers(
        prior_snapshot_history, candidate_sha=candidate_sha, wikipedia_sha=multilingual_history_sha,
    )
    target_ids = sorted((set(unresolved) - prior) & set(candidates))
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for carrier_id in target_ids:
        draft = candidates[carrier_id]
        club = draft["club"]
        selector = club["source_selector"]
        club_name = str(club.get("source_club_name") or selector["club_name"])
        try:
            search_term = squads.SEARCH_QUERIES.get(club_name, club_name)
            search_url = f"{squads.BASE_URL}/schnellsuche/ergebnis/schnellsuche?{urlencode({'query': search_term})}"
            search_payload = search_cache.get(search_url, f"search/2015/{carrier_id}.html")
            search_name, href, identity_method = _accepted_search_identity(
                club_name, squads.SearchParserLinks(search_payload),
            )
            slug, search_club_id = _club_from_search_href(href)
            squad_url = f"{squads.BASE_URL}/{slug}/kader/verein/{search_club_id}/saison_id/2015"
            squad_key = f"squad/2015/{carrier_id}-{search_club_id}.html"
            squad_payload = historical_squad_cache.get(squad_url, squad_key)
            pinned_slug, pinned_club_id, pinned_squad_url = v5._pinned_identity(squad_payload)
            if pinned_club_id != search_club_id:
                raise ExactSearchManagerError("historical-squad-club-id-does-not-match-accepted-search-result")
            manager_url = f"{opening.BASE_URL}/{pinned_slug}/mitarbeiterhistorie/verein/{pinned_club_id}"
            manager_key = f"manager-history/2015-exact-search/{pinned_club_id}.html"
            manager_payload = manager_history_cache.get(manager_url, manager_key)
            published_manager_name, manager_id = history.manager_at_date(manager_payload, v5.AS_OF)
            manager_name, spelling_method = _pm99_manager_name(carrier_id, published_manager_name)
            rows.append({
                "carrier_id": carrier_id,
                "source_club_name": club_name,
                "source_selector": {
                    key: str(selector[key]) for key in ("country_catalog", "competition_catalog", "club_name")
                },
                "snapshot_as_of": v5.AS_OF.isoformat(),
                "manager_name": manager_name,
                "published_manager_name": published_manager_name,
                "pm99_spelling_method": spelling_method,
                "source_name": "Transfermarkt published club manager history",
                "source_url": manager_url,
                "source_snapshot_sha256": manager_history_cache.used[manager_key]["sha256"],
                "pinned_2015_squad": {
                    "source_url": pinned_squad_url,
                    "source_snapshot_sha256": hashlib.sha256(squad_payload).hexdigest(),
                    "cache_path": squad_key,
                    "transfermarkt_club_id": pinned_club_id,
                    "search_url": search_url,
                    "search_display_name": search_name,
                    "search_identity_method": identity_method,
                },
                "reason": (
                    f"manager id {manager_id} uniquely covers the fixed 2015-09-01 "
                    "early-season snapshot for the exact or documented-alias Transfermarkt club result"
                ),
            })
        except (OSError, ValueError, history.ManagerHistoryError, opening.CaptureError, ExactSearchManagerError) as exc:
            gaps.append({"carrier_id": carrier_id, "source_club_name": club_name, "reason": str(exc)})

    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; retries only explicitly unresolved multilingual-Wikipedia carriers not attempted by "
            "pinned-squad V5; exact normalised Transfermarkt search name or documented historical alias only; "
            "pinned historical 2015 squad page; manager tenure uniquely covering 2015-09-01; "
            "no current/native fallback; no PM99 write"
        ),
        "sources": {
            "source_candidate_sha256": candidate_sha,
            "multilingual_wikipedia_history_sha256": multilingual_history_sha,
            "prior_pinned_squad_history_schema": str(prior_snapshot_history.get("schema_version")),
            "prior_attempted_carrier_count": len(prior),
            "search_cache_files": [search_cache.used[key] for key in sorted(search_cache.used)],
            "historical_squad_cache_files": [
                historical_squad_cache.used[key] for key in sorted(historical_squad_cache.used)
            ],
            "manager_history_cache_files": [
                manager_history_cache.used[key] for key in sorted(manager_history_cache.used)
            ],
        },
        "coverage": {
            "early_season_snapshot": v5.AS_OF.isoformat(),
            "multilingual_wikipedia_unresolved_carrier_count": len(unresolved),
            "prior_attempted_carrier_count": len(prior),
            "strict_search_candidate_count": len(target_ids),
            "dated_transfermarkt_manager_match_count": len(rows),
            "unresolved_strict_search_candidate_count": len(gaps),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": rows,
        "gaps": gaps,
    }


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExactSearchManagerError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ExactSearchManagerError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-candidate", required=True, type=Path)
    parser.add_argument("--multilingual-wikipedia-history", required=True, type=Path)
    parser.add_argument("--prior-pinned-squad-history", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ExactSearchManagerError(f"refusing to overwrite source receipt: {args.output}")
        candidate, candidate_sha = _load(args.source_candidate, "source candidate")
        multilingual, multilingual_sha = _load(
            args.multilingual_wikipedia_history, "multilingual Wikipedia history",
        )
        prior, _prior_sha = _load(args.prior_pinned_squad_history, "prior pinned-squad manager history")
        result = capture(
            candidate=candidate, candidate_sha=candidate_sha,
            multilingual_history=multilingual, multilingual_history_sha=multilingual_sha,
            prior_snapshot_history=prior,
            search_cache=opening.SnapshotCache(args.cache_root / "search", offline=args.offline, delay=args.delay),
            historical_squad_cache=opening.SnapshotCache(args.cache_root / "squads", offline=args.offline, delay=args.delay),
            manager_history_cache=opening.SnapshotCache(args.cache_root / "manager-history", offline=args.offline, delay=args.delay),
        )
    except (OSError, ExactSearchManagerError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
