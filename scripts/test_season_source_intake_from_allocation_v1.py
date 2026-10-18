from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import season_carrier_allocation_v1 as allocator
from scripts import season_source_intake_from_allocation_v1 as subject
from scripts import season_source_intake_v1 as intake_lib


def test_real_2000_inputs_adapt_and_validate() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / ".local/season-2000-01/carrier-allocation-expanded-v1.json",
             root / "seasons/2000-01/fixed-carrier-registry.json",
             root / ".local/season-2000-01/world-squads-composed-v1.json"]
    if not all(path.is_file() for path in paths):
        pytest.skip("local generated source backfill is unavailable")
    allocation, registry, source = [json.loads(path.read_text()) for path in paths]
    assignment = subject.adapt(allocation=allocation, registry=registry, source=source, assignment_id="test-world-assignment")
    assert len(assignment["assignments"]) == allocation["coverage"]["assignment_count"]
    assert {row["status"] for row in assignment["assignments"]} == {"candidate"}
    intake = intake_lib.build_intake(registry=registry, source_capture=source, assignment=assignment, intake_id="test-world-intake")
    intake_lib.validate_intake(intake=intake, registry=registry, source_capture=source, assignment=assignment)


def test_hash_mismatch_fails_closed() -> None:
    allocation = {"schema_version": subject.ALLOCATION_SCHEMA, "assignments": [], "source_sha256": "0" * 64, "registry_sha256": "0" * 64}
    with pytest.raises(Exception, match="hash-bound"):
        subject.adapt(allocation=allocation, registry={}, source={}, assignment_id="test-assignment")
