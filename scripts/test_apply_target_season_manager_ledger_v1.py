from scripts import apply_target_season_manager_ledger_v1 as ledger


def test_explicit_carrier_join_allows_a_historical_club_to_replace_native_name() -> None:
    package = {
        "season": {"start_year": 2015, "end_year": 2016},
        "artifacts": [],
        "clubs": [{"id": "club-961", "carrier_id": 961, "name": "Norrkoping", "manager_id": "manager-1"}],
        "managers": [{"id": "manager-1", "carrier_id": 100, "name": "Nordin", "policy": "preserve-existing-mode1"}],
    }
    source = {
        "season_start_year": 2015,
        "managers": [{
            "carrier_id": 961,
            "source_selector": {"club_name": "GIF Sundsvall"},
            "manager_name": "Joel Cedergren / Roger Franzén",
            "evidence": {},
        }],
    }

    derived, audit = ledger.apply_ledger(
        package, source, ledger_path=".local/test-ledger.json", ledger_sha256="a" * 64,
    )

    assert audit["coverage"]["changed_manager_count"] == 1
    assert audit["applied"][0]["package_join_method"] == "explicit-reviewed-carrier"
    assert derived["managers"][0]["name"] == "Joel Cedergren / Roger Franzén"
