import types

from pm99_editor.exporters import (
    generate_player_table_text,
    generate_coach_table_text,
    generate_team_table_text,
    format_table,
)


def _make_player(
    name="John Doe",
    team_id=3001,
    squad=9,
    position="Forward",
    attributes=None,
):
    class DummyPlayer:
        def __init__(self):
            self.name = name
            self.team_id = team_id
            self.squad_number = squad
            self.attributes = attributes if attributes is not None else [70, 68, 65, 63, 72, 69, 71, 60, 58, 62, 55, 50]

        def get_position_name(self):
            return position

    return DummyPlayer()


def _make_coach(name="Alex Smith"):
    return types.SimpleNamespace(full_name=name)


def _make_team(
    name="Debug FC",
    team_id=4001,
    league="Premier",
    stadium="Debug Arena",
    capacity=32786,
    car_park=1200,
    pitch="GOOD",
):
    return types.SimpleNamespace(
        name=name,
        team_id=team_id,
        league=league,
        stadium=stadium,
        stadium_capacity=capacity,
        car_park=car_park,
        pitch=pitch,
    )


def test_generate_player_table_text_includes_offset_and_team_name():
    player = _make_player()
    table = generate_player_table_text([(0x10, player)], team_lookup={3001: "Testers"})
    lines = table.splitlines()

    assert lines[0].startswith("Offset")
    assert "0x00000010" in lines[2]
    assert "John Doe" in lines[2]
    assert "3001 - Testers" in lines[2]
    assert "Forward" in lines[2]


def test_generate_player_detailed_export_includes_attributes_and_average():
    player = _make_player()
    table = generate_player_table_text(
        [(0x10, player)],
        team_lookup={3001: "Testers"},
        level="detailed",
    )
    lines = table.splitlines()

    assert "Team ID" in lines[0]
    assert "Average" in lines[0]
    assert "0x00000010" in lines[2]
    assert "3001" in lines[2]
    assert "Testers" in lines[2]
    # Average of first ten attributes from helper above
    assert "65" in lines[2]


def test_generate_coach_table_text_has_offsets():
    coach = _make_coach()
    table = generate_coach_table_text([(0x20, coach)])
    lines = table.splitlines()

    assert "0x00000020" in lines[2]
    assert "Alex Smith" in lines[2]


def test_generate_team_table_text_includes_stadium_details():
    team = _make_team()
    table = generate_team_table_text([(0x30, team)])
    lines = table.splitlines()

    assert "0x00000030" in lines[2]
    assert "Debug FC" in lines[2]
    assert "Premier" in lines[2]
    assert "Debug Arena" in lines[2]
    assert "32786" in lines[2]
    assert "1200" in lines[2]
    assert "GOOD" in lines[2]


def test_generate_team_detailed_export_lists_players():
    team = _make_team()
    player_one = _make_player(name="Keeper", squad=1, team_id=4001)
    player_two = _make_player(name="Striker", squad=9, team_id=4001)
    table = generate_team_table_text(
        [(0x30, team)],
        level="detailed",
        player_records=[(0x100, player_one), (0x120, player_two)],
        team_lookup={4001: "Debug FC"},
    )

    assert "Team Debug FC (ID 4001)" in table
    assert "Keeper" in table
    assert "Striker" in table
    assert "Squad #" in table
    assert "0x00000100" in table
    assert "0x00000120" in table


def test_format_table_handles_empty_rows():
    table = format_table(["A", "B"], [])
    assert table.startswith("A | B")
    assert "\n" in table
