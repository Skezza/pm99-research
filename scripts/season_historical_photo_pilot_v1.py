#!/usr/bin/env python3
"""Acquire dated Commons photographs and render a PM99 comparison pilot."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "scripts", ROOT / "upstream/pm99-skezmod-db-editor"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import discover_riff_palette_resource, iter_minifoto_records, load_riff_palette
from prepare_stoke_2015_face_dbdat import _build_palette_image, _build_replacement_bitmap
from scripts.season_pipeline_v2 import write_canonical_json

API = "https://commons.wikimedia.org/w/api.php"
UA = "PlayPM99/1.0 (historical football research; https://playpm99.com)"
SCHEMA = "pm99-historical-photo-pilot-v1"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def year_from(meta: dict[str, Any]) -> int | None:
    for key in ("DateTimeOriginal", "DateTime"):
        raw = str((meta.get(key) or {}).get("value") or "")
        match = re.search(r"\b(19|20)\d{2}\b", raw)
        if match:
            return int(match.group())
    return None


def search(name: str, club: str, target_year: int, window: int) -> dict[str, Any]:
    params = {
        "action": "query", "generator": "search", "gsrsearch": name,
        "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|timestamp|extmetadata", "iiurlwidth": 640,
        "format": "json", "formatversion": 2,
    }
    response = None
    for attempt in range(5):
        response = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=30)
        if response.status_code != 429:
            break
        time.sleep(min(16, 2 ** attempt))
    assert response is not None
    response.raise_for_status()
    candidates = []
    name_tokens = set(norm(name).split())
    ordered_name_tokens = norm(name).split()
    given_aliases = {"phillip": {"phillip", "phil"}, "steven": {"steven", "steve"}}
    for page in response.json().get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        photo_year = year_from(meta)
        haystack = norm(" ".join((str(page.get("title") or ""), str((meta.get("ObjectName") or {}).get("value") or ""), str((meta.get("ImageDescription") or {}).get("value") or ""))))
        title_tokens = set(norm(str(page.get("title") or "")).split())
        if photo_year is None or abs(photo_year - target_year) > window:
            continue
        if len(name_tokens.intersection(haystack.split())) < min(2, len(name_tokens)):
            continue
        # Search descriptions can mention a player who is not the subject.
        # Require both the given-name (or declared alias) and surname in the
        # file title before allowing automatic selection.
        if len(ordered_name_tokens) >= 2:
            given = given_aliases.get(ordered_name_tokens[0], {ordered_name_tokens[0]})
            if ordered_name_tokens[-1] not in title_tokens or not given.intersection(title_tokens):
                continue
        licence = str((meta.get("LicenseShortName") or {}).get("value") or "")
        licence_url = str((meta.get("LicenseUrl") or {}).get("value") or "")
        if not licence or not licence_url:
            continue
        club_bonus = 1 if norm(club) in haystack else 0
        candidates.append({
            "page_id": page.get("pageid"), "title": page.get("title"),
            "description_url": info.get("descriptionurl"),
            "image_url": info.get("thumburl") or info.get("url"),
            "original_url": info.get("url"), "photo_year": photo_year,
            "photo_date": str((meta.get("DateTimeOriginal") or meta.get("DateTime") or {}).get("value") or ""),
            "date_basis": "DateTimeOriginal" if meta.get("DateTimeOriginal") else "DateTime",
            "licence": licence, "licence_url": licence_url,
            "artist": re.sub(r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value") or "")),
            "description": re.sub(r"<[^>]+>", "", str((meta.get("ImageDescription") or {}).get("value") or "")),
            "score": 100 - 20 * abs(photo_year - target_year) + 5 * club_bonus,
        })
    candidates.sort(key=lambda row: (-row["score"], row["page_id"]))
    return {"name": name, "club": club, "status": "candidate" if candidates else "no-dated-licensed-photo", "candidates": candidates[:5]}


def face_crop(image: Image.Image, cascade: cv2.CascadeClassifier) -> tuple[Image.Image, list[int] | None]:
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(28, 28))
    if len(faces):
        x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        size = int(max(w * 2.4, h * 2.4))
        cx, cy = int(x + w / 2), int(y + h * 0.75)
        left = max(0, min(rgb.shape[1] - size, cx - size // 2))
        top = max(0, min(rgb.shape[0] - size, cy - int(size * .42)))
        right, bottom = min(rgb.shape[1], left + size), min(rgb.shape[0], top + size)
        size = min(right - left, bottom - top)
        return image.crop((left, top, left + size, top + size)), [int(x), int(y), int(w), int(h)]
    width, height = image.size
    size = min(width, height)
    left = (width - size) // 2
    top = max(0, min(height - size, int((height - size) * .18)))
    return image.crop((left, top, left + size, top + size)), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portrait-manifest", type=Path, required=True)
    parser.add_argument("--club", required=True)
    parser.add_argument("--target-year", type=int, required=True)
    parser.add_argument("--year-window", type=int, default=2)
    parser.add_argument("--minifoto", type=Path, required=True)
    parser.add_argument("--cascade", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.portrait_manifest.read_text(encoding="utf-8"))
    players = [row for row in source["players"] if row.get("target_club") == args.club]
    # Commons asks API clients to keep request rates modest. Discovery is
    # intentionally serial; the small delay avoids burst throttling.
    rows = []
    for player in players:
        rows.append(search(player["name"], args.club, args.target_year, args.year_window))
        time.sleep(.35)
    by_name = {row["name"]: row for row in players}
    records = list(iter_minifoto_records(args.minifoto))
    palette_path, _ = discover_riff_palette_resource(args.minifoto, extra_roots=[args.minifoto.parent, args.minifoto.parent.parent])
    if not records or palette_path is None:
        parser.error("MINIFOTO template or palette unavailable")
    palette = load_riff_palette(palette_path)
    palette_image = _build_palette_image(palette)
    cascade = cv2.CascadeClassifier(str(args.cascade))
    if cascade.empty():
        parser.error("face detector cascade is invalid")
    args.output_root.mkdir(parents=True, exist_ok=True)
    accepted = []
    for result in rows:
        if not result["candidates"]:
            continue
        try:
            evaluated = []
            for candidate in result["candidates"]:
                response = requests.get(candidate["image_url"], headers={"User-Agent": UA}, timeout=30)
                response.raise_for_status()
                with Image.open(io.BytesIO(response.content)) as opened:
                    original = ImageOps.exif_transpose(opened).convert("RGB")
                cropped, face = face_crop(original, cascade)
                if face is None:
                    continue
                face_fraction = (face[2] * face[3]) / max(1, original.width * original.height)
                evaluated.append((candidate["score"] + min(30, face_fraction * 600), candidate, response.content, cropped, face))
            if not evaluated:
                result["conversion_error"] = "no-candidate-with-detectable-face"
                continue
            _quality, selected, payload, cropped, face = max(evaluated, key=lambda item: item[0])
            carrier = int(by_name[result["name"]]["carrier_id"])
            bitmap, _prepared, preview = _build_replacement_bitmap(
                raw_bitmap_template=records[0].raw_bitmap, pixel_offset=records[0].pixel_offset,
                width=records[0].width, height=records[0].height, source_image=cropped,
                palette_image=palette_image, palette_rgb=palette, allowed_indices=list(range(len(palette))),
            )
            source_path = args.output_root / "sources" / f"J96{carrier:05d}.jpg"
            preview_path = args.output_root / "previews" / f"J96{carrier:05d}.png"
            bitmap_path = args.output_root / "converted" / f"J96{carrier:05d}.BMP"
            for path in (source_path, preview_path, bitmap_path): path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(source_path, "JPEG", quality=92)
            preview.save(preview_path, "PNG")
            bitmap_path.write_bytes(bitmap)
            accepted.append({**selected, "name": result["name"], "club": args.club, "carrier_id": carrier,
                "face_detection": face, "source_sha256": hashlib.sha256(payload).hexdigest(),
                "source_path": str(source_path.resolve()), "preview_path": str(preview_path.resolve()),
                "bitmap_path": str(bitmap_path.resolve()), "review_status": "automatic-candidate-needs-visual-review"})
        except Exception as exc:
            result["conversion_error"] = f"{type(exc).__name__}: {exc}"
    tiles = []
    font = ImageFont.load_default()
    for row in accepted[:12]:
        source_image = Image.open(row["source_path"]).convert("RGB").resize((150, 150), Image.Resampling.LANCZOS)
        preview = Image.open(row["preview_path"]).convert("RGB").resize((96, 96), Image.Resampling.NEAREST)
        tile = Image.new("RGB", (260, 205), "#20242b")
        tile.paste(source_image, (0, 0)); tile.paste(preview, (158, 27))
        draw = ImageDraw.Draw(tile)
        draw.text((4, 155), row["name"][:35], fill="white", font=font)
        draw.text((4, 172), f"Photo: {row['photo_date'][:10]} | {row['licence']}", fill="#d0d0d0", font=font)
        draw.text((4, 188), "source crop                 PM99", fill="#9bb7d4", font=font)
        tiles.append(tile)
    sheet = Image.new("RGB", (780, 205 * ((len(tiles) + 2) // 3)), "#11151a")
    for index, tile in enumerate(tiles): sheet.paste(tile, ((index % 3) * 260, (index // 3) * 205))
    sheet_path = args.output_root / "historical-photo-sample.png"
    sheet.save(sheet_path, "PNG")
    receipt = {"schema_version": SCHEMA, "generated_at": datetime.now().astimezone().isoformat(),
        "season": source.get("season"), "club": args.club, "target_year": args.target_year,
        "policy": "dated Wikimedia Commons photograph within declared year window; visual approval still required",
        "coverage": {"players": len(players), "dated_licensed_candidates": len(accepted), "no_candidate": len(players) - len(accepted)},
        "players": rows, "accepted_candidates": accepted, "sample_sheet": str(sheet_path.resolve())}
    write_canonical_json(args.output_root / "historical-photo-receipt.json", receipt)
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
