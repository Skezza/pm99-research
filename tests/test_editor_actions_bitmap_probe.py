from pathlib import Path

from app.editor_actions import inspect_bitmap_references


def test_inspect_bitmap_references_finds_markers_and_snippets(tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"

    player_file.write_bytes(b"header....PLAYER_FACE01.BMP....tail")
    team_file.write_bytes(b"prefix..KIT_AWAY_TEXTURE.TGA..suffix")
    coach_file.write_bytes(b"no marker payload")

    result = inspect_bitmap_references(
        player_file=str(player_file),
        team_file=str(team_file),
        coach_file=str(coach_file),
        markers=[".BMP", ".TGA"],
        max_hits_per_file=8,
    )

    assert result.markers == [".BMP", ".TGA"]
    assert len(result.files) == 3
    assert result.total_hits == 2

    players_result = result.files[0]
    teams_result = result.files[1]
    coaches_result = result.files[2]

    assert players_result.exists is True
    assert players_result.hit_count == 1
    assert players_result.hits[0].marker == ".BMP"
    assert "PLAYER_FACE01.BMP" in players_result.hits[0].snippet

    assert teams_result.exists is True
    assert teams_result.hit_count == 1
    assert teams_result.hits[0].marker == ".TGA"
    assert "KIT_AWAY_TEXTURE.TGA" in teams_result.hits[0].snippet

    assert coaches_result.exists is True
    assert coaches_result.hit_count == 0
    assert coaches_result.hits == []


def test_inspect_bitmap_references_reports_missing_files(tmp_path):
    player_file = tmp_path / "missing_player.fdi"
    team_file = tmp_path / "missing_team.fdi"
    coach_file = tmp_path / "missing_coach.fdi"

    result = inspect_bitmap_references(
        player_file=str(player_file),
        team_file=str(team_file),
        coach_file=str(coach_file),
        max_hits_per_file=4,
    )

    assert result.total_hits == 0
    assert len(result.files) == 3
    for file_result in result.files:
        assert file_result.exists is False
        assert file_result.read_error == "file missing"
        assert file_result.hit_count == 0
