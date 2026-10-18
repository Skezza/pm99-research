#!/usr/bin/env python3
"""Validate a bounded, allocation-bound seasonal kit source/render chunk.

Unlike the five-carrier proof-of-mechanics validator, this accepts a frozen
chunk of up to 25 assignments.  It is deliberately asset-only: a successful
receipt proves source, render, and archive-stage provenance, never a compiled
or playable database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.season_kit_catalogue_v1 import canonical_json_bytes


SCHEMA = "pm99-season-kit-chunk-validation-receipt-v1"
PLAN_SCHEMA = "pm99-season-kit-source-chunk-plan-v1"
CAPTURE_SCHEMA = "pm99-season-kit-source-capture-v1"
REQUEST_SCHEMA = "pm99-season-kit-catalogue-request-v1"
CATALOGUE_SCHEMA = "pm99-season-kit-catalogue-v1"
BINDINGS_SCHEMA = "pm99-season-kit-render-bindings-v1"
RENDER_SCHEMA = "pm99-season-kit-render-receipt-v1"
STAGE_SCHEMA = "pm99-season-kit-archive-materialisation-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")


class ChunkValidationError(ValueError):
    """A chunk output is stale, malformed, or outside its frozen scope."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _doc(path: Path, label: str, schema: str | None = None) -> tuple[Path, dict[str, Any], str]:
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ChunkValidationError(f"{label} must be a regular non-symlink file: {path}")
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChunkValidationError(f"{label} is not canonical JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != payload:
        raise ChunkValidationError(f"{label} must be a canonical JSON object")
    if schema is not None and value.get("schema_version") != schema:
        raise ChunkValidationError(f"{label} must use {schema}")
    return path.resolve(), value, _sha(payload)


def _ids(rows: Any, label: str) -> list[int]:
    if not isinstance(rows, list):
        raise ChunkValidationError(f"{label} must be a list")
    values = [row.get("carrier_id") if isinstance(row, Mapping) else None for row in rows]
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in values):
        raise ChunkValidationError(f"{label} has invalid carrier IDs")
    if values != sorted(values) or len(set(values)) != len(values):
        raise ChunkValidationError(f"{label} carrier IDs must be sorted and unique")
    return values


def validate(*, plan_path: Path, subset_path: Path, capture_path: Path, request_path: Path, catalogue_path: Path, bindings_path: Path, render_receipt_path: Path, archive_stage: Path) -> dict[str, Any]:
    plan_path, plan, plan_sha = _doc(plan_path, "chunk plan", PLAN_SCHEMA)
    subset_path, subset, subset_sha = _doc(subset_path, "subset allocation")
    assignments = subset.get("assignments")
    chunk_ids = _ids(assignments, "subset allocation assignments")
    if not 1 <= len(chunk_ids) <= 25:
        raise ChunkValidationError("subset allocation must contain one to 25 assignments")
    selection = plan.get("selection")
    full = plan.get("full_allocation")
    if not isinstance(selection, Mapping) or not isinstance(full, Mapping):
        raise ChunkValidationError("chunk plan has no selection/full-allocation binding")
    if plan.get("subset_allocation", {}).get("sha256") != subset_sha:
        raise ChunkValidationError("chunk plan subset allocation hash is stale")
    if selection.get("selected_carrier_ids") != chunk_ids or selection.get("selected_assignments_sha256") != _sha(canonical_json_bytes(assignments)):
        raise ChunkValidationError("chunk plan selection differs from subset allocation")
    full_path = Path(str(full.get("path") or ""))
    try:
        if full_path.is_symlink() or not full_path.is_file() or _sha(full_path.read_bytes()) != full.get("sha256"):
            raise ChunkValidationError("full allocation is unavailable or hash-stale")
    except OSError as exc:
        raise ChunkValidationError(f"full allocation is unavailable: {exc}") from exc

    capture_path, capture, capture_sha = _doc(capture_path, "source capture", CAPTURE_SCHEMA)
    provenance = capture.get("provenance")
    capture_rows = capture.get("rows")
    if not isinstance(provenance, Mapping) or _ids(capture_rows, "source capture rows") != chunk_ids:
        raise ChunkValidationError("source capture does not exactly cover this chunk")
    if provenance.get("allocation_sha256") != subset_sha or (provenance.get("chunk_plan") or {}).get("sha256") != plan_sha:
        raise ChunkValidationError("source capture is not bound to this plan/subset")
    if provenance.get("full_allocation_sha256") != full.get("sha256") or provenance.get("chunk_carrier_ids") != chunk_ids:
        raise ChunkValidationError("source capture full-allocation or carrier provenance is stale")
    if provenance.get("stale_capture_reuse") != "prohibited-fresh-cache-created-for-this-chunk":
        raise ChunkValidationError("source capture does not prohibit stale cache reuse")

    request_path, request, request_sha = _doc(request_path, "catalogue request", REQUEST_SCHEMA)
    catalogue_path, catalogue, catalogue_sha = _doc(catalogue_path, "kit catalogue", CATALOGUE_SCHEMA)
    if _ids(request.get("clubs"), "catalogue request clubs") != chunk_ids or _ids(catalogue.get("rows"), "kit catalogue rows") != chunk_ids:
        raise ChunkValidationError("catalogue inputs do not exactly cover the chunk")
    if (catalogue.get("provenance") or {}).get("request_sha256") != request_sha:
        raise ChunkValidationError("kit catalogue is not bound to its request")

    ready_ids = [row["carrier_id"] for row in catalogue["rows"] if row.get("status") == "source-ready"]
    capture_ready_ids = [row["carrier_id"] for row in capture_rows if row.get("status") == "revision-captured-home-fields-ready"]
    if ready_ids != capture_ready_ids:
        raise ChunkValidationError("catalogue source-ready rows differ from the fresh capture")

    bindings_path, bindings, bindings_sha = _doc(bindings_path, "render bindings", BINDINGS_SCHEMA)
    render_path, render, render_sha = _doc(render_receipt_path, "render receipt", RENDER_SCHEMA)
    binding_ids = _ids(bindings.get("clubs"), "render bindings clubs")
    rendered_ids = [row.get("carrier_id") for row in (render.get("rows") or []) if isinstance(row, Mapping) and row.get("status") == "rendered-source-ready"]
    if binding_ids != rendered_ids or bindings.get("kit_catalogue_sha256") != catalogue_sha or render.get("kit_catalogue_sha256") != catalogue_sha:
        raise ChunkValidationError("render outputs do not bind/cover the exact source-ready set")
    if not set(binding_ids).issubset(ready_ids) or (render.get("coverage") or {}).get("artifact_count") != len(binding_ids) * len(ARCHIVES):
        raise ChunkValidationError("render outputs contain unsafe carriers or stale artifact coverage")

    stage_path, stage, stage_sha = _doc(archive_stage / "kit-archive-materialisation-receipt-v1.json", "archive-stage receipt", STAGE_SCHEMA)
    stage_provenance = stage.get("provenance")
    if stage.get("result") != "archive-stage-materialised" or stage.get("release_eligible") is not False or not isinstance(stage_provenance, Mapping):
        raise ChunkValidationError("archive stage is not an explicitly non-release materialisation")
    if (stage_provenance.get("kit_render_bindings") or {}).get("sha256") != bindings_sha or (stage_provenance.get("kit_render_receipt") or {}).get("sha256") != render_sha or stage_provenance.get("kit_catalogue_sha256") != catalogue_sha:
        raise ChunkValidationError("archive stage does not bind the exact render inputs")
    events = stage.get("events")
    expected_events = {(archive, carrier) for archive in ARCHIVES for carrier in binding_ids}
    actual_events = {(row.get("archive"), row.get("carrier_id")) for row in events if isinstance(row, Mapping)} if isinstance(events, list) else set()
    if actual_events != expected_events:
        raise ChunkValidationError("archive-stage events do not exactly cover rendered carriers")
    archive_rows = stage.get("archives")
    if not isinstance(archive_rows, Mapping):
        raise ChunkValidationError("archive stage has no archive hashes")
    for archive in ARCHIVES:
        output = archive_stage / "archives" / archive
        if not output.is_file() or archive_rows.get(archive, {}).get("sha256_after") != _sha(output.read_bytes()):
            raise ChunkValidationError(f"archive stage hash is stale for {archive}")

    gap_rows = [{"carrier_id": row["carrier_id"], "club_name": row["club_name"], "capture_status": row.get("status")} for row in capture_rows if row["carrier_id"] not in ready_ids]
    render_gaps = [carrier for carrier in ready_ids if carrier not in binding_ids]
    return {
        "schema_version": SCHEMA,
        "result": "chunk-validated-not-release",
        "release_eligible": False,
        "scope": {"season": subset.get("season"), "chunk_carrier_ids": chunk_ids, "chunk_club_count": len(chunk_ids), "rendered_carrier_ids": binding_ids},
        "provenance": {
            "chunk_plan": {"path": str(plan_path), "sha256": plan_sha},
            "subset_allocation": {"path": str(subset_path), "sha256": subset_sha},
            "source_capture": {"path": str(capture_path), "sha256": capture_sha},
            "catalogue_request": {"path": str(request_path), "sha256": request_sha},
            "kit_catalogue": {"path": str(catalogue_path), "sha256": catalogue_sha},
            "render_bindings": {"path": str(bindings_path), "sha256": bindings_sha},
            "render_receipt": {"path": str(render_path), "sha256": render_sha},
            "archive_stage_receipt": {"path": str(stage_path), "sha256": stage_sha},
        },
        "coverage": {"fresh_revision_pinned_source_count": len(ready_ids), "explicit_source_gap_count": len(gap_rows), "rendered_carrier_count": len(binding_ids), "render_gap_count": len(render_gaps), "materialised_archive_event_count": len(actual_events)},
        "gaps": {"source": gap_rows, "render": render_gaps},
        "not_claimed": ["No target-season database was compiled.", "No archive stage was copied into a game tree.", "No visual or gameplay runtime evidence is claimed."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--subset-allocation", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--catalogue-request", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--render-receipt", type=Path, required=True)
    parser.add_argument("--archive-stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new validation receipt path")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error(f"refusing to replace validation receipt: {args.output}")
    try:
        result = validate(plan_path=args.plan, subset_path=args.subset_allocation, capture_path=args.capture, request_path=args.catalogue_request, catalogue_path=args.catalogue, bindings_path=args.bindings, render_receipt_path=args.render_receipt, archive_stage=args.archive_stage)
    except ChunkValidationError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"result": result["result"], "coverage": result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
