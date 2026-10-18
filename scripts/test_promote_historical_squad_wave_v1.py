from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts import capture_transfermarkt_historical_squads_v1 as capture_lib
from scripts import promote_historical_squad_wave_v1 as wave
from scripts.promote_historical_squad_wave_v1 import _declaration, promote_wave


def test_declaration_is_named_and_path_bound() -> None:
    assert _declaration("transfermarkt_serbia=capture.json") == (
        "transfermarkt_serbia", Path("capture.json")
    )
    with pytest.raises(argparse.ArgumentTypeError):
        _declaration("Bad-Name=capture.json")


def test_wave_refuses_duplicate_capture_names_before_writing(tmp_path: Path) -> None:
    captures = [("provider", tmp_path / "one.json"), ("provider", tmp_path / "two.json")]
    with pytest.raises(ValueError, match="unique"):
        promote_wave(
            season="2000-01", captures=captures, gaps=[], replacements=set(), output_root=tmp_path,
        )


def test_wave_refuses_orphan_replacement_before_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="also be declared"):
        promote_wave(
            season="2000-01", captures=[("provider", tmp_path / "one.json")], gaps=[],
            replacements={"other"}, output_root=tmp_path,
        )


def test_dry_run_projects_without_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    season = "2000-01"
    local = tmp_path / "output" / season
    registry_path = tmp_path / "seasons" / season / "fixed-carrier-registry.json"
    local.mkdir(parents=True)
    registry_path.parent.mkdir(parents=True)
    source = {"schema_version": "capture", "season": {"label": "2000/01"}, "clubs": []}
    allocation = {"coverage": {"assignment_count": 1}}
    capture = {
        "schema_version": "capture", "season": {"label": "2000/01"},
        "clubs": [{"club_name": "New", "country_catalog": "country", "competition_catalog": "league", "source_sha256": "a" * 64}],
    }
    for path, value in ((local / "source.json", source), (local / "allocation.json", allocation),
                        (registry_path, {"clubs": []}), (tmp_path / "capture.json", capture)):
        path.write_bytes(capture_lib.canonical_bytes(value))
    current = {
        "artifacts": {
            "source": {"path": "source.json", "sha256": wave.batch._document_sha(source)},
            "allocation": {"path": "allocation.json", "sha256": wave.batch._document_sha(allocation)},
        }
    }
    (local / "current.json").write_bytes(capture_lib.canonical_bytes(current))
    monkeypatch.setattr(wave, "ROOT", tmp_path)
    monkeypatch.setattr(wave.compositor, "compose", lambda **_kwargs: source)
    monkeypatch.setattr(wave.allocator, "build_allocation", lambda **_kwargs: {"coverage": {"assignment_count": 2}})
    monkeypatch.setattr(wave.batch, "_publish_revision", lambda **_kwargs: pytest.fail("published during dry run"))

    before = (local / "current.json").read_bytes()
    result = promote_wave(
        season=season, captures=[("provider", tmp_path / "capture.json")], gaps=[],
        replacements=set(), output_root=tmp_path / "output", dry_run=True,
    )

    assert result == {
        "assignment_count": 2, "current_assignment_count": 1,
        "dry_run": True, "season": season,
    }
    assert (local / "current.json").read_bytes() == before
