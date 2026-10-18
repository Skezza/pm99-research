#!/usr/bin/env python3
"""Materialise source-only 2015/16 world asset dispositions.

This is the release gate between the candidate manifest produced by
``audit_2015_world_assets.py`` and a future PM99 writer.  It deliberately
does *not* open or rewrite an EXE, FDI, PKF, MINIFOTO or release database.
Portraits with a locally cached, identity-matched source are rendered to a
reviewable crop candidate.  A player without an identity-safe source receives
an explicit native-no-photo disposition; the row can never fall through to a
carrier's old face.  FIFA URLs that have not been downloaded remain pending,
so they are not accidentally represented as either an approved face or a
native no-photo decision.

Reviewed kits are supplied through a small, explicit ledger.  Base EQ96 art,
English kit receipts, and probe copies are never inferred as a foreign
2015/16 kit.  Without a matching reviewed ledger row every kit is a blocked,
no-write disposition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised by an environment check
    Image = None  # type: ignore[assignment]


SCHEMA = "pm99-world-2015-asset-dispositions-v1"
KIT_LEDGER_SCHEMA = "pm99-world-reviewed-kit-candidates-v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class AssetDispositionError(ValueError):
    """A candidate or reviewed source cannot pass the disposition gate."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetDispositionError(f"cannot read {label}: {path}") from exc
    return value, hashlib.sha256(raw).hexdigest()


def _club_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _validate_reviewed_kit_row(carrier_id: int, row: Mapping[str, Any]) -> dict[str, Any]:
    if str(row.get("season") or "") != "2015-16":
        raise AssetDispositionError(f"reviewed kit carrier {carrier_id} is not season 2015-16")
    if str(row.get("review_status") or "") not in {"approved", "reviewed-2015-16"}:
        raise AssetDispositionError(f"reviewed kit carrier {carrier_id} is not approved")
    source_path = Path(str(row.get("candidate_path") or row.get("source_path") or "")).expanduser()
    if not source_path.is_file():
        raise AssetDispositionError(f"reviewed kit carrier {carrier_id} source is not a local file: {source_path}")
    actual_hash = sha256_file(source_path)
    declared_hash = str(row.get("source_sha256") or "").lower()
    if not _HEX64.fullmatch(declared_hash) or declared_hash != actual_hash:
        raise AssetDispositionError(f"reviewed kit carrier {carrier_id} source hash does not match")
    source_url = str(row.get("source_url") or "")
    if not source_url.startswith(("https://", "http://")):
        raise AssetDispositionError(f"reviewed kit carrier {carrier_id} requires an HTTP source URL")
    return {**row, "carrier_id": carrier_id, "source_path": str(source_path.resolve()), "source_sha256": actual_hash}


def _load_reviewed_kits(paths: Iterable[Path]) -> tuple[dict[int, dict[str, Any]], dict[str, str]]:
    """Load only approved local 2015/16 kit artifacts, keyed by carrier id."""

    indexed: dict[int, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for path in sorted({Path(item).resolve() for item in paths}, key=str):
        value, digest = _read_json(path, "reviewed kit ledger")
        hashes[str(path)] = digest
        if not isinstance(value, dict) or value.get("schema_version") != KIT_LEDGER_SCHEMA:
            raise AssetDispositionError(f"reviewed kit ledger has wrong schema: {path}")
        rows = value.get("rows")
        if not isinstance(rows, list):
            raise AssetDispositionError(f"reviewed kit ledger rows must be a list: {path}")
        for row in rows:
            if not isinstance(row, dict):
                raise AssetDispositionError(f"reviewed kit ledger has a malformed row: {path}")
            try:
                carrier_id = int(row["carrier_id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AssetDispositionError(f"reviewed kit row requires carrier_id: {path}") from exc
            if carrier_id in indexed:
                raise AssetDispositionError(f"duplicate reviewed kit carrier id {carrier_id}")
            indexed[carrier_id] = {**_validate_reviewed_kit_row(carrier_id, row), "ledger": str(path)}
    return indexed, hashes


def _crop_candidate(source_path: Path, destination: Path, *, size: int = 32) -> dict[str, Any]:
    if Image is None:
        raise AssetDispositionError("Pillow is required to materialise portrait crop candidates")
    try:
        with Image.open(source_path) as opened:
            image = opened.convert("RGBA")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise AssetDispositionError(f"portrait source has invalid dimensions: {source_path}")
            edge = min(width, height)
            left = (width - edge) // 2
            top = (height - edge) // 2
            crop = image.crop((left, top, left + edge, top + edge)).resize((size, size), Image.Resampling.LANCZOS)
            destination.parent.mkdir(parents=True, exist_ok=True)
            crop.save(destination, format="PNG", optimize=False, compress_level=9)
            return {"width": size, "height": size, "mode": "RGBA", "sha256": sha256_file(destination), "bytes": destination.stat().st_size}
    except AssetDispositionError:
        raise
    except Exception as exc:
        raise AssetDispositionError(f"cannot decode portrait source: {source_path}") from exc


def _portrait_disposition(player: Mapping[str, Any], output_dir: Path | None) -> dict[str, Any]:
    portrait = player.get("portrait") if isinstance(player.get("portrait"), dict) else {}
    status = str(portrait.get("status") or "")
    base = {
        "slot_index": int(player.get("slot_index") or 0),
        "player_carrier_id": int(player.get("player_carrier_id") or 0),
        "name": str(player.get("name") or ""),
        "fifa16_player_id": player.get("fifa16_player_id"),
    }
    if status == "cached-approved-era":
        source_text = str(portrait.get("source_image_path") or "")
        source_path = Path(source_text).expanduser()
        if not source_path.is_file():
            return {**base, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "approved-source-unavailable-at-materialisation", "source_image_path": source_text}
        source_hash = sha256_file(source_path)
        row = {**base, "status": "approved-crop-candidate", "action": "write-candidate-only", "source_image_path": str(source_path.resolve()), "source_sha256": source_hash, "source_url": str(portrait.get("source_url") or "")}
        if output_dir is None:
            row["status"] = "approved-source-ready-crop-not-materialised"
            row["action"] = "no-write"
            row["reason"] = "portrait-output-dir-not-supplied"
            return row
        destination = output_dir / "portraits" / f"carrier-{int(player.get('player_carrier_id') or 0):05d}" / f"slot-{int(player.get('slot_index') or 0):02d}.png"
        row["candidate_path"] = str(destination.resolve())
        row["candidate_image"] = _crop_candidate(source_path, destination)
        return row
    if status == "fifa16-url-candidate":
        return {**base, "status": "pending-source-materialisation", "action": "no-write", "reason": "identity-safe-url-present-but-not-cached-or-reviewed", "source_url": str(portrait.get("source_url") or "")}
    return {**base, "status": "native-no-photo", "action": "preserve-native-no-photo", "reason": "no-identity-safe-era-source", "source_url": str(portrait.get("source_url") or "")}


def build_dispositions(manifest: Mapping[str, Any], *, reviewed_kits: Mapping[int, Mapping[str, Any]] | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    if manifest.get("schema_version") != "pm99-world-2015-asset-candidate-manifest-v1":
        raise AssetDispositionError("candidate manifest has wrong schema")
    clubs = manifest.get("clubs")
    if not isinstance(clubs, list):
        raise AssetDispositionError("candidate manifest clubs must be a list")
    reviewed_kits = reviewed_kits or {}
    output_clubs: list[dict[str, Any]] = []
    portrait_counts: Counter[str] = Counter()
    kit_counts: Counter[str] = Counter()
    portrait_ready = kit_ready = asset_ready = 0
    for club in sorted((item for item in clubs if isinstance(item, dict)), key=lambda item: int(item.get("carrier_id") or 0)):
        carrier_id = int(club.get("carrier_id") or 0)
        kit_source = reviewed_kits.get(carrier_id)
        if kit_source is None:
            kit = {"status": "blocked-no-reviewed-2015-kit", "action": "no-write", "reason": "reviewed 2015-16 club kit candidate is required; base EQ96 art is not inherited", "base_art_ignored": True}
        else:
            kit_source = _validate_reviewed_kit_row(carrier_id, kit_source)
            if _club_key(kit_source.get("source_club_name")) != _club_key(club.get("source_club_name")) or _club_key(kit_source.get("source_country_catalog")) != _club_key(club.get("source_country_catalog")):
                raise AssetDispositionError(f"reviewed kit carrier {carrier_id} does not match candidate club identity")
            kit = {"status": "approved-reviewed-2015-kit-candidate", "action": "write-candidate-only", "source_club_name": kit_source.get("source_club_name"), "source_country_catalog": kit_source.get("source_country_catalog"), "season": kit_source.get("season"), "source_url": kit_source.get("source_url"), "source_path": kit_source.get("source_path"), "source_sha256": kit_source.get("source_sha256"), "ledger": kit_source.get("ledger")}
        kit_counts[kit["status"]] += 1
        players = [_portrait_disposition(player, output_dir) for player in club.get("players", []) if isinstance(player, dict)]
        portrait_counts.update(row["status"] for row in players)
        portraits_complete = bool(players) and all(row["status"] in {"approved-crop-candidate", "native-no-photo"} for row in players)
        kit_complete = kit["status"] == "approved-reviewed-2015-kit-candidate"
        portrait_ready += int(portraits_complete)
        kit_ready += int(kit_complete)
        asset_ready += int(portraits_complete and kit_complete and club.get("source_status") == "source-squad-ready")
        output_clubs.append({"carrier_id": carrier_id, "source_status": club.get("source_status"), "source_country_catalog": club.get("source_country_catalog"), "source_club_name": club.get("source_club_name"), "kit": kit, "players": players})
    return {"schema_version": SCHEMA, "season": "2015-16", "result": "source-only-dispositions; no PM99 binary writes", "policy": {"portrait": "identity-matched local source becomes a crop candidate; no identity-safe source becomes explicit native-no-photo; URL-only candidates remain pending", "kit": "only an identity-matched reviewed 2015-16 local candidate is eligible; base art and wrong-club inheritance are blocked", "scope": "no EXE, FDI, PKF, MINIFOTO or release DB writes"}, "coverage": {"foreign_carrier_count": len(output_clubs), "portrait_status_counts": dict(sorted(portrait_counts.items())), "kit_status_counts": dict(sorted(kit_counts.items())), "portrait_disposition_ready_carrier_count": portrait_ready, "kit_disposition_ready_carrier_count": kit_ready, "asset_release_ready_carrier_count": asset_ready}, "clubs": output_clubs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--reviewed-kit-ledger", type=Path, action="append", default=[])
    parser.add_argument("--portrait-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest, manifest_hash = _read_json(args.candidate_manifest, "candidate manifest")
        reviewed, kit_hashes = _load_reviewed_kits(args.reviewed_kit_ledger)
        result = build_dispositions(manifest, reviewed_kits=reviewed, output_dir=args.portrait_output.resolve() if args.portrait_output else None)
    except AssetDispositionError as exc:
        parser.error(str(exc))
    result["sources"] = {"candidate_manifest": {"path": str(args.candidate_manifest.resolve()), "sha256": manifest_hash}, "reviewed_kit_ledgers": {path: {"sha256": digest} for path, digest in sorted(kit_hashes.items())}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"output": str(args.output), **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
