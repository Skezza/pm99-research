"""Adversarial tests for plain-text DFB dated roster rows.

These tests exercise only the source parser: no game, recipe, release, or
checklist is opened for writing.
"""
from copy import deepcopy
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scripts import season_dated_roster_roles_v1 as dated
from scripts import season_opening_identity_exchange_v1 as exchange


ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / ".local/consolidated-audit-20261009/Mascherano2010-dated-role-v1/request-v1.json"


def _request_source():
    import json

    request = json.loads(REQUEST.read_text())
    row = request["changes"][0]
    return row["period_source"], row["before"]["source_name"], row["before"]["facts"]["birth_date"]


def test_exact_mascherano_liverpool_2010_11_row_is_midfield():
    source, name, birthday = _request_source()
    row = dated.period_row(source, "2010-11", name, birthday, "Liverpool")
    assert row == {
        "name": "Javier Mascherano",
        "birth_date": "1984-06-08",
        "primary_position": "M",
        "section": "Mittelfeld",
        "provider_player_id": None,
        "identity_basis": "exact-dated-club-full-name-and-literal-DOB-not-numeric-ID",
    }


@pytest.mark.parametrize(
    ("season", "name", "birthday", "club", "format_value"),
    [
        ("2011-12", "Javier Mascherano", "1984-06-08", "Liverpool", None),
        ("2010-11", "Javier Mascherano", "1984-06-08", "Everton", None),
        ("2010-11", "Javier M.", "1984-06-08", "Liverpool", None),
        ("2010-11", "Javier Mascherano", "1984-06-09", "Liverpool", None),
        ("2010-11", "Javier Mascherano", "1984-06-08", "Liverpool", "unknown-format"),
    ],
)
def test_plain_roster_rejects_wrong_context_or_identity(
    season, name, birthday, club, format_value
):
    source, _, _ = _request_source()
    source = dict(source)
    if format_value is not None:
        source["format"] = format_value
    with pytest.raises((ValueError, KeyError)):
        dated.period_row(source, season, name, birthday, club)


def _mutated_source(monkeypatch, tmp_path, transform):
    source, _, _ = _request_source()
    raw_path = ROOT / source["path"]
    page = BeautifulSoup(raw_path.read_bytes(), "lxml")
    transform(page)
    mutated_path = tmp_path / "dfb-roster.html"
    mutated_path.write_text(str(page), encoding="utf-8")
    monkeypatch.setattr(exchange, "original", lambda _source: mutated_path)
    return source


def test_duplicate_full_name_dob_rows_rejected(monkeypatch, tmp_path):
    def duplicate(page):
        row = next(
            row for row in page.select("tr.c-Table-body-row")
            if "Javier Mascherano" in row.get_text(" ", strip=True)
        )
        row.insert_after(deepcopy(row))

    source = _mutated_source(monkeypatch, tmp_path, duplicate)
    with pytest.raises(ValueError, match="one exact dated plain roster person"):
        dated.period_row(source, "2010-11", "Javier Mascherano", "1984-06-08", "Liverpool")


def test_wrong_section_header_rejected(monkeypatch, tmp_path):
    def change_header(page):
        row = next(
            row for row in page.select("tr.c-Table-body-row")
            if "Javier Mascherano" in row.get_text(" ", strip=True)
        )
        header = row.find_parent("table").select_one("thead th")
        header.string = "Tor"

    source = _mutated_source(monkeypatch, tmp_path, change_header)
    with pytest.raises(ValueError, match="birthday/role differs"):
        dated.period_row(source, "2010-11", "Javier Mascherano", "1984-06-08", "Liverpool")


def test_missing_section_header_rejected(monkeypatch, tmp_path):
    def remove_header(page):
        row = next(
            row for row in page.select("tr.c-Table-body-row")
            if "Javier Mascherano" in row.get_text(" ", strip=True)
        )
        row.find_parent("table").select_one("thead").decompose()

    source = _mutated_source(monkeypatch, tmp_path, remove_header)
    with pytest.raises(ValueError, match="birthday/role differs"):
        dated.period_row(source, "2010-11", "Javier Mascherano", "1984-06-08", "Liverpool")
