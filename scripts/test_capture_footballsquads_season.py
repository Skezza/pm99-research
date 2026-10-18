from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_footballsquads_season import CaptureError, capture_season  # noqa: E402


def _write_club(path: Path, *, title: str, rows: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        f"=  {title}\n\n"
        "Number, Name, Nat, Pos, Height, Weight, Date of Birth, Birth Place, Previous Club\n"
        f"{rows}\n\n"
        "== Past Players\n\n"
        "Number, Name, Nat, Pos, Height, Weight, Date of Birth, Birth Place, New Club\n"
        "99, Past Player, ENG, M, 1.80, 70, 01-01-80, Test, Elsewhere\n",
        encoding="utf-8",
    )


def test_capture_season_keeps_current_squad_facts_and_hashes(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "spain" / "2015-2016" / "laliga" / "barce.txt",
        title="Barcelona - Spanish La Liga 2015/16",
        rows=(
            "1, Marc Test, GER, G, 1.85, 82, 30-04-92, Test, Previous\n"
            "10, Field Test, ESP, M, 1.70, 65, 05-01-98, Test, Previous"
        ),
    )

    captured = capture_season(source_root=root, season="2015-2016")

    assert captured["season"] == {"catalog": "2015-2016", "label": "2015/16"}
    assert captured["summary"]["club_count"] == 1
    assert captured["summary"]["player_count"] == 2
    club = captured["clubs"][0]
    assert club["club_name"] == "Barcelona"
    assert club["source_path"] == "spain/2015-2016/laliga/barce.txt"
    assert len(club["source_sha256"]) == 64
    assert club["players"] == [
        {
            "shirt_number": 1,
            "name": "Marc Test",
            "nationality": "GER",
            "position": "G",
            "height_cm": 185,
            "weight_kg": 82,
            "birth_date": "1992-04-30",
            "unresolved_fields": [],
        },
        {
            "shirt_number": 10,
            "name": "Field Test",
            "nationality": "ESP",
            "position": "M",
            "height_cm": 170,
            "weight_kg": 65,
            "birth_date": "1998-01-05",
            "unresolved_fields": [],
        },
    ]


def test_capture_records_an_invalid_nationality_as_an_explicit_source_gap(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "spain" / "2015-2016" / "laliga" / "broken.txt",
        title="Broken - Spanish La Liga 2015/16",
        rows="1, Broken, ES, M, 1.70, 65, 05-01-98, Test, Previous",
    )

    captured = capture_season(source_root=root, season="2015-2016")

    assert captured["clubs"][0]["players"][0]["nationality"] is None
    assert captured["clubs"][0]["players"][0]["unresolved_fields"] == ["nationality"]


def test_capture_calendar_year_league_keeps_its_real_source_label(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "brazil" / "2015" / "brasileirao" / "test.txt",
        title="Test Clube - Campeonato Brasileiro Série A 2015",
        rows="1, Calendar Test, BRA, M, 1.80, 75, 01-01-90, Test, Previous",
    )

    captured = capture_season(source_root=root, season="2015")

    assert captured["season"] == {"catalog": "2015", "label": "2015"}
    assert captured["clubs"][0]["source_path"] == "brazil/2015/brasileirao/test.txt"
    assert captured["clubs"][0]["players"][0]["birth_date"] == "1990-01-01"


def test_capture_1999_season_preserves_legacy_imperial_facts_and_missing_nationality(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    path = root / "eng" / "1999-2000" / "faprem" / "test.txt"
    path.parent.mkdir(parents=True)
    path.write_text(
        "=  Test United - English Premier League 1999/00\n\n"
        "Number, Name, Pos, Height, Weight, Date of Birth, Birth Place, Previous Club\n"
        "1, Historic Keeper, G, 6'00\", 12 09, 10-11-73, Test, Previous\n",
        encoding="utf-8",
    )

    captured = capture_season(source_root=root, season="1999-2000")

    assert captured["season"] == {"catalog": "1999-2000", "label": "1999/00"}
    assert captured["clubs"][0]["players"] == [
        {
            "shirt_number": 1,
            "name": "Historic Keeper",
            "nationality": None,
            "position": "G",
            "height_cm": 183,
            "weight_kg": 80,
            "birth_date": "1973-11-10",
            "unresolved_fields": ["nationality"],
        }
    ]


def test_capture_split_season_accepts_any_dated_phase_within_its_years(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "arg" / "2005-2006" / "apertura" / "test.txt",
        title="Test Club - Argentinian Primera División 2005 Apertura",
        rows="1, Phase Test, ARG, M, 1.80, 75, 01-01-90, Test, Previous",
    )
    _write_club(
        root / "arg" / "2005-2006" / "clausura" / "test.txt",
        title="Test Club - Argentinian Primera División 2006 Clausura",
        rows="1, Phase Test, ARG, M, 1.80, 75, 01-01-90, Test, Previous",
    )
    _write_club(
        root / "mexico" / "2005-2006" / "bicent" / "test.txt",
        title="Test Club - Mexican Primera División 2006 Bicentenario",
        rows="1, Phase Test, MEX, M, 1.80, 75, 01-01-90, Test, Previous",
    )

    captured = capture_season(source_root=root, season="2005-2006")

    assert captured["season"] == {"catalog": "2005-2006", "label": "2005/06"}
    assert [club["competition_name"] for club in captured["clubs"]] == [
        "Argentinian Primera División Apertura",
        "Argentinian Primera División Clausura",
        "Mexican Primera División Bicentenario",
    ]


def test_capture_split_season_rejects_an_out_of_range_phase_year(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "arg" / "2005-2006" / "apertura" / "wrong.txt",
        title="Test Club - Argentinian Primera División 2004 Apertura",
        rows="1, Phase Test, ARG, M, 1.80, 75, 01-01-90, Test, Previous",
    )

    with pytest.raises(CaptureError, match="no usable current-squad"):
        capture_season(source_root=root, season="2005-2006")


def test_capture_split_season_accepts_full_four_digit_source_label(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "eng" / "2017-2018" / "faprem" / "test.txt",
        title="Test Club - English Premier League 2017/2018",
        rows="1, Full Label, ENG, M, 1.80, 75, 01-01-00, Test, Previous",
    )

    captured = capture_season(source_root=root, season="2017-2018")

    assert captured["season"] == {"catalog": "2017-2018", "label": "2017/18"}
    assert captured["clubs"][0]["players"][0]["birth_date"] == "2000-01-01"


def test_capture_records_past_only_file_as_a_blocked_source(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "eng" / "2009-2010" / "faprem" / "current.txt",
        title="Current Club - English Premier League 2009/10",
        rows="1, Current Player, ENG, M, 1.80, 75, 01-01-90, Test, Previous",
    )
    past_only = root / "eng" / "2009-2010" / "faprem" / "past-only.txt"
    past_only.write_text(
        "=  Past Club - English Premier League 2009/10\n\n"
        "== Past Players\n\n"
        "Number, Name, Nat, Pos, Height, Weight, Date of Birth, Birth Place, New Club\n"
        "1, Past Player, ENG, M, 1.80, 75, 01-01-90, Test, Elsewhere\n",
        encoding="utf-8",
    )

    captured = capture_season(source_root=root, season="2009-2010")

    assert captured["summary"]["blocked_source_count"] == 1
    assert captured["blocked_sources"] == [{
        "source_path": "eng/2009-2010/faprem/past-only.txt",
        "source_sha256": captured["blocked_sources"][0]["source_sha256"],
        "reason": "contains no current-squad CSV section",
    }]


def test_capture_country_filter_avoids_a_different_calendar_label(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    _write_club(
        root / "brazil" / "2015" / "brasileirao" / "test.txt",
        title="Test Clube - Campeonato Brasileiro Série A 2015",
        rows="1, Calendar Test, BRA, M, 1.80, 75, 01-01-90, Test, Previous",
    )
    _write_club(
        root / "japan" / "2015" / "jleague" / "wrong.txt",
        title="Wrong Calendar - J League 2016",
        rows="1, Wrong Test, JPN, M, 1.80, 75, 01-01-90, Test, Previous",
    )

    captured = capture_season(source_root=root, season="2015", countries={"brazil"})

    assert captured["summary"]["country_catalogs"] == ["brazil"]
