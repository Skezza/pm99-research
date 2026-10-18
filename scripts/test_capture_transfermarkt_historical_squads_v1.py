from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import capture_transfermarkt_historical_squads_v1 as subject
from scripts.capture_transfermarkt_opening_lineups_v1 import CaptureError, TeamRef


def write_json(path: Path, value: object) -> None:
    path.write_bytes(subject.canonical_bytes(value))


def test_scope_is_canonical_hash_bound_and_unique(tmp_path: Path) -> None:
    path = tmp_path / "scope.json"
    document = {"competitions": [{
        "competition_catalog": "eerste", "competition_name": "Belgian First Division",
        "country_catalog": "belgium", "source_competition_code": "BE1",
    }], "schema_version": subject.SCOPE_SCHEMA}
    write_json(path, document)
    rows, digest = subject.load_scope(path)
    assert rows[0]["source_competition_code"] == "BE1"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    document["competitions"].append(dict(document["competitions"][0]))
    write_json(path, document)
    with pytest.raises(CaptureError, match="duplicates"):
        subject.load_scope(path)


def test_build_capture_emits_canonical_players_and_explicit_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    def teams(**kwargs: object) -> list[TeamRef]:
        if kwargs["competition_code"] == "BAD":
            raise CaptureError("missing")
        return [TeamRef("Club", "Club FC", 7, "/club/startseite/verein/7", "source")]

    class Cache:
        def get(self, url: str, key: str) -> bytes:
            assert url.endswith("/saison_id/2000")
            return b"historic-squad"

    monkeypatch.setattr(subject, "_competition_teams", teams)
    scope = [
        {"country_catalog": "belgium", "competition_catalog": "eerste", "competition_name": "League", "source_competition_code": "BE1"},
        {"country_catalog": "wales", "competition_catalog": "prem", "competition_name": "League", "source_competition_code": "BAD"},
    ]
    parsed = [{"name": "Player One", "position": "D", "shirt_number": None, "nationality": "UNK", "height_cm": None, "weight_kg": None, "birth_date": None}]
    capture, gaps = subject.build_capture(
        season_start_year=2000, scope=scope, scope_sha256="a" * 64,
        cache=Cache(), parse=lambda _: parsed,  # type: ignore[arg-type]
    )
    assert capture["summary"]["club_count"] == 1
    assert capture["clubs"][0]["players"][0]["nationality"] is None
    assert capture["clubs"][0]["players"][0]["unresolved_fields"] == [
        "shirt_number", "nationality", "height_cm", "weight_kg", "birth_date"
    ]
    assert gaps["gaps"][0]["reason"] == "competition-page-unavailable-or-unparseable"


def test_pre_premier_league_aliases_are_dated_and_retain_logical_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []

    def teams(**kwargs: object) -> list[TeamRef]:
        code = str(kwargs["competition_code"])
        attempted.append(code)
        if code != "EFD1":
            raise CaptureError("missing")
        return [TeamRef("Arsenal", "Arsenal FC", 11, "/arsenal/startseite/verein/11", "source")]

    class Cache:
        def get(self, url: str, key: str) -> bytes:
            assert "/saison_id/1990" in url
            assert "/EFD1/" in key
            return b"historic-squad"

    monkeypatch.setattr(subject, "_competition_teams", teams)
    parsed = [{
        "name": "Player One", "position": "D", "shirt_number": None,
        "nationality": "UNK", "height_cm": None, "weight_kg": None,
        "birth_date": None,
    }]
    capture, gaps = subject.build_capture(
        season_start_year=1990,
        scope=[{
            "country_catalog": "eng", "competition_catalog": "faprem",
            "competition_name": "English top tier", "source_competition_code": "GB1",
        }],
        scope_sha256="a" * 64, cache=Cache(), parse=lambda _: parsed,  # type: ignore[arg-type]
    )

    assert attempted == ["EFD1"]
    assert not gaps["gaps"]
    assert capture["clubs"][0]["competition_catalog"] == "faprem"
    assert capture["clubs"][0]["source_competition_code"] == "EFD1"
    assert subject.competition_code_candidates("GB1", 1992) == ["GB1"]


def test_player_rejects_missing_name_or_position() -> None:
    with pytest.raises(CaptureError, match="name or supported"):
        subject.canonical_player({"name": "", "position": "M"})


def test_dom_fallback_reads_nested_transfermarkt_player_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "parse_squad", lambda _payload: [])
    payload = b"""
    <table class="items"><tbody><tr class="odd">
      <td class="zentriert rueckennummer" title="Defender"><div class="rn_nummer">4</div></td>
      <td><table><tr><td><a href="/ana-example/profil/spieler/7">Ana Example</a></td></tr>
          <tr><td>Centre-Back</td></tr></table></td>
      <td>24</td><td><img class="flaggenrahmen" title="Romania"></td>
    </tr></tbody></table>
    """

    assert subject.parse_squad_with_dom_fallback(payload) == [{
        "birth_date": None, "height_cm": None, "name": "Ana Example", "nationality": "ROU",
        "position": "D", "shirt_number": 4, "weight_kg": None,
        "source_identity": {"provider": "transfermarkt", "player_id": "7"},
    }]
