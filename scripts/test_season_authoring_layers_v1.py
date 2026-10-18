"""Contract tests for the distinct generic pre-package authoring layers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_intake_package_v1 as package_intake  # noqa: E402
from scripts import season_source_intake_v1 as source_intake  # noqa: E402
from test_season_source_intake_v1 import (  # noqa: E402
    _candidate_assignment,
    _capture,
    _registry,
)


def test_raw_source_intake_is_not_a_downstream_package_intake() -> None:
    """Keep evidence capture separate from fully reconciled package source."""

    registry = _registry()
    capture = _capture()
    assignment = _candidate_assignment(registry=registry, capture=capture)
    raw = source_intake.build_intake(
        registry=registry,
        source_capture=capture,
        assignment=assignment,
        intake_id="world-2000-01-source-intake",
    )

    source_intake.validate_intake(
        intake=raw,
        registry=registry,
        source_capture=capture,
        assignment=assignment,
    )
    audit = source_intake.audit_intake(
        intake=raw,
        registry=registry,
        source_capture=capture,
        assignment=assignment,
    )

    assert raw["schema_version"] == "pm99-season-source-intake-v1"
    assert audit["coverage"]["source_player_rows_with_unresolved_facts"] == 1
    assert any(
        row["code"] == "source-intake-is-not-a-package-or-database-build"
        for row in audit["blockers"]
    )
    with pytest.raises(package_intake.IntakePackageError, match="must have exactly"):
        package_intake.validate_intake(raw)
