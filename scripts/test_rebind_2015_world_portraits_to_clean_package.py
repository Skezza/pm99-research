from scripts.rebind_2015_world_portraits_to_clean_package import rebind


def test_rebinds_by_identity_and_fails_open():
    package = {
        "schema_version": "pm99-season-package-v2",
        "clubs": [{"id": "club-1", "carrier_id": 1, "name": "Club", "roster_player_ids": ["player-99", "player-98"]}],
        "players": [
            {"id": "player-99", "carrier_id": 99, "club_id": "club-1", "source_name": "Á Player"},
            {"id": "player-98", "carrier_id": 98, "club_id": "club-1", "source_name": "Missing Person"},
        ],
    }
    manifest = {
        "schema_version": "pm99-world-2015-asset-candidate-manifest-v1",
        "clubs": [{"carrier_id": 1, "players": [{
            "slot_index": 0, "player_carrier_id": 10, "name": "A Player", "fifa16_player_id": 7,
            "portrait": {"status": "fifa16-url-candidate", "source_url": "https://example.invalid/7.png"},
        }]}],
    }
    materialisation = {
        "schema_version": "pm99-world-2015-portrait-materialisation-v1",
        "rows": [{"carrier_id": 1, "slot_index": 0, "player_carrier_id": 10, "name": "A Player", "status": "approved-crop-conversion-candidate"}],
    }
    rebound_manifest, rebound_materialisation, receipt = rebind(
        package=package, old_manifest=manifest, old_materialisation=materialisation,
    )
    assert rebound_manifest["clubs"][0]["players"][0]["player_carrier_id"] == 99
    assert rebound_materialisation["rows"][0]["player_carrier_id"] == 99
    assert receipt["coverage"] == {
        "clean_sourced_player_count": 2,
        "reused_approved_portrait_count": 1,
        "native_no_photo_count": 1,
        "old_download_failure_count": 0,
        "no_candidate_or_unmatched_count": 1,
        "identity_unmatched_count": 1,
    }


def test_old_preserve_native_portrait_is_not_replayed_to_new_carrier():
    package = {
        "schema_version": "pm99-season-package-v2",
        "clubs": [{"id": "club-1", "carrier_id": 1, "name": "Club", "roster_player_ids": ["player-99"]}],
        "players": [{"id": "player-99", "carrier_id": 99, "club_id": "club-1", "source_name": "Player"}],
    }
    manifest = {
        "schema_version": "pm99-world-2015-asset-candidate-manifest-v1",
        "clubs": [{"carrier_id": 1, "players": [{
            "slot_index": 0, "player_carrier_id": 10, "name": "Player",
            "portrait": {"status": "preserve-native-carrier-portrait"},
        }]}],
    }
    _, rebound_materialisation, receipt = rebind(
        package=package, old_manifest=manifest,
        old_materialisation={"schema_version": "pm99-world-2015-portrait-materialisation-v1", "rows": []},
    )
    assert rebound_materialisation["rows"] == []
    assert receipt["rows"][0]["resulting_state"] == "native-no-photo"
