from scripts.season_english_kit_layer_v1 import build_layer, capture_allocation


def intake() -> dict:
    return {"schema_version": "pm99-season-source-intake-v1", "season": {"label": "2000/01", "catalog": "2000-2001"}, "source_clubs": [{"selector": {"country_catalog": "eng", "competition_catalog": "faprem", "club_name": "Stoke City"}}, {"selector": {"country_catalog": "eng", "competition_catalog": "d1", "club_name": "Example Town"}}, {"selector": {"country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Barcelona"}}]}


def catalogue() -> dict:
    return {"schema_version": "pm99-season-kit-catalogue-v1", "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"}, "rows": [{"carrier_id": 1, "club_name": "Example Town", "status": "blocked-no-target-season-source", "reason": "gap"}, {"carrier_id": 2, "club_name": "Stoke City", "status": "source-ready", "render_contract": {"kind": "wikipedia-template-fields"}, "source": {"page_url": "https://en.wikipedia.org/wiki/Test", "revision_id": 123, "revision_timestamp": "2026-09-02T00:00:00Z", "cache_sha256": "a" * 64, "attribution": "Wikipedia contributors"}}]}


def test_capture_allocation_is_deterministic_and_english_only() -> None:
    allocation = capture_allocation(intake())
    assert [row["club_name"] for row in allocation["assignments"]] == ["Example Town", "Stoke City"]
    assert [row["carrier_id"] for row in allocation["assignments"]] == [1, 2]


def test_layer_preserves_exact_source_and_explicit_gap() -> None:
    layer = build_layer(intake(), catalogue())
    assert layer["schema_version"] == "pm99-season-kit-layer-v1"
    assert layer["coverage"]["english_club_count"] == 2
    ready = next(row for row in layer["clubs"] if row["club"] == "Stoke City")
    assert ready["policy"] == "historical-target-season"
    assert ready["source_revision_id"] == 123
    gap = next(row for row in layer["clubs"] if row["club"] == "Example Town")
    assert gap["policy"] == "blocked-no-target-season-source"
    assert gap["source_url"] is None


def test_exact_stoke_matrix_overrides_wikipedia_row() -> None:
    matrix = {"schema_version": "pm99-stoke-home-kit-evidence-matrix-v1", "rows": [{"season": "2000/01", "club": "Stoke City", "status": "source-ready", "source": {"page_url": "https://www.historicalkits.co.uk/Stoke_City/Stoke_City.htm", "page_sha256": "b" * 64, "evidence_url": "https://www.historicalkits.co.uk/Stoke_City/images/test.gif", "evidence_sha256": "c" * 64, "attribution": "Copyright Historical Football Kits and reproduced by kind permission."}, "facts": "red/white vertical-striped shirt; white shorts", "render_contract": {"kind": "reviewed-pm99-style", "style": {"pattern": "vertical_stripes", "colors": ["red", "white"], "shorts": "white"}}}]}
    layer = build_layer(intake(), catalogue(), matrix)
    ready = next(row for row in layer["clubs"] if row["club"] == "Stoke City")
    assert ready["home"]["kind"] == "reviewed-pm99-style"
    assert ready["source_evidence_sha256"] == "c" * 64
