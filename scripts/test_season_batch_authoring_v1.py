"""Tests for the season-neutral batch authoring coordinator."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import season_batch_authoring_v1 as batch


HASH = "a" * 64


def _capture(label: str, club_count: int, players_per_club: int) -> dict:
    clubs = []
    for club_index in range(club_count):
        clubs.append({
            "club_name": f"Club {club_index}",
            "country_catalog": "spain",
            "competition_catalog": "laliga",
            "competition_name": "League",
            "source_path": f"spain/{label}/club-{club_index}.txt",
            "source_sha256": HASH,
            "players": [{"name": f"Player {club_index}-{offset}"} for offset in range(players_per_club)],
        })
    return {
        "schema_version": batch.CAPTURE_SCHEMA,
        "source": {"title": "Fixture"},
        "season": {"label": label},
        "clubs": clubs,
    }


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(batch.canonical_json_bytes(value))


def _registry() -> dict:
    return {
        "carriers": [
            {"carrier_id": 1, "baseline_club": {"name": "Old Club", "full_name": "Old Club"}, "roster_slots": [1]},
            {"carrier_id": 2, "baseline_club": {"name": "Other Club", "full_name": "Other Club"}, "roster_slots": [2]},
        ]
    }


def test_batch_selects_largest_valid_capture_and_never_claims_database(tmp_path: Path) -> None:
    season_dir = tmp_path / "seasons" / "2000-01"
    _write(season_dir / "sources/small.json", _capture("2000/01", 1, 20))
    _write(season_dir / "sources/largest.json", _capture("2000/01", 2, 3))
    _write(season_dir / "sources/not-a-capture.json", {"schema_version": "other"})
    _write(season_dir / batch.REGISTRY_NAME, _registry())

    matrix = batch.build_batch(
        seasons_root=tmp_path / "seasons",
        output_root=tmp_path / "output",
        selected=["2000-01"],
        template_package=None,
    )

    row = matrix["rows"][0]
    assert row["lanes"]["source_capture"]["path"] == "sources/largest.json"
    assert row["lanes"]["source_capture"]["club_count"] == 2
    assert row["status"] == "blocked"
    assert matrix["summary"]["database_count"] == 0
    assert (tmp_path / "output/2000-01/carrier-allocation.json").is_file()
    assert not any(path.suffix.upper() == ".FDI" for path in (tmp_path / "output").rglob("*"))
    codes = {item["code"] for item in row["hard_blockers"]}
    assert "target-season-managers-input-missing-or-invalid" in codes
    assert "target-season-kits-input-missing-or-invalid" in codes
    assert "opening-lineups-input-missing-or-invalid" in codes


def test_materialises_package_and_rating_lanes_when_inputs_exist(tmp_path: Path, monkeypatch) -> None:
    season_dir = tmp_path / "seasons/2000-01"
    capture = _capture("2000/01", 1, 1)
    _write(season_dir / "sources/capture.json", capture)
    _write(season_dir / batch.REGISTRY_NAME, _registry())
    _write(season_dir / batch.INTAKE_NAME, {"source_capture_sha256": batch.document_sha256(capture)})
    _write(season_dir / batch.RATING_INPUT_NAME, {"rating": "input"})
    for filename in batch.REQUIRED_EVIDENCE.values():
        _write(season_dir / filename, {"evidence": filename})

    calls = {"package": 0, "ratings": 0}

    def fake_draft(*, template, source_intake, registry, carrier_allocation, template_prevalidated=False):
        calls["package"] += 1
        assert template_prevalidated is True
        assert carrier_allocation["schema_version"] == batch.carrier_allocation.SCHEMA
        return ({"draft": True}, {"release_eligible": False, "coverage": {"players": 1}, "hard_blockers": [{"code": "fixture-blocker", "message": "fixture"}]})

    def fake_ratings(payload):
        calls["ratings"] += 1
        return {"coverage": {"player_count": 1}, "ratings": True}

    monkeypatch.setattr(batch.package_builder, "build_draft", fake_draft)
    monkeypatch.setattr(batch.editorial_ratings, "build_rating_output", fake_ratings)
    row = batch.author_season(
        season_id="2000-01",
        season_dir=season_dir,
        output_dir=tmp_path / "output/2000-01",
        template={"template": True},
    )

    assert calls == {"package": 1, "ratings": 1}
    assert row["lanes"]["package_candidate"]["status"] == "draft-materialised"
    assert row["lanes"]["editorial_ratings"]["status"] == "materialised"
    assert {item["code"] for item in row["hard_blockers"]} == {"carrier-allocation-gaps", "fixture-blocker"}
    assert json.loads((tmp_path / "output/2000-01/draft-season-package.json").read_text())["draft"] is True


def test_selection_tie_break_is_path_stable(tmp_path: Path) -> None:
    season_dir = tmp_path / "season"
    capture = _capture("2000/01", 1, 1)
    _write(season_dir / "sources/z.json", capture)
    _write(season_dir / "sources/a.json", capture)
    path, selected, rejected = batch.select_capture(season_dir)
    assert path == season_dir / "sources/a.json"
    assert selected == capture
    assert rejected == []
