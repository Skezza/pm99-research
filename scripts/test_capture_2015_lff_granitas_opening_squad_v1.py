"""Tests for the LFF source-table parser used by the Granitas exception."""

from scripts.capture_2015_lff_granitas_opening_squad_v1 import (
    LffOpeningSquadError,
    _footballty_2015_positions,
    _match_players,
)


def test_match_players_selects_only_the_declared_target_side() -> None:
    rows = []
    for number in range(1, 12):
        rows.append(
            f'<tr class="firstteam"><td><a href="/zaidejai/home-{number}/">Home {number}{" (C)" if number == 1 else ""}</a></td>'
            f'<td>{number}</td><td></td><td>{number + 20}</td>'
            f'<td><a href="/zaidejai/away-{number}/">Away {number}</a></td></tr>'
        )
    rows.append(
        '<tr class="bench"><td><a href="/zaidejai/home-12/">Home 12</a></td><td>12</td><td></td>'
        '<td>32</td><td><a href="/zaidejai/away-12/">Away 12</a></td></tr>'
    )
    payload = ("<table class=\"teams\">" + "".join(rows) + "</table>").encode()
    rows = _match_players(payload, match={"name_cell_index": 4, "shirt_cell_index": 3})
    home_rows = _match_players(payload, match={"name_cell_index": 0, "shirt_cell_index": 1})
    assert [(row["name"], row["shirt_number"], row["role"]) for row in rows[:2]] == [
        ("Away 1", 21, "starting-xi"), ("Away 2", 22, "starting-xi"),
    ]
    assert rows[-1] == {
        "name": "Away 12", "player_id": "away-12", "player_url": "https://lietuvosfutbolas.lt/zaidejai/away-12/",
        "role": "substitute", "shirt_number": 32,
    }
    assert home_rows[0]["name"] == "Home 1"


class _Cache:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, url: str, key: str) -> bytes:
        assert url == "https://footballty.com/team/granitas-klaip-da/"
        assert key == "position-source/footballty-granitas-2015.html"
        return self.payload


def test_secondary_position_parser_requires_the_declared_2015_squad_section() -> None:
    payload = b'''<section data-scroll-section="lineup"><div>A Lyga 2015/2015</div>
    <players-list-item><a href="/player/alison/"><div>Alison Pierre Moreira e Silva</div></a>
    <div>BRA BRA F 27</div></players-list-item></section>'''
    assert _footballty_2015_positions(
        candidates=[{"player_id": "alison", "name": "Alison Pierre Moreira e Silva"}], cache=_Cache(payload)  # type: ignore[arg-type]
    ) == {"alison": "F"}


def test_secondary_position_parser_rejects_an_undated_row() -> None:
    payload = b'''<section data-scroll-section="lineup"><div>A Lyga</div>
    <players-list-item><a href="/player/alison/"><div>Alison Pierre Moreira e Silva</div></a>
    <div>BRA BRA F 27</div></players-list-item></section>'''
    try:
        _footballty_2015_positions(
            candidates=[{"player_id": "alison", "name": "Alison Pierre Moreira e Silva"}], cache=_Cache(payload)  # type: ignore[arg-type]
        )
    except LffOpeningSquadError as exc:
        assert "declared 2015" in str(exc)
    else:
        raise AssertionError("expected the undated secondary source to be rejected")


def test_secondary_position_parser_allows_only_the_declared_spelling_alias() -> None:
    payload = b'''<section data-scroll-section="lineup"><div>A Lyga 2015/2015</div>
    <players-list-item><a href="/player/zigmantas/"><div>Zigmantas Jesipovas</div></a>
    <div>LIT LIT M 21</div></players-list-item></section>'''
    assert _footballty_2015_positions(
        candidates=[{"player_id": "zigmantas-jesipov-1209", "name": "Zigmantas Jesipov"}], cache=_Cache(payload)  # type: ignore[arg-type]
    ) == {"zigmantas-jesipov-1209": "M"}
