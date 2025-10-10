import types

from pm99_editor.exporters import (
    generate_player_table_text,
    generate_coach_table_text,
    generate_team_table_text,
    format_table,
)


def _make_player(name="John Doe", team_id=3001, squad=9, position="Forward"):
    class DummyPlayer:
        def __init__(self):
            self.name = name
            self.team_id = team_id
            self.squad_number = squad

        def get_position_name(self):
            return position

    return DummyPlayer()


def _make_coach(name="Alex Smith"):
    return types.SimpleNamespace(full_name=name)


def _make_team(name="Debug FC", team_id=4001, league="Premier"):
    return types.SimpleNamespace(name=name, team_id=team_id, league=league)


def test_generate_player_table_text_includes_offset_and_team_name():
    player = _make_player()
    table = generate_player_table_text([(0x10, player)], team_lookup={3001: "Testers"})
    lines = table.splitlines()

    assert lines[0].startswith("Offset")
    assert "0x00000010" in lines[2]
    assert "John Doe" in lines[2]
    assert "3001 - Testers" in lines[2]
    assert "Forward" in lines[2]


def test_generate_coach_table_text_has_offsets():
    coach = _make_coach()
    table = generate_coach_table_text([(0x20, coach)])
    lines = table.splitlines()

    assert "0x00000020" in lines[2]
    assert "Alex Smith" in lines[2]


def test_generate_team_table_text_includes_league():
    team = _make_team()
    table = generate_team_table_text([(0x30, team)])
    lines = table.splitlines()

    assert "0x00000030" in lines[2]
    assert "Debug FC" in lines[2]
    assert "Premier" in lines[2]


def test_format_table_handles_empty_rows():
    table = format_table(["A", "B"], [])
    assert table.startswith("A | B")
    assert "\n" in table
