from __future__ import annotations

import pytest

from scripts import season_batch_matrix_merge_v1 as merger
from scripts import season_batch_authoring_v1 as batch


def _matrix(season: str, *, draft: bool = True):
    return {"schema_version": batch.SCHEMA, "rows": [{"season_id": season, "status": "blocked", "lanes": {}, "outputs": {"draft_package": "x"} if draft else {}, "hard_blockers": []}], "summary": {}}


def test_merges_disjoint_rows_in_season_order() -> None:
    result = merger.merge([_matrix("2001-02"), _matrix("2000-01")])
    assert [row["season_id"] for row in result["rows"]] == ["2000-01", "2001-02"]
    assert result["summary"] == {"season_count": 2, "candidate_ready_count": 0, "blocked_count": 2, "draft_package_count": 2, "database_count": 0}


def test_rejects_duplicate_season() -> None:
    with pytest.raises(merger.MatrixMergeError, match="duplicate"):
        merger.merge([_matrix("2000-01"), _matrix("2000-01")])


def test_explicit_later_replacement_is_supported() -> None:
    result = merger.merge([_matrix("2000-01", draft=False), _matrix("2000-01")], replace_duplicates=True)
    assert result["summary"]["draft_package_count"] == 1
