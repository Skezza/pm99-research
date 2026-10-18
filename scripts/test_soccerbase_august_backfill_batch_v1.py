import json

import pytest

from scripts.soccerbase_august_backfill_batch_v1 import _scope


def test_scope_selects_requested_seasons_in_order(tmp_path):
    path = tmp_path / "scope.json"
    path.write_text(json.dumps({
        "schema_version": "pm99-soccerbase-august-scope-v1",
        "seasons": [
            {"season": "2002-03", "competition": "X", "season_id": 2, "tournament_id": 3},
            {"season": "2001-02", "competition": "X", "season_id": 1, "tournament_id": 4},
        ],
    }))
    assert [row["season"] for row in _scope(path, {"2002-03"})] == ["2002-03"]


def test_scope_rejects_unknown_requested_season(tmp_path):
    path = tmp_path / "scope.json"
    path.write_text(json.dumps({"schema_version": "pm99-soccerbase-august-scope-v1", "seasons": []}))
    with pytest.raises(ValueError, match="absent"):
        _scope(path, {"2002-03"})
