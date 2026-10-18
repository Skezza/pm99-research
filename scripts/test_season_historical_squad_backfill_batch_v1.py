from __future__ import annotations

from pathlib import Path
import json
import pytest

from scripts import season_historical_squad_backfill_batch_v1 as subject


def test_discover_base_selects_largest_canonical_capture() -> None:
    root = Path(__file__).resolve().parents[1]
    assert subject.discover_base(root / "seasons/2004-05").name == "footballsquads-2004-05-composed.json"


def test_missing_scope_excludes_existing_country_aliases() -> None:
    base = {"clubs": [{"country_catalog": "holland"}, {"country_catalog": "ger"}]}
    scope = [
        {"country_catalog": "netherlands", "competition_catalog": "ere", "competition_name": "E", "source_competition_code": "NL1"},
        {"country_catalog": "germany", "competition_catalog": "bundes", "competition_name": "B", "source_competition_code": "L1"},
        {"country_catalog": "belgium", "competition_catalog": "eerste", "competition_name": "P", "source_competition_code": "BE1"},
    ]
    assert [row["country_catalog"] for row in subject.missing_scope(base, scope)] == ["belgium"]


def test_publish_revision_is_immutable_and_current_is_hash_bound(tmp_path: Path) -> None:
    artifacts = {name: {"name": name} for name in (
        "source", "supplemental", "gaps", "allocation", "assignment", "intake"
    )}
    revision_id, manifest = subject._publish_revision(local=tmp_path, season="2000-01", artifacts=artifacts)
    assert json.loads((tmp_path / "current.json").read_text()) == manifest
    assert all((tmp_path / row["path"]).is_file() for row in manifest["artifacts"].values())
    assert subject._publish_revision(local=tmp_path, season="2000-01", artifacts=artifacts)[0] == revision_id


def test_publish_revision_supports_valid_named_provider_artifacts(tmp_path: Path) -> None:
    _revision, manifest = subject._publish_revision(
        local=tmp_path, season="2000-01", artifacts={"transfermarkt_argentina": {"clubs": []}}
    )
    assert manifest["artifacts"]["transfermarkt_argentina"]["path"].endswith(
        "transfermarkt-argentina.json"
    )
    with pytest.raises(ValueError, match="invalid revision artifact name"):
        subject._publish_revision(local=tmp_path, season="2000-01", artifacts={"../bad": {}})
