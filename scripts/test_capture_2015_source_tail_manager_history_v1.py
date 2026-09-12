from scripts import capture_2015_source_tail_manager_history_v1 as capture


def test_targets_require_one_unique_pinned_historical_identity() -> None:
    source = {
        "clubs": [{
            "candidate_carrier_id": 706,
            "club_name": "Borac",
            "country_catalog": "serbia",
            "source_identity": {
                "transfermarkt_club_id": 2209,
                "transfermarkt_slug": "fk-borac-1926-cacak",
            },
            "source_url": "https://www.transfermarkt.com/fk-borac-1926-cacak/kader/verein/2209/saison_id/2015",
            "source_sha256": "a" * 64,
        }],
    }

    assert capture._targets(source) == [{
        "carrier_id": 706,
        "source_club_name": "Borac",
        "source_selector": {
            "country_catalog": "serbia",
            "competition_catalog": "transfermarkt-2015-source-tail-domestic-opening-window",
            "club_name": "Borac",
        },
        "transfermarkt_club_id": 2209,
        "transfermarkt_slug": "fk-borac-1926-cacak",
        "pinned_squad_url": "https://www.transfermarkt.com/fk-borac-1926-cacak/kader/verein/2209/saison_id/2015",
        "pinned_squad_sha256": "a" * 64,
        "opening_fixture_date": None,
    }]


def test_targets_reject_duplicate_carriers() -> None:
    source = {"clubs": [
        {
            "candidate_carrier_id": 706, "club_name": "Borac", "country_catalog": "serbia",
            "source_identity": {"transfermarkt_club_id": 2209, "transfermarkt_slug": "borac"},
        },
        {
            "candidate_carrier_id": 706, "club_name": "Other", "country_catalog": "serbia",
            "source_identity": {"transfermarkt_club_id": 2210, "transfermarkt_slug": "other"},
        },
    ]}
    try:
        capture._targets(source)
    except capture.SourceTailManagerError as error:
        assert "unique carrier" in str(error)
    else:
        raise AssertionError("expected duplicate carrier to be rejected")
