from scripts.historical_squad_recurring_gap_matrix_v1 import build


def test_build_clusters_real_carrier_gaps_by_country_and_carrier():
    matrix = {"seasons": [
        {"season": "2000-01", "unassigned_real_carrier_ids": [381, 2202]},
        {"season": "2001-02", "unassigned_real_carrier_ids": [381]},
    ]}
    registries = {
        season: {"carriers": [
            {"carrier_id": 381, "baseline_club": {"name": "Hereford U."}},
            {"carrier_id": 2202, "baseline_club": {"name": "KI"}},
        ]}
        for season in ("2000-01", "2001-02")
    }
    result = build(matrix, registries, "a" * 64)
    assert result["summary"] == {"carrier_season_gap_count": 3, "unique_carrier_gap_count": 2}
    assert result["country_groups"] == [
        {"carrier_season_gap_count": 2, "country_group": "english-non-league"},
        {"carrier_season_gap_count": 1, "country_group": "faroe-islands"},
    ]
    assert result["carrier_gaps"][0]["seasons"] == ["2000-01", "2001-02"]
