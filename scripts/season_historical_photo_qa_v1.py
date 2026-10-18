#!/usr/bin/env python3
"""Conservative identity, date and framing QA for a historical photo pilot."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "scripts", ROOT / "upstream/pm99-skezmod-db-editor"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from app.minifoto_bitmap_archive import discover_riff_palette_resource, iter_minifoto_records, load_riff_palette
from prepare_stoke_2015_face_dbdat import _build_palette_image, _build_replacement_bitmap
from scripts.season_pipeline_v2 import write_canonical_json

UA = "PlayPM99/1.0 (historical football research; https://playpm99.com)"
MIN_SIMILARITY = 0.42
MIN_MARGIN = 0.08


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as opened:
        rgb = np.asarray(ImageOps.exif_transpose(opened).convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def faces(detector, image):
    detector.setInputSize((image.shape[1], image.shape[0]))
    _, found = detector.detect(image)
    return found if found is not None else []


def fifa_bytes(row, cache):
    url = row.get("source_image_url")
    if not url:
        return None
    key = sha(url.encode())
    path = cache / "url-payloads" / key[:2] / (key + ".bin")
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if sha(data) == row.get("source_sha256") else None


def photo_bytes(url, cache):
    key = sha(url.encode())
    path = cache / key[:2] / (key + ".bin")
    if path.is_file():
        return path.read_bytes()
    response = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    data = response.content
    decode(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def matched_face(photo, reference, detector, recognizer):
    reference_faces = faces(detector, reference)
    photo_faces = faces(detector, photo)
    if len(reference_faces) != 1 or len(photo_faces) == 0:
        return None, {"reason": "face-detection-incomplete", "photo_faces": len(photo_faces)}
    ref = recognizer.feature(recognizer.alignCrop(reference, reference_faces[0]))
    scored = sorted(
        ((float(recognizer.match(ref, recognizer.feature(recognizer.alignCrop(photo, face)),
                                 cv2.FaceRecognizerSF_FR_COSINE)), index)
         for index, face in enumerate(photo_faces)),
        reverse=True,
    )
    best, index = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else None
    detail = {"similarity": round(best, 4), "runner_up": round(runner_up, 4) if runner_up is not None else None,
              "photo_faces": len(photo_faces)}
    if best < MIN_SIMILARITY or runner_up is not None and best - runner_up < MIN_MARGIN:
        return None, {**detail, "reason": "identity-match-uncertain"}
    face = photo_faces[index]
    if min(face[2], face[3]) < 65:
        return None, {**detail, "reason": "face-too-small"}
    return face, detail


def tight_crop(photo, face):
    x, y, width, height = map(float, face[:4])
    side = max(width, height) * 1.65
    left = x + width / 2 - side / 2
    top = y + height * .56 - side * .43
    if left < 0 or top < 0 or left + side > photo.shape[1] or top + side > photo.shape[0]:
        return None
    rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb).crop((int(left), int(top), int(left + side), int(top + side)))


def make_sheet(rows, fifa, output):
    sheet = Image.new("RGB", (900, max(215, ((len(rows) + 4) // 5) * 215)), "#11151a")
    font = ImageFont.load_default()
    for index, row in enumerate(rows):
        tile = Image.new("RGB", (180, 215), "#242a32")
        selected = row.get("selected")
        if selected:
            crop = Image.open(selected["crop"]).convert("RGB").resize((112, 112))
            preview = Image.open(selected["preview"]).convert("RGB").resize((56, 56), Image.Resampling.NEAREST)
            tile.paste(crop, (5, 5))
            tile.paste(preview, (119, 30))
        else:
            path = fifa[row["carrier_id"]].get("preview_path")
            if path and Path(path).is_file():
                tile.paste(Image.open(path).convert("RGB").resize((112, 112), Image.Resampling.NEAREST), (5, 5))
        draw = ImageDraw.Draw(tile)
        draw.text((5, 125), row["name"][:25], fill="white", font=font)
        draw.text((5, 145), row["status"], fill="#b9d5f0", font=font)
        draw.text((5, 165), row["reason"][:26], fill="#cccccc", font=font)
        if selected:
            draw.text((5, 185), selected["photo_date"][:10], fill="#cccccc", font=font)
        sheet.paste(tile, ((index % 5) * 180, (index // 5) * 215))
    path = output / "club-photo-qa-sheet.png"
    sheet.save(path)
    return path


def run(args):
    fifa_doc = json.loads(args.fifa_manifest.read_text())
    discovery = json.loads(args.discovery_receipt.read_text())
    fifa = {int(p["carrier_id"]): p for p in fifa_doc["players"] if p.get("target_club") == discovery["club"]}
    discovered = {p["name"]: p for p in discovery["players"]}
    detector = cv2.FaceDetectorYN_create(str(args.detector), "", (320, 320), score_threshold=.75)
    recognizer = cv2.FaceRecognizerSF_create(str(args.recognizer), "")
    records = list(iter_minifoto_records(args.minifoto))
    palette_path, _ = discover_riff_palette_resource(args.minifoto, extra_roots=[args.minifoto.parent, args.minifoto.parent.parent])
    if not records or palette_path is None:
        raise ValueError("PM99 minifoto template or palette missing")
    palette = load_riff_palette(palette_path)
    palette_image = _build_palette_image(palette)
    args.output_root.mkdir(parents=True, exist_ok=True)
    outcomes = []
    for carrier, player in sorted(fifa.items()):
        name = player["name"]
        reference_data = fifa_bytes(player, args.fifa_cache)
        row = {"name": name, "carrier_id": carrier, "status": "fifa-fallback" if reference_data else "no-photo",
               "reason": "no-approved-historical-photo", "attempts": []}
        if reference_data:
            reference = decode(reference_data)
            for candidate in discovered.get(name, {}).get("candidates", []):
                attempt = {"title": candidate["title"], "source_page": candidate["description_url"],
                           **{key: candidate.get(key) for key in ("photo_date", "date_basis", "licence",
                              "licence_url", "artist", "image_url", "original_url")}}
                try:
                    taken = date.fromisoformat(candidate["photo_date"][:10])
                    if not date.fromisoformat(args.season_start) <= taken <= date.fromisoformat(args.season_end):
                        attempt["reason"] = "outside-season-date"
                        row["attempts"].append(attempt)
                        continue
                    data = photo_bytes(candidate["image_url"], args.photo_cache)
                    photo = decode(data)
                    face, detail = matched_face(photo, reference, detector, recognizer)
                    attempt.update(detail)
                    if face is None:
                        row["attempts"].append(attempt)
                        continue
                    crop = tight_crop(photo, face)
                    if crop is None:
                        attempt["reason"] = "face-too-close-to-edge"
                        row["attempts"].append(attempt)
                        continue
                    bitmap, _, preview = _build_replacement_bitmap(
                        raw_bitmap_template=records[0].raw_bitmap, pixel_offset=records[0].pixel_offset,
                        width=records[0].width, height=records[0].height, source_image=crop,
                        palette_image=palette_image, palette_rgb=palette,
                        allowed_indices=list(range(len(palette))))
                    basename = f"J96{carrier:05d}"
                    paths = {"crop": args.output_root / "crops" / (basename + ".png"),
                             "preview": args.output_root / "previews" / (basename + ".png"),
                             "bitmap": args.output_root / "converted" / (basename + ".BMP")}
                    for path in paths.values():
                        path.parent.mkdir(parents=True, exist_ok=True)
                    crop.save(paths["crop"])
                    preview.save(paths["preview"])
                    paths["bitmap"].write_bytes(bitmap)
                    row["status"] = "photo-candidate"
                    row["reason"] = "identity-and-framing-pass"
                    row["selected"] = {**attempt, "source_sha256": sha(data),
                                       "bitmap_sha256": sha(bitmap),
                                       **{key: str(path.resolve()) for key, path in paths.items()}}
                    row["attempts"].append(attempt)
                    break
                except (ValueError, OSError, requests.RequestException, cv2.error) as exc:
                    attempt["reason"] = "candidate-error:" + type(exc).__name__ + ":" + str(exc)[:120]
                row["attempts"].append(attempt)
        outcomes.append(row)
    sheet = make_sheet(outcomes, fifa, args.output_root)
    counts = {status: sum(row["status"] == status for row in outcomes)
              for status in sorted({row["status"] for row in outcomes})}
    receipt = {"schema_version": "pm99-historical-photo-qa-v1", "club": discovery["club"],
               "season": discovery["season"], "season_dates": [args.season_start, args.season_end],
               "thresholds": {"similarity": MIN_SIMILARITY, "margin": MIN_MARGIN,
                              "minimum_face_pixels": 65, "crop_multiplier": 1.65},
               "input_hashes": {"fifa_manifest": sha(args.fifa_manifest.read_bytes()),
                                "discovery_receipt": sha(args.discovery_receipt.read_bytes()),
                                "detector": sha(args.detector.read_bytes()),
                                "recognizer": sha(args.recognizer.read_bytes())},
               "counts": counts, "players": outcomes, "sheet": str(sheet.resolve())}
    write_canonical_json(args.output_root / "historical-photo-qa.json", receipt)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fifa-manifest", "discovery-receipt", "fifa-cache", "photo-cache", "minifoto",
                 "detector", "recognizer", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--season-start", default="2012-07-01", help="earliest permitted photo date")
    parser.add_argument("--season-end", default="2015-06-30")
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
