#!/usr/bin/env python3
"""Apply provenance-recorded close-era headshots to an English-92 PM99 game.

This is a deliberately conservative artwork stage.  A player receives a new
minifoto only when the season compiler made an identity-safe FIFA 16 match or
its explicitly labelled FIFA 15/17--19 close-era fallback. The image URL is a
Futbin CDN rendition keyed by that verified player id; it is already a
contemporary head-and-shoulders image rather than an inferred web-search
result. The per-player receipt retains both the identity match method and the
actual image source used.

Existing carrier faces are replaced in ``MINIFOTO.PKF``.  Players without an
archive record receive a supported loose ``DBDAT/MINIFOTO/J96xxxxx.BMP``.  A
player with no identity-safe FIFA source is *not* assigned an unrelated 1999
carrier face: PM99's native no-photo state is written and the precise reason
is kept in the receipt. Portrait research therefore fails open; it cannot
block a database release or leave an unrelated carrier face visible.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR) not in sys.path:
    sys.path.insert(0, str(EDITOR))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from app.minifoto_bitmap_archive import (  # noqa: E402
    discover_riff_palette_resource,
    iter_minifoto_records,
    iter_minifoto_records_from_bytes,
    load_riff_palette,
)
from prepare_stoke_2015_face_dbdat import (  # noqa: E402
    _build_palette_image,
    _build_replacement_bitmap,
)


CDN = "https://cdn.futbin.com/content/fifa{edition}/img/players/{player_id}.png"
SOFIFA_CDN = "https://cdn.sofifa.net/players/{folder}/{suffix}/{edition}_120.png"
USER_AGENT = "pm99-research/2015-16-face-stage (+local historical game mod)"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _source_candidates(item: dict[str, Any]) -> list[tuple[str, str]]:
    source = str(item.get("portrait_source") or "").strip().lower()
    player_id = str(item.get("portrait_player_id") or item.get("fifa16_player_id") or "").strip()
    if not player_id:
        return []
    if source.startswith("fifa") and source[4:].isdigit():
        first = source[4:]
    else:
        first = "16"
    # A small number of FIFA 16 FUT entries no longer have a downloadable
    # Fifa16 image. The same verified EA id in the immediately following
    # edition is still a contemporary image and is explicitly recorded as a
    # fallback; do not silently substitute a random player image.
    editions = [first]
    for edition in ("15", "16", "17", "18", "19"):
        if edition not in editions and int(edition) >= int(first):
            editions.append(edition)
    return [(edition, player_id) for edition in editions]


def _manual_source(item: dict[str, Any]) -> dict[str, str] | None:
    """Return an explicitly reviewed non-FIFA artwork source, if present.

    The normal release path is deliberately FIFA-edition-only.  A very small
    lower-league tail has no surviving rendition on either the FUTBIN or
    SoFIFA CDN, however, so a named source ledger can supply a portrait after
    identity review.  It is intentionally *not* silently folded into the
    FIFA path: its source date and provenance remain visible in the receipt.
    """
    url = str(item.get("manual_source_url") or "").strip()
    if not url.startswith(("https://", "http://")):
        return None
    return {
        "url": url,
        "label": str(item.get("manual_source_label") or "reviewed-manual-portrait"),
        "temporal_note": str(item.get("manual_source_temporal_note") or ""),
        "identity_evidence_url": str(item.get("manual_source_identity_evidence_url") or ""),
    }


def _manual_source_crop(item: dict[str, Any], image: Image.Image) -> Image.Image:
    """Apply an explicitly reviewed, normalised crop for a manual source.

    The close-era FIFA sources are already portrait assets.  A manual source
    can instead be a dated match or signing photograph, where blindly taking
    its centre square can retain a second person or miss the player's face.
    A source ledger may therefore provide ``source_crop`` as normalised
    ``left``, ``top``, ``width`` and ``height`` values.  This remains a
    source-specific, auditable decision rather than an inferred face crop.
    """
    raw = item.get("manual_source_crop")
    if raw is None:
        return image
    if not isinstance(raw, dict):
        raise ValueError("manual source crop must be an object")
    try:
        left = float(raw["left"])
        top = float(raw["top"])
        width = float(raw["width"])
        height = float(raw["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("manual source crop requires numeric left, top, width and height") from exc
    if left < 0 or top < 0 or width <= 0 or height <= 0 or left + width > 1 or top + height > 1:
        raise ValueError("manual source crop must fit within the normalised source image")
    source_width, source_height = image.size
    crop_left = int(round(left * source_width))
    crop_top = int(round(top * source_height))
    crop_right = int(round((left + width) * source_width))
    crop_bottom = int(round((top + height) * source_height))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        raise ValueError("manual source crop resolved to an empty image")
    return image.crop((crop_left, crop_top, crop_right, crop_bottom))


def _disable_archive_minifoto_record(archive: bytearray, *, record_offset: int) -> None:
    """Use PM99's normal no-photo state without repacking the PKF archive.

    The first byte of an active bitmap directory record is ``0x02``. Changing
    only that byte to zero keeps every offset and image payload intact, while
    making the matching `J96xxxxx.BMP` lookup miss.
    """
    if record_offset < 0 or record_offset >= len(archive) or archive[record_offset] != 0x02:
        raise ValueError("MINIFOTO directory record is not an active bitmap entry")
    archive[record_offset] = 0


def _set_native_no_photo(
    *,
    entry: dict[str, Any],
    record_id: int,
    archive: bytearray,
    records: dict[int, Any],
    loose_root: Path,
    reason: str,
) -> None:
    """Remove any inherited portrait while preserving PM99's archive shape.

    A missing historical image is not an error condition.  The important
    guardrail is that it must never fall through to the original carrier's
    unrelated portrait.  Disabling the active directory byte is PM99's native
    no-photo representation and does not repack offsets or image payloads.
    """
    loose_path = loose_root / f"J96{record_id:05d}.BMP"
    loose_was_present = loose_path.is_file()
    loose_path.unlink(missing_ok=True)
    existing_record = records.get(record_id)
    if existing_record is not None:
        _disable_archive_minifoto_record(archive, record_offset=int(existing_record.record_offset))
        entry["storage"] = "MINIFOTO.PKF-entry-disabled"
        entry["disabled_archive_record"] = {
            "directory_offset": int(existing_record.record_offset),
            "bitmap_offset": int(existing_record.bitmap_offset),
            "bitmap_length": int(existing_record.bitmap_length),
        }
    else:
        entry["storage"] = "no-photo"
    entry["removed_loose_bitmap"] = loose_was_present
    entry["status"] = "intentionally-no-photo"
    entry["no_verified_portrait_reason"] = reason


def _fetch(item: dict[str, Any]) -> tuple[int, bytes | None, str | None, str | None]:
    record_id = int(item["record_id"])
    manual = _manual_source(item)
    if manual is not None:
        headers = {"User-Agent": USER_AGENT}
        # Wikimedia's thumbnail host rejects synthetic same-site referers
        # intermittently.  Its public FilePath redirect already carries the
        # file provenance, so fetch it without one.  It also rate-limits a
        # small parallel thumbnail batch; retry that transient response.
        if "wikimedia.org" not in manual["url"]:
            headers["Referer"] = manual["identity_evidence_url"] or "https://globalsportsarchive.com/"
        for attempt in range(3):
            try:
                response = requests.get(manual["url"], headers=headers, timeout=30)
                if response.status_code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                if response.status_code != 200:
                    return record_id, None, None, f"manual:http-{response.status_code}"
                image = Image.open(io.BytesIO(response.content))
                image.verify()
                return record_id, response.content, manual["url"], None
            except Exception as exc:  # the exact external source failure stays in the receipt
                if attempt == 2:
                    return record_id, None, None, f"manual:{type(exc).__name__}: {exc}"
                time.sleep(1)
    candidates = _source_candidates(item)
    if not candidates:
        return record_id, None, None, "no-identity-safe-player-id"
    failures: list[str] = []
    for edition, player_id in candidates:
        urls = [
            (CDN.format(edition=edition, player_id=player_id), {"User-Agent": USER_AGENT}),
            (
                SOFIFA_CDN.format(folder=int(player_id) // 1000, suffix=f"{int(player_id) % 1000:03d}", edition=edition),
                {"User-Agent": "Mozilla/5.0", "Referer": f"https://sofifa.com/player/{player_id}/"},
            ),
        ]
        for url, headers in urls:
            for attempt in range(2):
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    if response.status_code != 200:
                        failures.append(f"fifa{edition}:{'sofifa' if 'sofifa' in url else 'futbin'}:http-{response.status_code}")
                        break
                    image = Image.open(io.BytesIO(response.content))
                    image.verify()
                    return record_id, response.content, url, None
                except Exception as exc:  # network failures are surfaced in the receipt
                    failures.append(f"fifa{edition}:attempt-{attempt + 1}:{type(exc).__name__}: {exc}")
    return record_id, None, None, "; ".join(failures)


def _edition_from_source_url(source_url: str) -> str:
    futbin = re.search(r"/fifa(?P<edition>\d+)/", source_url)
    sofifa = re.search(r"/(?P<edition>\d+)_120\.png", source_url)
    match = futbin or sofifa
    if match is None:
        raise ValueError(f"unrecognised close-era source URL: {source_url}")
    return str(match.group("edition"))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path, help="compiler build directory containing game/ and player-ledger.json")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-players", type=int, default=0, help="test only: restrict to this many source-qualified players")
    parser.add_argument(
        "--manual-source-ledger", type=Path, action="append", default=[],
        help=(
            "reviewed JSON face-source ledger for players absent from the edition CDNs; "
            "repeat to combine independently audited source batches"
        ),
    )
    parser.add_argument(
        "--no-portrait-ledger", type=Path, action="append", default=[],
        help=(
            "reviewed JSON ledger of players for whom no credible portrait could be found; "
            "uses PM99's normal no-photo state instead of retaining an unrelated carrier face"
        ),
    )
    parser.add_argument(
        "--reuse-receipt", type=Path,
        help=(
            "reuse already-applied, identity-checked portrait rows from an earlier compatible "
            "face-stage receipt. The corresponding MINIFOTO.PKF and loose MINIFOTO files "
            "must already have been copied into this build."
        ),
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless every compiled player has either an approved portrait or PM99's native no-photo disposition",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    build = args.build_dir.expanduser().resolve()
    game = build / "game"
    ledger_path = build / "player-ledger.json"
    minifoto_path = game / "DBDAT" / "MINIFOTO.PKF"
    if not ledger_path.is_file() or not minifoto_path.is_file():
        raise SystemExit("build directory must contain player-ledger.json and game/DBDAT/MINIFOTO.PKF")
    players = list(json.loads(ledger_path.read_text(encoding="utf-8")) or [])
    if not players:
        raise SystemExit("empty player ledger")
    manual_by_id: dict[int, dict[str, Any]] = {}
    no_portrait_by_id: dict[int, dict[str, Any]] = {}
    compiled_by_id = {int(row["record_id"]): row for row in players}
    for manual_path in args.manual_source_ledger:
        raw_manual = json.loads(manual_path.expanduser().resolve().read_text(encoding="utf-8"))
        manual_rows = raw_manual.get("rows", raw_manual) if isinstance(raw_manual, dict) else raw_manual
        if not isinstance(manual_rows, list):
            raise SystemExit("manual source ledger must be a JSON array or an object with a rows array")
        for supplied in manual_rows:
            if not isinstance(supplied, dict):
                raise SystemExit("manual source ledger contains a non-object row")
            record_id = int(supplied["record_id"])
            compiled = compiled_by_id.get(record_id)
            if compiled is None:
                raise SystemExit(f"manual source record {record_id} is not in this build")
            if str(supplied.get("player") or compiled["name"]) != str(compiled["name"]):
                raise SystemExit(f"manual source player mismatch for record {record_id}")
            if str(supplied.get("club") or compiled["club"]) != str(compiled["club"]):
                raise SystemExit(f"manual source club mismatch for record {record_id}")
            if not str(supplied.get("source_url") or "").startswith(("https://", "http://")):
                raise SystemExit(f"manual source record {record_id} has no http(s) source_url")
            if record_id in manual_by_id:
                raise SystemExit(f"manual source ledgers duplicate record {record_id}")
            manual_by_id[record_id] = dict(supplied)
        for player in players:
            supplied = manual_by_id.get(int(player["record_id"]))
            if supplied is None:
                continue
            player["manual_source_url"] = supplied["source_url"]
            player["manual_source_label"] = supplied.get("source_label")
            player["manual_source_temporal_note"] = supplied.get("temporal_note")
            player["manual_source_identity_evidence_url"] = supplied.get("identity_evidence_url")
            player["manual_source_crop"] = supplied.get("source_crop")

    for no_portrait_path in args.no_portrait_ledger:
        raw_no_portrait = json.loads(no_portrait_path.expanduser().resolve().read_text(encoding="utf-8"))
        no_portrait_rows = raw_no_portrait.get("rows", raw_no_portrait) if isinstance(raw_no_portrait, dict) else raw_no_portrait
        if not isinstance(no_portrait_rows, list):
            raise SystemExit("no-portrait ledger must be a JSON array or an object with a rows array")
        for supplied in no_portrait_rows:
            if not isinstance(supplied, dict):
                raise SystemExit("no-portrait ledger contains a non-object row")
            record_id = int(supplied["record_id"])
            compiled = compiled_by_id.get(record_id)
            if compiled is None:
                raise SystemExit(f"no-portrait record {record_id} is not in this build")
            if str(supplied.get("player") or compiled["name"]) != str(compiled["name"]):
                raise SystemExit(f"no-portrait player mismatch for record {record_id}")
            if str(supplied.get("club") or compiled["club"]) != str(compiled["club"]):
                raise SystemExit(f"no-portrait club mismatch for record {record_id}")
            if not str(supplied.get("reason") or "").strip():
                raise SystemExit(f"no-portrait record {record_id} has no review reason")
            if record_id in manual_by_id or record_id in no_portrait_by_id:
                raise SystemExit(f"portrait ledgers duplicate record {record_id}")
            no_portrait_by_id[record_id] = dict(supplied)
        for player in players:
            supplied = no_portrait_by_id.get(int(player["record_id"]))
            if supplied is not None:
                player["no_verified_portrait"] = supplied

    # A later compiler pass can add one or two players to an otherwise
    # identical season. Re-downloading and re-encoding thousands of already
    # reviewed portraits is both wasteful and a source of release drift. A
    # reused row is accepted only when its record id, club and display name
    # still match the current ledger; the caller remains responsible for
    # copying the actual PKF/loose bitmap payload beforehand.
    reused_rows: dict[int, dict[str, Any]] = {}
    if args.reuse_receipt is not None:
        previous = json.loads(args.reuse_receipt.expanduser().resolve().read_text(encoding="utf-8"))
        previous_rows = list(previous.get("rows") or [])
        current_by_id = {int(row["record_id"]): row for row in players}
        for supplied in previous_rows:
            if not isinstance(supplied, dict) or supplied.get("status") != "applied":
                continue
            record_id = int(supplied["record_id"])
            current = current_by_id.get(record_id)
            if current is None:
                continue
            if str(supplied.get("player")) != str(current["name"]):
                raise SystemExit(f"reused portrait player mismatch for record {record_id}")
            if str(supplied.get("club")) != str(current["club"]):
                raise SystemExit(f"reused portrait club mismatch for record {record_id}")
            reused_rows[record_id] = dict(supplied)

    qualified = [
        row for row in players
        if int(row["record_id"]) not in reused_rows and (
            _source_candidates(row) or _manual_source(row)
        )
    ]
    if args.max_players:
        qualified = qualified[: args.max_players]
    downloads: dict[int, bytes] = {}
    source_urls: dict[int, str] = {}
    errors: dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for record_id, payload, source_url, error in pool.map(_fetch, qualified):
            if payload is not None:
                downloads[record_id] = payload
                source_urls[record_id] = str(source_url)
            else:
                errors[record_id] = str(error)

    original = minifoto_path.read_bytes()
    archive = bytearray(original)
    records = {record.player_record_id: record for record in iter_minifoto_records(minifoto_path)}
    if not records:
        raise RuntimeError("MINIFOTO.PKF has no parseable image records")
    template = next(iter(records.values()))
    palette_path, palette_source = discover_riff_palette_resource(minifoto_path, extra_roots=[game / "DBDAT", game])
    if palette_path is None:
        raise RuntimeError("could not resolve a PM99 RIFF palette for MINIFOTO conversion")
    palette_rgb = load_riff_palette(palette_path)
    palette_image = _build_palette_image(palette_rgb)
    loose_root = game / "DBDAT" / "MINIFOTO"
    loose_root.mkdir(parents=True, exist_ok=True)
    provenance_root = build / "face-sources"
    preview_root = build / "face-previews"
    provenance_root.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    all_indices = list(range(len(palette_rgb)))

    # Archive replacement itself must remain ordered, but image decode/crop/
    # palette conversion has no shared state.  Parallelising that CPU-heavy
    # portion turns the full English-92 batch from an overnight serial job
    # into a bounded release step while retaining byte-for-byte container
    # validation in the ordered write below.
    def convert_one(player: dict[str, Any]) -> tuple[int, bytes | None, bytes | None, str | None]:
        record_id = int(player["record_id"])
        payload = downloads.get(record_id)
        if payload is None:
            return record_id, None, None, "not-downloaded"
        try:
            record = records.get(record_id, template)
            with Image.open(io.BytesIO(payload)) as image:
                source_image = _manual_source_crop(player, image) if _manual_source(player) is not None else image
                bitmap, _crop, preview = _build_replacement_bitmap(
                    raw_bitmap_template=record.raw_bitmap,
                    pixel_offset=record.pixel_offset,
                    width=record.width,
                    height=record.height,
                    source_image=source_image,
                    palette_image=palette_image,
                    palette_rgb=palette_rgb,
                    allowed_indices=all_indices,
                )
            encoded_preview = io.BytesIO()
            preview.save(encoded_preview, format="PNG")
            return record_id, bitmap, encoded_preview.getvalue(), None
        except Exception as exc:
            return record_id, None, None, f"{type(exc).__name__}: {exc}"

    converted: dict[int, tuple[bytes, bytes]] = {}
    conversion_errors: dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for record_id, bitmap, preview_payload, error in pool.map(convert_one, qualified):
            if bitmap is not None and preview_payload is not None:
                converted[record_id] = (bitmap, preview_payload)
            else:
                conversion_errors[record_id] = str(error)

    receipt: list[dict[str, Any]] = []
    qualified_by_id = {int(row["record_id"]): row for row in qualified}
    for player in players:
        record_id = int(player["record_id"])
        reused = reused_rows.get(record_id)
        if reused is not None:
            reused["reused_from_compatible_receipt"] = True
            receipt.append(reused)
            continue
        entry: dict[str, Any] = {
            "record_id": record_id,
            "club": player["club"],
            "player": player["name"],
            "fifa16_player_id": player.get("fifa16_player_id"),
        "portrait_source": (
            "reviewed-no-verified-portrait" if player.get("no_verified_portrait") is not None else
            "reviewed-manual" if _manual_source(player) is not None else
            player.get("portrait_source") or ("fifa16" if player.get("fifa16_player_id") else None)
        ),
            "portrait_player_id": player.get("portrait_player_id") or player.get("fifa16_player_id"),
            "identity_match_method": player.get("fifa16_match_method") or player.get("fifa17_match_method"),
            "source_url": None,
        }
        no_portrait = player.get("no_verified_portrait")
        if no_portrait is not None:
            _set_native_no_photo(
                entry=entry, record_id=record_id, archive=archive, records=records,
                loose_root=loose_root, reason=str(no_portrait["reason"]),
            )
            entry["review_evidence_url"] = str(no_portrait.get("review_evidence_url") or "")
            receipt.append(entry)
            continue
        if record_id not in qualified_by_id:
            _set_native_no_photo(
                entry=entry, record_id=record_id, archive=archive, records=records,
                loose_root=loose_root, reason="no identity-safe close-era portrait source",
            )
            receipt.append(entry)
            continue
        payload = downloads.get(record_id)
        if payload is None:
            _set_native_no_photo(
                entry=entry, record_id=record_id, archive=archive, records=records,
                loose_root=loose_root, reason="portrait source download failed",
            )
            entry["error"] = errors.get(record_id, "not-downloaded")
            receipt.append(entry)
            continue
        converted_row = converted.get(record_id)
        if converted_row is None:
            _set_native_no_photo(
                entry=entry, record_id=record_id, archive=archive, records=records,
                loose_root=loose_root, reason="portrait conversion failed",
            )
            entry["error"] = conversion_errors.get(record_id, "not-converted")
            receipt.append(entry)
            continue
        manual = _manual_source(player)
        source_edition = _edition_from_source_url(source_urls[record_id]) if manual is None else None
        source_directory = (
            f"fifa{source_edition}" if source_edition is not None else "reviewed-manual"
        )
        image_path = None
        if payload is not None:
            image_path = provenance_root / source_directory / f"{record_id:05d}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(payload)
        record = records.get(record_id, template)
        bitmap, preview_payload = converted_row
        preview_path = preview_root / source_directory / f"{record_id:05d}.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(preview_payload)
        if record_id in records:
            # ``records`` was parsed and the freshly built bitmap was shape
            # validated before this ordered write. Re-parsing a multi-megabyte
            # PKF once per player made a 2,000-photo release quadratic. Patch
            # the verified offsets in one buffer and do one full post-write
            # parse below instead.
            start = int(record.bitmap_offset)
            end = start + int(record.bitmap_length)
            if len(bitmap) != int(record.bitmap_length):
                raise RuntimeError(f"{record_id}: replacement bitmap length drift")
            archive[start:end] = bitmap
            entry["storage"] = "MINIFOTO.PKF"
            entry["replace_result"] = {
                "bitmap_offset": int(record.bitmap_offset),
                "bitmap_length": int(record.bitmap_length),
            }
        else:
            loose_path = loose_root / f"J96{record_id:05d}.BMP"
            loose_path.write_bytes(bitmap)
            entry["storage"] = "loose-DBDAT/MINIFOTO"
            entry["loose_path"] = str(loose_path)
        entry["status"] = "applied"
        entry["source_url"] = source_urls[record_id]
        if manual is not None:
            entry["source_label"] = manual["label"]
            entry["source_temporal_note"] = manual["temporal_note"]
            entry["identity_evidence_url"] = manual["identity_evidence_url"]
            if player.get("manual_source_crop") is not None:
                entry["source_crop"] = player["manual_source_crop"]
        if image_path is not None:
            entry["source_image_path"] = str(image_path)
        entry["preview_path"] = str(preview_path)
        receipt.append(entry)

    # One full parse validates every existing archive replacement after the
    # batch write. Loose files use a supported runtime lookup and are checked
    # by their own emitted path/bytes receipt.
    verified_archive = bytes(archive)
    reread = {record.player_record_id: record for record in iter_minifoto_records_from_bytes(minifoto_path.name, verified_archive)}
    for row in receipt:
        if row.get("status") != "applied" or row.get("storage") != "MINIFOTO.PKF":
            continue
        record_id = int(row["record_id"])
        # A reused receipt describes a bitmap that was already present in the
        # input archive.  This run deliberately did not re-download or
        # re-convert it, so there is no entry in ``converted`` to compare.
        # Its identity and archive payload were validated by the compatible
        # receipt gate above; only newly converted rows are checked here.
        if record_id in reused_rows:
            continue
        expected = converted[record_id][0]
        observed = reread.get(record_id)
        if observed is None or observed.raw_bitmap != expected:
            raise RuntimeError(f"{record_id}: batch archive post-write validation failed")
    for row in receipt:
        if row.get("status") != "intentionally-no-photo":
            continue
        record_id = int(row["record_id"])
        if record_id in reread:
            raise RuntimeError(f"{record_id}: disabled MINIFOTO record still resolves")
        if (loose_root / f"J96{record_id:05d}.BMP").exists():
            raise RuntimeError(f"{record_id}: loose MINIFOTO override remains")
    minifoto_path.write_bytes(verified_archive)
    approved_portraits = sum(1 for row in receipt if row["status"] == "applied")
    intentionally_no_photo = sum(1 for row in receipt if row["status"] == "intentionally-no-photo")
    unresolved = [row for row in receipt if row["status"] not in {"applied", "intentionally-no-photo"}]
    output = {
        "schema_version": "pm99-2015-16-close-era-face-stage-v4",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "build_dir": str(build),
        "source": "Futbin/SoFIFA FIFA 16--19 headshots plus explicitly reviewed manual fallback rows; every fallback retains its own provenance and temporal note",
        "palette_path": str(palette_path),
        "palette_source": palette_source,
        "minifoto_sha256_before": hashlib.sha256(original).hexdigest(),
        "minifoto_sha256_after": _sha256(minifoto_path),
        "players_total": len(players),
        "reused": len(reused_rows),
        "qualified_by_identity": len(qualified),
        "applied": approved_portraits,
        "verified_portraits": approved_portraits,
        "intentionally_no_photo": intentionally_no_photo,
        "unresolved": len(unresolved),
        "complete": approved_portraits + intentionally_no_photo == len(players),
        "rows": receipt,
    }
    _json(build / "face-stage-receipt.json", output)
    print(json.dumps({key: output[key] for key in ("players_total", "qualified_by_identity", "applied", "verified_portraits", "intentionally_no_photo", "unresolved", "complete")}, indent=2))
    if args.require_complete and not output["complete"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
