#!/usr/bin/env python3
"""Build a hash-bound English home-kit layer from Historical Football Kits.

Source graphics remain in the ignored evidence cache and are not redistributed.
The output contains a deterministic, deliberately small PM99 render contract
inferred from the exact dated graphic.  That contract is source-backed but is
still an approximation and remains visible to editorial review.
"""

from __future__ import annotations

import argparse
import copy
import html
import io
import json
import math
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.patch_english80_reference_kits_v2 import COLORS  # noqa: E402
from scripts.season_english_kit_layer_v1 import canonical_json_bytes, english_clubs  # noqa: E402
from scripts.season_stoke_kit_evidence_v1 import HFK_ATTRIBUTION, StokeKitEvidenceError, capture_url  # noqa: E402


SCHEMA = "pm99-season-kit-layer-v1"
INDEX_URL = "https://www.historicalkits.co.uk/English_Football_League/index.html"


class HFKEnglishKitError(ValueError):
    """The HFK evidence cannot be joined to the requested season exactly."""


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", html.unescape(str(value or "")))
    return "".join(char.casefold() for char in text if char.isalnum() and not unicodedata.combining(char))


def _quote_url(url: str) -> str:
    split = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (split.scheme, split.netloc, urllib.parse.quote(split.path, safe="/%"), split.query, split.fragment)
    )


def parse_index(payload: bytes) -> dict[str, dict[str, str]]:
    text = payload.decode("utf-8", errors="replace")
    if not re.search(r"<title>.*English (?:Football )?League Clubs", text, re.I | re.S):
        raise HFKEnglishKitError("HFK index failed English Football League identity gate")
    rows: dict[str, dict[str, str]] = {}
    for href, label in re.findall(r'<a\s+[^>]*href="([^"]+\.html?)"[^>]*>(.*?)</a>', text, re.I | re.S):
        name = re.sub(r"<[^>]+>", "", html.unescape(label)).strip()
        key = _normalise(name)
        if not key or key in {"home", "england", "historicalfootballkits"}:
            continue
        url = urllib.parse.urljoin(INDEX_URL, html.unescape(href))
        url = _quote_url(url)
        if "historicalkits.co.uk/" not in url or "/English_Football_League/" in url:
            continue
        candidate = {"club": name, "page_url": url}
        if key in rows and rows[key] != candidate:
            raise HFKEnglishKitError(f"ambiguous HFK index identity: {name}")
        rows[key] = candidate
        if key == _normalise("AFC Bournemouth"):
            rows[_normalise("Bournemouth")] = candidate
    if len(rows) < 80:
        raise HFKEnglishKitError(f"HFK index returned only {len(rows)} club identities")
    return rows


def _date_interval(label: str) -> tuple[int, int] | None:
    cleaned = re.sub(r"\s+", "", html.unescape(label)).replace("–", "-").replace("—", "-")
    match = re.fullmatch(r"((?:18|19|20)\d{2})-((?:18|19|20)\d{2}|\d{2})", cleaned)
    if not match:
        years = [int(value) for value in re.findall(r"(?:18|19|20)\d{2}", cleaned)]
        if not years:
            return None
        start = years[0]
        end = years[1] if len(years) > 1 else start + 1
        ending_month = re.search(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
            rf"{end}\b",
            label,
            re.I,
        )
        if ending_month and ending_month.group(0)[:3].casefold() in {"aug", "sep", "oct", "nov", "dec"}:
            end += 1
        return start, end
    start = int(match.group(1))
    tail = match.group(2)
    end = int(tail) if len(tail) == 4 else (start // 100) * 100 + int(tail)
    if end <= start:
        end += 100
    return start, end


def _covers_august(label: str) -> bool:
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    if re.match(r"\s*(?:18|19|20)\d{2}(?:\D|$)", label):
        return True
    month_range = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*[-–]\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b",
        label,
        re.I,
    )
    if month_range:
        return months.index(month_range.group(1)[:3].casefold()) <= 7 <= months.index(month_range.group(2)[:3].casefold())
    leading_month = re.match(r"\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", label, re.I)
    return bool(leading_month and months.index(leading_month.group(1)[:3].casefold()) <= 7)


def parse_club_page(payload: bytes, page_url: str, expected_club: str) -> list[dict[str, Any]]:
    text = payload.decode("utf-8", errors="replace")
    title = re.search(r"<title>\s*(.*?)\s*-\s*Historic(?:al)? Football Kits\s*</title>", text, re.I | re.S)
    if not title:
        raise HFKEnglishKitError(f"HFK club page has no exact title: {page_url}")
    title_name = re.sub(r"<[^>]+>", "", html.unescape(title.group(1))).strip()
    expected = _normalise(expected_club)
    actual = _normalise(title_name)
    # HFK sometimes omits City/Town/Athletic suffixes in its visible title;
    # require a strong prefix relationship, never an arbitrary fuzzy match.
    aliases = {(_normalise("Bournemouth"), _normalise("AFC Bournemouth"))}
    if (
        expected != actual
        and (expected, actual) not in aliases
        and not (expected.startswith(actual) or actual.startswith(expected))
    ):
        raise HFKEnglishKitError(
            f"HFK club page identity mismatch: expected {expected_club!r}, got {title_name!r}"
        )
    rows = []
    blocks = re.findall(
        r'<div class="float">(.*?)(?=<div class="float">|<!-- InstanceEndRepeat -->)',
        text,
        re.I | re.S,
    )
    for block in blocks:
        image_match = re.search(r'<img\s+[^>]*src="([^"]+\.gif)"', block, re.I)
        date_match = re.search(r'class="date"[^>]*>.*?-->(.*?)<!--', block, re.I | re.S)
        if not image_match or not date_match:
            continue
        label = re.sub(r"<[^>]+>", "", date_match.group(1)).strip()
        interval = _date_interval(label)
        image_path = html.unescape(image_match.group(1))
        if interval is not None and interval[1] - interval[0] > 10:
            # A handful of HFK captions contain an obvious end-year typo while
            # the immutable image filename carries the normal season interval
            # (for example 2019-2010 beside a 2019-2020 image). Prefer that
            # exact same-entry filename interval; never infer from a neighbour.
            interval = _date_interval(image_path)
        if interval is None:
            continue
        maker_match = re.search(r'class="manufacturer"[^>]*>.*?-->(.*?)<!--', block, re.I | re.S)
        rows.append(
            {
                "from_year": interval[0],
                "to_year": interval[1],
                "date_label": label,
                "image_url": _quote_url(urllib.parse.urljoin(page_url, image_path)),
                "manufacturer": re.sub(r"<[^>]+>", "", maker_match.group(1)).strip()
                if maker_match
                else "",
                "kit_type": "alternate"
                if (
                    re.search(r"\b(?:Away|EUR|European)\b", f"{label} {image_path}", re.I)
                    or re.search(r"\b(?:Special|Anniversary|Centenary|Play\s*-?\s*Off|Final)\b", label, re.I)
                )
                else "home",
                "month_qualified": bool(
                    re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", label, re.I)
                ),
                # A label such as ``2000-March 2001`` starts with the season
                # and therefore covers its opening month; the named month is
                # the end boundary.  Conversely ``April-May 2001`` is a late
                # interval and must not be selected for August 2000.
                "opening_month": _covers_august(label),
            }
        )
    return rows


def _nearest_colour(pixel: tuple[int, int, int]) -> tuple[str, float]:
    best_name = "black"
    best_distance = math.inf
    for name, rgb in COLORS.items():
        distance = sum((int(pixel[index]) - rgb[index]) ** 2 for index in range(3))
        if distance < best_distance:
            best_name, best_distance = name, distance
    return best_name, math.sqrt(best_distance)


def _region_colours(image: Image.Image, box: tuple[float, float, float, float]) -> Counter[str]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    left, top, right, bottom = (
        int(box[0] * width),
        int(box[1] * height),
        int(box[2] * width),
        int(box[3] * height),
    )
    background = rgb.getpixel((0, 0))
    counts: Counter[str] = Counter()
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            pixel = rgb.getpixel((x, y))
            if math.dist(pixel, background) < 28:
                continue
            name, distance = _nearest_colour(pixel)
            if distance <= 105:
                counts[name] += 1
    return counts


def infer_render_contract(payload: bytes, club: str) -> dict[str, Any]:
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    if image.width < 80 or image.height < 150:
        raise HFKEnglishKitError(f"unexpected HFK kit dimensions for {club}: {image.size}")
    torso = _region_colours(image, (0.28, 0.16, 0.72, 0.48))
    shorts = _region_colours(image, (0.30, 0.49, 0.70, 0.69))
    sleeves = _region_colours(image, (0.12, 0.18, 0.88, 0.43))
    ignored = {"cream"}
    ranked = [(name, count) for name, count in torso.most_common() if name not in ignored]
    if not ranked:
        raise HFKEnglishKitError(f"no shirt colours inferred from HFK graphic: {club}")
    primary = ranked[0][0]
    secondary = next((name for name, count in ranked[1:] if count >= ranked[0][1] * 0.16), None)
    shirt_colours = [primary] + ([secondary] if secondary and secondary != primary else [])

    # Compare colour changes along central rows/columns. Sponsor and badge noise
    # is suppressed by voting over several sample lines.
    rgb = image
    background = rgb.getpixel((0, 0))
    horizontal_changes = 0
    vertical_changes = 0
    for y_fraction in (0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35):
        labels = []
        y = int(y_fraction * image.height)
        for x_fraction in tuple(0.30 + index * 0.035 for index in range(12)):
            pixel = rgb.getpixel((int(x_fraction * image.width), y))
            labels.append(None if math.dist(pixel, background) < 28 else _nearest_colour(pixel)[0])
        horizontal_changes += sum(a != b for a, b in zip(labels, labels[1:]) if a and b)
    for x_fraction in tuple(0.30 + index * 0.035 for index in range(12)):
        labels = []
        x = int(x_fraction * image.width)
        for y_fraction in (0.20, 0.225, 0.25, 0.275, 0.30, 0.325, 0.35):
            pixel = rgb.getpixel((x, int(y_fraction * image.height)))
            labels.append(None if math.dist(pixel, background) < 28 else _nearest_colour(pixel)[0])
        vertical_changes += sum(a != b for a, b in zip(labels, labels[1:]) if a and b)

    pattern = "solid"
    if len(shirt_colours) > 1:
        if horizontal_changes >= 12 and horizontal_changes > vertical_changes * 1.3:
            pattern = "vertical_stripes"
        elif vertical_changes >= 12 and vertical_changes > horizontal_changes * 1.3:
            pattern = "hoops"
        else:
            sleeve_top = sleeves.most_common(1)[0][0] if sleeves else primary
            pattern = "sleeves" if sleeve_top != primary else "halves"
    shorts_colour = shorts.most_common(1)[0][0] if shorts else primary
    style: dict[str, Any] = {
        "name": club,
        "pattern": pattern,
        "colors": shirt_colours,
        "shorts": shorts_colour,
        "trim": secondary or primary,
        "notes": "Deterministic PM99-scale approximation inferred from exact dated HFK evidence; editorial review remains available",
    }
    if pattern == "vertical_stripes":
        style["stripe_count"] = 5
    if pattern == "hoops":
        style["band_count"] = 5
    return {"kind": "reviewed-pm99-style", "style": style}


def build_layer(
    source_intake: Mapping[str, Any], cache_dir: Path, *, allow_network: bool,
    overrides: Mapping[str, Any] | None = None,
    provisional_fallback_layers: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    season, clubs = english_clubs(source_intake)
    index_receipt = capture_url(INDEX_URL, cache_dir, allow_network=allow_network)
    index_payload = (cache_dir / index_receipt["relative_path"]).read_bytes()
    index = parse_index(index_payload)
    rows = []
    for club in clubs:
        index_row = index.get(_normalise(club))
        if index_row is None:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": "hfk-index-identity-missing", "source_url": INDEX_URL})
            continue
        page_receipt = capture_url(index_row["page_url"], cache_dir, allow_network=allow_network)
        page_payload = (cache_dir / page_receipt["relative_path"]).read_bytes()
        try:
            entries = parse_club_page(page_payload, index_row["page_url"], club)
        except HFKEnglishKitError as exc:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": "hfk-page-identity-failed", "reason": str(exc), "source_url": index_row["page_url"], "source_cache_sha256": page_receipt["sha256"]})
            continue
        matches = [
            entry
            for entry in entries
            if entry["kit_type"] == "home"
            and entry["from_year"] <= season["start_year"] < entry["to_year"]
            and (
                not entry["month_qualified"]
                or entry["from_year"] < season["start_year"]
                or entry["opening_month"]
            )
            and entry["to_year"] - entry["from_year"] <= 10
        ]
        # HFK numbers sequential same-season variants when a sponsor or other
        # detail changed during the season. Variant 1 is the opening kit; later
        # variants must not make the August selection ambiguous.
        opening_variants = [entry for entry in matches if re.search(r"\s1\s*$", entry["date_label"])]
        if len(matches) > 1 and len(opening_variants) == 1:
            matches = opening_variants
        if len(matches) != 1:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": "hfk-dated-kit-match-not-unique", "reason": f"match-count-{len(matches)}", "source_url": index_row["page_url"], "source_cache_sha256": page_receipt["sha256"]})
            continue
        match = matches[0]
        image_receipt = capture_url(match["image_url"], cache_dir, allow_network=allow_network)
        image_payload = (cache_dir / image_receipt["relative_path"]).read_bytes()
        try:
            contract = infer_render_contract(image_payload, club)
        except (HFKEnglishKitError, OSError) as exc:
            rows.append({"club": club, "policy": "blocked-no-target-season-source", "status": "hfk-render-contract-failed", "reason": str(exc), "source_url": index_row["page_url"], "source_cache_sha256": page_receipt["sha256"], "source_evidence_url": match["image_url"], "source_evidence_sha256": image_receipt["sha256"]})
            continue
        rows.append(
            {
                "club": club,
                "policy": "historical-target-season",
                "status": "source-ready",
                "source_url": index_row["page_url"],
                "source_cache_sha256": page_receipt["sha256"],
                "source_evidence_url": match["image_url"],
                "source_evidence_sha256": image_receipt["sha256"],
                "source_date_label": match["date_label"],
                "source_manufacturer": match["manufacturer"],
                "attribution": HFK_ATTRIBUTION,
                "facts": "home-kit colour and coarse pattern mechanically inferred from the exact dated source graphic",
                "home": contract,
            }
        )
    if overrides is not None:
        if overrides.get("schema_version") == "pm99-season-kit-source-overrides-batch-v1":
            selected = [row for row in overrides.get("seasons") or [] if row.get("season") == season["label"]]
            if len(selected) > 1:
                raise HFKEnglishKitError("kit override batch contains a duplicate season")
            overrides = {
                "schema_version": "pm99-season-kit-source-overrides-v1",
                "season": season["label"],
                "clubs": selected[0].get("clubs") or [] if selected else [],
                "allow_unhashed_source": bool(overrides.get("allow_unhashed_source")),
            }
        if overrides.get("schema_version") != "pm99-season-kit-source-overrides-v1" or overrides.get("season") != season["label"]:
            raise HFKEnglishKitError("kit overrides schema or season does not match source intake")
        by_club = {_normalise(row["club"]): index for index, row in enumerate(rows)}
        seen: set[str] = set()
        for override in overrides.get("clubs") or []:
            club = str(override.get("club") or "")
            key = _normalise(club)
            if not key or key in seen or key not in by_club:
                raise HFKEnglishKitError(f"kit override identity is missing, duplicated, or not selected: {club!r}")
            seen.add(key)
            source_url = str(override.get("source_url") or "")
            style = override.get("style")
            if not source_url.startswith("https://") or not isinstance(style, Mapping):
                raise HFKEnglishKitError(f"kit override lacks HTTPS source or style contract: {club}")
            evidence_status = "hash-captured"
            try:
                receipt = capture_url(source_url, cache_dir, allow_network=allow_network)
            except (OSError, StokeKitEvidenceError):
                if not overrides.get("allow_unhashed_source"):
                    raise
                receipt = {"sha256": None}
                evidence_status = "explicit-source-url-automation-blocked"
            rows[by_club[key]] = {
                "club": club,
                "policy": "historical-target-season",
                "status": "source-ready",
                "source_url": source_url,
                "source_cache_sha256": receipt["sha256"],
                "source_evidence_status": evidence_status,
                "source_date_label": season["label"],
                "attribution": str(override.get("attribution") or ""),
                "facts": str(override.get("facts") or ""),
                "home": {"kind": "reviewed-pm99-style", "style": dict(style)},
            }
    if provisional_fallback_layers:
        fallback_by_club: dict[str, tuple[str, Mapping[str, Any]]] = {}
        for layer in provisional_fallback_layers:
            layer_season = str((layer.get("season") or {}).get("label") or "")
            for row in layer.get("clubs") or []:
                key = _normalise(row.get("club"))
                if row.get("status") != "source-ready" or not isinstance(row.get("home"), Mapping):
                    continue
                if key not in fallback_by_club or layer_season > fallback_by_club[key][0]:
                    fallback_by_club[key] = (layer_season, row)
        for index, row in enumerate(rows):
            if row.get("status") == "source-ready":
                continue
            key = _normalise(row.get("club"))
            prior = fallback_by_club.get(key)
            if prior is None:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", str(row["club"]).casefold()).strip("-")
            season_slug = season["label"].replace("/", "-")
            rows[index] = {
                "club": row["club"],
                "policy": "target-season-url-with-nearest-source-backed-style-provisional",
                "status": "source-ready",
                "source_url": f"https://www.footballkitarchive.com/{slug}-{season_slug}-home-kit/",
                "source_cache_sha256": None,
                "source_evidence_status": "explicit-target-season-url-automation-blocked",
                "source_date_label": season["label"],
                "attribution": "Football Kit Archive; target-season page. PM99 style contract is a declared nearest-season editorial carry-forward.",
                "facts": f"Target-season kit requires visual review; PM99 style carried from {prior[0]}",
                "style_source_season": prior[0],
                "style_source_url": prior[1].get("source_url"),
                "style_source_sha256": prior[1].get("source_evidence_sha256") or prior[1].get("source_cache_sha256"),
                "home": copy.deepcopy(prior[1]["home"]),
            }
    counts = Counter(str(row["status"]) for row in rows)
    return {
        "schema_version": SCHEMA,
        "season": season,
        "policy": {
            "continuing_club": "exact-target-season-HFK-date-range-required",
            "identity": "source-intake-club-to-HFK-index-normalised-exact-join",
            "rendering": "deterministic-coarse-PM99-approximation; no-source-image-redistribution",
            "editorial_status": "source-backed contracts remain reviewable",
        },
        "credits": [{"publisher": "Historical Football Kits", "url": INDEX_URL, "notice": HFK_ATTRIBUTION}],
        "evidence": {"index_url": INDEX_URL, "index_sha256": index_receipt["sha256"]},
        "coverage": {"english_club_count": len(rows), "status_counts": dict(sorted(counts.items()))},
        "clubs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-intake", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-layer", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--provisional-fallback-layer", type=Path, action="append", default=[])
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    intake = json.loads(args.source_intake.read_text(encoding="utf-8"))
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else None
    fallback_layers = [json.loads(path.read_text(encoding="utf-8")) for path in args.provisional_fallback_layer]
    layer = build_layer(
        intake, args.cache_dir, allow_network=args.allow_network, overrides=overrides,
        provisional_fallback_layers=fallback_layers,
    )
    args.output_layer.parent.mkdir(parents=True, exist_ok=True)
    args.output_layer.write_bytes(canonical_json_bytes(layer))
    print(json.dumps(layer["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
