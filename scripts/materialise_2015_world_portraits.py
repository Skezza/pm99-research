#!/usr/bin/env python3
"""Download and convert identity-bound FIFA 16 world portrait candidates.

The command consumes the source-only world candidate manifest and never opens
or writes a game directory.  Each portrait is fetched using its verified FIFA
player id, validated as an image, stored under a SHA-256 content-addressed
cache, and passed through the existing PM99 crop/palette conversion helper.
HTTP, identity, decode, and conversion failures become explicit native-no-photo
rows; no player is substituted with a different carrier's face.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import (  # noqa: E402
    discover_riff_palette_resource,
    iter_minifoto_records,
    load_riff_palette,
)
from prepare_stoke_2015_face_dbdat import (  # noqa: E402
    _build_palette_image,
    _build_replacement_bitmap,
)


SCHEMA = "pm99-world-2015-portrait-materialisation-v1"
USER_AGENT = "pm99-research/2015-16-world-portrait-lane (+local historical game mod)"
_FUTBIN = "https://cdn.futbin.com/content/fifa16/img/players/{player_id}.png"
_SOFIFA = "https://cdn.sofifa.net/players/{folder}/{suffix:03d}/16_120.png"


class PortraitMaterialisationError(ValueError):
    """A source or PM99 conversion prerequisite is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8")), sha256_bytes(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortraitMaterialisationError(f"cannot read JSON: {path}") from exc


def _url_bound_to_id(url: str, player_id: int) -> bool:
    """Validate the numeric player binding in FIFAindex/Futbin/SoFIFA URLs."""
    text = url.rstrip("/")
    direct = re.search(r"/(\d+)\.png$", text, re.IGNORECASE)
    if direct is not None:
        return int(direct.group(1)) == player_id
    sofifa = re.search(r"/players/(\d+)/(\d{3})/16_120\.png$", text, re.IGNORECASE)
    return sofifa is not None and int(sofifa.group(1)) * 1000 + int(sofifa.group(2)) == player_id


def _mirror_urls(player_id: int, source_url: str) -> list[str]:
    """Return deterministic identity-bound mirrors after the manifest URL."""
    # FIFAIndex is retained as provenance, but commonly spends the full
    # timeout returning a challenge page from this environment.  The SoFIFA
    # mirror is known to be reachable with its referer and is therefore first;
    # Futbin is the second fast identity-bound mirror, then the manifest URL.
    candidates = [_SOFIFA.format(folder=player_id // 1000, suffix=player_id % 1000), _FUTBIN.format(player_id=player_id), source_url]
    return list(dict.fromkeys(url for url in candidates if _url_bound_to_id(url, player_id)))


def _validate_image(payload: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("non-positive dimensions")
            return int(width), int(height), str(image.format or "unknown")
    except Exception as exc:
        raise PortraitMaterialisationError(f"image decode failed: {type(exc).__name__}: {exc}") from exc


def _fetch_one(player: Mapping[str, Any], *, timeout: int = 12) -> dict[str, Any]:
    player_id = player.get("fifa16_player_id")
    base: dict[str, Any] = {
        "carrier_id": int(player.get("carrier_id") or 0),
        "slot_index": int(player.get("slot_index") or 0),
        "player_carrier_id": int(player.get("player_carrier_id") or 0),
        "name": str(player.get("name") or ""),
        "fifa16_player_id": player_id,
    }
    portrait = player.get("portrait") if isinstance(player.get("portrait"), dict) else {}
    source_url = str(portrait.get("source_url") or "")
    if not isinstance(player_id, int) or player_id <= 0:
        return {**base, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "missing-positive-fifa16-player-id", "attempts": []}
    urls = _mirror_urls(player_id, source_url)
    if not urls:
        return {**base, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "source-url-is-not-bound-to-fifa16-player-id", "source_url": source_url, "attempts": []}
    attempts: list[dict[str, Any]] = []
    for url in urls:
        try:
            headers = {"User-Agent": USER_AGENT, "Accept": "image/png,image/*;q=0.9"}
            if "cdn.sofifa.net/" in url:
                headers["Referer"] = "https://sofifa.com/"
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code != 200:
                attempts.append({"url": url, "headers": headers, "status": f"http-{response.status_code}"})
                continue
            payload = bytes(response.content)
            width, height, image_format = _validate_image(payload)
            return {**base, "status": "downloaded-source", "source_url": source_url, "download_url": url, "download_headers": headers, "attempts": attempts + [{"url": url, "headers": headers, "status": "ok"}], "payload": payload, "source_dimensions": {"width": width, "height": height, "format": image_format}}
        except Exception as exc:
            attempts.append({"url": url, "headers": headers, "status": f"{type(exc).__name__}: {exc}"})
    return {**base, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "all-identity-bound-source-urls-failed", "source_url": source_url, "attempts": attempts}


def _players(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "pm99-world-2015-asset-candidate-manifest-v1":
        raise PortraitMaterialisationError("candidate manifest has wrong schema")
    selected: list[dict[str, Any]] = []
    for club in manifest.get("clubs", []):
        if not isinstance(club, dict) or club.get("source_status") != "source-squad-ready":
            continue
        for player in club.get("players", []):
            if not isinstance(player, dict):
                continue
            portrait = player.get("portrait") if isinstance(player.get("portrait"), dict) else {}
            if portrait.get("status") != "fifa16-url-candidate":
                continue
            selected.append({**player, "carrier_id": int(club.get("carrier_id") or 0)})
    return sorted(selected, key=lambda row: (int(row["carrier_id"]), int(row.get("slot_index") or 0), int(row.get("player_carrier_id") or 0)))


def _materialise_download(result: Mapping[str, Any], *, cache_dir: Path, output_dir: Path, template: Any, palette_image: Image.Image, palette_rgb: list[tuple[int, int, int]]) -> dict[str, Any]:
    if result.get("status") != "downloaded-source":
        return dict(result)
    payload = result.get("payload")
    if not isinstance(payload, bytes):
        raise PortraitMaterialisationError("download result has no byte payload")
    digest = sha256_bytes(payload)
    cache_path = cache_dir / digest[:2] / f"{digest}.png"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and sha256_file(cache_path) != digest:
        raise PortraitMaterialisationError(f"content-addressed cache collision: {cache_path}")
    if not cache_path.exists():
        cache_path.write_bytes(payload)
    try:
        with Image.open(io.BytesIO(payload)) as source_image:
            bitmap, crop, preview = _build_replacement_bitmap(raw_bitmap_template=template.raw_bitmap, pixel_offset=template.pixel_offset, width=template.width, height=template.height, source_image=source_image, palette_image=palette_image, palette_rgb=palette_rgb, allowed_indices=list(range(len(palette_rgb))))
    except Exception as exc:
        return {key: value for key, value in result.items() if key != "payload"} | {"status": "native-no-photo", "action": "preserve-native-no-photo", "reason": f"pm99-conversion-failed: {type(exc).__name__}: {exc}", "cache_path": str(cache_path.resolve())}
    carrier_id = int(result["carrier_id"])
    slot = int(result["slot_index"])
    converted_path = output_dir / "converted" / f"carrier-{carrier_id:04d}" / f"slot-{slot:02d}-player-{int(result['player_carrier_id']):05d}.bmp"
    preview_path = output_dir / "previews" / f"carrier-{carrier_id:04d}" / f"slot-{slot:02d}-player-{int(result['player_carrier_id']):05d}.png"
    converted_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    converted_path.write_bytes(bitmap)
    preview.save(preview_path, format="PNG", optimize=False, compress_level=9)
    row = {key: value for key, value in result.items() if key != "payload"}
    row.update({"status": "approved-crop-conversion-candidate", "action": "write-candidate-only", "source_sha256": digest, "cache_path": str(cache_path.resolve()), "converted_path": str(converted_path.resolve()), "converted_sha256": sha256_file(converted_path), "preview_path": str(preview_path.resolve()), "preview_sha256": sha256_file(preview_path), "pm99_dimensions": {"width": int(template.width), "height": int(template.height)}, "crop_dimensions": {"width": int(crop.width), "height": int(crop.height)}})
    return row


def materialise_portraits(manifest: Mapping[str, Any], *, minifoto_path: Path, cache_dir: Path, output_dir: Path, workers: int = 16) -> dict[str, Any]:
    players = _players(manifest)
    if not minifoto_path.is_file():
        raise PortraitMaterialisationError(f"MINIFOTO archive has no parseable records: {minifoto_path}")
    records = list(iter_minifoto_records(minifoto_path))
    if not records:
        raise PortraitMaterialisationError(f"MINIFOTO archive has no parseable records: {minifoto_path}")
    palette_path, palette_source = discover_riff_palette_resource(minifoto_path, extra_roots=[minifoto_path.parent, minifoto_path.parent.parent])
    if palette_path is None:
        raise PortraitMaterialisationError("could not resolve PM99 RIFF palette")
    palette_rgb = load_riff_palette(palette_path)
    palette_image = _build_palette_image(palette_rgb)
    template = records[0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        fetched = list(pool.map(_fetch_one, players))
    # Conversion is CPU-bound but independent for each player.  Keep ordered
    # map output so the receipt and candidate paths remain deterministic.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(lambda result: _materialise_download(result, cache_dir=cache_dir, output_dir=output_dir, template=template, palette_image=palette_image, palette_rgb=palette_rgb), fetched))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    successes = [row for row in rows if row["status"] == "approved-crop-conversion-candidate"]
    failures = [row for row in rows if row["status"] == "native-no-photo"]
    pending = [row for row in rows if row["status"] not in {"approved-crop-conversion-candidate", "native-no-photo"}]
    clean_rows = [{key: value for key, value in row.items() if key != "payload"} for row in rows]
    return {"schema_version": SCHEMA, "season": "2015-16", "result": "source-only-portrait-candidates; no PM99 binary writes", "policy": {"source": "FIFA16 player-ID-bound URL or deterministic identity-bound mirror only", "failure": "every HTTP/decode/conversion failure is native-no-photo; no random substitution", "scope": "MINIFOTO.PKF is read-only; outputs are cache/crop/preview candidates"}, "coverage": {"candidate_url_player_count": len(players), "status_counts": dict(sorted(counts.items())), "success_count": len(successes), "native_no_photo_failure_count": len(failures), "pending_count": len(pending)}, "source": {"candidate_manifest_sha256": sha256_bytes(canonical_json_bytes(manifest)), "minifoto_path": str(minifoto_path.resolve()), "minifoto_sha256": sha256_file(minifoto_path), "palette_path": str(palette_path), "palette_source": str(palette_source)}, "successes": successes, "failures": failures, "pending": pending, "rows": clean_rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--minifoto", type=Path, required=True, help="read-only MINIFOTO.PKF used for PM99 bitmap shape/palette")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)
    try:
        manifest, manifest_file_hash = _read_json(args.candidate_manifest)
        result = materialise_portraits(manifest, minifoto_path=args.minifoto.resolve(), cache_dir=args.cache_dir.resolve(), output_dir=args.output_dir.resolve(), workers=args.workers)
    except PortraitMaterialisationError as exc:
        parser.error(str(exc))
    result["source"]["candidate_manifest_file_sha256"] = manifest_file_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"output": str(args.output), **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
