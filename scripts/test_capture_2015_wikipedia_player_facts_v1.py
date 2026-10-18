from scripts import capture_2015_wikipedia_player_facts_v1 as capture


def test_parses_only_unambiguous_infobox_secondary_facts() -> None:
    content = """{{Infobox football biography
| birth_date = {{Birth date and age|1990|5|27}}
| nationality = [[Germany]]
| height = 1.85 m
| weight = 75 kg
}}"""

    assert capture._facts(content) == {
        "birth_date": "1990-05-27",
        "nationality": "GER",
        "height_cm": 185,
        "weight_kg": 75,
    }


def test_refuses_multiple_nationality_values() -> None:
    assert capture._nationality("[[England]] / [[Ghana]]") is None
