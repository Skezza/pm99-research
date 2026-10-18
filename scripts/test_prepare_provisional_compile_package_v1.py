from scripts import prepare_provisional_compile_package_v1 as subject


def test_duplicate_group_does_not_hide_wrong_nationality() -> None:
    package = {"players": [
        {"id": "a", "name": "A. Player", "source_name": "Actual Player",
         "facts": {"birth_date": "1980-01-02", "nationality": "XXX"}},
        {"id": "b", "name": "Actual Player", "source_name": "Actual Player",
         "facts": {"birth_date": "1980-01-02", "nationality": "ESP"}},
    ]}
    groups = subject._duplicate_groups(package)
    assert len(groups) == 1
    key, rows = groups[0]
    assert key == ("actualplayer", "1980-01-02")
    assert {row["id"] for row in rows} == {"a", "b"}


def _club(club_id: str, opening_ids: list[str] | None = None) -> dict:
    if opening_ids is None:
        opening = {"policy": "preserve-existing-mode1"}
    else:
        opening = {"starting_xi_player_ids": opening_ids, "substitute_player_ids": []}
    return {"id": club_id, "opening": opening}


def test_retained_candidate_prefers_unique_source_captured_claim() -> None:
    rows = [
        {"id": "player-old", "club_id": "club-old", "proof": {"grade": "source-receipt"}},
        {"id": "player-dated", "club_id": "club-dated", "proof": {"grade": "source-captured"}},
    ]
    clubs = {
        "club-old": _club("club-old"),
        "club-dated": _club("club-dated"),
    }

    retained, method = subject._retained_candidate(rows, clubs)

    assert retained["id"] == "player-dated"
    assert method == "unique-source-captured-player-claim"


def test_retained_candidate_keeps_ambiguous_source_claims_editorial() -> None:
    rows = [
        {"id": "player-b", "club_id": "club-b", "proof": {"grade": "source-captured"}},
        {"id": "player-a", "club_id": "club-a", "proof": {"grade": "source-captured"}},
    ]
    clubs = {"club-a": _club("club-a"), "club-b": _club("club-b")}

    retained, method = subject._retained_candidate(rows, clubs)

    assert retained["id"] == "player-a"
    assert method == "stable-provisional-choice-editorial-ownership-unresolved"


def test_retained_candidate_keeps_opening_evidence_precedence() -> None:
    rows = [
        {"id": "player-opening", "club_id": "club-opening", "proof": {"grade": "source-receipt"}},
        {"id": "player-dated", "club_id": "club-dated", "proof": {"grade": "source-captured"}},
    ]
    clubs = {
        "club-opening": _club("club-opening", ["player-opening"]),
        "club-dated": _club("club-dated"),
    }

    retained, method = subject._retained_candidate(rows, clubs)

    assert retained["id"] == "player-opening"
    assert method == "unique-package-opening-xi-or-bench-claim"


def _rated_player(player_id: str, position: object, handling: int, quality: int = 60) -> dict:
    return {
        "id": player_id,
        "person_id": f"person-{player_id}",
        "facts": {"primary_position": position},
        "ratings": {
            "values": {"quality": quality, "handling": handling},
            "provenance": {"method": "test-source"},
        },
    }


def test_position_handling_normalises_both_known_lanes_deterministically() -> None:
    players = {
        "outfield": _rated_player("outfield", "M", 81),
        "keeper": _rated_player("keeper", "G", 12, quality=70),
        "unknown": _rated_player("unknown", {"policy": "preserve-existing-mode1"}, 81),
    }

    audit = subject._normalise_position_handling(players)

    assert 1 <= players["outfield"]["ratings"]["values"]["handling"] <= 20
    assert players["keeper"]["ratings"]["values"]["handling"] >= 58
    assert players["unknown"]["ratings"]["values"]["handling"] == 81
    assert [row["player_id"] for row in audit["outfield"]] == ["outfield"]
    assert [row["player_id"] for row in audit["goalkeeper"]] == ["keeper"]
