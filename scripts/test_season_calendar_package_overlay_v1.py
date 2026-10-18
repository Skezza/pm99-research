from __future__ import annotations

import pytest

from scripts import season_calendar_package_overlay_v1 as overlay
from scripts import test_season_package_v2 as fixtures


def _receipt():
    return {"schema_version": "pm99-calendar-patch-v1", "base_year": 1998, "target_year": 2015,
            "target_rollover_year": 2016, "patch_count": 853,
            "source_operand_counts": {"1998": 50, "1999": 803}, "after_sha256": "b" * 64}


def test_binds_exact_receipt_and_keeps_runtime_pending() -> None:
    package, audit = overlay.bind_calendar(package=fixtures._valid_package(), receipt=_receipt(),
                                           receipt_relative_path=".local/calendar-v1/2015-16/calendar-receipt.json",
                                           receipt_sha256="a" * 64,
                                           executable_sha256="b" * 64)
    assert package["calendar"]["patch_artifact_id"] == "calendar-2015-16-receipt"
    assert package["artifacts"][-1]["sha256"] == "a" * 64
    assert audit["receipt_sha256"] == "a" * 64
    assert package["calendar"]["proof"]["grade"] == "static-contract"
    assert audit["runtime_validation_pending"] is True


def test_rejects_wrong_executable() -> None:
    with pytest.raises(overlay.CalendarOverlayError, match="differs"):
        overlay.bind_calendar(package=fixtures._valid_package(), receipt=_receipt(),
                              receipt_relative_path="receipt.json", receipt_sha256="a" * 64,
                              executable_sha256="c" * 64)
