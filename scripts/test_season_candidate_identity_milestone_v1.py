from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignments  # noqa: E402
from scripts import season_candidate_identity_milestone_v1 as milestone  # noqa: E402


def _write(path: Path, value: dict[str, object]) -> str:
    path.write_bytes(assignments.canonical_json_bytes(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_select_bound_source_uses_assignment_hash_not_receipt_count(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    calendar = {"schema_version": "fixture", "kind": "calendar"}
    split = {"schema_version": "fixture", "kind": "split"}
    calendar_hash = _write(sources / "footballsquads-calendar.json", calendar)
    _write(sources / "footballsquads-split.json", split)

    path, selected = milestone._select_bound_source(sources_dir=sources, expected_source_hash=calendar_hash)

    assert path.name == "footballsquads-calendar.json"
    assert selected == calendar


def test_select_bound_source_refuses_missing_or_ambiguous_hash(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    receipt = {"schema_version": "fixture", "kind": "calendar"}
    digest = _write(sources / "footballsquads-calendar.json", receipt)
    with pytest.raises(milestone.SeasonCandidateMilestoneError, match="matching"):
        milestone._select_bound_source(sources_dir=sources, expected_source_hash="a" * 64)
    _write(sources / "footballsquads-calendar-copy.json", receipt)
    with pytest.raises(milestone.SeasonCandidateMilestoneError, match="matching"):
        milestone._select_bound_source(sources_dir=sources, expected_source_hash=digest)
