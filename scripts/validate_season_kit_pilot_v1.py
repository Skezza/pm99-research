#!/usr/bin/env python3
"""Validate one small, allocation-bound seasonal compact-kit pilot.

This is intentionally a proof-of-mechanics boundary.  It accepts no more
than five carrier assignments taken verbatim from one full carrier allocation,
then checks their fresh source capture, catalogue, render bindings, and new
archive stage.  A passing receipt is explicitly *not* a release or a claim of
season-wide kit coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from scripts import materialise_season_kit_archives_v1 as materialiser  # noqa: E402
from scripts import season_kit_catalogue_v1 as catalogue_v1  # noqa: E402


SCHEMA = "pm99-season-kit-pilot-validation-receipt-v1"
CAPTURE_SCHEMA = "pm99-season-kit-source-capture-v1"
CATALOGUE_SCHEMA = "pm99-season-kit-catalogue-v1"
BINDING_SCHEMA = "pm99-season-kit-render-bindings-v1"
RENDER_SCHEMA = "pm99-season-kit-render-receipt-v1"
STAGE_SCHEMA = "pm99-season-kit-archive-materialisation-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
KIT_NAME = re.compile(r"^EQ96(?P<carrier>\d{4})\.BMP$", re.IGNORECASE)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PilotValidationError(ValueError):
    """One purported pilot artifact is stale, malformed, or out of scope."""


def _canonical(value: Any) -> bytes:
    return catalogue_v1.canonical_json_bytes(value)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular(path: Path, label: str) -> Path:
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise PilotValidationError(f"{label} must be a regular non-symlink file: {path}")
    except OSError as exc:
        raise PilotValidationError(f"{label} is unavailable: {path}") from exc
    return path.resolve()


def _document(path: Path, label: str) -> tuple[Path, dict[str, Any], str]:
    path = _regular(path, label)
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotValidationError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict) or payload != _canonical(value):
        raise PilotValidationError(f"{label} must be a canonical JSON object")
    return path, value, _sha_bytes(payload)


def _schema(value: Mapping[str, Any], expected: str, label: str) -> None:
    if value.get("schema_version") != expected:
        raise PilotValidationError(f"{label} must use {expected}")


def _carrier(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PilotValidationError(f"{label} must be a positive carrier ID")
    return value


def _records(path: Path, label: str) -> dict[int, Any]:
    output: dict[int, Any] = {}
    for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
        match = KIT_NAME.fullmatch(str(record.file_name))
        if match is None:
            continue
        carrier = int(match.group("carrier"))
        if carrier in output:
            raise PilotValidationError(f"{label} has duplicate compact-kit carrier {carrier}")
        try:
            shape = validate_minifoto_bitmap(record.raw_bitmap)
        except ValueError as exc:
            raise PilotValidationError(f"{label} carrier {carrier} is not a supported OS/2 bitmap") from exc
        if (shape.width, shape.height, shape.bits_per_pixel, shape.pixel_offset, shape.bitmap_length) != (
            record.width, record.height, record.bits_per_pixel, record.pixel_offset, record.bitmap_length,
        ):
            raise PilotValidationError(f"{label} carrier {carrier} bitmap shape is inconsistent")
        output[carrier] = record
    if not output:
        raise PilotValidationError(f"{label} has no compact-kit records")
    return output


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise PilotValidationError(f"{label} must be a lowercase SHA-256")
    return value


def _assert_only_pixel_bytes_changed(before: bytes, after: bytes, records: Mapping[int, Any], carriers: set[int], label: str) -> None:
    if len(before) != len(after):
        raise PilotValidationError(f"{label} archive length changed")
    permitted: list[tuple[int, int]] = []
    for carrier in carriers:
        record = records[carrier]
        start = int(record.bitmap_offset) + int(record.pixel_offset)
        permitted.append((start, start + int(record.width) * int(record.height)))
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not any(start <= index < end for start, end in permitted):
            raise PilotValidationError(f"{label} changed non-pixel byte at archive offset {index}")


def validate(
    *, full_allocation_path: Path, capture_path: Path, catalogue_request_path: Path, catalogue_path: Path,
    bindings_path: Path, render_receipt_path: Path, archive_stage: Path,
) -> dict[str, Any]:
    full_path, full, full_sha = _document(full_allocation_path, "full allocation")
    _schema(full, "pm99-season-carrier-allocation-v1", "full allocation")
    assignments = full.get("assignments")
    if not isinstance(assignments, list):
        raise PilotValidationError("full allocation assignments must be a list")
    allocation_by_carrier = {_carrier(row.get("carrier_id"), "full allocation carrier_id"): row for row in assignments if isinstance(row, Mapping)}
    if len(allocation_by_carrier) != len(assignments):
        raise PilotValidationError("full allocation has invalid or duplicate carrier assignments")

    capture_path, capture, capture_sha = _document(capture_path, "fresh source capture")
    _schema(capture, CAPTURE_SCHEMA, "fresh source capture")
    provenance = capture.get("provenance")
    if not isinstance(provenance, Mapping):
        raise PilotValidationError("fresh source capture has no provenance")
    if provenance.get("full_allocation_sha256") != full_sha:
        raise PilotValidationError("fresh source capture does not bind this full allocation")
    carrier_ids = provenance.get("pilot_carrier_ids")
    if not isinstance(carrier_ids, list) or carrier_ids != sorted(carrier_ids) or not 1 <= len(carrier_ids) <= 5:
        raise PilotValidationError("pilot must name one to five sorted carrier IDs")
    carrier_ids = [_carrier(item, "pilot carrier ID") for item in carrier_ids]
    if len(set(carrier_ids)) != len(carrier_ids):
        raise PilotValidationError("pilot carrier IDs must be unique")
    selected = [allocation_by_carrier.get(carrier) for carrier in carrier_ids]
    if any(row is None for row in selected):
        raise PilotValidationError("pilot names a carrier absent from full allocation")
    selected = [dict(row) for row in selected if row is not None]
    if provenance.get("pilot_assignments_sha256") != _sha_bytes(_canonical(selected)):
        raise PilotValidationError("pilot assignment hash does not match full allocation rows")
    subset = {"season": full.get("season"), "assignments": selected}
    if provenance.get("allocation_sha256") != _sha_bytes(_canonical(subset)):
        raise PilotValidationError("fresh source capture subset allocation hash is stale")
    if provenance.get("stale_capture_reuse") != "prohibited-fresh-cache-created-for-this-pilot":
        raise PilotValidationError("fresh capture does not explicitly prohibit stale cache reuse")
    capture_rows = capture.get("rows")
    if not isinstance(capture_rows, list) or [row.get("carrier_id") for row in capture_rows] != carrier_ids:
        raise PilotValidationError("fresh capture rows do not exactly cover pilot carriers")
    for row in capture_rows:
        if row.get("status") != "revision-captured-home-fields-ready" or row.get("parse_status") != "home-kit-fields-ready":
            raise PilotValidationError(f"pilot carrier {row.get('carrier_id')} lacks usable exact-season kit source")
        if not isinstance(row.get("page_title"), str) or not isinstance(row.get("page_id"), int) or not isinstance(row.get("revision_id"), int):
            raise PilotValidationError(f"pilot carrier {row.get('carrier_id')} source page is not revision-pinned")

    request_path, request, request_sha = _document(catalogue_request_path, "kit catalogue request")
    if request.get("schema_version") != catalogue_v1.REQUEST_SCHEMA:
        raise PilotValidationError("kit catalogue request schema is unsupported")
    request_rows = request.get("clubs")
    if not isinstance(request_rows, list) or [row.get("carrier_id") for row in request_rows] != carrier_ids:
        raise PilotValidationError("kit catalogue request does not exactly cover pilot carriers")
    source_titles = {row["carrier_id"]: row.get("page_title") for row in capture_rows}
    for row in request_rows:
        source = row.get("source")
        if row.get("carrier_status") != "continuing" or not isinstance(source, Mapping) or source.get("provider") != catalogue_v1.WIKI_PROVIDER:
            raise PilotValidationError(f"pilot carrier {row.get('carrier_id')} request permits an unsafe fallback")
        if source.get("page_title") != source_titles[row["carrier_id"]]:
            raise PilotValidationError(f"pilot carrier {row.get('carrier_id')} request differs from captured page")

    catalogue_path, kit_catalogue, kit_catalogue_sha = _document(catalogue_path, "kit catalogue")
    _schema(kit_catalogue, CATALOGUE_SCHEMA, "kit catalogue")
    if (kit_catalogue.get("provenance") or {}).get("request_sha256") != request_sha:
        raise PilotValidationError("kit catalogue does not bind the pilot request")
    catalogue_rows = kit_catalogue.get("rows")
    if not isinstance(catalogue_rows, list) or [row.get("carrier_id") for row in catalogue_rows] != carrier_ids:
        raise PilotValidationError("kit catalogue does not exactly cover pilot carriers")
    for row in catalogue_rows:
        contract = row.get("render_contract")
        if row.get("status") != "source-ready" or not isinstance(contract, Mapping) or contract.get("kind") != "wikipedia-template-fields":
            raise PilotValidationError(f"pilot carrier {row.get('carrier_id')} is not source-renderable")

    bindings_path, bindings, bindings_sha = _document(bindings_path, "kit render bindings")
    _schema(bindings, BINDING_SCHEMA, "kit render bindings")
    receipt_path, render_receipt, render_receipt_sha = _document(render_receipt_path, "kit render receipt")
    _schema(render_receipt, RENDER_SCHEMA, "kit render receipt")
    if bindings.get("kit_catalogue_sha256") != kit_catalogue_sha or render_receipt.get("kit_catalogue_sha256") != kit_catalogue_sha:
        raise PilotValidationError("render artifacts do not bind the exact kit catalogue")
    binding_rows = bindings.get("clubs")
    rendered_rows = [row for row in (render_receipt.get("rows") or []) if row.get("status") == "rendered-source-ready"]
    if not isinstance(binding_rows, list) or [row.get("carrier_id") for row in binding_rows] != carrier_ids or [row.get("carrier_id") for row in rendered_rows] != carrier_ids:
        raise PilotValidationError("render bindings or receipt do not exactly cover pilot carriers")
    if (render_receipt.get("coverage") or {}).get("artifact_count") != len(carrier_ids) * len(ARCHIVES):
        raise PilotValidationError("render receipt artifact count is stale")

    stage_receipt_path, stage, stage_sha = _document(archive_stage / "kit-archive-materialisation-receipt-v1.json", "archive-stage receipt")
    _schema(stage, STAGE_SCHEMA, "archive-stage receipt")
    if stage.get("result") != "archive-stage-materialised" or stage.get("release_eligible") is not False:
        raise PilotValidationError("archive stage is not explicitly release-ineligible materialisation")
    stage_provenance = stage.get("provenance")
    if not isinstance(stage_provenance, Mapping):
        raise PilotValidationError("archive stage has no provenance")
    if (stage_provenance.get("kit_render_bindings") or {}).get("sha256") != bindings_sha or (stage_provenance.get("kit_render_receipt") or {}).get("sha256") != render_receipt_sha:
        raise PilotValidationError("archive stage does not bind exact render inputs")
    if stage_provenance.get("kit_catalogue_sha256") != kit_catalogue_sha:
        raise PilotValidationError("archive stage does not bind exact kit catalogue")
    base_dir = Path(str(stage_provenance.get("clean_dbdat") or ""))
    if base_dir.is_symlink() or not base_dir.is_dir():
        raise PilotValidationError("archive stage clean base is unavailable")
    events = stage.get("events")
    if not isinstance(events, list) or len(events) != len(carrier_ids) * len(ARCHIVES):
        raise PilotValidationError("archive stage event count is stale")
    event_keys = {(row.get("archive"), row.get("carrier_id")) for row in events if isinstance(row, Mapping)}
    if event_keys != {(archive, carrier) for archive in ARCHIVES for carrier in carrier_ids}:
        raise PilotValidationError("archive stage events do not exactly cover pilot records")

    archive_checks = []
    for archive in ARCHIVES:
        base_archive = _regular(base_dir / archive, f"clean base {archive}")
        staged_archive = _regular(archive_stage / "archives" / archive, f"staged {archive}")
        archive_row = (stage.get("archives") or {}).get(archive)
        if not isinstance(archive_row, Mapping):
            raise PilotValidationError(f"archive stage has no row for {archive}")
        if archive_row.get("sha256_before") != _sha_file(base_archive) or archive_row.get("sha256_after") != _sha_file(staged_archive):
            raise PilotValidationError(f"archive stage hashes are stale for {archive}")
        before_records, after_records = _records(base_archive, f"clean base {archive}"), _records(staged_archive, f"staged {archive}")
        if set(before_records) != set(after_records) or not set(carrier_ids).issubset(before_records):
            raise PilotValidationError(f"{archive} carrier record set changed unexpectedly")
        _assert_only_pixel_bytes_changed(base_archive.read_bytes(), staged_archive.read_bytes(), before_records, set(carrier_ids), archive)
        for carrier, before in before_records.items():
            after = after_records[carrier]
            if carrier not in carrier_ids and before.raw_bitmap != after.raw_bitmap:
                raise PilotValidationError(f"{archive} unbound carrier {carrier} changed")
            if carrier in carrier_ids:
                event = next(row for row in events if row["archive"] == archive and row["carrier_id"] == carrier)
                if _sha_bytes(after.raw_bitmap) != event.get("bitmap_sha256_after"):
                    raise PilotValidationError(f"{archive} carrier {carrier} post-write bitmap hash is stale")
                artifact = bindings_path.parent / str(event.get("render_artifact_relative_path") or "")
                if not artifact.is_file() or _sha_file(artifact) != event.get("render_artifact_sha256") or artifact.read_bytes() != after.raw_bitmap:
                    raise PilotValidationError(f"{archive} carrier {carrier} staged bitmap differs from its render artifact")
        archive_checks.append({"archive": archive, "carrier_record_count": len(before_records), "all_records_os2_8bit_validated": True, "only_bound_pixel_bytes_changed": True})

    return {
        "schema_version": SCHEMA,
        "result": "pilot-validated-not-release",
        "release_eligible": False,
        "scope": {
            "season": full.get("season"),
            "full_allocation": {"path": str(full_path), "sha256": full_sha},
            "pilot_carrier_ids": carrier_ids,
            "pilot_clubs": [{"carrier_id": row["carrier_id"], "club_name": row["club_name"]} for row in selected],
            "limit": 5,
        },
        "provenance": {
            "fresh_source_capture": {"path": str(capture_path), "sha256": capture_sha},
            "kit_catalogue_request": {"path": str(request_path), "sha256": request_sha},
            "kit_catalogue": {"path": str(catalogue_path), "sha256": kit_catalogue_sha},
            "kit_render_bindings": {"path": str(bindings_path), "sha256": bindings_sha},
            "kit_render_receipt": {"path": str(receipt_path), "sha256": render_receipt_sha},
            "archive_stage_receipt": {"path": str(stage_receipt_path), "sha256": stage_sha},
        },
        "validation": {
            "fresh_revision_pinned_sources": len(carrier_ids),
            "rendered_artifacts": len(carrier_ids) * len(ARCHIVES),
            "archive_checks": archive_checks,
            "stale_capture_reuse": "prohibited-and-verified-by-fresh-capture-provenance",
            "native_or_fallback_art": "not-used",
        },
        "gaps": [],
        "not_claimed": [
            "This validates only five compact-kit carriers, not full 2020/21 coverage.",
            "This archive stage is not compiled into a season database or copied into a game tree.",
            "No gameplay or visual runtime evidence is claimed by this mechanics/source pilot.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-allocation", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--catalogue-request", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--render-receipt", type=Path, required=True)
    parser.add_argument("--archive-stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new validation receipt path")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error(f"refusing to replace existing receipt: {args.output}")
    try:
        result = validate(
            full_allocation_path=args.full_allocation,
            capture_path=args.capture,
            catalogue_request_path=args.catalogue_request,
            catalogue_path=args.catalogue,
            bindings_path=args.bindings,
            render_receipt_path=args.render_receipt,
            archive_stage=args.archive_stage,
        )
    except PilotValidationError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(result))
    print(json.dumps({"result": result["result"], "pilot_carrier_ids": result["scope"]["pilot_carrier_ids"], "rendered_artifacts": result["validation"]["rendered_artifacts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
