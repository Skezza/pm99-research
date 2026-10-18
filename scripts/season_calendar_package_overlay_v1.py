#!/usr/bin/env python3
"""Bind a verified calendar patch receipt to a season package draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402

SCHEMA = "pm99-season-calendar-package-overlay-v1"


class CalendarOverlayError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _validated_patch_count(receipt: Mapping[str, Any]) -> int:
    """Accept the fixed 853 year operands plus declared day corrections."""
    counts = receipt.get("source_operand_counts")
    if not isinstance(counts, Mapping) or counts.get("1998") != 50 or counts.get("1999") != 803:
        raise CalendarOverlayError("calendar receipt does not match the proved year-operand profile")
    day_overrides = receipt.get("day_overrides", [])
    if not isinstance(day_overrides, list) or any(not isinstance(row, Mapping) for row in day_overrides):
        raise CalendarOverlayError("calendar receipt has malformed day overrides")
    patch_count = receipt.get("patch_count")
    expected = 853 + len(day_overrides)
    if patch_count != expected:
        raise CalendarOverlayError("calendar receipt patch count does not match its declared corrections")
    return expected


def bind_calendar(*, package: Mapping[str, Any], receipt: Mapping[str, Any], receipt_relative_path: str,
                  receipt_sha256: str, executable_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    output = json.loads(json.dumps(package))
    package_v2.validate_package(output, strict=False)
    season = output["season"]
    if receipt.get("schema_version") != "pm99-calendar-patch-v1":
        raise CalendarOverlayError("unsupported calendar receipt")
    if receipt.get("target_year") != season["start_year"] or receipt.get("target_rollover_year") != season["end_year"]:
        raise CalendarOverlayError("calendar receipt targets a different season")
    if receipt.get("base_year") != 1998:
        raise CalendarOverlayError("calendar receipt does not match the proved PM99 patch profile")
    patch_count = _validated_patch_count(receipt)
    if receipt.get("after_sha256") != executable_sha256:
        raise CalendarOverlayError("calendar executable hash differs from its receipt")
    if not package_v2.SHA256_RE.fullmatch(executable_sha256):
        raise CalendarOverlayError("calendar executable hash is invalid")
    if not package_v2.SHA256_RE.fullmatch(receipt_sha256):
        raise CalendarOverlayError("calendar receipt hash is invalid")
    suffix = f"{season['start_year']}-{str(season['end_year'])[-2:]}"
    artifact_id = f"calendar-{suffix}-receipt"
    artifact = {"id": artifact_id, "kind": "calendar-patch", "relative_path": receipt_relative_path, "sha256": receipt_sha256}
    output["artifacts"] = sorted([row for row in output["artifacts"] if row["id"] != artifact_id] + [artifact], key=lambda row: row["id"])
    output["calendar"] = {
        "base_year": 1998, "target_year": season["start_year"],
        "target_rollover_year": season["end_year"], "patch_artifact_id": artifact_id,
        "proof": {"grade": "static-contract", "artifact_id": artifact_id},
    }
    package_v2.validate_package(output, strict=False)
    audit = {
        "schema_version": SCHEMA, "season": dict(season), "receipt_sha256": receipt_sha256,
        "executable_sha256": executable_sha256, "patch_count": patch_count,
        "output_package_sha256": hashlib.sha256(_bytes(output)).hexdigest(),
        "runtime_validation_pending": True,
    }
    return output, audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--receipt-relative-path", required=True)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package = json.loads(args.package.read_text(encoding="utf-8"))
        receipt_bytes = args.receipt.read_bytes()
        receipt = json.loads(receipt_bytes.decode("utf-8"))
        exe_hash = hashlib.sha256(args.executable.read_bytes()).hexdigest()
        output, audit = bind_calendar(package=package, receipt=receipt,
                                      receipt_relative_path=args.receipt_relative_path,
                                      receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
                                      executable_sha256=exe_hash)
        for path, value in ((args.output_package, output), (args.output_audit, audit)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_bytes(value))
    except (OSError, ValueError, json.JSONDecodeError, package_v2.PackageValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(audit, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
