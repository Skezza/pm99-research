#!/usr/bin/env python3
"""Capture and render-contract Stoke home-kit evidence for the 25 seasons.

The Historical Football Kits graphics are fetched only into the ignored local
evidence cache so their bytes can be hash-bound.  They are never copied into a
release.  PM99 artwork is independently rendered from the reviewed factual
colour/pattern contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable


SCHEMA = "pm99-stoke-home-kit-evidence-matrix-v1"
HFK_PAGE = "https://www.historicalkits.co.uk/Stoke_City/Stoke_City.htm"
HFK_ATTRIBUTION = "Copyright Historical Football Kits and reproduced by kind permission."
MACRON_2023 = "https://about.macron.com/en/news/kit-launches/tradition-and-sustainability-for-stoke-city-fcs-new-home-shirts/"
MACRON_2024 = "https://about.macron.com/en/news/kit-launches/macrons-new-home-kit-for-stoke-city-fc-conveys-the-clubs-close-ties-to-the-city-and-its-industrial-past/"
MACRON_2025 = "https://about.macron.com/en/news/kit-launches/an-innovative-design-chosen-by-the-fans-in-the-2025-26-home-kit-made-by-macron-for-stoke-city-fc/"
TARGET_SEASONS = tuple(
    f"{year}/{str(year + 1)[-2:]}" for year in range(2000, 2026) if year != 2015
)


class StokeKitEvidenceError(ValueError):
    """Evidence is missing, ambiguous, or does not identify Stoke and season."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PM99RE-kit-evidence/1.0 (local non-commercial research)"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def capture_url(url: str, cache_dir: Path, *, allow_network: bool, fetcher: Callable[[str], bytes] = _fetch) -> dict[str, Any]:
    index_path = cache_dir / "url-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
    if index_path.is_file():
        row = json.loads(index_path.read_text(encoding="utf-8"))
        blob = cache_dir / str(row.get("relative_path") or "")
        if blob.is_file() and sha256_bytes(blob.read_bytes()) == row.get("sha256"):
            return row
    if not allow_network:
        raise StokeKitEvidenceError(f"evidence cache miss with network disabled: {url}")
    payload = fetcher(url)
    digest = sha256_bytes(payload)
    blob = cache_dir / "blobs" / digest[:2] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    if blob.exists() and blob.read_bytes() != payload:
        raise StokeKitEvidenceError(f"content-addressed collision: {blob}")
    if not blob.exists():
        blob.write_bytes(payload)
    row = {"url": url, "sha256": digest, "byte_count": len(payload), "relative_path": str(blob.relative_to(cache_dir))}
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(canonical_json_bytes(row))
    return row


def parse_hfk_entries(page: bytes) -> list[dict[str, str]]:
    text = page.decode("utf-8", errors="replace")
    if not re.search(r"<title>\s*Stoke City\s*-\s*Historical Football Kits\s*</title>", text, re.I):
        raise StokeKitEvidenceError("HFK page failed exact Stoke City identity gate")
    rows = []
    for block in re.findall(r'<div class="float">(.*?)(?=<div class="float">|<!-- InstanceEndRepeat -->)', text, re.S):
        image = re.search(r'<img\s+src="([^"]+\.gif)"', block, re.I)
        date = re.search(r'class="date"[^>]*>.*?-->(.*?)<!--', block, re.S | re.I)
        maker = re.search(r'class="manufacturer"[^>]*>.*?-->(.*?)<!--', block, re.S | re.I)
        if not image or not date:
            continue
        label = re.sub(r"<[^>]+>", "", date.group(1)).strip()
        match = re.fullmatch(r"((?:19|20)\d{2})-((?:19|20)\d{2})", label)
        if not match:
            continue
        image_url = urllib.parse.urljoin(HFK_PAGE, image.group(1))
        rows.append({"from_year": match.group(1), "to_year": match.group(2), "date_label": label, "image_url": image_url, "manufacturer": re.sub(r"<[^>]+>", "", maker.group(1)).strip() if maker else ""})
    return rows


def _style(*, trim: str = "red", detail: str = "straight") -> dict[str, Any]:
    return {
        "kind": "reviewed-pm99-style",
        "style": {
            "name": "Stoke City",
            "pattern": "vertical_stripes",
            "colors": ["red", "white"],
            "shorts": "white",
            "trim": trim,
            "stripe_count": 5,
            "notes": f"PM99-scale independent rendering of source-evidenced {detail} red/white vertical stripes and white shorts",
        },
    }


def _recent_specs() -> dict[str, dict[str, str]]:
    return {
        "2023/24": {"title": "2023–24 Stoke City F.C. season", "facts_url": MACRON_2023, "facts": "narrow red/white vertical stripes; white shorts; black/red/white trim"},
        "2024/25": {"title": "2024–25 Stoke City F.C. season", "facts_url": MACRON_2024, "facts": "broad red/white vertical stripes; white shorts; black trim"},
        "2025/26": {"title": "2025–26 Stoke City F.C. season", "facts_url": MACRON_2025, "facts": "wavy red/white vertical stripes; white shorts; black trim"},
    }


def _wikipedia_export(title: str) -> str:
    return "https://en.wikipedia.org/wiki/Special:Export/" + urllib.parse.quote(title.replace(" ", "_"), safe="_.()")


def parse_wikipedia_home_export(payload: bytes, expected_title: str) -> dict[str, Any]:
    root = ET.fromstring(payload)
    namespace = {"mw": "http://www.mediawiki.org/xml/export-0.11/"}
    title = root.findtext(".//mw:page/mw:title", namespaces=namespace)
    if title != expected_title:
        raise StokeKitEvidenceError(f"Wikipedia export identity mismatch: expected {expected_title!r}, got {title!r}")
    revision = root.find(".//mw:page/mw:revision", namespace)
    if revision is None:
        raise StokeKitEvidenceError("Wikipedia export has no revision")
    text = revision.findtext("mw:text", default="", namespaces=namespace)
    fields = {}
    for key in ("pattern_la1", "pattern_b1", "pattern_ra1", "leftarm1", "body1", "rightarm1", "shorts1", "socks1"):
        match = re.search(rf"(?i)\|\s*{key}\s*=\s*([^\n|}}]+)", text)
        if not match or not match.group(1).strip():
            raise StokeKitEvidenceError(f"Wikipedia export lacks exact home field {key}: {expected_title}")
        fields[key] = match.group(1).strip()
    return {"revision_id": int(revision.findtext("mw:id", namespaces=namespace) or 0), "revision_timestamp": revision.findtext("mw:timestamp", namespaces=namespace), "fields": fields}


def build_matrix(cache_dir: Path, *, allow_network: bool, fetcher: Callable[[str], bytes] = _fetch) -> dict[str, Any]:
    page_cache = capture_url(HFK_PAGE, cache_dir, allow_network=allow_network, fetcher=fetcher)
    page = (cache_dir / page_cache["relative_path"]).read_bytes()
    entries = parse_hfk_entries(page)
    rows = []
    for season in TARGET_SEASONS:
        start = int(season[:4])
        if start <= 2022:
            matches = [row for row in entries if int(row["from_year"]) <= start < int(row["to_year"])]
            if len(matches) != 1:
                raise StokeKitEvidenceError(f"HFK exact dated identity match count for {season}: {len(matches)}")
            match = matches[0]
            image_cache = capture_url(match["image_url"], cache_dir, allow_network=allow_network, fetcher=fetcher)
            trim = "black" if season in {"2000/01", "2022/23"} else "red"
            rows.append({
                "season": season, "club": "Stoke City", "status": "source-ready",
                "source": {"publisher": "Historical Football Kits", "page_url": HFK_PAGE, "page_sha256": page_cache["sha256"], "date_label": match["date_label"], "manufacturer": match["manufacturer"], "evidence_url": match["image_url"], "evidence_sha256": image_cache["sha256"], "attribution": HFK_ATTRIBUTION},
                "facts": "red/white vertical-striped shirt; white shorts", "render_contract": _style(trim=trim),
            })
            continue
        spec = _recent_specs()[season]
        export_url = _wikipedia_export(spec["title"])
        evidence = capture_url(export_url, cache_dir, allow_network=allow_network, fetcher=fetcher)
        payload = (cache_dir / evidence["relative_path"]).read_bytes()
        parsed = parse_wikipedia_home_export(payload, spec["title"])
        article_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(spec["title"].replace(" ", "_"), safe="_.()")
        rows.append({
            "season": season, "club": "Stoke City", "status": "source-ready",
            "source": {"publisher": "Wikipedia", "page_url": article_url, "page_sha256": evidence["sha256"], "evidence_url": export_url, "evidence_sha256": evidence["sha256"], "revision_id": parsed["revision_id"], "revision_timestamp": parsed["revision_timestamp"], "attribution": "Wikipedia contributors (CC BY-SA); factual kit description cross-checked against Macron", "facts_url": spec["facts_url"]},
            "facts": spec["facts"], "render_contract": {"kind": "wikipedia-template-fields", "fields": parsed["fields"]},
        })
    return {
        "schema_version": SCHEMA,
        "policy": {"identity": "exact Stoke City and exact dated season/range", "rendering": "independent PM99-scale factual approximation; no source image redistribution", "fallback": "none"},
        "coverage": {"target_seasons": len(TARGET_SEASONS), "source_ready": len(rows), "gaps": len(TARGET_SEASONS) - len(rows)},
        "credits": [{"publisher": "Historical Football Kits", "url": HFK_PAGE, "notice": HFK_ATTRIBUTION}, {"publisher": "Wikipedia", "url": "https://en.wikipedia.org/", "notice": "Wikipedia contributors; CC BY-SA"}, {"publisher": "Macron", "url": MACRON_2023}],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    matrix = build_matrix(args.cache_dir, allow_network=args.allow_network)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(matrix))
    print(json.dumps(matrix["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
