from pathlib import Path

from scripts.season_kit_source_capture_v1 import club_identity, discover, materialise, season_title_identity


def allocation() -> dict:
    return {"schema_version": "pm99-season-carrier-allocation-v1", "season": {"catalog": "2000-2001", "label": "2000/01"}, "assignments": [{"carrier_id": 1, "club_name": "Barcelona"}, {"carrier_id": 42, "club_name": "Stoke City"}]}


def page(page_id: int, title: str, complete: bool = True) -> dict:
    fields = {"pattern_la1": "_red_stripes", "pattern_b1": "_redstripes2", "pattern_ra1": "_red_stripes", "leftarm1": "FFFFFF", "body1": "FF0000", "rightarm1": "FFFFFF", "shorts1": "FFFFFF", "socks1": "FF0000"}
    text = "{{Football kit\n" + "\n".join(f"| {key} = {value}" for key, value in fields.items()) + "\n}}" if complete else "{{Football kit|body1=FF0000}}"
    return {"language": "en", "page_id": page_id, "page_title": title, "page_url": "https://en.wikipedia.org/wiki/Test", "revision_id": page_id + 100, "revision_timestamp": "2026-09-02T00:00:00Z", "wikitext": text}


def test_identity_accepts_only_legal_affix_equivalence() -> None:
    assert club_identity("FC Barcelona") == club_identity("Barcelona")
    assert season_title_identity("2000–01 Stoke City F.C. season", 2000, 2001) == club_identity("Stoke City")
    assert season_title_identity("2000–01 Stoke City Town F.C. season", 2000, 2001) != club_identity("Stoke City")
    assert season_title_identity("2001–02 Stoke City F.C. season", 2000, 2001) is None


def test_discovery_reports_ready_and_missing_fields() -> None:
    pages = [page(1, "2000–01 FC Barcelona season", complete=False), page(2, "2000–01 Stoke City F.C. season")]
    ledger, selected = discover(allocation(), allow_network=True, batch_fetcher=lambda _language, _titles: pages)
    assert selected.keys() == {1, 42}
    assert ledger["coverage"]["status_counts"] == {"revision-captured-home-fields-missing": 1, "revision-captured-home-fields-ready": 1}


def test_materialise_replays_revision_without_native_fallback(tmp_path: Path) -> None:
    pages = [page(1, "2000–01 FC Barcelona season", complete=False), page(2, "2000–01 Stoke City F.C. season")]
    result = materialise(allocation(), output_dir=tmp_path / "out", cache_dir=tmp_path / "cache", allow_network=True, batch_fetcher=lambda _language, _titles: pages)
    assert result["catalogue"]["status_counts"] == {"blocked-missing-home-kit-fields": 1, "source-ready": 1}
    assert "native-fallback" not in (tmp_path / "out" / "kit-catalogue-request-v1.json").read_text()
    assert list((tmp_path / "cache" / "objects").glob("*/*.json"))


def test_materialised_capture_binds_exact_allocation_hash(tmp_path: Path) -> None:
    pages = [page(1, "2000–01 FC Barcelona season", complete=False), page(2, "2000–01 Stoke City F.C. season")]
    materialise(allocation(), output_dir=tmp_path / "out", cache_dir=tmp_path / "cache", allow_network=True, batch_fetcher=lambda _language, _titles: pages)
    import hashlib, json
    from scripts.season_kit_source_capture_v1 import canonical_json_bytes
    retained = json.loads((tmp_path / "out" / "kit-source-capture-v1.json").read_text())
    assert retained["provenance"]["allocation_sha256"] == hashlib.sha256(canonical_json_bytes(allocation())).hexdigest()


def test_historical_current_pointer_is_hash_verified(tmp_path: Path) -> None:
    import hashlib, json
    from scripts.season_kit_source_capture_v1 import _allocation_paths, canonical_json_bytes
    season = tmp_path / "2000-01"
    revision = season / "revisions/rev-test"
    revision.mkdir(parents=True)
    payload = canonical_json_bytes(allocation())
    target = revision / "carrier-allocation.json"
    target.write_bytes(payload)
    pointer = {"schema_version": "pm99-historical-squad-backfill-current-v1", "revision_id": "rev-test", "season": "2000-01", "artifacts": {"allocation": {"path": "revisions/rev-test/carrier-allocation.json", "sha256": hashlib.sha256(payload).hexdigest()}}}
    (season / "current.json").write_bytes(canonical_json_bytes(pointer))
    rows = list(_allocation_paths(tmp_path))
    assert rows[0][0] == target
    assert rows[0][1]["historical_revision_id"] == "rev-test"
    target.write_bytes(payload + b"x")
    import pytest
    with pytest.raises(ValueError, match="hash mismatch"):
        list(_allocation_paths(tmp_path))
