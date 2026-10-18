#!/usr/bin/env python3
"""Materialise hash-bound seasonal kit renders into new PM99 archive copies.

This is deliberately an archive stage, not a release command.  It accepts a
matching ``pm99-season-kit-render-bindings-v1`` / render receipt pair only
when the supplied clean base is byte-for-byte the base used to render those
assets.  It writes three *new* compact-kit archives and a receipt; it never
edits the base, an existing stage, a package, or a game tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import (  # noqa: E402
    iter_obfuscated_bmp_records,
    iter_obfuscated_bmp_records_from_bytes,
    validate_minifoto_bitmap,
)


SCHEMA = "pm99-season-kit-archive-materialisation-v1"
BINDING_SCHEMA = "pm99-season-kit-render-bindings-v1"
RENDER_RECEIPT_SCHEMA = "pm99-season-kit-render-receipt-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
_KIT_NAME = re.compile(r"^EQ96(?P<carrier>\d{4})\.BMP$", re.IGNORECASE)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KitArchiveMaterialisationError(ValueError):
    """A kit archive stage input is unsafe, stale, or malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_regular_file(path: Path) -> bool:
    try:
        return not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)
    except OSError:
        return False


def _require_regular_file(path: Path, label: str) -> Path:
    if not _is_regular_file(path):
        raise KitArchiveMaterialisationError(f"{label} must be an existing regular non-symlink file: {path}")
    return path.resolve()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    path = _require_regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitArchiveMaterialisationError(f"{label} is not a valid JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise KitArchiveMaterialisationError(f"{label} must be a JSON object")
    return value


def _require_sha256(value: Any, label: str) -> str:
    digest = str(value or "")
    if not _SHA256.fullmatch(digest):
        raise KitArchiveMaterialisationError(f"{label} must be a lowercase SHA-256")
    return digest


def _carrier(value: Any, label: str) -> int:
    # bool is an int subclass, but never a valid carrier ID.
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9999:
        raise KitArchiveMaterialisationError(f"{label} must be a carrier ID in 0..9999")
    return value


def _safe_artifact_path(*, bindings_root: Path, relative_path: Any, label: str) -> Path:
    raw = str(relative_path or "")
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise KitArchiveMaterialisationError(f"{label} has an unsafe relative artifact path")
    unresolved = bindings_root / candidate
    if not _is_regular_file(unresolved):
        raise KitArchiveMaterialisationError(f"{label} artifact must be an existing regular non-symlink file")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(bindings_root)
    except ValueError as exc:
        raise KitArchiveMaterialisationError(f"{label} artifact resolves outside the bindings directory") from exc
    return resolved


def _artifact_token(value: Any, label: str) -> tuple[str, str, str, str]:
    if not isinstance(value, Mapping):
        raise KitArchiveMaterialisationError(f"{label} artifact must be an object")
    artifact_id = str(value.get("id") or "")
    kind = str(value.get("kind") or "")
    digest = _require_sha256(value.get("sha256"), f"{label}.sha256")
    relative_path = str(value.get("relative_path") or "")
    if not artifact_id.startswith("kit-render-") or kind != "kit-render" or not relative_path:
        raise KitArchiveMaterialisationError(f"{label} must declare id, kind=kit-render, and relative_path")
    return artifact_id, kind, digest, relative_path


def _index_binding_rows(binding: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    rows = binding.get("clubs")
    if not isinstance(rows, list) or not rows:
        raise KitArchiveMaterialisationError("kit render bindings must contain a non-empty clubs list")
    indexed: dict[int, list[dict[str, Any]]] = {}
    artifact_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise KitArchiveMaterialisationError(f"binding club row {index} must be an object")
        carrier = _carrier(row.get("carrier_id"), f"binding club row {index}.carrier_id")
        if carrier in indexed:
            raise KitArchiveMaterialisationError(f"kit render bindings collide on carrier {carrier}")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != len(ARCHIVES):
            raise KitArchiveMaterialisationError(f"binding carrier {carrier} must have exactly {len(ARCHIVES)} artifacts")
        copied = [dict(artifact) if isinstance(artifact, Mapping) else artifact for artifact in artifacts]
        for artifact_index, artifact in enumerate(copied):
            artifact_id, _kind, _digest, _relative = _artifact_token(
                artifact, f"binding carrier {carrier} artifact {artifact_index}"
            )
            if artifact_id in artifact_ids:
                raise KitArchiveMaterialisationError(f"kit render bindings collide on artifact id {artifact_id}")
            artifact_ids.add(artifact_id)
        indexed[carrier] = copied
    return indexed


def _index_rendered_receipt_rows(receipt: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise KitArchiveMaterialisationError("kit render receipt rows must be a list")
    indexed: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise KitArchiveMaterialisationError(f"render receipt row {index} must be an object")
        if row.get("status") != "rendered-source-ready":
            continue
        carrier = _carrier(row.get("carrier_id"), f"render receipt row {index}.carrier_id")
        if carrier in indexed:
            raise KitArchiveMaterialisationError(f"render receipt collides on rendered carrier {carrier}")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != len(ARCHIVES):
            raise KitArchiveMaterialisationError(
                f"render receipt carrier {carrier} must have exactly {len(ARCHIVES)} artifacts"
            )
        copied = [dict(artifact) if isinstance(artifact, Mapping) else artifact for artifact in artifacts]
        for artifact_index, artifact in enumerate(copied):
            _artifact_token(artifact, f"render receipt carrier {carrier} artifact {artifact_index}")
        indexed[carrier] = copied
    return indexed


def _verify_render_provenance(*, binding: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    if binding.get("schema_version") != BINDING_SCHEMA:
        raise KitArchiveMaterialisationError("kit render bindings schema is unsupported")
    if receipt.get("schema_version") != RENDER_RECEIPT_SCHEMA:
        raise KitArchiveMaterialisationError("kit render receipt schema is unsupported")
    binding_catalogue_sha = _require_sha256(binding.get("kit_catalogue_sha256"), "bindings.kit_catalogue_sha256")
    receipt_catalogue_sha = _require_sha256(receipt.get("kit_catalogue_sha256"), "receipt.kit_catalogue_sha256")
    if binding_catalogue_sha != receipt_catalogue_sha:
        raise KitArchiveMaterialisationError("kit render bindings and receipt name different kit catalogues")
    if not isinstance(receipt.get("season"), Mapping):
        raise KitArchiveMaterialisationError("kit render receipt season must be an object")

    binding_rows = _index_binding_rows(binding)
    receipt_rows = _index_rendered_receipt_rows(receipt)
    if set(binding_rows) != set(receipt_rows):
        raise KitArchiveMaterialisationError("kit render binding carrier set differs from rendered receipt carrier set")
    for carrier in sorted(binding_rows):
        binding_tokens = sorted(
            _artifact_token(value, f"binding carrier {carrier}") for value in binding_rows[carrier]
        )
        receipt_tokens = sorted(
            _artifact_token(value, f"render receipt carrier {carrier}") for value in receipt_rows[carrier]
        )
        if binding_tokens != receipt_tokens:
            raise KitArchiveMaterialisationError(f"binding artifacts differ from render receipt for carrier {carrier}")

    coverage = receipt.get("coverage")
    if not isinstance(coverage, Mapping):
        raise KitArchiveMaterialisationError("kit render receipt coverage must be an object")
    if not isinstance(coverage.get("bound_club_count"), int) or isinstance(coverage.get("bound_club_count"), bool) or coverage.get("bound_club_count") != len(binding_rows):
        raise KitArchiveMaterialisationError("kit render receipt bound club count is stale")
    if not isinstance(coverage.get("artifact_count"), int) or isinstance(coverage.get("artifact_count"), bool) or coverage.get("artifact_count") != len(binding_rows) * len(ARCHIVES):
        raise KitArchiveMaterialisationError("kit render receipt artifact count is stale")
    return binding_rows


def _records_by_carrier(path: Path) -> dict[int, Any]:
    records: dict[int, Any] = {}
    for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
        match = _KIT_NAME.fullmatch(str(record.file_name))
        if match is None:
            continue
        carrier = int(match.group("carrier"))
        if carrier in records:
            raise KitArchiveMaterialisationError(f"{path.name} has colliding kit records for carrier {carrier}")
        # Iteration only yields recognised OS/2 8-bit bitmaps. Validate the
        # raw value again so the archive contract is explicit at this boundary.
        try:
            shape = validate_minifoto_bitmap(record.raw_bitmap)
        except ValueError as exc:
            raise KitArchiveMaterialisationError(
                f"{path.name} carrier {carrier} has an unsupported bitmap format"
            ) from exc
        if (
            shape.width != record.width
            or shape.height != record.height
            or shape.bits_per_pixel != record.bits_per_pixel
            or shape.pixel_offset != record.pixel_offset
            or shape.bitmap_length != record.bitmap_length
        ):
            raise KitArchiveMaterialisationError(f"{path.name} carrier {carrier} bitmap shape is inconsistent")
        records[carrier] = record
    if not records:
        raise KitArchiveMaterialisationError(f"{path.name} has no recognised EQ96 compact-kit records")
    return records


def _archive_for_artifact(*, artifact: Mapping[str, Any], carrier: int) -> str:
    artifact_id, _kind, _digest, _relative = _artifact_token(artifact, f"binding carrier {carrier}")
    matches = [
        archive
        for archive in ARCHIVES
        if artifact_id.endswith(f"-{carrier}-{archive.removesuffix('.PKF').lower()}")
    ]
    if len(matches) != 1:
        raise KitArchiveMaterialisationError(
            f"binding carrier {carrier} artifact id does not name exactly one target compact-kit archive: {artifact_id}"
        )
    return matches[0]


def _candidate_payload(
    *, artifact: Mapping[str, Any], carrier: int, archive: str, bindings_root: Path, record: Any
) -> tuple[bytes, dict[str, Any]]:
    _artifact_id, _kind, expected_hash, relative_path = _artifact_token(
        artifact, f"binding carrier {carrier} {archive}"
    )
    candidate_path = _safe_artifact_path(
        bindings_root=bindings_root,
        relative_path=relative_path,
        label=f"binding carrier {carrier} {archive}",
    )
    payload = candidate_path.read_bytes()
    if sha256_bytes(payload) != expected_hash:
        raise KitArchiveMaterialisationError(f"binding carrier {carrier} {archive} artifact hash is stale")
    try:
        candidate_shape = validate_minifoto_bitmap(payload)
        base_shape = validate_minifoto_bitmap(record.raw_bitmap)
    except ValueError as exc:
        raise KitArchiveMaterialisationError(
            f"binding carrier {carrier} {archive} uses an unsupported bitmap format"
        ) from exc
    attributes = ("width", "height", "bits_per_pixel", "pixel_offset", "bitmap_length")
    if any(getattr(candidate_shape, key) != getattr(base_shape, key) for key in attributes):
        raise KitArchiveMaterialisationError(
            f"binding carrier {carrier} {archive} bitmap dimensions or format do not match the verified base"
        )
    pixel_end = candidate_shape.pixel_offset + candidate_shape.pixel_length
    if (
        payload[:candidate_shape.pixel_offset] != record.raw_bitmap[:base_shape.pixel_offset]
        or payload[pixel_end:] != record.raw_bitmap[pixel_end:]
    ):
        raise KitArchiveMaterialisationError(
            f"binding carrier {carrier} {archive} changes non-pixel bitmap bytes"
        )
    return payload, {
        "carrier_id": carrier,
        "archive": archive,
        "file_name": record.file_name,
        "bitmap_offset": int(record.bitmap_offset),
        "bitmap_length": int(record.bitmap_length),
        "pixel_offset": int(record.pixel_offset),
        "width": int(record.width),
        "height": int(record.height),
        "bits_per_pixel": int(record.bits_per_pixel),
        "bitmap_sha256_before": sha256_bytes(record.raw_bitmap),
        "bitmap_sha256_after": expected_hash,
        "render_artifact_id": str(artifact["id"]),
        "render_artifact_relative_path": str(artifact["relative_path"]),
        "render_artifact_sha256": expected_hash,
    }


def _verify_base_archives(*, base_dbdat: Path, receipt: Mapping[str, Any]) -> tuple[dict[str, bytes], dict[str, dict[int, Any]], dict[str, str]]:
    source = receipt.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("archive_sha256"), Mapping):
        raise KitArchiveMaterialisationError("kit render receipt has no clean-base archive hashes")
    declared_hashes = source["archive_sha256"]
    base_bytes: dict[str, bytes] = {}
    records: dict[str, dict[int, Any]] = {}
    hashes: dict[str, str] = {}
    for archive in ARCHIVES:
        declared = _require_sha256(declared_hashes.get(archive), f"render receipt clean base {archive}")
        path = _require_regular_file(base_dbdat / archive, f"clean base archive {archive}")
        actual = sha256_file(path)
        if actual != declared:
            raise KitArchiveMaterialisationError(
                f"clean base archive {archive} does not match the archive used to render the bindings"
            )
        base_bytes[archive] = path.read_bytes()
        records[archive] = _records_by_carrier(path)
        hashes[archive] = actual
    return base_bytes, records, hashes


def _build_archives(*, binding_rows: Mapping[int, list[dict[str, Any]]], bindings_root: Path,
                    base_bytes: Mapping[str, bytes], records: Mapping[str, Mapping[int, Any]]) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    staged = {archive: bytearray(payload) for archive, payload in base_bytes.items()}
    events: list[dict[str, Any]] = []
    targets: set[tuple[str, int]] = set()
    for carrier in sorted(binding_rows):
        by_archive: dict[str, dict[str, Any]] = {}
        for artifact in binding_rows[carrier]:
            archive = _archive_for_artifact(artifact=artifact, carrier=carrier)
            if archive in by_archive:
                raise KitArchiveMaterialisationError(f"binding carrier {carrier} collides on target archive {archive}")
            by_archive[archive] = artifact
        if set(by_archive) != set(ARCHIVES):
            raise KitArchiveMaterialisationError(f"binding carrier {carrier} does not cover every compact-kit archive")
        for archive in ARCHIVES:
            target = (archive, carrier)
            if target in targets:
                raise KitArchiveMaterialisationError(f"kit archive materialisation target collision: {archive} carrier {carrier}")
            targets.add(target)
            record = records[archive].get(carrier)
            if record is None:
                raise KitArchiveMaterialisationError(f"verified base {archive} has no kit record for carrier {carrier}")
            payload, event = _candidate_payload(
                artifact=by_archive[archive], carrier=carrier, archive=archive,
                bindings_root=bindings_root, record=record,
            )
            start, end = int(record.bitmap_offset), int(record.bitmap_offset + record.bitmap_length)
            staged[archive][start:end] = payload
            events.append(event)

    output = {archive: bytes(payload) for archive, payload in staged.items()}
    for archive in ARCHIVES:
        after_records = _records_by_carrier_bytes(archive, output[archive])
        before_records = records[archive]
        changed_carriers = {event["carrier_id"] for event in events if event["archive"] == archive}
        for carrier in changed_carriers:
            event = next(value for value in events if value["archive"] == archive and value["carrier_id"] == carrier)
            if sha256_bytes(after_records[carrier].raw_bitmap) != event["bitmap_sha256_after"]:
                raise KitArchiveMaterialisationError(f"post-write readback failed for {archive} carrier {carrier}")
        for carrier, before in before_records.items():
            if carrier not in changed_carriers and after_records.get(carrier) is None:
                raise KitArchiveMaterialisationError(f"post-write record disappeared from {archive} carrier {carrier}")
            if carrier not in changed_carriers and after_records[carrier].raw_bitmap != before.raw_bitmap:
                raise KitArchiveMaterialisationError(f"unbound kit record changed in {archive} carrier {carrier}")
    return output, sorted(events, key=lambda value: (value["archive"], value["carrier_id"]))


def _records_by_carrier_bytes(archive_name: str, payload: bytes) -> dict[int, Any]:
    records: dict[int, Any] = {}
    for record in iter_obfuscated_bmp_records_from_bytes(
        archive_name, payload, file_name_pattern=r"^EQ96\d{4}\.BMP$"
    ):
        match = _KIT_NAME.fullmatch(str(record.file_name))
        if match is None:
            continue
        carrier = int(match.group("carrier"))
        if carrier in records:
            raise KitArchiveMaterialisationError(f"{archive_name} has colliding kit records for carrier {carrier}")
        try:
            validate_minifoto_bitmap(record.raw_bitmap)
        except ValueError as exc:
            raise KitArchiveMaterialisationError(
                f"{archive_name} carrier {carrier} has an unsupported bitmap format after materialisation"
            ) from exc
        records[carrier] = record
    if not records:
        raise KitArchiveMaterialisationError(f"{archive_name} has no recognised EQ96 compact-kit records after materialisation")
    return records


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def materialise(*, render_bindings: Path, render_receipt: Path, clean_dbdat: Path, output_dir: Path) -> dict[str, Any]:
    """Build a one-shot archive stage and return its release-ineligible receipt."""
    if _path_lexists(output_dir):
        raise KitArchiveMaterialisationError(f"refusing to replace existing output directory: {output_dir}")
    binding_path = _require_regular_file(render_bindings, "kit render bindings")
    receipt_path = _require_regular_file(render_receipt, "kit render receipt")
    clean_dbdat = clean_dbdat.expanduser()
    if clean_dbdat.is_symlink():
        raise KitArchiveMaterialisationError("clean DBDAT must not be a symlink")
    base_dbdat = clean_dbdat.resolve()
    if not base_dbdat.is_dir():
        raise KitArchiveMaterialisationError("clean DBDAT must be an existing non-symlink directory")
    binding = _read_object(binding_path, "kit render bindings")
    receipt = _read_object(receipt_path, "kit render receipt")
    binding_rows = _verify_render_provenance(binding=binding, receipt=receipt)
    base_bytes, records, base_hashes = _verify_base_archives(base_dbdat=base_dbdat, receipt=receipt)
    output_archives, events = _build_archives(
        binding_rows=binding_rows,
        bindings_root=binding_path.parent.resolve(),
        base_bytes=base_bytes,
        records=records,
    )
    after_hashes = {archive: sha256_bytes(output_archives[archive]) for archive in ARCHIVES}
    result = {
        "schema_version": SCHEMA,
        "result": "archive-stage-materialised",
        "release_eligible": False,
        "policy": {
            "writes": "new-write-once compact-kit archive stage only",
            "base": "all three clean archives must exactly match the render receipt provenance",
            "binding": "every rendered receipt carrier and artifact must exactly match the supplied binding",
            "bitmap": "only matched 8-bit OS/2 bitmap pixel bytes may change",
            "release": "this stage does not compile, audit, launch, or release a database",
        },
        "season": dict(receipt.get("season") or {}),
        "provenance": {
            "kit_render_bindings": {"path": str(binding_path), "sha256": sha256_file(binding_path)},
            "kit_render_receipt": {"path": str(receipt_path), "sha256": sha256_file(receipt_path)},
            "kit_catalogue_sha256": binding["kit_catalogue_sha256"],
            "clean_dbdat": str(base_dbdat),
            "clean_archive_sha256": base_hashes,
        },
        "coverage": {
            "bound_carrier_count": len(binding_rows),
            "patched_record_count": len(events),
            "archive_count": len(ARCHIVES),
        },
        "archives": {
            archive: {
                "relative_path": f"archives/{archive}",
                "sha256_before": base_hashes[archive],
                "sha256_after": after_hashes[archive],
                "patched_record_count": sum(1 for event in events if event["archive"] == archive),
            }
            for archive in ARCHIVES
        },
        "events": events,
    }

    output_parent = output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_parent))
    created_output = False
    try:
        archive_dir = temporary_root / "archives"
        archive_dir.mkdir()
        for archive in ARCHIVES:
            (archive_dir / archive).write_bytes(output_archives[archive])
        (temporary_root / "kit-archive-materialisation-receipt-v1.json").write_bytes(
            canonical_json_bytes(result)
        )
        # Reserve the final directory with mkdir, whose create operation is
        # exclusive.  We then move the fully written children into that new
        # directory.  This avoids rename's platform-dependent replacement
        # behaviour for an existing empty directory.
        try:
            os.mkdir(output_dir)
        except FileExistsError as exc:
            raise KitArchiveMaterialisationError(
                f"refusing to replace existing output directory: {output_dir}"
            ) from exc
        created_output = True
        os.rename(archive_dir, output_dir / "archives")
        os.rename(
            temporary_root / "kit-archive-materialisation-receipt-v1.json",
            output_dir / "kit-archive-materialisation-receipt-v1.json",
        )
        temporary_root.rmdir()
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        if created_output:
            shutil.rmtree(output_dir, ignore_errors=True)
        raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-render-bindings", type=Path, required=True)
    parser.add_argument("--kit-render-receipt", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="new, nonexistent archive-stage directory")
    args = parser.parse_args()
    try:
        result = materialise(
            render_bindings=args.kit_render_bindings,
            render_receipt=args.kit_render_receipt,
            clean_dbdat=args.clean_dbdat,
            output_dir=args.output_dir,
        )
    except KitArchiveMaterialisationError as exc:
        parser.error(str(exc))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
