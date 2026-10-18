from scripts import season_carrier_allocation_v1 as allocation


def test_verified_historical_top_division_vocabularies_are_allocatable() -> None:
    assert "national-division" in allocation.PRIMARY_COMPETITIONS["luxembourg"]
    assert "premier" in allocation.PRIMARY_COMPETITIONS["malta"]
    assert "otpliga" in allocation.PRIMARY_COMPETITIONS["hungary"]
    assert "division-profesional" in allocation.PRIMARY_COMPETITIONS["bolivia"]
    assert "superl" in allocation.PRIMARY_COMPETITIONS["serbia"]
    assert "superl" in allocation.PRIMARY_COMPETITIONS["slovakia"]


def _club(name: str, country: str, competition: str, suffix: str) -> dict:
    return {
        "club_name": name, "country_catalog": country,
        "competition_catalog": competition, "competition_name": competition,
        "source_path": f"{suffix}.txt", "source_sha256": suffix[0] * 64,
        "players": [{"name": f"Player {index}"} for index in range(11)],
    }


def test_preserves_continuing_club_then_allocates_replacement_in_country() -> None:
    source = {
        "schema_version": allocation.SOURCE_SCHEMA,
        "season": {"label": "2000/01", "start_year": 2000, "end_year": 2001},
        "clubs": [
            _club("Barcelona", "spain", "laliga", "a"),
            _club("Newly Promoted", "spain", "laliga", "b"),
            _club("Second Division", "spain", "segunda", "c"),
        ],
    }
    registry = {
        "carriers": [
            {"carrier_id": 1, "baseline_club": {"name": "F.C. Barcelona", "full_name": "Futbol Club Barcelona"}, "roster_slots": [1, 2]},
            {"carrier_id": 2, "baseline_club": {"name": "Exited Club", "full_name": "Exited Club"}, "roster_slots": [3]},
        ]
    }
    result = allocation.build_allocation(source=source, registry=registry)
    assert [(row["carrier_id"], row["club_name"], row["method"]) for row in result["assignments"]] == [
        (1, "Barcelona", "continuing-club-normalized-identity"),
        (2, "Newly Promoted", "same-country-replacement-canonical-source-order"),
    ]
    assert all(row["club_name"] != "Second Division" for row in result["assignments"])


def test_is_input_order_independent_and_logs_capacity_gaps() -> None:
    clubs = [_club("One", "spain", "laliga", "a"), _club("Two", "spain", "laliga", "b")]
    source = {"schema_version": allocation.SOURCE_SCHEMA, "season": {"label": "x"}, "clubs": clubs}
    registry = {"carriers": [{"carrier_id": 1, "baseline_club": {"name": "Old"}, "roster_slots": [1]}]}
    first = allocation.build_allocation(source=source, registry=registry)
    source["clubs"].reverse()
    second = allocation.build_allocation(source=source, registry=registry)
    assert first["assignments"] == second["assignments"]
    assert first["gaps"] == second["gaps"]
    assert first["gaps"] == [{
        "club_name": "Two", "country_group": "spain", "source_path": "b.txt",
        "status": "source-club-exceeds-fixed-country-capacity",
    }]


def test_allocates_english_non_league_and_out_of_range_real_clubs() -> None:
    source = {
        "schema_version": allocation.SOURCE_SCHEMA,
        "season": {"label": "2000/01"},
        "clubs": [
            _club("Doncaster Rovers", "eng", "national", "d"),
            _club("Hereford United", "eng", "national", "h"),
            _club("Woking", "eng", "national", "w"),
        ],
    }
    registry = {"carriers": [
        {"carrier_id": 377, "baseline_club": {"name": "Doncaster R.", "full_name": "Doncaster Rovers"}, "roster_slots": [1]},
        {"carrier_id": 381, "baseline_club": {"name": "Hereford U.", "full_name": "Hereford United"}, "roster_slots": [2]},
        {"carrier_id": 3321, "baseline_club": {"name": "Woking", "full_name": "Woking"}, "roster_slots": [3]},
    ]}
    result = allocation.build_allocation(source=source, registry=registry)
    assert [(row["carrier_id"], row["club_name"]) for row in result["assignments"]] == [
        (377, "Doncaster Rovers"), (381, "Hereford United"), (3321, "Woking"),
    ]


def test_does_not_promote_thin_source_evidence_as_an_opening_squad() -> None:
    club = _club("Woking", "eng", "national", "w")
    club["players"] = club["players"][:4]
    result = allocation.build_allocation(
        source={"schema_version": allocation.SOURCE_SCHEMA, "season": {"label": "2000/01"}, "clubs": [club]},
        registry={"carriers": [{"carrier_id": 3321, "baseline_club": {"name": "Woking"}, "roster_slots": list(range(20))}]},
    )
    assert not result["assignments"]
    assert {row["status"] for row in result["gaps"]} == {
        "source-club-below-opening-xi-minimum-blocked",
        "source-unavailable-or-insufficient-country-capacity-blocked",
    }


def test_xi_source_does_not_imply_release_capacity_eligibility() -> None:
    club = _club("Woking", "eng", "national", "w")
    result = allocation.build_allocation(
        source={"schema_version": allocation.SOURCE_SCHEMA, "season": {"label": "2000/01"}, "clubs": [club]},
        registry={"carriers": [{"carrier_id": 3321, "baseline_club": {"name": "Woking"}, "roster_slots": list(range(20))}]},
    )
    assert result["coverage"]["xi_source_eligible_count"] == 1
    assert result["coverage"]["release_capacity_eligible_count"] == 0
    assert "source-club-below-carrier-capacity-blocked" in {row["status"] for row in result["gaps"]}


def test_capacity_matching_does_not_strand_a_smaller_squad() -> None:
    small = _club("Small Squad", "spain", "laliga", "s")
    small["players"] = small["players"] + [{"name": f"Small Extra {index}"} for index in range(7)]
    large = _club("Large Squad", "spain", "laliga", "l")
    large["players"] = large["players"] + [{"name": f"Large Extra {index}"} for index in range(11)]
    result = allocation.build_allocation(
        source={"schema_version": allocation.SOURCE_SCHEMA, "season": {"label": "2000/01"}, "clubs": [large, small]},
        registry={"carriers": [
            {"carrier_id": 1, "baseline_club": {"name": "Old One"}, "roster_slots": list(range(18))},
            {"carrier_id": 2, "baseline_club": {"name": "Old Two"}, "roster_slots": list(range(22))},
        ]},
    )
    assert [(row["carrier_id"], row["club_name"]) for row in result["assignments"]] == [
        (1, "Small Squad"), (2, "Large Squad")
    ]
    assert result["coverage"]["release_capacity_eligible_count"] == 2


def test_system_selections_are_not_real_club_allocation_targets() -> None:
    result = allocation.build_allocation(
        source={"schema_version": allocation.SOURCE_SCHEMA, "season": {"label": "2000/01"}, "clubs": []},
        registry={"carriers": [
            {"carrier_id": carrier_id, "baseline_club": {"name": "System"}, "roster_slots": [1]}
            for carrier_id in sorted(allocation.SYSTEM_SELECTION_IDS)
        ]},
    )
    assert result["assignments"] == []
    assert result["gaps"] == []


def test_relegated_continuing_club_is_retained_but_not_an_arbitrary_lower_club() -> None:
    source = {
        "schema_version": allocation.SOURCE_SCHEMA,
        "season": {"label": "2000/01"},
        "clubs": [
            _club("Top Flight", "spain", "laliga", "t"),
            _club("Relegated Carrier", "spain", "segunda", "r"),
            _club("Unrelated Lower Club", "spain", "segunda", "u"),
        ],
    }
    registry = {"carriers": [
        {"carrier_id": 1, "baseline_club": {"name": "Top Flight"}, "roster_slots": [1]},
        {"carrier_id": 2, "baseline_club": {"name": "Relegated Carrier"}, "roster_slots": [2]},
    ]}
    result = allocation.build_allocation(source=source, registry=registry)
    assert [(row["carrier_id"], row["club_name"]) for row in result["assignments"]] == [
        (1, "Top Flight"), (2, "Relegated Carrier")
    ]
    assert all(row.get("club_name") != "Unrelated Lower Club" for row in result["assignments"])


def test_reviewed_english_abbreviations_lock_to_historical_identity() -> None:
    source = {
        "schema_version": allocation.SOURCE_SCHEMA,
        "season": {"label": "2000/01"},
        "clubs": [
            _club("Hereford", "english-non-league", "soccerbase-august", "h"),
            _club("Stevenage", "english-non-league", "soccerbase-august", "s"),
        ],
    }
    registry = {"carriers": [
        {"carrier_id": 381, "baseline_club": {"name": "Hereford U."}, "roster_slots": [1]},
        {"carrier_id": 3300, "baseline_club": {"name": "Other"}, "roster_slots": [2]},
    ]}
    result = allocation.build_allocation(source=source, registry=registry)
    assert [(row["carrier_id"], row["club_name"], row["method"]) for row in result["assignments"]] == [
        (381, "Hereford", "continuing-club-normalized-identity"),
        (3300, "Stevenage", "same-country-replacement-canonical-source-order"),
    ]
