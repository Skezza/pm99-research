#!/usr/bin/env python3
"""Capture and render source-only 2015/16 world home-kit candidates.

Wikipedia season-page infobox fields are used as an auditable design source:
the three home pattern tokens and five home colours must all be present.  The
renderer applies those colours to the silhouette of existing PM99 compact kit
records and writes candidate BMPs for MINIESC/NANOESC/RIDIESC.  Existing
archive bytes are read only; no wrong 1998 kit is copied or modified.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import (  # noqa: E402
    discover_riff_palette_resource,
    iter_obfuscated_bmp_records,
    load_riff_palette,
)
from scripts import pm99_kit_raster_v1 as kit_raster  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402

SCHEMA = "pm99-world-2015-kit-materialisation-v1"
USER_AGENT = "pm99-research/2015-16-world-kit-lane (+local historical game mod)"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
FIELDS = ("pattern_la1", "pattern_b1", "pattern_ra1", "leftarm1", "body1", "rightarm1", "shorts1", "socks1")
COLOUR_FIELDS = ("leftarm1", "body1", "rightarm1", "shorts1", "socks1")
PATTERN_GEOMETRIES = {
    "_white_hoops": "horizontal-hoops",
    "_shoulder_stripes_white_stripes": "white-shoulder-stripes",
    "_vneck": "v-neck",
}
WIKI_LANG_BY_CATALOG = {"spain": "es", "italy": "it", "ger": "de", "france": "fr", "portugal": "pt", "russia": "ru", "netherl": "nl", "belgium": "nl", "sweden": "sv", "turkey": "tr", "poland": "pl", "switz": "de", "austria": "de", "denmark": "da", "scots": "en", "greece": "el", "norway": "no", "hungary": "hu", "ukraine": "uk", "ireland": "en", "brazil": "pt", "chile": "es", "arg": "es", "eng": "en"}


class KitMaterialisationError(ValueError):
    """A source page or candidate rendering prerequisite is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _club_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _search_match(title: str, club_name: str) -> bool:
    title_key = _club_key(title)
    club_key = _club_key(club_name)
    if not club_key or "201516" not in title_key or "season" not in title_key:
        return False
    # A full club key is too strict for abbreviations such as Betis/Las
    # Palmas. Requiring every meaningful token prevents a neighbouring club's
    # season page from satisfying the identity binding.
    # Parenthetical catalog qualifiers (for example ``Godoy Cruz
    # (Mendoza)``) are source disambiguators, not normally part of the
    # Wikipedia season title.
    source_text = str(club_name).lower()
    primary_name = source_text.split("(", 1)[0]
    tokens = [token for token in re.findall(r"[a-z0-9]+", primary_name) if token not in {"fc", "cf", "sc", "ac", "c", "de", "la", "the"}]
    if not tokens or not all(token in title_key for token in tokens if len(token) >= 3):
        return False
    title_phrase = re.sub(r"^2015(?:–|-)?16\s*", "", str(title).lower())
    title_phrase = re.sub(r"\s+season\s*$", "", title_phrase)
    title_tokens = re.findall(r"[a-z0-9]+", title_phrase)
    source_all = set(re.findall(r"[a-z0-9]+", source_text))
    allowed_suffix = {"fc", "cf", "sc", "ac", "as", "ss", "ssc", "afc", "acf", "c", "de", "la", "the", "club", "football", "city", "united", "real", "cr"}
    extras = [token for token in title_tokens if token not in source_all and token not in allowed_suffix]
    # A title such as River Plate Montevideo is not the Argentine River
    # Plate carrier; disambiguating city/country words are never silently
    # accepted as legal suffixes.
    return not extras


def _native_search_match(title: str, club_name: str) -> bool:
    """Strict identity check for translated season words."""
    key = _club_key(title)
    if "2015" not in key or "16" not in key:
        return False
    lowered = str(title).lower()
    if any(term in lowered for term in ("women", "vrouwen", "femminile", "féminine", "feminino", "femenino", "dames")):
        return False
    primary = str(club_name).lower().split("(", 1)[0]
    tokens = [token for token in re.findall(r"[a-z0-9]+", primary) if len(token) >= 3 and token not in {"the", "club"}]
    return bool(tokens) and all(token in key for token in tokens)


def _title_candidates(club_name: str) -> list[str]:
    name = club_name.strip()
    base = name.split("(", 1)[0].strip()
    aliases: list[str] = []
    if base == "Barcelona":
        aliases += ["FC Barcelona", base]
    elif base == "Milan":
        aliases += ["A.C. Milan", "AC Milan", base]
    elif base == "Betis":
        aliases += ["Real Betis", base]
    elif base == "Real Madrid":
        aliases += ["Real Madrid CF", "Real Madrid C.F.", base]
    elif base == "Bayern Munich":
        aliases += ["FC Bayern Munich", base]
    elif base == "Juventus":
        aliases += ["Juventus F.C.", "Juventus FC", base]
    elif base == "Lazio":
        aliases += ["S.S. Lazio", "SS Lazio", base]
    elif base == "Roma":
        aliases += ["A.S. Roma", "AS Roma", base]
    elif base == "Napoli":
        aliases += ["S.S.C. Napoli", "SSC Napoli", base]
    elif base == "Internazionale":
        aliases += ["Inter Milan", "Internazionale", "F.C. Internazionale Milano"]
    elif base == "Fiorentina":
        aliases += ["ACF Fiorentina", base]
    elif base == "Bayern Munich":
        aliases += ["FC Bayern Munich", "Bayern Munich", "FC Bayern München"]
    elif base == "Hertha Berlin":
        aliases += ["Hertha BSC", base]
    elif base == "Schalke 04":
        aliases += ["FC Schalke 04", base]
    elif base == "Marseille":
        aliases += ["Olympique de Marseille", base]
    elif base == "Lyon":
        aliases += ["Olympique Lyonnais", base]
    elif base == "PSV Eindhoven":
        aliases += ["PSV Eindhoven", "PSV"]
    elif base == "Ajax":
        aliases += ["AFC Ajax", "Ajax"]
    elif base == "Sporting Gijón":
        aliases += ["Sporting de Gijón", "Sporting Gijon"]
    elif base == "Atlético Madrid":
        aliases += ["Atlético Madrid", "Atletico Madrid"]
    # Most season pages use an expanded legal suffix/prefix even when the
    # source catalog uses a short display name.
    aliases += [base, f"FC {base}", f"{base} F.C.", f"{base} FC", f"A.C. {base}", f"A.S. {base}"]
    out: list[str] = []
    for alias in aliases:
        out.append(f"2015–16 {alias} season")
    return list(dict.fromkeys(out))


def _query_wikitext(domain: str, title: str, *, timeout: int = 20) -> dict[str, Any]:
    """Resolve one exact title through MediaWiki and return revision-bound source.

    The old ``action=raw`` route returned redirect bodies and the REST search
    endpoint rate-limited a parallel build.  The action API resolves redirects
    server-side and records the exact revision id/timestamp used by the build.
    """
    response = requests.get(
        f"https://{domain}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "titles": title,
            "redirects": "1",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content|ids|timestamp",
            "format": "json",
            "formatversion": "2",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    if response.status_code != 200:
        return {"status": f"http-{response.status_code}"}
    pages = (response.json().get("query") or {}).get("pages") or []
    if len(pages) != 1 or pages[0].get("missing") is True:
        return {"status": "missing"}
    page = pages[0]
    revisions = page.get("revisions") or []
    if len(revisions) != 1:
        return {"status": "missing-revision"}
    revision = revisions[0]
    text = str(((revision.get("slots") or {}).get("main") or {}).get("content") or "")
    if not text.strip():
        return {"status": "missing-content"}
    return {
        "status": "ok",
        "page_title": str(page.get("title") or title),
        "page_domain": domain,
        "page_id": page.get("pageid"),
        "revision_id": revision.get("revid"),
        "revision_parent_id": revision.get("parentid"),
        "revision_timestamp": revision.get("timestamp"),
        "page_url": f"https://{domain}.wikipedia.org/wiki/{requests.utils.quote(str(page.get('title') or title).replace(' ', '_'))}",
        "wikitext": text,
        "page_sha256": sha256_bytes(text.encode("utf-8")),
    }


def _prefetch_english_pages(clubs: list[Mapping[str, Any]], *, timeout: int = 20) -> dict[int, dict[str, Any]]:
    """Resolve all predictable English season titles in bounded API batches."""
    candidate_titles = list(dict.fromkeys(title for club in clubs for title in _title_candidates(str(club.get("source_club_name") or ""))))
    resolved_pages: list[dict[str, Any]] = []
    for offset in range(0, len(candidate_titles), 50):
        batch = candidate_titles[offset : offset + 50]
        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "titles": "|".join(batch), "redirects": "1", "prop": "info", "format": "json", "formatversion": "2"},
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            if response.status_code != 200:
                continue
            for page in ((response.json().get("query") or {}).get("pages") or []):
                if page.get("missing") is not True and page.get("pageid"):
                    resolved_pages.append({"page_title": str(page.get("title") or ""), "page_id": page.get("pageid")})
        except Exception:
            # Per-club lookup remains the deterministic fallback.
            continue
    found: dict[int, dict[str, Any]] = {}
    for club in clubs:
        carrier = int(club.get("carrier_id") or 0)
        name = str(club.get("source_club_name") or "")
        matches = [page for page in resolved_pages if _search_match(page["page_title"], name)]
        if len(matches) == 1:
            found[carrier] = {"status": "page-found", "page_domain": "en", **matches[0], "attempts": [{"status": "batched-exact-title-resolution"}]}
    return found


def _search_page(club: Mapping[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    name = str(club.get("source_club_name") or "")
    if not name:
        return {"status": "missing-page", "reason": "missing-source-club-name", "attempts": []}
    headers = {"User-Agent": USER_AGENT}
    domains = ["en"]
    native = WIKI_LANG_BY_CATALOG.get(str(club.get("source_country_catalog") or ""))
    if native and native not in domains:
        domains.append(native)
    attempts: list[dict[str, Any]] = []
    # Exact title candidates are resolved through action=query.  This follows
    # redirects and yields revision-bound source without REST search throttling.
    for title in _title_candidates(name):
        try:
            queried = _query_wikitext(domains[0], title, timeout=timeout)
            resolved = str(queried.get("page_title") or title)
            if queried.get("status") == "ok" and _search_match(resolved, name):
                return {"status": "page-found", **{key: value for key, value in queried.items() if key != "status"}, "attempts": attempts + [{"title": title, "resolved_title": resolved, "status": "ok"}]}
            attempts.append({"title": title, "resolved_title": resolved, "status": str(queried.get("status") or "identity-mismatch")})
        except Exception as exc:
            attempts.append({"title": title, "status": f"{type(exc).__name__}: {exc}"})
    # REST search is less aggressively throttled than the legacy list=search
    # API and resolves names such as Juventus FC or clubs whose season title
    # contains a legal suffix not predictable from the catalog.
    try:
        response = requests.get(f"https://{domains[0]}.wikipedia.org/w/rest.php/v1/search/page", params={"q": f"{name} 2015-16 season", "limit": 10}, headers=headers, timeout=timeout)
        if response.status_code == 200:
            pages = response.json().get("pages", [])
            for hit in pages if isinstance(pages, list) else []:
                title = str(hit.get("title") or "")
                if _search_match(title, name):
                    return {"status": "page-found", "page_title": title, "page_domain": domains[0], "page_id": hit.get("id"), "attempts": attempts + [{"status": "rest-search-ok", "title": title}]}
            attempts.append({"status": "rest-search-no-strict-hit", "hit_count": len(pages) if isinstance(pages, list) else 0})
        else:
            attempts.append({"status": f"rest-search-http-{response.status_code}"})
    except Exception as exc:
        attempts.append({"status": f"rest-search-{type(exc).__name__}: {exc}"})
    # Native-language search is a second, auditable source for clubs whose
    # English season article is absent. Require the same club tokens and a
    # 2015/16 year pair; field names are still the stable Football kit
    # template parameters.
    for domain in domains[1:]:
        try:
            response = requests.get(f"https://{domain}.wikipedia.org/w/rest.php/v1/search/page", params={"q": f"{name} 2015 2016", "limit": 20}, headers=headers, timeout=timeout)
            pages = response.json().get("pages", []) if response.status_code == 200 else []
            for hit in pages if isinstance(pages, list) else []:
                title = str(hit.get("title") or "")
                if _native_search_match(title, name):
                    return {"status": "page-found", "page_title": title, "page_domain": domain, "page_id": hit.get("id"), "attempts": attempts + [{"status": "native-search-ok", "domain": domain, "title": title}]}
        except Exception as exc:
            attempts.append({"status": f"native-search-{type(exc).__name__}: {exc}", "domain": domain})
    return {"status": "missing-page", "reason": "no-strict-identity-season-title", "attempts": attempts}


def _fetch_wikitext(page: Mapping[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    title = str(page.get("page_title") or "")
    if not title:
        return {"status": "missing-page", "reason": "no-page-title"}
    try:
        domain = str(page.get("page_domain") or "en")
        response = requests.get(f"https://{domain}.wikipedia.org/w/index.php", params={"title": title, "action": "raw"}, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if response.status_code != 200:
            return {"status": "missing-page", "reason": f"page-http-{response.status_code}"}
        text = response.text
        if not text.strip():
            return {"status": "missing-page", "reason": "page-response-has-no-wikitext"}
        return {"status": "page-fetched", "page_title": title, "page_url": response.url, "wikitext": text, "page_sha256": sha256_bytes(text.encode("utf-8"))}
    except Exception as exc:
        return {"status": "missing-page", "reason": f"page-{type(exc).__name__}: {exc}"}


def parse_home_fields(wikitext: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for field in FIELDS:
        match = re.search(rf"\|\s*{re.escape(field)}\s*=\s*([^\n|}}]+)", wikitext, flags=re.IGNORECASE)
        if match:
            fields[field] = match.group(1).strip()
    missing = [field for field in FIELDS if not fields.get(field)]
    bad_colours = [field for field in COLOUR_FIELDS if fields.get(field) and not re.fullmatch(r"[0-9a-fA-F]{6}", fields[field])]
    if missing:
        return {"status": "missing-home-kit-fields", "missing_fields": missing, "fields": fields}
    if bad_colours:
        return {"status": "invalid-home-kit-colours", "invalid_fields": bad_colours, "fields": fields}
    return {"status": "home-kit-fields-ready", "fields": fields}


def pattern_geometry(token: str) -> str | None:
    """Return only explicitly reviewed generic template geometry names."""
    return PATTERN_GEOMETRIES.get(str(token or "").strip().lower())


def _nearest_palette(rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> int:
    return min(range(len(palette)), key=lambda idx: ((rgb[0] - palette[idx][0]) ** 2 + (rgb[1] - palette[idx][1]) ** 2 + (rgb[2] - palette[idx][2]) ** 2, idx))


def render_candidate(record: Any, fields: Mapping[str, str], palette: list[tuple[int, int, int]]) -> bytes:
    width, height = int(record.width), int(record.height)
    colours = {field: tuple(bytes.fromhex(fields[field])) for field in COLOUR_FIELDS}
    shirt_top = int(height * 0.22)
    shirt_bottom = int(height * 0.60)
    shorts_bottom = int(height * 0.78)
    socks_bottom = int(height * 0.90)

    def colour_at(x: int, y: int) -> tuple[int, int, int] | None:
        if y < shirt_top or y > socks_bottom:
            return None
        if y >= shorts_bottom:
            field = "socks1"
        elif y >= shirt_bottom:
            field = "shorts1"
        elif x < int(width * 0.24):
            field = "leftarm1"
        elif x >= int(width * 0.76):
            field = "rightarm1"
        else:
            field = "body1"
        rgb = colours[field]
        geometry = pattern_geometry(fields["pattern_b1"])
        if geometry == "horizontal-hoops" and field == "body1" and (y // max(1, height // 8)) % 2 == 1:
            return (255, 255, 255)
        if geometry == "white-shoulder-stripes" and field in {"leftarm1", "rightarm1"} and y < int(height * 0.35) and (x % max(1, width // 6)) < max(1, width // 12):
            return (255, 255, 255)
        if geometry == "v-neck" and field == "body1" and y < int(height * 0.18) and abs(x - width // 2) <= max(1, y // 3):
            return (0, 0, 0)
        return rgb

    return kit_raster.rasterize_preserving_native_shading(record, palette, colour_at)


def _write_content_addressed(payload: bytes, root: Path, suffix: str) -> tuple[Path, str]:
    digest = sha256_bytes(payload)
    path = root / digest[:2] / f"{digest}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha256_file(path) != digest:
        raise KitMaterialisationError(f"content-addressed collision: {path}")
    if not path.exists():
        path.write_bytes(payload)
    return path, digest


def _fetch_pattern_layers(pattern_tokens: Mapping[str, str], cache_dir: Path, *, timeout: int = 10) -> dict[str, Any]:
    """Fetch exact Commons Kit_body/left_arm/right_arm layers.

    Wikipedia's infobox permits different tokens for torso and arms, so each
    layer is resolved from its own pattern field. Commons is used directly to
    avoid the scripted-client rate limit on enwiki's redirect endpoint.
    """
    layers: dict[str, Any] = {}
    for part in ("body", "left_arm", "right_arm"):
        stem = str(pattern_tokens.get(part) or "").strip().lstrip("_")
        if not stem:
            return {"status": "missing", "reason": f"empty-{part}-pattern-token"}
        url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/Kit_{part}_{stem}.png"
        index_path = cache_dir / "pattern-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
        if index_path.is_file():
            try:
                cached = json.loads(index_path.read_text(encoding="utf-8"))
                cached_path = Path(str(cached.get("path") or ""))
                if cached_path.is_file() and sha256_file(cached_path) == str(cached.get("sha256")):
                    layers[part] = cached
                    continue
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        for attempt in range(2):
            try:
                response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
                if response.status_code == 429 and attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                if response.status_code != 200:
                    return {"status": "missing", "reason": f"{part}-http-{response.status_code}", "failed_url": url}
                image = Image.open(io.BytesIO(response.content))
                image.verify()
                path, digest = _write_content_addressed(bytes(response.content), cache_dir / "patterns", ".png")
                layers[part] = {"url": url, "path": str(path.resolve()), "sha256": digest, "dimensions": {"width": image.width, "height": image.height}}
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_bytes(canonical_json_bytes(layers[part]))
                break
            except Exception as exc:
                if attempt == 2:
                    return {"status": "missing", "reason": f"{part}-{type(exc).__name__}: {exc}", "failed_url": url}
                time.sleep(0.5 * (attempt + 1))
        if part not in layers:
            return {"status": "missing", "reason": f"{part}-no-valid-response", "failed_url": url}
    return {"status": "ready", "tokens": dict(pattern_tokens), "layers": layers}


def _render_with_pattern_layers(record: Any, layer_info: Mapping[str, Any], palette: list[tuple[int, int, int]]) -> bytes:
    """Composite Wikimedia's exact opaque kit layers into PM99's silhouette."""
    canvas = Image.new("RGB", (100, 100), (255, 255, 255))
    opened: list[Image.Image] = []
    try:
        for part, xy in (("left_arm", (0, 0)), ("body", (31, 0)), ("right_arm", (69, 0))):
            image = Image.open(layer_info["layers"][part]["path"]).convert("RGB")
            opened.append(image)
            canvas.paste(image, xy)
        height = int(record.height)
        shirt_top = int(height * 0.22)
        shirt_bottom = int(height * 0.60)
        source = canvas.resize((int(record.width), shirt_bottom - shirt_top), Image.Resampling.LANCZOS)
        return kit_raster.rasterize_preserving_native_shading(
            record,
            palette,
            lambda x, y: tuple(int(value) for value in source.getpixel((x, y - shirt_top))) if shirt_top <= y < shirt_bottom else None,
        )
    finally:
        for image in opened:
            image.close()


def materialise_kits(manifest: Mapping[str, Any], *, dbdat: Path, cache_dir: Path, output_dir: Path, workers: int = 8) -> dict[str, Any]:
    if manifest.get("schema_version") != "pm99-world-2015-asset-candidate-manifest-v1":
        raise KitMaterialisationError("candidate manifest has wrong schema")
    archives: dict[str, dict[int, Any]] = {}
    archive_hashes: dict[str, str] = {}
    for archive in ARCHIVES:
        path = dbdat / archive
        if not path.is_file():
            raise KitMaterialisationError(f"missing read-only kit archive: {path}")
        archive_hashes[archive] = sha256_file(path)
        archives[archive] = {int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), flags=re.IGNORECASE).group(1)): record for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")}
    try:
        palette, palette_source = runtime_kit_palette(dbdat)
    except ValueError as exc:
        raise KitMaterialisationError(str(exc)) from exc
    clubs = [club for club in manifest.get("clubs", []) if isinstance(club, dict)]
    ready = [club for club in clubs if club.get("source_status") == "source-squad-ready"]
    prefetched_pages = _prefetch_english_pages(ready) if len(ready) > 1 else {}
    def process(club: Mapping[str, Any]) -> dict[str, Any]:
        carrier = int(club.get("carrier_id") or 0)
        page = prefetched_pages.get(carrier) or _search_page(club)
        row: dict[str, Any] = {"carrier_id": carrier, "source_country_catalog": club.get("source_country_catalog"), "source_club_name": club.get("source_club_name"), "source_status": club.get("source_status"), "page": page}
        if page.get("status") != "page-found":
            row.update({"status": "blocked-missing-season-page", "action": "no-write", "reason": page.get("reason")})
            return row
        fetched = ({**page, "status": "page-fetched"} if isinstance(page.get("wikitext"), str) else _fetch_wikitext(page))
        if fetched.get("status") != "page-fetched":
            row.update({"status": "blocked-page-fetch-failed", "action": "no-write", "reason": fetched.get("reason")})
            return row
        row["page"] = {key: value for key, value in fetched.items() if key != "wikitext"}
        page_cache_payload = canonical_json_bytes({"page_title": fetched.get("page_title"), "page_id": fetched.get("page_id"), "wikitext": fetched.get("wikitext")})
        page_cache_path, page_cache_hash = _write_content_addressed(page_cache_payload, cache_dir / "pages", ".json")
        row["page"]["cache_path"] = str(page_cache_path.resolve())
        row["page"]["cache_sha256"] = page_cache_hash
        parsed = parse_home_fields(str(fetched["wikitext"]))
        row["home_kit"] = parsed
        if parsed["status"] != "home-kit-fields-ready":
            row.update({"status": "blocked-missing-home-kit-fields", "action": "no-write", "reason": "all required 2015-16 home template fields are required"})
            return row
        pattern_layers = _fetch_pattern_layers({"body": parsed["fields"]["pattern_b1"], "left_arm": parsed["fields"]["pattern_la1"], "right_arm": parsed["fields"]["pattern_ra1"]}, cache_dir)
        row["pattern_layers"] = {key: value for key, value in pattern_layers.items() if key != "layers"}
        if pattern_layers.get("status") == "ready":
            row["pattern_layers"]["layers"] = pattern_layers["layers"]
        assets: dict[str, Any] = {}
        try:
            for archive in ARCHIVES:
                record = archives[archive].get(carrier)
                if record is None:
                    row.update({"status": "blocked-missing-pm99-carrier-record", "action": "no-write", "reason": f"{archive} has no EQ96 record for carrier"})
                    return row
                payload = (_render_with_pattern_layers(record, pattern_layers, palette) if pattern_layers.get("status") == "ready" else render_candidate(record, parsed["fields"], palette))
                path, digest = _write_content_addressed(payload, output_dir / "candidate-bmps" / archive, ".bmp")
                assets[archive] = {"path": str(path.resolve()), "sha256": digest, "file_name": str(record.file_name), "width": int(record.width), "height": int(record.height)}
        except Exception as exc:
            row.update({"status": "blocked-render-failed", "action": "no-write", "reason": f"{type(exc).__name__}: {exc}"})
            return row
        geometry = pattern_geometry(parsed["fields"]["pattern_b1"])
        if pattern_layers.get("status") == "ready":
            row.update({"status": "release-eligible-exact-pattern-candidate", "action": "write-candidate-only", "pattern_geometry": "wikimedia-layer-composite", "assets": assets})
        elif geometry:
            row.update({"status": "release-eligible-exact-geometry-candidate", "action": "write-candidate-only", "pattern_geometry": geometry, "assets": assets})
        else:
            row.update({"status": "rendered-colour-candidate-pattern-unresolved", "action": "write-candidate-only", "review_blocker": "pattern token is recorded exactly but its historical raster layer requires separate reviewed geometry capture", "assets": assets})
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(process, sorted(ready, key=lambda club: int(club.get("carrier_id") or 0))))
    processed_ids = {row["carrier_id"] for row in rows}
    for club in sorted(clubs, key=lambda value: int(value.get("carrier_id") or 0)):
        if int(club.get("carrier_id") or 0) not in processed_ids:
            rows.append({"carrier_id": int(club.get("carrier_id") or 0), "source_country_catalog": club.get("source_country_catalog"), "source_club_name": club.get("source_club_name"), "source_status": club.get("source_status"), "status": "blocked-not-source-squad-ready", "action": "no-write", "reason": "foreign identity lacks source-ready club binding"})
    rows.sort(key=lambda row: int(row["carrier_id"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    exact_count = counts.get("release-eligible-exact-geometry-candidate", 0) + counts.get("release-eligible-exact-pattern-candidate", 0)
    unresolved_count = counts.get("rendered-colour-candidate-pattern-unresolved", 0)
    return {"schema_version": SCHEMA, "season": "2015-16", "result": "source-only-kit-candidates; no PM99 binary writes", "policy": {"source": "strict Wikipedia season-page home-kit fields plus exact Wikimedia Kit_* pattern layers", "render": "PM99 silhouette is composited from the exact body/arm layers where available; only those or explicitly mapped generic geometry may be release-eligible", "inheritance": "base 1998 EQ96 art is never copied or claimed complete", "scope": "MINIESC/NANOESC/RIDIESC are read-only; candidate BMPs only"}, "coverage": {"foreign_carrier_count": len(clubs), "source_ready_carrier_count": len(ready), "status_counts": dict(sorted(counts.items())), "rendered_colour_candidate_count": unresolved_count, "release_eligible_exact_geometry_candidate_count": exact_count, "release_approved_count": exact_count, "missing_follow_up_count": len(rows) - unresolved_count - exact_count}, "source": {"candidate_manifest_sha256": sha256_bytes(canonical_json_bytes(manifest)), "dbdat": str(dbdat.resolve()), "archive_sha256": archive_hashes, "palette": {**palette_source, "sha256": sha256_file(Path(str(palette_source["path"]))) }}, "rows": rows, "missing_follow_up": [row for row in rows if row["status"] not in {"rendered-colour-candidate-pattern-unresolved", "release-eligible-exact-geometry-candidate", "release-eligible-exact-pattern-candidate"}]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True, help="reserved for page cache artefacts")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        raw, manifest_hash = args.candidate_manifest.read_bytes(), None
        manifest = json.loads(raw.decode("utf-8")); manifest_hash = sha256_bytes(raw)
        result = materialise_kits(manifest, dbdat=args.dbdat.resolve(), cache_dir=args.cache_dir.resolve(), output_dir=args.output_dir.resolve(), workers=args.workers)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KitMaterialisationError) as exc:
        parser.error(str(exc))
    result["source"]["candidate_manifest_file_sha256"] = manifest_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"output": str(args.output), **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
