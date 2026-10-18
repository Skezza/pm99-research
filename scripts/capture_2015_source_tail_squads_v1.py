#!/usr/bin/env python3
"""Capture exact historical squads for the approved 2015 source-tail plan.

The input plan has already proved target-season league membership and unique
carrier reservations.  This step adds the missing roster evidence by accepting
only an exact (or documented-name-alias) Transfermarkt search result, pinning
the Transfermarkt selector that actually represents each target season, and
checking immutable PM99 capacity.
It creates source facts only and cannot write a database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_world_manager_transfermarkt_exact_search_v6 as search_v6  # noqa: E402
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

# The shared early source parser predates this all-country capture and only
# knows a small nationality table.  These are exact Transfermarkt image-title
# labels observed in this cached 2015 source set, translated to the PM99
# recipe codes already recognised by the compiler.  They repair a parser-map
# omission; they do not infer nationality from a name, club, or league.
NATIONALITY_CODES = {
    **squads.NATIONALITY_CODES,
    "Algeria": "ALG", "Angola": "ANG", "Antigua and Barbuda": "ATG", "Australia": "AUS", "Austria": "AUT",
    "Barbados": "BRB", "Belgium": "BEL", "Bosnia-Herzegovina": "BIH", "Cameroon": "CMR", "Canada": "CAN",
    "Cape Verde": "CPV", "Chad": "CHA", "Chile": "CHI", "China": "CHN", "Congo": "CGO",
    "Costa Rica": "CRC", "Cote d'Ivoire": "CIV", "Curacao": "CUW", "Czech Republic": "CZE",
    "Djibouti": "DJI", "DR Congo": "COD",
    "Egypt": "EGY", "Equatorial Guinea": "EQG", "Estonia": "EST", "Gabon": "GAB", "Gibraltar": "GIB", "Greece": "GRE", "Grenada": "GRN",
    "Guinea": "GUI", "Hungary": "HUN", "Iran": "IRN", "Iraq": "IRQ",
    "Honduras": "HON", "Ireland": "IRL", "Jamaica": "JAM", "Japan": "JPN", "Korea, South": "KOR",
    "Kosovo": "KSV", "Kyrgyzstan": "KGZ", "Lithuania": "LTU", "Luxembourg": "LUX",
    "Mali": "MLI", "Montserrat": "MSR", "Morocco": "MAR", "New Zealand": "NZL", "Northern Ireland": "NIR", "Panama": "PAN", "Poland": "POL",
    "Scotland": "SCO", "Senegal": "SEN", "Sierra Leone": "SLE", "South Africa": "RSA", "St. Kitts & Nevis": "SKN", "St. Lucia": "LCA",
    "Suriname": "SUR", "Sweden": "SWE", "Switzerland": "SUI", "Syria": "SYR", "Trinidad and Tobago": "TRI",
    "The Gambia": "GAM", "Tunisia": "TUN", "Türkiye": "TUR", "United States": "USA",
    "Uzbekistan": "UZB", "Vietnam": "VIE", "Yemen": "YEM", "Zambia": "ZAM",
}

# Transfermarkt's ``saison_id`` is a start-year selector for European seasons,
# but a *following calendar year* selector in these leagues.  The old blanket
# ``saison_id/2015`` rule therefore returned title-labelled 2016 squads here.
# Use the prior selector, which the source page itself labels 2015.  This is a
# source-calendar convention, not an editorial roster choice.
CALENDAR_YEAR_2015_SOURCE_SELECTOR_COUNTRIES = {
    "bolivia", "ecuador", "finland", "kazakhstan", "lithuania", "uruguay", "venezuela",
}

PINNED_SQUAD_URL_RE = re.compile(
    r"(?:https?:)?//(?:www\.)?transfermarkt\.[^/]+/([^/]+)/kader/verein/([1-9]\d*)/saison_id/(\d+)(?:[/?#\"']|$)",
    re.I,
)


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


def _restore_transfermarkt_nationalities(payload: bytes, players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restore published country labels dropped by the legacy squad parser.

    ``supplement_2015_ntf_with_transfermarkt.parse_squad`` safely parses the
    player table but maps an unknown nationality label straight to ``UNK``.
    Its parser still retains the exact label in the same cached table row, so
    recover it only by the parser's exact person key.  Conflicting duplicate
    source rows fail closed instead of selecting a nationality arbitrarily.
    """

    parser = squads.SquadParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    nationality_by_player: dict[str, str] = {}
    for row in parser.rows:
        name = str(row.get("player_name") or "").strip()
        images = row.get("images") or []
        label = str(images[3] if len(images) > 3 and images[3] is not None else "").strip()
        if not name or not label:
            continue
        key = squads._person_key(name)
        previous = nationality_by_player.setdefault(key, label)
        if previous != label:
            raise SourceTailSquadError(f"conflicting published nationalities for {name!r}")
    repaired: list[dict[str, Any]] = []
    for player in players:
        row = dict(player)
        if row.get("nationality") != "UNK":
            repaired.append(row)
            continue
        label = nationality_by_player.get(squads._person_key(str(row.get("name") or "")))
        code = NATIONALITY_CODES.get(label or "")
        if code is None:
            repaired.append(row)
            continue
        row["nationality"] = code
        row["unresolved_fields"] = [
            field for field in row.get("unresolved_fields") or [] if field != "nationality_code"
        ]
        repaired.append(row)
    return repaired


def _parse_transfermarkt_squad(payload: bytes) -> list[dict[str, Any]]:
    """Parse a dated squad without collapsing distinct same-named people.

    The inherited parser keys its result by normalised display name.  That is
    fine for its original supplementation job, but a historical roster can
    legitimately contain two Gustavo Fernándezes.  The published profile ID
    is the identity key here, so both source rows survive.
    """

    page = BeautifulSoup(payload, "html.parser")
    result: dict[str, dict[str, Any]] = {}
    for row in page.select("table.items > tbody > tr"):
        link = row.select_one('a[href*="/profil/spieler/"]')
        match = re.search(r"/profil/spieler/(\d+)", str(link.get("href") or "")) if link else None
        cells = row.find_all("td", recursive=False)
        name = link.get_text(" ", strip=True) if link is not None else ""
        if match is None or not name or len(cells) < 4:
            continue
        position = next(
            (parsed for cell in cells[1:] if (parsed := squads._position(cell.get_text(" ", strip=True))) is not None),
            None,
        )
        if position is None:
            continue
        number = cells[0].get_text(" ", strip=True)
        shirt_number = int(number) if number.isdigit() and 0 <= int(number) <= 99 else None
        nation_image = row.select_one("img.flaggenrahmen")
        nationality_label = str(
            nation_image.get("title") or nation_image.get("alt") or ""
        ).strip() if nation_image is not None else ""
        nationality = NATIONALITY_CODES.get(nationality_label, "UNK")
        unresolved = ["birth_date", "height_cm", "weight_kg"]
        if shirt_number is None:
            unresolved.append("shirt_number")
        if nationality == "UNK":
            unresolved.append("nationality_code")
        player = {
            "shirt_number": shirt_number,
            "name": name,
            "nationality": nationality,
            "position": position,
            "height_cm": None,
            "weight_kg": None,
            "birth_date": None,
            "unresolved_fields": unresolved,
            "source_player_id": match.group(1),
        }
        prior = result.get(match.group(1))
        if prior is not None and prior != player:
            raise SourceTailSquadError(f"conflicting source rows for Transfermarkt player {match.group(1)}")
        result[match.group(1)] = player
    if result:
        return [
            player
            for _source_id, player in sorted(
                result.items(), key=lambda item: (item[1]["position"], item[1]["name"], int(item[0]))
            )
        ]
    # Retain the tested legacy parser only for archived structural variants
    # that do not expose contemporary ``table.items > tbody > tr`` markup.
    return _restore_transfermarkt_nationalities(payload, squads.parse_squad(payload))


def _source_saison_id(assignment: Mapping[str, Any]) -> int:
    country = str(assignment.get("family") or "")
    return 2014 if country in CALENDAR_YEAR_2015_SOURCE_SELECTOR_COUNTRIES else 2015


def _squad_cache_key(*, carrier_id: int, club_id: int, source_saison_id: int) -> str:
    """Keep the legacy verified 2015 cache immutable; segregate corrections."""

    suffix = "" if source_saison_id == 2015 else f"-selector-{source_saison_id}"
    return f"squad/2015/{carrier_id}-{club_id}{suffix}.html"


def _pinned_squad_identity(payload: bytes, *, source_saison_id: int) -> tuple[str, int, str]:
    """Read one exact team identity from either reviewed historical selector."""

    matches = {
        (match.group(1), int(match.group(2)))
        for match in PINNED_SQUAD_URL_RE.finditer(payload.decode("utf-8", errors="replace"))
        if int(match.group(3)) == source_saison_id
    }
    if len(matches) != 1:
        raise SourceTailSquadError(
            f"pinned squad cache has {len(matches)} unique Transfermarkt club identities for selector {source_saison_id}"
        )
    slug, club_id = next(iter(matches))
    return slug, club_id, (
        f"https://www.transfermarkt.com/{slug}/kader/verein/{club_id}/saison_id/{source_saison_id}"
    )


def _capture_one(
    *,
    assignment: Mapping[str, Any],
    search_cache: opening.SnapshotCache,
    squad_cache: opening.SnapshotCache,
    footballsquads_source_root: Path | None,
) -> dict[str, Any]:
    carrier_id = int(assignment["carrier_id"])
    source_saison_id = _source_saison_id(assignment)
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
    squad_url = f"{squads.BASE_URL}/{slug}/kader/verein/{club_id}/saison_id/{source_saison_id}"
    squad_payload = squad_cache.get(
        squad_url,
        _squad_cache_key(
            carrier_id=carrier_id, club_id=club_id, source_saison_id=source_saison_id,
        ),
    )
    pinned_slug, pinned_id, pinned_url = _pinned_squad_identity(
        squad_payload, source_saison_id=source_saison_id,
    )
    if pinned_id != club_id:
        raise SourceTailSquadError("historical-squad-club-id-does-not-match-accepted-search-result")
    players = _parse_transfermarkt_squad(squad_payload)
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
        "source_season_label": (
            "2015-calendar" if fallback is None and source_saison_id == 2014
            else "2015/16"
        ),
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
            "transfermarkt_saison_id": source_saison_id,
            **({"identity_evidence_url": identity_evidence_url} if identity_evidence_url else {}),
        },
        **({
            "capacity_fallback": {
                "source_name": "footballcsv/cache.footballsquads",
                "source_path": fallback["source_path"],
                "source_sha256": fallback["source_sha256"],
                "source_season_label": "2015/16",
                "pinned_transfermarkt_attempt_url": pinned_url,
                "pinned_transfermarkt_player_count": len(_parse_transfermarkt_squad(squad_payload)),
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
            "exact Transfermarkt search display name or documented alias; pinned reviewed historical "
            "Transfermarkt selector (2014 for declared calendar-year leagues, otherwise 2015); "
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
