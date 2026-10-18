#!/usr/bin/env python3
"""Capture missing 2015/16 player facts from exact-title Wikipedia pages.

The current world recipe contains many players whose dated squad identity is
known but whose secondary facts were left as native values.  This command is
a bounded, polite source stage, not a database writer.  It asks the MediaWiki
API only for an *exact title equal to the declared source name*, caches every
batch response, and emits only parsed, plausible fields that were absent in
the input package.  A title mismatch, disambiguation or incomplete infobox is
a recorded gap, never a fuzzy identity match.

It intentionally ignores rows without ``source_name``.  Those are not safe
Wikipedia lookup targets: a native player name is not proof that the player
belongs to the target-season squad.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_2015_world_manager_history_v2 as wikipedia  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402
from scripts import prepare_2015_world_fifa16_drafts as fifa  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-world-2015-wikipedia-player-facts-v1"
API = "https://en.wikipedia.org/w/api.php"
FACT_FIELDS = ("birth_date", "nationality", "height_cm", "weight_kg")

# Wikipedia commonly writes a demonym rather than a country link in old
# football infoboxes.  This small table covers only unambiguous English
# demonyms; anything else stays in the receipt gap queue.
DEMONYM_TO_PM99 = {
    "albanian": "ALB", "algerian": "ALG", "argentine": "ARG", "austrian": "AUT",
    "belgian": "BEL", "brazilian": "BRA", "bulgarian": "BUL", "cameroonian": "CMR",
    "canadian": "CAN", "chilean": "CHI", "colombian": "COL", "croatian": "CRO",
    "czech": "CZE", "danish": "DEN", "ecuadorean": "ECU", "ecuadorian": "ECU",
    "english": "ENG", "estonian": "EST", "finnish": "FIN", "french": "FRA",
    "german": "GER", "ghanaian": "GHA", "greek": "GRE", "hungarian": "HUN",
    "icelandic": "ISL", "iranian": "IRN", "irish": "IRL", "israeli": "ISR",
    "italian": "ITA", "jamaican": "JAM", "japanese": "JPN", "latvian": "LVA",
    "lithuanian": "LTU", "mexican": "MEX", "moldovan": "MDA", "montenegrin": "MNE",
    "moroccan": "MAR", "dutch": "NED", "nigerian": "NGA", "norwegian": "NOR",
    "paraguayan": "PAR", "peruvian": "PER", "polish": "POL", "portuguese": "POR",
    "romanian": "ROU", "russian": "RUS", "scottish": "SCO", "senegalese": "SEN",
    "serbian": "SRB", "slovak": "SVK", "slovenian": "SVN", "south african": "RSA",
    "spanish": "ESP", "swedish": "SWE", "swiss": "SUI", "tunisian": "TUN",
    "turkish": "TUR", "ukrainian": "UKR", "uruguayan": "URU", "venezuelan": "VEN",
    "welsh": "WAL", "american": "USA", "ivorian": "CIV", "curacaoan": "CUW",
}


class PlayerFactCaptureError(ValueError):
    """A source package or cached API response violates the fact contract."""


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char.casefold() for char in text if char.isalnum())


def canonical_json_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _missing_fields(player: Mapping[str, Any]) -> tuple[str, ...]:
    facts = player.get("facts")
    if not isinstance(facts, Mapping):
        raise PlayerFactCaptureError(f"player {player.get('id')!r} has no facts object")
    return tuple(field for field in FACT_FIELDS if facts.get(field) is None or isinstance(facts.get(field), Mapping))


def _targets(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    players = package.get("players")
    if not isinstance(players, list):
        raise PlayerFactCaptureError("package has no player list")
    rows: list[dict[str, Any]] = []
    for player in players:
        if not isinstance(player, Mapping):
            raise PlayerFactCaptureError("package player list contains a malformed row")
        source_name = " ".join(str(player.get("source_name") or "").split())
        missing = _missing_fields(player)
        if not missing or not source_name:
            continue
        player_id = player.get("id")
        if not isinstance(player_id, str):
            raise PlayerFactCaptureError("package player has no stable id")
        rows.append({
            "player_id": player_id,
            "carrier_id": int(player.get("carrier_id") or 0),
            "player_name": str(player.get("name") or ""),
            "source_name": source_name,
            "missing_fields": list(missing),
        })
    return sorted(rows, key=lambda row: (str(row["source_name"]), str(row["player_id"])))


def _identity_gaps(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    """List missing-fact rows that cannot safely be looked up by person name.

    These are preserved mode-1 rows without a dated source-person identity.
    They need a squad-source repair before a public biography lookup; this
    queue makes that dependency visible instead of treating the inherited
    display name as evidence.
    """
    rows: list[dict[str, Any]] = []
    for player in package.get("players") or []:
        if not isinstance(player, Mapping):
            continue
        missing = _missing_fields(player)
        if not missing or str(player.get("source_name") or "").strip():
            continue
        rows.append({
            "player_id": str(player.get("id") or ""),
            "carrier_id": int(player.get("carrier_id") or 0),
            "player_name": str(player.get("name") or ""),
            "missing_fields": list(missing),
            "reason": "no-dated-target-season-source-name; do-not-query-inherited-pm99-name",
        })
    return sorted(rows, key=lambda row: str(row["player_id"]))


def _balanced_infobox(content: str) -> str | None:
    for match in re.finditer(r"{{\s*Infobox\b", content, re.I):
        found = wikipedia._balanced_template(content, match.start())
        if found is not None:
            return found
    return None


def _parameter(content: str, *names: str) -> str | None:
    template = _balanced_infobox(content)
    return wikipedia._top_level_parameter(template or "", {name.casefold() for name in names})


def _birth_date(raw: str | None) -> str | None:
    value = str(raw or "")
    # The supported values are ``{{birth date...|YYYY|MM|DD...}}`` and the
    # much less common ISO literal.  Other prose is intentionally not parsed.
    match = re.search(r"(?:birth[ _]date[^|{}]*|birth date[^|{}]*)\|\s*((?:19|20)\d{2})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", value, re.I)
    if match is None:
        match = re.search(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b", value)
    if match is None:
        return None
    try:
        result = dt.date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:
        return None
    return result


def _nationality(raw: str | None) -> str | None:
    value = wikipedia._clean_wikitext(str(raw or ""))
    value = re.sub(r"\s*\([^)]*\)", "", value).strip().casefold()
    value = " ".join(value.split())
    if "/" in value or "," in value or " and " in value:
        return None
    pm99 = fifa.FIFA_NATIONALITY_TO_PM99.get(value)
    if pm99 is not None:
        return pm99
    return DEMONYM_TO_PM99.get(value)


def _height_cm(raw: str | None) -> int | None:
    value = wikipedia._clean_wikitext(str(raw or ""))
    centimetres = re.search(r"\b(1[4-9]\d|2[01]\d)\s*cm\b", value, re.I)
    if centimetres is not None:
        return int(centimetres.group(1))
    metres = re.search(r"\b([12][.,]\d{1,2})\s*m(?:\b|$)", value, re.I)
    if metres is None:
        return None
    result = round(float(metres.group(1).replace(",", ".")) * 100)
    return result if 140 <= result <= 220 else None


def _weight_kg(raw: str | None) -> int | None:
    value = wikipedia._clean_wikitext(str(raw or ""))
    match = re.search(r"\b(4\d|[5-9]\d|1[0-2]\d|130)\s*kg\b", value, re.I)
    return int(match.group(1)) if match is not None else None


def _facts(content: str) -> dict[str, Any]:
    return {
        "birth_date": _birth_date(_parameter(content, "birth_date", "birth date")),
        "nationality": _nationality(_parameter(content, "nationality")),
        "height_cm": _height_cm(_parameter(content, "height")),
        "weight_kg": _weight_kg(_parameter(content, "weight")),
    }


def _fetch_batches(*, titles: list[str], cache: opening.SnapshotCache, batch_size: int,
                   title_offset: int) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    # The revisions API accepts a bounded set of titles in one request.  This
    # is deliberately capped at ten by the CLI: it lowers request volume while
    # keeping the response small enough to cache and to retry politely.  It is
    # not a parallel scrape and SnapshotCache still sleeps between cache misses.
    for batch_number, start in enumerate(range(0, len(titles), batch_size), start=1):
        batch = titles[start : start + batch_size]
        query = {
            "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
            # Deliberately omit rvlimit. MediaWiki permits a multi-title
            # revision-content request only with its default one revision per
            # page; passing the explicit single-page rvlimit parameter causes
            # an ``invalidparammix`` response.
            "prop": "revisions", "rvprop": "ids|timestamp|content", "rvslots": "main",
            "titles": "|".join(batch),
        }
        url = f"{API}?{urlencode(query)}"
        # Include the exact query digest.  An older one-title cache must never
        # be mistaken for a newer multi-title request at the same offset, and
        # a resumable run must never replay a different title set.
        key = (
            f"pages/{title_offset + start + 1:04d}-"
            f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}.json"
        )
        payload = cache.get(url, key)
        try:
            document = json.loads(payload.decode("utf-8"))
            response_pages = document["query"]["pages"]
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlayerFactCaptureError("Wikipedia response has no query pages") from exc
        if not isinstance(response_pages, list):
            raise PlayerFactCaptureError("Wikipedia response pages is not a list")
        for page in response_pages:
            if not isinstance(page, Mapping) or page.get("missing"):
                continue
            title = str(page.get("title") or "")
            revisions = page.get("revisions")
            if not title or not isinstance(revisions, list) or len(revisions) != 1:
                continue
            revision = revisions[0]
            content = ((revision.get("slots") or {}).get("main") or {}).get("content")
            if not isinstance(content, str):
                continue
            pages[_normalise(title.split("(", 1)[0].strip())] = {
                "title": title, "pageid": page.get("pageid"), "revid": revision.get("revid"),
                "timestamp": revision.get("timestamp"), "content": content,
                "cache_path": key, "cache_sha256": cache.used[key]["sha256"],
            }
    return pages


def capture(*, package: Mapping[str, Any], package_sha256: str,
            cache: opening.SnapshotCache, batch_size: int, limit: int | None,
            offset: int = 0) -> dict[str, Any]:
    all_targets = _targets(package)
    targets = all_targets[offset:]
    identity_gaps = _identity_gaps(package)
    if limit is not None:
        targets = targets[:limit]
    titles = sorted({str(row["source_name"]) for row in targets})
    pages = _fetch_batches(
        titles=titles, cache=cache, batch_size=batch_size, title_offset=offset,
    )
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for target in targets:
        key = _normalise(target["source_name"])
        page = pages.get(key)
        if page is None:
            gaps.append({**target, "reason": "no-exact-wikipedia-title-page"})
            continue
        found = _facts(str(page["content"]))
        facts = {field: found[field] for field in target["missing_fields"] if found.get(field) is not None}
        if not facts:
            gaps.append({**target, "reason": "exact-wikipedia-page-has-none-of-the-missing-facts", "source_page_title": page["title"]})
            continue
        rows.append({
            **target,
            "facts": facts,
            "source_name": "English Wikipedia current player-page revision",
            "source_url": f"https://en.wikipedia.org/w/index.php?title={quote(str(page['title']).replace(' ', '_'))}&oldid={page['revid']}",
            "source_page_title": page["title"],
            "source_page_id": page["pageid"],
            "source_revision_id": page["revid"],
            "source_revision_timestamp": page["timestamp"],
            "source_snapshot_sha256": page["cache_sha256"],
            "source_cache_path": page["cache_path"],
        })
    missing_after = Counter(
        field for target in targets for field in target["missing_fields"]
    )
    sourced = Counter(field for row in rows for field in row["facts"])
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; players with declared source_name only; exact normalised Wikipedia title "
            "only; current revision cached in batches; fill absent fields only; no fuzzy identity, "
            "no native-name inference and no PM99 binary write"
        ),
        "sources": {
            "base_package_sha256": package_sha256,
            "wikipedia_cache_files": [cache.used[key] for key in sorted(cache.used)],
        },
        "coverage": {
            "source_named_player_with_missing_facts_count": len(all_targets),
            "selected_source_named_player_count": len(targets),
            "missing-fact-player-without-dated-source-name-count": len(identity_gaps),
            "unique_exact_title_request_count": len(titles),
            "player_rows_with_at_least_one_sourced_fact": len(rows),
            "player_rows_unresolved_or_partial": len(gaps),
            "missing_field_counts_before": dict(sorted(missing_after.items())),
            "sourced_field_counts": dict(sorted(sourced.items())),
            "unresolved_reason_counts": dict(sorted(Counter(row["reason"] for row in gaps).items())),
        },
        "rows": sorted(rows, key=lambda row: str(row["player_id"])),
        "gaps": sorted(gaps, key=lambda row: str(row["player_id"])),
        "identity_gaps": identity_gaps,
        "selection": {"offset": offset, "limit": limit},
    }


def _load_package(path: Path) -> tuple[dict[str, Any], str]:
    try:
        value = package_v2.read_canonical_package(path)
        package_v2.validate_package(value)
    except (OSError, package_v2.PackageValidationError) as exc:
        raise PlayerFactCaptureError(f"cannot use package: {exc}") from exc
    raw = path.read_bytes()
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--limit", type=int, help="safe smoke-run cap; omit to capture every exact source-name target")
    parser.add_argument("--offset", type=int, default=0, help="stable source-name offset for a resumable bounded pass")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise PlayerFactCaptureError(f"refusing to overwrite source receipt: {args.output}")
        if not 1 <= args.batch_size <= 10:
            raise PlayerFactCaptureError(
                "batch size must be between 1 and 10 so historical source requests remain polite"
            )
        if args.limit is not None and args.limit <= 0:
            raise PlayerFactCaptureError("limit must be positive")
        if args.offset < 0:
            raise PlayerFactCaptureError("offset must not be negative")
        package, package_sha256 = _load_package(args.package)
        result = capture(
            package=package, package_sha256=package_sha256,
            cache=opening.SnapshotCache(
                args.cache_root, offline=args.offline, delay=args.delay,
                validator=lambda payload, _url: json.loads(payload.decode("utf-8")),
            ),
            batch_size=args.batch_size, limit=args.limit, offset=args.offset,
        )
    except (OSError, PlayerFactCaptureError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
