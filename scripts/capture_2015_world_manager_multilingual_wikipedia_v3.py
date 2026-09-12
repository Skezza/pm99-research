#!/usr/bin/env python3
"""Backfill unresolved 2015/16 world managers from national Wikipedias.

English Wikipedia leaves many historically relevant clubs without a dated
manager field.  This source-only follow-up uses an exact Wikidata football
club identity and its country-appropriate Wikipedia sitelink before reading a
revision at or before 1 September 2015.  Search rank alone is never accepted:
the Wikidata result must be a unique football club in the declared source
country and have a matching national-wiki sitelink.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import html
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_2015_world_manager_history_v2 import (
    DEFAULT_AS_OF,
    SCHEMA as ENGLISH_HISTORY_SCHEMA,
    canonical_json_bytes,
)


SCHEMA = "pm99-world-2015-multilingual-wikipedia-manager-history-v3"
SOURCE_CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = (
    "PM99RE-source-research/1.0 "
    "(https://github.com/openai/codex; source-research@example.invalid)"
)

# The language list is intentionally short and tied to the country recorded
# in the dated squad source.  It is not a name-guessing table: Wikidata
# supplies the club identity and exact page title.
COUNTRY_WIKIS: dict[str, tuple[str, ...]] = {
    "arg": ("es",), "austria": ("de",), "norway": ("no",),
    "hungary": ("hu",), "brazil": ("pt",), "czechia": ("cs",),
    "bulgaria": ("bg",), "slovakia": ("sk",), "cyprus": ("el",),
    "israel": ("he",), "romania": ("ro",), "slovenia": ("sl",),
    "finland": ("fi",), "peru": ("es",), "chile": ("es",),
    "colombia": ("es",), "paraguay": ("es",), "switz": ("de", "fr", "it"),
    "switzerland": ("de", "fr", "it"), "iceland": ("is",),
    "faroe-islands": ("fo",), "albania": ("sq",), "georgia": ("ka",),
    "ecuador": ("es",), "belarus": ("be", "ru"), "venezuela": ("es",),
    "latvia": ("lv",), "serbia": ("sr",), "sweden": ("sv",),
    "luxembourg": ("fr", "de"), "lithuania": ("lt",), "armenia": ("hy",),
    "north-macedonia": ("mk",), "azerbaijan": ("az",), "portugal": ("pt",),
}
# A P17 country check excludes homonymous clubs, towns and women/reserve sides.
# Northern Ireland and Wales use the United Kingdom as the club's Wikidata P17.
COUNTRY_QIDS = {
    "arg": "Q414", "austria": "Q40", "norway": "Q20", "hungary": "Q28",
    "brazil": "Q155", "czechia": "Q213", "bulgaria": "Q219", "slovakia": "Q214",
    "cyprus": "Q229", "israel": "Q801", "romania": "Q218", "slovenia": "Q215",
    "finland": "Q33", "peru": "Q419", "chile": "Q298", "colombia": "Q739",
    "paraguay": "Q733", "switz": "Q39", "switzerland": "Q39", "iceland": "Q189",
    "faroe-islands": "Q4628", "albania": "Q222", "georgia": "Q230",
    "ecuador": "Q736", "belarus": "Q184", "venezuela": "Q717", "latvia": "Q211",
    "serbia": "Q403", "sweden": "Q34", "luxembourg": "Q32", "lithuania": "Q37",
    "armenia": "Q399", "north-macedonia": "Q221", "azerbaijan": "Q227",
    "portugal": "Q45",
}
MANAGER_FIELDS = {
    "es": {"entrenador", "director técnico", "director tecnico", "técnico", "tecnico"},
    "de": {"trainer", "cheftrainer"}, "fr": {"entraîneur", "entraineur"},
    "it": {"allenatore"}, "no": {"trener"}, "hu": {"edző", "edzo"},
    "pt": {"treinador", "técnico", "tecnico"}, "cs": {"trenér", "trener"},
    "pl": {"trener"}, "bg": {"старши треньор", "треньор"},
    "sk": {"tréner", "trener"}, "el": {"προπονητής"}, "he": {"מאמן"},
    "ro": {"antrenor"}, "sl": {"trener"}, "fi": {"päävalmentaja", "valmentaja"},
    "is": {"þjálfari"}, "fo": {"venjari"}, "sq": {"trajner"},
    "ka": {"მწვრთნელი"}, "be": {"трэнер"}, "ru": {"тренер"},
    "lv": {"galvenais treneris", "treneris"}, "sr": {"тренер", "trener"},
    "sv": {"tränare", "tranare"}, "lt": {"treneris"}, "hy": {"գլխավոր մարզիչ"},
    "mk": {"тренер"}, "az": {"baş məşqçi", "bas mesqci"},
}


class CaptureError(ValueError):
    pass


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character.casefold()
        for character in text
        if character.isalnum() and not unicodedata.combining(character)
    )


def _fetch_json(api: str, query: Mapping[str, str]) -> dict[str, Any] | None:
    # Public APIs can transiently rate-limit a bulk historical lookup.  An
    # empty result must mean genuinely unresolved, not merely one failed HTTP
    # request, so retry the exact immutable request before recording a gap.
    for attempt in range(3):
        try:
            request = Request(f"{api}?{urlencode(query)}", headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            return result if isinstance(result, dict) else None
        except Exception:
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    return None


def _wd_search(name: str, language: str) -> list[dict[str, Any]]:
    payload = _fetch_json(WIKIDATA_API, {
        "action": "wbsearchentities", "format": "json", "language": language,
        "limit": "20", "search": name,
    })
    rows = (payload or {}).get("search") or []
    return [dict(row) for row in rows if isinstance(row, Mapping) and row.get("id")]


def _wd_entities(ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    payload = _fetch_json(WIKIDATA_API, {
        "action": "wbgetentities", "format": "json", "ids": "|".join(sorted(set(ids))),
        "props": "claims|sitelinks",
    })
    rows = (payload or {}).get("entities") or {}
    return {str(key): dict(value) for key, value in rows.items() if isinstance(value, Mapping)}


def _club_qid(name: str, country: str, languages: tuple[str, ...]) -> tuple[str, str] | None:
    """Find one country-bound football-club entity, or leave the row unresolved."""
    results: dict[str, dict[str, Any]] = {}
    for language in dict.fromkeys(("en", *languages)):
        for row in _wd_search(name, language):
            results.setdefault(str(row["id"]), row)
    entities = _wd_entities(list(results))
    expected_country = COUNTRY_QIDS.get(country)
    eligible: list[tuple[str, str]] = []
    source_key = _normalise(name)
    for qid, entity in entities.items():
        result = results[qid]
        description = str(result.get("description") or "").casefold()
        sport_ids = {
            str(claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") or "")
            for claim in (entity.get("claims", {}).get("P641") or [])
            if isinstance(claim, Mapping)
        }
        football_club_ids = {
            str(claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") or "")
            for claim in (entity.get("claims", {}).get("P31") or [])
            if isinstance(claim, Mapping)
        }
        if not (
            "Q476028" in football_club_ids  # association football club
            or ("Q847017" in football_club_ids and "Q2736" in sport_ids)
        ):
            continue
        if any(token in description for token in ("women", "reserve team", "b team", "youth team")):
            continue
        countries = {
            str(claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") or "")
            for claim in (entity.get("claims", {}).get("P17") or [])
            if isinstance(claim, Mapping)
        }
        if expected_country and expected_country not in countries:
            continue
        sitelinks = entity.get("sitelinks") or {}
        if not any(f"{language}wiki" in sitelinks for language in languages):
            continue
        exact_values = [result.get("label"), (result.get("match") or {}).get("text")]
        exact = any(_normalise(value) == source_key for value in exact_values if value)
        label_key = _normalise(result.get("label"))
        # This is intentionally a one-way expansion only: the supplied club
        # label must be the complete leading identity of the football-club
        # label (Rosenborg -> Rosenborg BK), never a fuzzy similarity score.
        expansion = len(source_key) >= 5 and label_key.startswith(source_key)
        if exact:
            eligible.append((qid, "wikidata-exact-label-or-alias"))
        elif expansion:
            eligible.append((qid, "wikidata-unique-football-club-label-expansion"))
    return eligible[0] if len(eligible) == 1 else None


def _fetch_revision(language: str, title: str, as_of: str) -> dict[str, Any] | None:
    payload = _fetch_json(f"https://{language}.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "revisions", "rvprop": "ids|timestamp|content", "rvslots": "main",
        "rvstart": as_of, "rvdir": "older", "rvlimit": "1", "titles": title,
    })
    pages = (payload or {}).get("query", {}).get("pages") or []
    if len(pages) != 1 or not isinstance(pages[0], Mapping) or pages[0].get("missing"):
        return None
    page = pages[0]
    revisions = page.get("revisions") or []
    if len(revisions) != 1 or not isinstance(revisions[0], Mapping):
        return None
    revision = revisions[0]
    content = ((revision.get("slots") or {}).get("main") or {}).get("content")
    if not isinstance(content, str):
        return None
    return {
        "title": page.get("title"), "pageid": page.get("pageid"), "revid": revision.get("revid"),
        "timestamp": revision.get("timestamp"),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
    }


def _clean(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<ref\b[^>/]*>.*?</ref\s*>", "", value, flags=re.I | re.S)
    value = re.sub(r"<ref\b[^>]*/\s*>", "", value, flags=re.I)
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    # Some language templates carry the linked name as Ziel/Name rather than
    # an ordinary wiki-link (notably {{AUT|Ziel=Zoran Barisic}}).
    def template(match: re.Match[str]) -> str:
        body = match.group(1)
        named = re.search(r"(?:ziel|name|link)\s*=\s*([^|{}]+)", body, re.I)
        if named:
            return f" {named.group(1)} "
        return " "
    for _ in range(3):
        value = re.sub(r"{{([^{}]*)}}", template, value)
    for _ in range(3):
        value = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", value)
        value = re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    # Local infoboxes sometimes label a caretaker in parentheses.  The name
    # itself remains the source fact; the appointment qualifier is preserved
    # in the page revision rather than stuffed into PM99's name field.
    return re.sub(r"\s*\([^()]{1,60}\)\s*$", "", value).strip(" ,;")


def _manager(content: str, language: str) -> tuple[str | None, str | None]:
    fields = MANAGER_FIELDS.get(language, set())
    if not fields:
        return None, "manager-field-language-not-implemented"
    pattern = re.compile(
        r"^\s*\|\s*(" + "|".join(re.escape(field) for field in sorted(fields)) + r")\s*=\s*(.*)$",
        re.I | re.M,
    )
    match = pattern.search(content)
    if match is None:
        return None, "manager-field-absent"
    value = _clean(match.group(2))
    if (
        not value
        or "|" in value
        or "=" in value
        or _normalise(value) in {"vacant", "none", "unknown", "tba"}
    ):
        return None, "manager-field-blank"
    if re.search(r"\s/(?:\s|$)|\s+(?:and|&|och|und|et|y)\s+", value, re.I):
        return None, "multiple-or-joint-manager-value"
    return value, None


def _pm99_representable(value: str) -> bool:
    """Mirror the compiler's documented CP1252/transliteration boundary."""
    substitutions = str.maketrans({
        "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o",
        "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d",
        "İ": "I", "ı": "i",
    })
    normalised = unicodedata.normalize("NFKD", value.translate(substitutions))
    storage = "".join(char for char in normalised if not unicodedata.combining(char))
    try:
        storage.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def _country_by_carrier(source_candidate: Mapping[str, Any]) -> dict[int, str]:
    if source_candidate.get("schema_version") != SOURCE_CANDIDATE_SCHEMA:
        raise CaptureError("source candidate schema is unsupported")
    result = {}
    for row in source_candidate.get("carrier_drafts") or []:
        if not isinstance(row, Mapping):
            continue
        selector = ((row.get("club") or {}).get("source_selector") or {})
        country = selector.get("country_catalog")
        if isinstance(country, str) and country:
            result[int(row["carrier_id"])] = country
    return result


def _one(row: Mapping[str, Any], country: str | None, as_of: str) -> dict[str, Any]:
    carrier = int(row["carrier_id"])
    name = str(row["source_club_name"])
    if country is None or country not in COUNTRY_WIKIS or country not in COUNTRY_QIDS:
        return {"carrier_id": carrier, "source_club_name": name, "status": "requires-review-no-country-scoped-wiki-route"}
    languages = COUNTRY_WIKIS[country]
    identity = _club_qid(name, country, languages)
    if identity is None:
        return {"carrier_id": carrier, "source_club_name": name, "country_catalog": country, "status": "requires-review-no-unique-country-scoped-wikidata-football-club"}
    qid, identity_method = identity
    entity = _wd_entities([qid]).get(qid, {})
    sitelinks = entity.get("sitelinks") or {}
    considered = []
    for language in languages:
        link = sitelinks.get(f"{language}wiki") or {}
        title = link.get("title") if isinstance(link, Mapping) else None
        if not isinstance(title, str):
            continue
        page = _fetch_revision(language, title, as_of)
        if page is None:
            considered.append({"language": language, "title": title, "result": "page-or-revision-unavailable"})
            continue
        manager, issue = _manager(str(page["content"]), language)
        if manager:
            status = (
                "dated-national-wikipedia-manager-match"
                if _pm99_representable(manager)
                else "dated-national-wikipedia-manager-source-pm99-transliteration-required"
            )
            return {
                "carrier_id": carrier, "source_club_name": name, "country_catalog": country,
                "status": status, "identity_method": identity_method,
                "wikidata_entity_id": qid, "language": language, "snapshot_as_of": as_of,
                "facts": {"manager": manager},
                "pm99_storage": {
                    "status": "cp1252-representable" if status.endswith("-match") else "latin-transliteration-required",
                },
                "page": {key: page[key] for key in ("title", "pageid", "revid", "timestamp", "content_sha256")},
            }
        considered.append({"language": language, "title": title, "result": issue or "manager-field-absent"})
    return {
        "carrier_id": carrier, "source_club_name": name, "country_catalog": country,
        "wikidata_entity_id": qid, "status": "requires-review-no-dated-national-wikipedia-manager-match",
        "considered": considered,
    }


def build(history: Mapping[str, Any], source_candidate: Mapping[str, Any], *, as_of: str, jobs: int) -> dict[str, Any]:
    if history.get("schema_version") != ENGLISH_HISTORY_SCHEMA:
        raise CaptureError("English history receipt schema is unsupported")
    country_by_carrier = _country_by_carrier(source_candidate)
    selected = [
        row for row in history.get("rows") or []
        if isinstance(row, Mapping) and row.get("status") == "requires-review-no-dated-historical-manager-match"
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        rows = list(pool.map(lambda row: _one(row, country_by_carrier.get(int(row["carrier_id"])), as_of), selected))
    matches = [row for row in rows if row["status"] == "dated-national-wikipedia-manager-match"]
    transliteration = [row for row in rows if row["status"] == "dated-national-wikipedia-manager-source-pm99-transliteration-required"]
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; unique-country-scoped-Wikidata-football-club-identity; exact-national-Wikipedia-sitelink; "
            "dated-revision-at-or-before-snapshot; no-search-rank-identity; no-PM99-write"
        ),
        "sources": {
            "english_history_sha256": hashlib.sha256(canonical_json_bytes(history)).hexdigest(),
            "source_candidate_sha256": hashlib.sha256(canonical_json_bytes(source_candidate)).hexdigest(),
            "wikidata_api": WIKIDATA_API,
        },
        "coverage": {
            "english_unresolved_input_count": len(selected),
            "dated_national_wikipedia_manager_match_count": len(matches),
            "dated_manager_source_transliteration_required_count": len(transliteration),
            "unresolved_count": len(selected) - len(matches),
            "status_counts": dict(sorted(Counter(row["status"] for row in rows).items())),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--english-history", required=True, type=Path)
    parser.add_argument("--source-candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--jobs", default=4, type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    history_raw = args.english_history.read_bytes()
    source_raw = args.source_candidate.read_bytes()
    history = json.loads(history_raw.decode("utf-8"))
    source_candidate = json.loads(source_raw.decode("utf-8"))
    if history_raw != canonical_json_bytes(history) or source_raw != canonical_json_bytes(source_candidate):
        parser.error("inputs must use canonical JSON bytes")
    try:
        receipt = build(history, source_candidate, as_of=args.as_of, jobs=args.jobs)
    except CaptureError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(receipt))
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
