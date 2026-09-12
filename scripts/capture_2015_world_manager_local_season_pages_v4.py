#!/usr/bin/env python3
"""Check dated national Wikipedia season pages after a club-page manager gap.

The preceding multilingual club-page receipt already proves a club's Wikidata
identity and country-specific Wikipedia title.  This follow-up is deliberately
narrow: it only searches that same wiki for a 2015 season-page title containing
the exact local club title, then reads the revision at or before 1 September
2015.  It neither accepts a search rank as identity nor writes PM99 data.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_2015_world_manager_history_v2 import canonical_json_bytes
from scripts.capture_2015_world_manager_multilingual_wikipedia_v3 import (
    DEFAULT_AS_OF,
    SCHEMA as MULTILINGUAL_SCHEMA,
    _fetch_json,
    _fetch_revision,
    _manager,
    _normalise,
    _pm99_representable,
)


SCHEMA = "pm99-world-2015-local-season-page-manager-history-v4"
USER_AGENT = "PM99RE-source-research/1.0"


class CaptureError(ValueError):
    pass


def _season_title_matches(title: str, local_club_title: str) -> bool:
    """Require an exact local club-title component and explicit 2015 year."""
    title_key = _normalise(title)
    club_key = _normalise(local_club_title)
    return bool(club_key and club_key in title_key and title_key.startswith("2015"))


def _search_titles(language: str, local_club_title: str) -> list[str]:
    payload = _fetch_json(f"https://{language}.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": "2",
        "list": "search", "srnamespace": "0", "srlimit": "20",
        "srsearch": f'"{local_club_title}" 2015',
    })
    rows = (payload or {}).get("query", {}).get("search") or []
    return sorted({
        str(row.get("title") or "") for row in rows
        if isinstance(row, Mapping) and _season_title_matches(str(row.get("title") or ""), local_club_title)
    })


Search = Callable[[str, str], list[str]]
Fetch = Callable[[str, str, str], dict[str, Any] | None]


def _fetch(language: str, title: str, as_of: str) -> dict[str, Any] | None:
    return _fetch_revision(language, title, as_of)


def _local_title(row: Mapping[str, Any]) -> tuple[str, str] | None:
    considered = row.get("considered") or []
    if not isinstance(considered, list):
        return None
    usable = [
        (str(item.get("language") or ""), str(item.get("title") or ""))
        for item in considered
        if isinstance(item, Mapping) and item.get("language") and item.get("title")
    ]
    return usable[0] if len(usable) == 1 else None


def _one(
    row: Mapping[str, Any], *, as_of: str,
    search: Search = _search_titles, fetch: Fetch = _fetch,
) -> dict[str, Any]:
    carrier = int(row["carrier_id"])
    name = str(row["source_club_name"])
    local = _local_title(row)
    if local is None:
        return {
            "carrier_id": carrier, "source_club_name": name,
            "status": "requires-review-no-single-national-club-title-from-prior-receipt",
        }
    language, local_title = local
    titles = search(language, local_title)
    considered = []
    for title in titles:
        page = fetch(language, title, as_of)
        if page is None:
            considered.append({"title": title, "result": "page-or-revision-unavailable"})
            continue
        manager, issue = _manager(str(page.get("content") or ""), language)
        if manager:
            status = (
                "dated-local-season-page-manager-match"
                if _pm99_representable(manager)
                else "dated-local-season-page-manager-source-pm99-transliteration-required"
            )
            return {
                "carrier_id": carrier, "source_club_name": name,
                "country_catalog": row.get("country_catalog"), "language": language,
                "status": status,
                "identity_method": "prior-Wikidata-club-identity; exact-local-club-title-in-2015-season-page-title",
                "snapshot_as_of": as_of,
                "facts": {"manager": manager},
                "pm99_storage": {
                    "status": "cp1252-or-compiler-transliterable" if status.endswith("-match") else "latin-transliteration-required",
                },
                "page": {key: page[key] for key in ("title", "pageid", "revid", "timestamp", "content_sha256")},
            }
        considered.append({"title": title, "result": issue or "manager-field-absent"})
    return {
        "carrier_id": carrier, "source_club_name": name,
        "country_catalog": row.get("country_catalog"), "language": language,
        "status": "requires-review-no-dated-local-season-page-manager-match",
        "considered": considered,
    }


def build(history: Mapping[str, Any], *, as_of: str, jobs: int) -> dict[str, Any]:
    if history.get("schema_version") != MULTILINGUAL_SCHEMA:
        raise CaptureError("multilingual history receipt schema is unsupported")
    selected = [
        row for row in history.get("rows") or []
        if isinstance(row, Mapping) and row.get("status") == "requires-review-no-dated-national-wikipedia-manager-match"
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        rows = list(pool.map(lambda row: _one(row, as_of=as_of), selected))
    ready = [row for row in rows if row["status"] == "dated-local-season-page-manager-match"]
    transliteration = [row for row in rows if row["status"] == "dated-local-season-page-manager-source-pm99-transliteration-required"]
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; only prior-Wikidata-identified national club pages; "
            "exact local club title within a 2015 season-page title; dated revision; no PM99 write"
        ),
        "sources": {"multilingual_history_sha256": hashlib.sha256(canonical_json_bytes(history)).hexdigest()},
        "coverage": {
            "prior_club_page_manager_gap_count": len(selected),
            "dated_local_season_page_manager_match_count": len(ready),
            "dated_manager_source_transliteration_required_count": len(transliteration),
            "unresolved_count": len(selected) - len(ready) - len(transliteration),
            "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--multilingual-history", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--jobs", default=4, type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    raw = args.multilingual_history.read_bytes()
    history = json.loads(raw.decode("utf-8"))
    if raw != canonical_json_bytes(history):
        parser.error("multilingual history receipt must use canonical JSON bytes")
    try:
        receipt = build(history, as_of=args.as_of, jobs=args.jobs)
    except CaptureError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
