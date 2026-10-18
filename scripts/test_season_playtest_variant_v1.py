from __future__ import annotations

import copy
import hashlib

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import season_playtest_variant_v1 as variants


def _inventory(rows: list[tuple[str, bytes]]) -> dict[str, object]:
    files = [
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
        for path, payload in rows
    ]
    return {
        "schema": pipeline.FILE_INVENTORY_SCHEMA,
        "file_count": len(files),
        "total_bytes": sum(row["size"] for row in files),
        "files_fingerprint": pipeline.canonical_json_sha256(files),
        "files": files,
    }


def _calendar(year: int, after: str) -> dict[str, object]:
    return {
        "schema_version": "pm99-calendar-patch-v1",
        "profile": "managpre-calendar-1998-99-to-target-v1",
        "base_year": 1998,
        "rollover_year": 1999,
        "target_year": year,
        "target_rollover_year": year + 1,
        "before_sha256": "a" * 64,
        "after_sha256": after,
        "patch_count": 853,
        "source_operand_counts": {1998: 50, 1999: 803},
        "patches": [],
    }


def test_calendar_only_difference_accepts_only_executable_change() -> None:
    baseline = _inventory([("DBDAT/JUG98030.FDI", b"players"), ("MANAGPRE.EXE", b"old")])
    output = _inventory([("DBDAT/JUG98030.FDI", b"players"), ("MANAGPRE.EXE", b"new")])
    difference = variants._assert_calendar_only_difference(
        base_inventory=baseline,
        output_inventory=output,
        baseline_exe_sha256=hashlib.sha256(b"old").hexdigest(),
        target_exe_sha256=hashlib.sha256(b"new").hexdigest(),
    )
    assert [row["path"] for row in difference["changed"]] == ["MANAGPRE.EXE"]


def test_calendar_only_difference_rejects_database_drift() -> None:
    baseline = _inventory([("DBDAT/JUG98030.FDI", b"players"), ("MANAGPRE.EXE", b"old")])
    output = _inventory([("DBDAT/JUG98030.FDI", b"different"), ("MANAGPRE.EXE", b"new")])
    with pytest.raises(variants.PlaytestVariantError, match="exactly MANAGPRE.EXE"):
        variants._assert_calendar_only_difference(
            base_inventory=baseline,
            output_inventory=output,
            baseline_exe_sha256=hashlib.sha256(b"old").hexdigest(),
            target_exe_sha256=hashlib.sha256(b"new").hexdigest(),
        )


def test_manifest_rejects_target_calendar_not_matching_target_season() -> None:
    baseline = _inventory([("MANAGPRE.EXE", b"old")])
    output = _inventory([("MANAGPRE.EXE", b"new")])
    baseline_calendar = _calendar(2015, hashlib.sha256(b"old").hexdigest())
    target_calendar = _calendar(2000, hashlib.sha256(b"new").hexdigest())
    manifest = variants._manifest(
        variant_id="pm99-2000-01-calendar-r0",
        target_season="2000-01",
        baseline_id="pm99-2015-16-world-r0",
        baseline_season="2015-16",
        base_inventory=baseline,
        output_inventory=output,
        receipts={key: "b" * 64 for key in variants.RECEIPT_NAMES},
        baseline_calendar=baseline_calendar,
        target_calendar=target_calendar,
    )
    assert variants.validate_manifest(manifest)["target_season"] == "2000-01"
    invalid = copy.deepcopy(manifest)
    invalid["calendar"]["target_start_year"] = 2001
    with pytest.raises(variants.PlaytestVariantError, match="target year"):
        variants.validate_manifest(invalid)


def test_target_26_seasons_is_exact_requested_range() -> None:
    assert len(variants.TARGET_26_SEASONS) == 26
    assert variants.TARGET_26_SEASONS[0] == "2000-01"
    assert variants.TARGET_26_SEASONS[-1] == "2025-26"
