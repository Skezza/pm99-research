from scripts.materialise_2015_world_fifaindex_kits import bind_team, identity_key, parse_team_catalog


def test_fifaindex_catalog_binds_image_and_page_team_id() -> None:
    text = "[![Image 1](https://images.fifaindex.com/fifa16/teams/241.png)FC Barcelona](https://fifaindex.com/teams/241-fc-barcelona/fifa16)84"
    rows = parse_team_catalog(text)
    assert rows[0]["fifa_team_id"] == 241
    assert rows[0]["home_kit_origin_url"].endswith("/home/241.png")


def test_dominant_player_club_is_required_to_be_unique() -> None:
    club = {"source_club_name": "Wrong display", "players": [{"fifa16_player_id": 1}, {"fifa16_player_id": 2}, {"fifa16_player_id": 3}]}
    catalog = [{"fifa_team_id": 241, "fifa_team_name": "FC Barcelona", "identity_key": identity_key("FC Barcelona"), "identity_aliases": [identity_key("FC Barcelona")]}]
    result = bind_team(club, {1: "FC Barcelona", 2: "FC Barcelona", 3: "Real Madrid"}, catalog)
    assert result["status"] == "identity-bound"
    assert result["team"]["fifa_team_id"] == 241


def test_legal_suffix_normalisation_is_stable() -> None:
    assert identity_key("F.C. Barcelona") == identity_key("FC Barcelona") == identity_key("Barcelona")
