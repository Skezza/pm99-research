#!/usr/bin/env python3
"""Build a deterministic, season-neutral home-kit source catalogue.

The catalogue is the ``kit-catalogue`` input to a season recipe.  It does not
write PM99 archives.  Wikipedia source is retained in a content-addressed
cache and can subsequently be replayed offline.  Football Kit Archive rows
are deliberately reviewed descriptions rather than scraped artwork: the
source URL and the hash of locally retained evidence remain attached to the
rendering contract.

Network access is opt-in.  With the default offline mode, absent evidence is
reported as an explicit gap.  A native PM99 kit is only authorised when the
request marks the carrier club as exited, matching the V1 season policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA = "pm99-season-kit-catalogue-v1"
REQUEST_SCHEMA = "pm99-season-kit-catalogue-request-v1"
USER_AGENT = "pm99-research/season-kit-catalogue-v1 (+local historical game mod)"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WIKI_PROVIDER = "wikipedia-football-kit-template"
FKA_PROVIDER = "football-kit-archive-reviewed-description"
PATTERNS = {
    "chest_band",
    "diagonal_sash",
    "halves",
    "hoops",
    "quarters",
    "sleeves",
    "solid",
    "vertical_stripes",
}
STYLE_KEYS = {
    "pattern",
    "colors",
    "shorts",
    "trim",
    "sleeves",
    "stripe_count",
    "band_count",
    "accent",
    "side_panel",
    "yoke",
    "notes",
}


class KitCatalogueError(ValueError):
    """The source request or retained evidence is unsafe or ambiguous."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _cache_key(source: Mapping[str, Any]) -> str:
    identity = {
        "provider": source.get("provider"),
        "language": source.get("language"),
        "page_title": source.get("page_title"),
    }
    return sha256_bytes(canonical_json_bytes(identity))


def _cache_paths(cache_dir: Path, source: Mapping[str, Any]) -> tuple[Path, Path]:
    key = _cache_key(source)
    return cache_dir / "index" / f"{key}.json", cache_dir / "objects"


def _read_cached_wikipedia(cache_dir: Path, source: Mapping[str, Any]) -> dict[str, Any] | None:
    index_path, object_root = _cache_paths(cache_dir, source)
    if not index_path.is_file():
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        digest = str(index["sha256"])
        if not SHA256_RE.fullmatch(digest):
            return None
        object_path = object_root / digest[:2] / f"{digest}.json"
        payload = object_path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
        if payload != canonical_json_bytes(value) or sha256_bytes(payload) != digest:
            return None
        return value
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_cached_wikipedia(cache_dir: Path, source: Mapping[str, Any], value: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(dict(value))
    digest = sha256_bytes(payload)
    index_path, object_root = _cache_paths(cache_dir, source)
    object_path = object_root / digest[:2] / f"{digest}.json"
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists() and object_path.read_bytes() != payload:
        raise KitCatalogueError(f"content-addressed cache collision: {object_path}")
    if not object_path.exists():
        object_path.write_bytes(payload)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(canonical_json_bytes({"sha256": digest}))
    return digest


def fetch_wikipedia(source: Mapping[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    """Fetch one exact MediaWiki revision; callers decide whether networking is allowed."""

    language = str(source.get("language") or "")
    title = str(source.get("page_title") or "")
    if not re.fullmatch(r"[a-z-]{2,16}", language) or not title:
        raise KitCatalogueError("Wikipedia source requires language and exact page_title")
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "titles": title,
            "redirects": "1",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content|ids|timestamp",
            "format": "json",
            "formatversion": "2",
        }
    )
    request = urllib.request.Request(
        f"https://{language}.wikipedia.org/w/api.php?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS host
        document = json.loads(response.read().decode("utf-8"))
    pages = ((document.get("query") or {}).get("pages") or [])
    if len(pages) != 1 or pages[0].get("missing") is True:
        raise KitCatalogueError(f"Wikipedia page is missing: {title}")
    page = pages[0]
    revisions = page.get("revisions") or []
    if len(revisions) != 1:
        raise KitCatalogueError(f"Wikipedia page has no unambiguous revision: {title}")
    revision = revisions[0]
    wikitext = str(((revision.get("slots") or {}).get("main") or {}).get("content") or "")
    if not wikitext.strip():
        raise KitCatalogueError(f"Wikipedia page has no wikitext: {title}")
    resolved_title = str(page.get("title") or title)
    return {
        "language": language,
        "page_id": int(page["pageid"]),
        "page_title": resolved_title,
        "page_url": f"https://{language}.wikipedia.org/wiki/{urllib.parse.quote(resolved_title.replace(' ', '_'))}",
        "revision_id": int(revision["revid"]),
        "revision_timestamp": str(revision["timestamp"]),
        "wikitext": wikitext,
    }


def _parse_wikipedia_home_kit(wikitext: str) -> dict[str, Any]:
    # Reuse the parser which established the successful 2015 source contract.
    from scripts.materialise_2015_world_kits import parse_home_fields

    parsed = parse_home_fields(wikitext)
    fields = dict(parsed.get("fields") or {})
    # Do not silently discard shorts overlays. Some encode the ENTIRE shorts
    # colour rather than decoration (e.g. Atlético 2014/15). Renderers must
    # explicitly support these fields or retain a gap.
    for field in ('pattern_sh1', 'pattern_so1'):
        match = re.search(rf'\|\s*{field}\s*=\s*([^\n|}}]*)', wikitext, re.I)
        if match:
            fields[field] = match[1].strip()
    colour_fields = ("leftarm1", "body1", "rightarm1", "shorts1", "socks1")
    normalised = {}
    for field in colour_fields:
        original = str(fields.get(field) or "").strip()
        value = original.replace("<!--", "").replace("-->", "").strip()
        value = re.sub(r"^=\s*", "", value)
        if re.fullmatch(r"[0-9a-fA-F]{3}", value):
            value = "".join(character * 2 for character in value)
        elif len(value) > 6 and len(set(value.casefold())) == 1 and re.fullmatch(r"[0-9a-fA-F]+", value):
            value = value[:6]
        if value != original:
            normalised[field] = {"captured": original, "css_hex": value}
        if value:
            fields[field] = value
    all_fields = ("pattern_la1", "pattern_b1", "pattern_ra1", *colour_fields)
    missing = {field for field in all_fields if not fields.get(field)}
    bad_colours = {field for field in colour_fields if fields.get(field) and not re.fullmatch(r"[0-9a-fA-F]{6}", str(fields[field]))}
    if bad_colours:
        return {"status": "invalid-home-kit-colours", "invalid_fields": sorted(bad_colours), "fields": fields, "normalised_colour_fields": normalised}
    # Football-kit pattern parameters are overlays. Omission means the exact
    # six-digit colour field is painted without an overlay. Apply that default
    # only when all five colour fields are present and valid; never infer one.
    pattern_fields = {"pattern_la1", "pattern_b1", "pattern_ra1"}
    if missing and missing <= pattern_fields and all(re.fullmatch(r"[0-9a-fA-F]{6}", str(fields.get(field) or "")) for field in colour_fields):
        for field in missing:
            fields[field] = ""
        return {"status": "home-kit-fields-ready", "fields": fields, "defaulted_empty_pattern_fields": sorted(missing), "normalised_colour_fields": normalised}
    if missing:
        return {"status": "missing-home-kit-fields", "missing_fields": sorted(missing), "fields": fields, "normalised_colour_fields": normalised}
    return {"status": "home-kit-fields-ready", "fields": fields, "normalised_colour_fields": normalised}


def _normalise_style(value: Any) -> dict[str, Any]:
    from scripts.patch_english80_reference_kits_v2 import COLORS

    if not isinstance(value, dict) or set(value) - STYLE_KEYS:
        raise KitCatalogueError("reviewed_style has unsupported fields")
    pattern = value.get("pattern")
    colors = value.get("colors")
    if pattern not in PATTERNS:
        raise KitCatalogueError(f"unsupported PM99 kit pattern: {pattern!r}")
    if not isinstance(colors, list) or not 1 <= len(colors) <= 4 or not all(
        isinstance(color, str) and color for color in colors
    ):
        raise KitCatalogueError("reviewed_style.colors must contain one to four names")
    color_fields = [*colors]
    color_fields.extend(value[key] for key in ("shorts", "trim", "sleeves", "accent", "side_panel", "yoke") if value.get(key))
    unsupported_colors = sorted({str(color) for color in color_fields if color not in COLORS})
    if unsupported_colors:
        raise KitCatalogueError(f"unsupported PM99 renderer colours: {unsupported_colors}")
    for count_key in ("stripe_count", "band_count"):
        count = value.get(count_key)
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count <= 0):
            raise KitCatalogueError(f"reviewed_style.{count_key} must be a positive integer")
    result = {key: value[key] for key in sorted(value) if value[key] is not None}
    result["colors"] = list(colors)
    return result


def _validate_request(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise KitCatalogueError(f"request schema must be {REQUEST_SCHEMA}")
    season = request.get("season")
    if not isinstance(season, dict) or set(season) != {"start_year", "end_year", "label"}:
        raise KitCatalogueError("season must contain start_year, end_year and label")
    start, end = season.get("start_year"), season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int) or end != start + 1:
        raise KitCatalogueError("season years must be consecutive integers")
    if season.get("label") != f"{start}/{str(end)[-2:]}":
        raise KitCatalogueError("season label must match its consecutive years")
    clubs = request.get("clubs")
    if not isinstance(clubs, list):
        raise KitCatalogueError("clubs must be a list")
    ids = [row.get("carrier_id") for row in clubs if isinstance(row, dict)]
    if len(ids) != len(clubs) or ids != sorted(ids) or len(ids) != len(set(ids)):
        raise KitCatalogueError("clubs must be objects sorted by unique carrier_id")
    for row in clubs:
        if not isinstance(row.get("carrier_id"), int) or int(row["carrier_id"]) <= 0:
            raise KitCatalogueError("carrier_id must be a positive integer")
        if not isinstance(row.get("club_name"), str) or not row["club_name"].strip():
            raise KitCatalogueError("club_name must be non-empty")
        if row.get("carrier_status") not in {"continuing", "exited"}:
            raise KitCatalogueError("carrier_status must be continuing or exited")
        source = row.get("source")
        if source is not None and not isinstance(source, dict):
            raise KitCatalogueError("source must be an object or null")
    return [dict(row) for row in clubs]


def build_catalogue(
    request: Mapping[str, Any],
    *,
    cache_dir: Path,
    allow_network: bool = False,
    wikipedia_fetcher: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve every requested carrier to evidence, an authorised fallback or a gap."""

    clubs = _validate_request(request)
    fetcher = wikipedia_fetcher or fetch_wikipedia
    rows: list[dict[str, Any]] = []
    for club in clubs:
        base = {
            "carrier_id": int(club["carrier_id"]),
            "carrier_status": str(club["carrier_status"]),
            "club_name": str(club["club_name"]),
        }
        source = club.get("source")
        if not source:
            if club["carrier_status"] == "exited":
                rows.append({**base, "status": "native-fallback-authorized", "reason": "carrier-club-exited"})
            else:
                rows.append({**base, "status": "blocked-no-target-season-source", "reason": "continuing-club-requires-historical-kit"})
            continue
        provider = source.get("provider")
        if provider == WIKI_PROVIDER:
            cached = _read_cached_wikipedia(cache_dir, source)
            if cached is None and allow_network:
                try:
                    cached = fetcher(source)
                    _write_cached_wikipedia(cache_dir, source, cached)
                except Exception as exc:
                    rows.append({**base, "status": "blocked-source-fetch-failed", "reason": f"{type(exc).__name__}: {exc}"})
                    continue
            if cached is None:
                rows.append({**base, "status": "blocked-cache-miss", "reason": "network-disabled-and-no-retained-wikipedia-snapshot"})
                continue
            cache_sha = sha256_bytes(canonical_json_bytes(cached))
            parsed = _parse_wikipedia_home_kit(str(cached.get("wikitext") or ""))
            if parsed.get("status") != "home-kit-fields-ready":
                rows.append({**base, "status": "blocked-missing-home-kit-fields", "reason": str(parsed.get("status")), "source": {"provider": provider, "page_url": cached.get("page_url"), "revision_id": cached.get("revision_id"), "cache_sha256": cache_sha}})
                continue
            rows.append(
                {
                    **base,
                    "status": "source-ready",
                    "render_contract": {"kind": "wikipedia-template-fields", "fields": parsed["fields"], "defaulted_empty_pattern_fields": parsed.get("defaulted_empty_pattern_fields", []), "normalised_colour_fields": parsed.get("normalised_colour_fields", {})},
                    "source": {
                        "provider": provider,
                        "page_title": cached.get("page_title"),
                        "page_url": cached.get("page_url"),
                        "revision_id": cached.get("revision_id"),
                        "revision_timestamp": cached.get("revision_timestamp"),
                        "cache_sha256": cache_sha,
                        "attribution": "Wikipedia contributors; source page revision and licence terms apply",
                    },
                }
            )
            continue
        if provider == FKA_PROVIDER:
            url, evidence_sha = source.get("url"), source.get("evidence_sha256")
            if not isinstance(url, str) or not url.startswith("https://www.footballkitarchive.com/"):
                raise KitCatalogueError("Football Kit Archive source requires its HTTPS page URL")
            if not isinstance(evidence_sha, str) or not SHA256_RE.fullmatch(evidence_sha):
                raise KitCatalogueError("Football Kit Archive source requires retained evidence_sha256")
            rows.append(
                {
                    **base,
                    "status": "source-ready",
                    "render_contract": {"kind": "reviewed-pm99-style", "style": _normalise_style(source.get("reviewed_style"))},
                    "source": {
                        "provider": provider,
                        "page_url": url,
                        "evidence_sha256": evidence_sha,
                        "attribution": "Football Kit Archive; manually reviewed kit reference (no source artwork redistributed)",
                    },
                }
            )
            continue
        raise KitCatalogueError(f"unsupported kit source provider: {provider!r}")

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema_version": SCHEMA,
        "season": dict(request["season"]),
        "provenance": {"request_sha256": sha256_bytes(canonical_json_bytes(dict(request)))},
        "policy": {
            "continuing_club": "target-season-source-required",
            "exited_carrier": "native-fallback-authorized",
            "network": "opt-in-exact-page-fetch-content-addressed-replay",
            "rendering": "reuse-pm99-native-silhouette-palette-and-record-length",
        },
        "coverage": {"club_count": len(rows), "status_counts": dict(sorted(status_counts.items()))},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true", help="fetch exact requested Wikipedia pages on cache miss")
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    result = build_catalogue(request, cache_dir=args.cache_dir, allow_network=args.allow_network)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
