#!/usr/bin/env python3
"""Capture 2015/16 manager facts from dated English Wikipedia club revisions.

This is deliberately a source-only step.  It does not decide which PM99 ENT
record a manager will receive and cannot modify a database.  A row is usable
only when a page reached from the declared club title (including a Wikipedia
redirect) has a manager field in the revision at or before the declared
season snapshot.  Search results may discover a title to inspect, but are
never themselves an identity decision.

The original world capture only accepted the small set of English Wikipedia
``2015–16 <club> season`` pages.  Many historically relevant clubs do not
have one.  This capture therefore uses a dated revision of the club page,
which is the more widely available source.  Its date scope remains explicit:
it is an early-season snapshot, not a claim about every later managerial
change.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCHEMA = "pm99-world-2015-wikipedia-manager-history-v2"
PACKAGE_SCHEMA = "pm99-season-package-v2"
API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "PM99RE-source-research/1.0 "
    "(https://github.com/openai/codex; source-research@example.invalid)"
)
DEFAULT_AS_OF = "2015-09-01T00:00:00Z"
SPECIAL_CLUB_NAMES = {
    "Sel. Europa", "Sel. América", "Stars", "Free players", "Youth players",
}


class CaptureError(ValueError):
    """The declared world package cannot be used as a capture input."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _normalise(value: object) -> str:
    """Return an accent-insensitive identity key, without making it fuzzy."""
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character.casefold()
        for character in text
        if character.isalnum() and not unicodedata.combining(character)
    )


def _fetch_json(query: Mapping[str, str]) -> dict[str, Any] | None:
    request = Request(
        f"{API}?{urlencode(query)}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _fetch_historical_page(title: str, as_of: str) -> dict[str, Any] | None:
    payload = _fetch_json({
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "rvstart": as_of,
        "rvdir": "older",
        "rvlimit": "1",
        "titles": title,
        "redirects": "1",
    })
    query = (payload or {}).get("query", {})
    pages = query.get("pages", [])
    if not isinstance(pages, list) or len(pages) != 1:
        return None
    page = pages[0]
    if not isinstance(page, dict) or page.get("missing"):
        return None
    revisions = page.get("revisions") or []
    if not isinstance(revisions, list) or len(revisions) != 1:
        return None
    revision = revisions[0]
    content = ((revision.get("slots") or {}).get("main") or {}).get("content")
    if not isinstance(content, str):
        return None
    redirects = query.get("redirects") or []
    redirected_from = next(
        (
            str(row.get("from"))
            for row in redirects
            if isinstance(row, Mapping) and str(row.get("to") or "") == str(page.get("title") or "")
        ),
        None,
    )
    return {
        "title": str(page.get("title") or ""),
        "pageid": page.get("pageid"),
        "revid": revision.get("revid"),
        "timestamp": revision.get("timestamp"),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
        "redirected_from": redirected_from,
    }


def _search_titles(name: str) -> list[str]:
    payload = _fetch_json({
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "list": "search",
        "srnamespace": "0",
        "srlimit": "5",
        "srsearch": f'"{name}" football club',
    })
    rows = (payload or {}).get("query", {}).get("search", [])
    if not isinstance(rows, list):
        return []
    return sorted({str(row.get("title") or "") for row in rows if row.get("title")})


def _balanced_template(text: str, start: int) -> str | None:
    """Return one balanced ``{{...}}`` template beginning at ``start``."""
    depth = 0
    cursor = start
    while cursor < len(text) - 1:
        token = text[cursor : cursor + 2]
        if token == "{{":
            depth += 1
            cursor += 2
            continue
        if token == "}}":
            depth -= 1
            cursor += 2
            if depth == 0:
                return text[start:cursor]
            continue
        cursor += 1
    return None


def _club_infobox(content: str) -> str | None:
    for match in re.finditer(r"{{\s*Infobox\s+football\s+club\b", content, re.I):
        found = _balanced_template(content, match.start())
        if found is not None:
            return found
    return None


def _top_level_parameter(template: str, names: set[str]) -> str | None:
    """Read a named infobox parameter without mistaking nested pipes for it."""
    depth = 0
    chunks: list[str] = []
    cursor = 2  # Skip the opening ``{{``.
    while cursor < len(template) - 2:
        token = template[cursor : cursor + 2]
        if token == "{{":
            depth += 1
            chunks.append(token)
            cursor += 2
            continue
        if token == "}}":
            if depth == 0:
                break
            depth -= 1
            chunks.append(token)
            cursor += 2
            continue
        if token == "[[":
            depth += 1
            chunks.append(token)
            cursor += 2
            continue
        if token == "]]" and depth:
            depth -= 1
            chunks.append(token)
            cursor += 2
            continue
        if template[cursor] == "|" and depth == 0:
            chunks.append("\n")
            cursor += 1
            continue
        chunks.append(template[cursor])
        cursor += 1
    for chunk in "".join(chunks).split("\n"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key.strip().casefold() in names:
            return value.strip()
    return None


def _clean_wikitext(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<ref\b[^>/]*>.*?</ref\s*>", "", value, flags=re.I | re.S)
    value = re.sub(r"<ref\b[^>]*/\s*>", "", value, flags=re.I)
    # The flag is decoration; the linked name is the manager identity.
    value = re.sub(r"{{\s*flag(?:icon|icon image)?\s*\|[^{}]*}}", "", value, flags=re.I)
    for _ in range(3):
        value = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", value)
        value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"{{[^{}]*}}", "", value)
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    # A trailing appointment note is scope information, not part of the name.
    value = re.sub(r"\s*\((?:from|since|until|interim|caretaker)\b[^)]*\)\s*$", "", value, flags=re.I)
    return value.strip(" ,;")


def _manager_from_page(page: Mapping[str, Any]) -> tuple[str | None, str | None]:
    template = _club_infobox(str(page.get("content") or ""))
    if template is None:
        return None, None
    raw = _top_level_parameter(template, {"manager", "head coach", "coach"})
    if raw is None:
        return None, None
    value = _clean_wikitext(raw)
    if not value or _normalise(value) in {"vacant", "tba", "unknown", "none"}:
        return None, None
    if re.search(r"\s/(?:\s|$)|\s+(?:and|&)\s+", value, flags=re.I):
        return None, "multiple-or-joint-manager-value"
    return value, None


def _page_identity(page: Mapping[str, Any], declared_name: str) -> str | None:
    """Return a conservative reason that the dated page belongs to this club."""
    if _normalise(page.get("title")) == _normalise(declared_name):
        return "exact-title-or-redirect"
    template = _club_infobox(str(page.get("content") or ""))
    if template is None:
        return None
    for key in {"clubname", "club name", "fullname", "full name", "short name", "name"}:
        value = _top_level_parameter(template, {key})
        if value and _normalise(_clean_wikitext(value)) == _normalise(declared_name):
            return "exact-historical-infobox-club-label"
    return None


def _candidate_titles(name: str) -> list[str]:
    stripped = re.sub(r"^(?:F\.?C\.?\s+)", "", name, flags=re.I).strip()
    # A normal MediaWiki title request follows redirects, which covers spelling
    # and English-name variants without multiplying requests.  The bare form
    # is retained only for source labels explicitly prefixed with FC.
    values = [name, stripped]
    return list(dict.fromkeys(value for value in values if value))


FetchPage = Callable[[str, str], dict[str, Any] | None]
SearchTitles = Callable[[str], list[str]]


def _one(
    club: Mapping[str, Any], *, as_of: str,
    fetch_page: FetchPage = _fetch_historical_page,
    search_titles: SearchTitles = _search_titles,
) -> dict[str, Any]:
    name = str(club["name"])
    carrier_id = int(club["carrier_id"])
    if name in SPECIAL_CLUB_NAMES:
        return {
            "carrier_id": carrier_id,
            "source_club_name": name,
            "status": "out-of-scope-non-club-carrier",
            "reason": "PM99 special carrier has no historical club-manager identity",
        }
    seen_titles: set[str] = set()
    considered: list[dict[str, str]] = []
    for discovery, titles in (("declared-title", _candidate_titles(name)), ("search-discovery", search_titles(name))):
        for title in titles:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            page = fetch_page(title, as_of)
            if page is None:
                considered.append({"title": title, "result": "page-or-revision-unavailable"})
                continue
            identity = _page_identity(page, name)
            # A request for the declared source label may resolve to an
            # English/legacy title.  That MediaWiki redirect is an explicit
            # publisher-maintained identity link, unlike a search rank.
            if (
                identity is None
                and discovery == "declared-title"
                and _normalise(title) == _normalise(name)
                and _normalise(page.get("redirected_from")) == _normalise(title)
            ):
                identity = "declared-title-wikipedia-redirect"
            manager, manager_issue = _manager_from_page(page) if identity else (None, None)
            considered.append({
                "title": str(page.get("title") or title),
                "result": "dated-manager-found" if manager else (
                    manager_issue or (
                        "identity-not-proven" if identity is None else "manager-field-absent"
                    )
                ),
            })
            if identity and manager:
                return {
                    "carrier_id": carrier_id,
                    "source_club_name": name,
                    "status": "dated-historical-club-page-manager-match",
                    "identity_method": identity,
                    "discovery_method": discovery,
                    "snapshot_as_of": as_of,
                    "facts": {"manager": manager},
                    "page": {
                        key: page[key]
                        for key in ("title", "pageid", "revid", "timestamp", "content_sha256")
                    },
                }
    return {
        "carrier_id": carrier_id,
        "source_club_name": name,
        "status": "requires-review-no-dated-historical-manager-match",
        "snapshot_as_of": as_of,
        "considered": considered,
    }


def build(
    package: Mapping[str, Any], *, as_of: str = DEFAULT_AS_OF,
    fetch_page: FetchPage = _fetch_historical_page,
    search_titles: SearchTitles = _search_titles,
    jobs: int = 8,
) -> dict[str, Any]:
    if package.get("schema_version") != PACKAGE_SCHEMA:
        raise CaptureError(f"package must use {PACKAGE_SCHEMA}")
    managers = {
        str(row.get("id")): row
        for row in package.get("managers", [])
        if isinstance(row, Mapping)
    }
    selected = []
    for club in package.get("clubs", []):
        if not isinstance(club, Mapping):
            continue
        manager = managers.get(str(club.get("manager_id")))
        if manager and manager.get("policy") == "preserve-existing-mode1":
            selected.append(dict(club))
    if not selected:
        raise CaptureError("package has no manager-fallback clubs to capture")
    selected.sort(key=lambda row: int(row["carrier_id"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        rows = list(pool.map(lambda club: _one(club, as_of=as_of, fetch_page=fetch_page, search_titles=search_titles), selected))
    matched = [row for row in rows if row["status"] == "dated-historical-club-page-manager-match"]
    unresolved = [row for row in rows if row["status"] == "requires-review-no-dated-historical-manager-match"]
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; dated-English-Wikipedia-club-page-revision-at-or-before-snapshot; "
            "declared-title-or-exact-historical-infobox-identity; search-discovery-only; "
            "no-current-page-fallback; no-PM99-write"
        ),
        "sources": {
            "world_package_sha256": hashlib.sha256(canonical_json_bytes(package)).hexdigest(),
            "mediawiki_api": API,
        },
        "coverage": {
            "manager_fallback_club_count": len(rows),
            "dated_manager_match_count": len(matched),
            "unresolved_club_count": len(unresolved),
            "out_of_scope_non_club_count": sum(row["status"] == "out-of-scope-non-club-carrier" for row in rows),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--jobs", default=8, type=int)
    args = parser.parse_args()
    raw = args.package.read_bytes()
    package = json.loads(raw.decode("utf-8"))
    if raw != canonical_json_bytes(package):
        parser.error("package must use canonical JSON bytes")
    try:
        receipt = build(package, as_of=args.as_of, jobs=args.jobs)
    except CaptureError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
