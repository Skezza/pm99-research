"""Tests for forward-only manager overlay construction."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_manager_overlay_v1 as overlay  # noqa: E402


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_writes_a_manager_ledger_as_a_new_baseline_pinned_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(overlay, "ROOT", tmp_path)
    season = "2000-01"
    base = tmp_path / ".local/calendar/2000-01/draft.json"
    base_sha = _write(base, {"season": season})
    baseline = tmp_path / "baseline.json"
    _write(baseline, {
        "schema_version": overlay.BASELINE_SCHEMA,
        "state": "frozen-provisional-base",
        "seasons": [{"season": season, "base_draft": {"path": ".local/calendar/2000-01/draft.json", "sha256": base_sha}}],
    })
    selector = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example Town"}
    source = tmp_path / "source.json"
    _write(source, {"clubs": [selector]})
    lineups = tmp_path / "lineups.json"
    _write(lineups, {"schema_version": "pm99-composed-opening-lineup-source-v1", "season_start_year": 2000, "clubs": [], "source": {"cache_files": []}})
    supplement = tmp_path / "supplement.json"
    _write(supplement, {
        "schema_version": "pm99-opening-manager-supplement-v1", "season_start_year": 2000,
        "managers": [{
            "source_selector": selector, "opening_fixture_date": "2000-08-12", "manager_name": "Historical Manager",
            "source_name": "Test source", "source_url": "https://example.test/manager",
            "source_snapshot_sha256": "a" * 64, "reason": "unique dated tenure",
        }], "gaps": [],
    })
    output = tmp_path / "overlay"

    receipt = overlay.write_overlay(
        baseline_index=baseline, season=season, source_capture=source,
        opening_lineups=lineups, supplements=[supplement], output_root=output,
    )

    assert receipt["coverage"]["resolved_manager_count"] == 1
    assert json.loads((output / "opening-manager-ledger.json").read_text())["managers"][0]["manager_name"] == "Historical Manager"
    with pytest.raises(overlay.ManagerOverlayError, match="refusing to overwrite"):
        overlay.write_overlay(
            baseline_index=baseline, season=season, source_capture=source,
            opening_lineups=lineups, supplements=[supplement], output_root=output,
        )
