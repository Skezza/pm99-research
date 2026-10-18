from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import capture_opening_manager_history_supplements_v1 as history


def test_manager_history_selects_the_unique_tenure_covering_fixture() -> None:
    payload = b'''<table class="items"><tbody>
      <tr><td><a title="Earlier Manager" href="/earlier/profil/trainer/1">Earlier</a></td><td></td><td>01/07/1999</td><td>30/06/2001</td></tr>
      <tr><td><a href="/opening/profil/trainer/2"><img title="Opening Manager"></a><a title="Opening Manager" href="/opening/profil/trainer/2">Opening</a></td><td></td><td>01/07/2001</td><td>30/06/2002</td></tr>
    </tbody></table>'''
    assert history.manager_at_date(payload, date(2001, 8, 11)) == ("Opening Manager", "2")


def test_manager_history_rejects_overlapping_tenures() -> None:
    payload = b'''<table class="items"><tbody>
      <tr><td><a title="One" href="/one/profil/trainer/1">One</a></td><td></td><td>01/07/2001</td><td></td></tr>
      <tr><td><a title="Two" href="/two/profil/trainer/2">Two</a></td><td></td><td>01/08/2001</td><td></td></tr>
    </tbody></table>'''
    with pytest.raises(history.ManagerHistoryError, match="2 managers"):
        history.manager_at_date(payload, date(2001, 8, 11))


def test_composed_lineup_binds_manager_capture_to_exact_selector_projection(tmp_path: Path) -> None:
    result = history.capture(
        source_capture={"clubs": []},
        source_capture_sha256="full-squad-source-sha",
        lineups={
            "source": {
                "source_capture_sha256": "full-squad-source-sha",
                "lineup_source_selection_sha256": "selection-sha",
            },
            "season_start_year": 2003,
            "clubs": [],
        },
        lineup_sha256="lineup-sha",
        lineup_source_selection={"clubs": []},
        lineup_source_selection_sha256="selection-sha",
        competition_map={},
        competition_map_sha256="map-sha",
        aliases={},
        aliases_sha256=None,
        cache=history.opening.SnapshotCache(tmp_path, offline=True, delay=0),
    )

    assert result["summary"]["supplemented_manager_count"] == 0


def test_soccerbase_opening_lineup_uses_competition_lookup_for_manager_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "d3", "club_name": "Barnet"}
    calls: list[object] = []

    def _teams(**_: object) -> list[history.opening.TeamRef]:
        calls.append("teams")
        return [history.opening.TeamRef("Barnet", "Barnet", 344, "/barnet/startseite/verein/344", "test")]

    def _fixture(*_: object, **__: object) -> dict[str, str]:
        calls.append("fixture")
        return {"date": "2000-08-12", "schedule_url": "https://example.invalid"}

    monkeypatch.setattr(history.opening, "_competition_teams", _teams)
    monkeypatch.setattr(history.opening, "_first_fixture", _fixture)
    result = history.capture(
        source_capture={"clubs": [selector]},
        source_capture_sha256="source-sha",
        lineups={
            "source": {"source_capture_sha256": "source-sha", "lineup_source_selection_sha256": "selection-sha"},
            "season_start_year": 2000,
            "clubs": [{"source_selector": {**selector, "soccerbase_team_id": 344}, "declared_manager": None}],
        },
        lineup_sha256="lineup-sha",
        lineup_source_selection={"clubs": [selector]},
        lineup_source_selection_sha256="selection-sha",
        competition_map={("eng", "d3"): "GB3"},
        competition_map_sha256="map-sha",
        aliases={}, aliases_sha256=None,
        cache=history.opening.SnapshotCache(tmp_path, offline=True, delay=0),
    )

    assert calls == ["teams", "fixture"]
    assert result["summary"]["unresolved_manager_count"] == 1


def test_direct_lineup_receipt_binds_its_selector_projection_to_the_current_source(tmp_path: Path) -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "d3", "club_name": "Barnet"}
    result = history.capture(
        source_capture={"clubs": [selector]},
        source_capture_sha256="full-source-sha",
        lineups={
            "source": {"source_capture_sha256": "selector-sha"},
            "season_start_year": 2007,
            "clubs": [],
        },
        lineup_sha256="lineup-sha",
        lineup_source_selection={"clubs": [selector]},
        lineup_source_selection_sha256="selector-sha",
        competition_map={}, competition_map_sha256="map-sha",
        aliases={}, aliases_sha256=None,
        cache=history.opening.SnapshotCache(tmp_path, offline=True, delay=0),
    )

    assert result["sources"]["full_source_capture_sha256"] == "full-source-sha"
    assert result["sources"]["lineup_source_capture_or_selector_sha256"] == "selector-sha"
