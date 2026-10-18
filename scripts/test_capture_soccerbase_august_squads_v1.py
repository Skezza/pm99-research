from scripts.capture_soccerbase_august_squads_v1 import (
    august_games,
    career_covers,
    player_profile,
    side_players,
    tournament_teams,
)


def test_tournament_teams_deduplicates_standings_links():
    html = b"""<table class='table'><tr><td><a href='/teams/team.sd?team_id=7'>Hereford</a>
      <a href='/teams/team.sd?team_id=7'>Hereford</a></td></tr></table>"""
    assert tournament_teams(html) == [("Hereford", 7)]


def test_august_games_uses_visible_tournament_anchor_not_hidden_duplicate_text():
    html = b"""<h1>Hereford results</h1><table><tr class='match' id='tgc42'>
      <td class='dateTime'><span class='hide'>2000-08-12</span></td>
      <td class='tournament'><a>Football Conference</a><span>Football Conference</span></td>
      <td class='homeTeam'><a href='?team_id=7'>Hereford</a></td>
      <td class='awayTeam'><a href='?team_id=8'>Woking</a></td></tr></table>"""
    name, games = august_games(html, competition="Football Conference", start_year=2000)
    assert name == "Hereford"
    assert [(row[0].isoformat(), row[1]) for row in games] == [("2000-08-12", 42)]


def test_side_players_orders_starters_then_named_substitutes():
    starters = "".join(
        f"<p><a href='/players/player.sd?player_id={number}'>{number}</a> (D)</p>"
        for number in range(1, 12)
    )
    html = (f"<div class='lineup'><div class='teamA'>{starters}"
            "<p><a href='/players/player.sd?player_id=20'>Sub</a> (M)</p>"
            "</div></div>").encode()
    rows = side_players(html, side="teamA")
    assert len(rows) == 12
    assert all(row[3] for row in rows[:11])
    assert rows[11] == (20, "Sub", "M", False)


def test_player_profile_keeps_missing_secondary_facts_explicit():
    row = player_profile(b"<h1>Tom White</h1><table class='playerInfo'>Defender</table>",
                         fallback_name="T White", fallback_position=None)
    assert row["name"] == "Tom White"
    assert row["position"] == "D"
    assert set(row["unresolved_fields"]) == {
        "shirt_number", "nationality", "height_cm", "weight_kg", "birth_date"
    }


def test_player_profile_removes_soccerbase_squad_number_prefix():
    row = player_profile(b"<h1>14. Kevin McIntyre</h1><table class='playerInfo'>Midfielder</table>",
                         fallback_name="Kevin McIntyre", fallback_position=None)
    assert row["name"] == "Kevin McIntyre"


def test_player_profile_logs_corrupt_measurements_as_unresolved():
    html = b"""<h1>Ross Example</h1><table class='playerInfo'>Goalkeeper</table>
      Height 8ft 1in (2.46m) Weight 25st 3lb (160kg)"""
    row = player_profile(html, fallback_name="Ross Example", fallback_position=None)
    assert row["height_cm"] is None
    assert row["weight_kg"] is None
    assert {"height_cm", "weight_kg"} <= set(row["unresolved_fields"])


def test_career_membership_must_cover_august_cutoff():
    html = b"""<table><tr><td>Doncaster</td><td>28 Jul, 99</td>
      <td>12 Aug, 05</td><td>Signed</td></tr></table>"""
    from datetime import date
    assert career_covers(html, club_name="Doncaster", cutoff=date(2000, 8, 31))
    assert not career_covers(html, club_name="Doncaster", cutoff=date(2006, 8, 31))
