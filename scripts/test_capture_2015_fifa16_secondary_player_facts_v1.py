from scripts import capture_2015_fifa16_secondary_player_facts_v1 as capture


def test_curacao_remains_a_declared_unrepresentable_fact_not_unknown() -> None:
    assert capture._facts({"birthdate": "1992-01-01", "nationality": "Curacao", "height": "180", "weight": "75"}) == {
        "birth_date": "1992-01-01", "nationality": "CUW", "height_cm": 180, "weight_kg": 75,
    }
