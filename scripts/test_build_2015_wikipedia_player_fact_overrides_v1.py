from scripts import build_2015_wikipedia_player_fact_overrides_v1 as build


def test_builds_only_missing_fact_patches() -> None:
    package = {"players": [{
        "id": "player-1", "facts": {"birth_date": None, "nationality": "ENG", "height_cm": 180, "weight_kg": 75},
    }]}
    receipt = {
        "schema_version": "pm99-world-2015-wikipedia-player-facts-v1",
        "sources": {"base_package_sha256": "a" * 64},
        "rows": [{"player_id": "player-1", "facts": {"birth_date": "1990-01-02"}}],
    }
    result, queue = build.build(
        package=package, package_sha256="a" * 64, receipt=receipt,
        receipt_path=".local/receipt.json", receipt_sha256="b" * 64,
    )
    assert result["data_patches"][0]["expected"] == {"facts.birth_date": None}
    assert result["data_patches"][0]["set"] == {"facts.birth_date": "1990-01-02"}
    assert queue["withheld_patch_count"] == 0
