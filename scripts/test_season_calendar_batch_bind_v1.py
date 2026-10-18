"""Tests for the non-promoting calendar batch binder."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from season_calendar_batch_bind_v1 import bind_batch  # noqa: E402
from season_package_v2 import read_canonical_package, write_canonical_package  # noqa: E402
from test_season_package_v2 import _valid_package  # noqa: E402


def test_binds_a_calendar_without_promoting_the_draft(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    calendar_root = tmp_path / "calendar"
    package_path = input_root / "2015-16" / "draft-season-package.json"
    package = _valid_package()
    write_canonical_package(package_path, package)

    executable = calendar_root / "2015-16" / "MANAGPRE.EXE"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture-calendar-executable")
    receipt = {
        "schema_version": "pm99-calendar-patch-v1",
        "base_year": 1998,
        "target_year": 2015,
        "target_rollover_year": 2016,
        "patch_count": 853,
        "source_operand_counts": {"1998": 50, "1999": 803},
        "after_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    receipt_path = executable.with_name("calendar-receipt.json")
    receipt_path.write_bytes(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )

    output_root = tmp_path / "output"
    result = bind_batch(
        input_root=input_root, calendar_root=calendar_root, output_root=output_root,
        receipt_root_relative=".local/calendar-v1", workers=2,
    )

    assert result["summary"] == {
        "season_count": 1,
        "calendar_bound_draft_count": 1,
        "playable_count": 0,
    }
    bound = read_canonical_package(output_root / "2015-16" / "draft-season-package.calendar-bound.json")
    assert bound["calendar"]["patch_artifact_id"] == "calendar-2015-16-receipt"
    audit = json.loads((output_root / "2015-16" / "calendar-binding-audit.json").read_text(encoding="utf-8"))
    assert audit["runtime_validation_pending"] is True
    assert result["rows"][0]["release_eligible"] is False
