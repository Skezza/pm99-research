from __future__ import annotations

from pathlib import Path

import pytest

from scripts.season_kit_catalogue_v1 import (
    FKA_PROVIDER,
    WIKI_PROVIDER,
    KitCatalogueError,
    build_catalogue,
)


def request(*clubs: dict) -> dict:
    return {
        "schema_version": "pm99-season-kit-catalogue-request-v1",
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"},
        "clubs": list(clubs),
    }


def wiki_source() -> dict:
    return {"provider": WIKI_PROVIDER, "language": "en", "page_title": "2000–01 Stoke City F.C. season"}


def wiki_payload() -> dict:
    fields = {
        "pattern_la1": "_red_stripes",
        "pattern_b1": "_redstripes2",
        "pattern_ra1": "_red_stripes",
        "leftarm1": "FFFFFF",
        "body1": "FF0000",
        "rightarm1": "FFFFFF",
        "shorts1": "FFFFFF",
        "socks1": "FF0000",
    }
    return {
        "language": "en",
        "page_id": 123,
        "page_title": "2000–01 Stoke City F.C. season",
        "page_url": "https://en.wikipedia.org/wiki/2000%E2%80%9301_Stoke_City_F.C._season",
        "revision_id": 456,
        "revision_timestamp": "2026-08-31T12:00:00Z",
        "wikitext": "{{Football kit\n" + "\n".join(f"| {key} = {value}" for key, value in fields.items()) + "\n}}",
    }


def test_home_parser_retains_shorts_overlay_instead_of_discarding_it():
    from scripts.season_kit_catalogue_v1 import _parse_wikipedia_home_kit
    text = wiki_payload()['wikitext'].replace('\n}}', '\n| pattern_sh1 = _am1415h\n}}')
    assert _parse_wikipedia_home_kit(text)['fields']['pattern_sh1'] == '_am1415h'


def test_network_capture_is_replayed_offline_from_content_addressed_cache(tmp_path: Path) -> None:
    req = request({"carrier_id": 42, "club_name": "Stoke City", "carrier_status": "continuing", "source": wiki_source()})
    calls = []

    def fetcher(source: dict) -> dict:
        calls.append(source)
        return wiki_payload()

    first = build_catalogue(req, cache_dir=tmp_path, allow_network=True, wikipedia_fetcher=fetcher)
    replay = build_catalogue(req, cache_dir=tmp_path, allow_network=False)
    assert len(calls) == 1
    assert first == replay
    assert replay["rows"][0]["status"] == "source-ready"
    assert replay["rows"][0]["source"]["revision_id"] == 456
    assert list((tmp_path / "objects").glob("*/*.json"))


def test_missing_source_is_explicit_and_fallback_is_only_for_exited_carrier(tmp_path: Path) -> None:
    result = build_catalogue(
        request(
            {"carrier_id": 1, "club_name": "Continuing FC", "carrier_status": "continuing", "source": None},
            {"carrier_id": 2, "club_name": "Exited FC", "carrier_status": "exited", "source": None},
            {"carrier_id": 3, "club_name": "Uncached FC", "carrier_status": "continuing", "source": wiki_source()},
        ),
        cache_dir=tmp_path,
    )
    assert [row["status"] for row in result["rows"]] == [
        "blocked-no-target-season-source",
        "native-fallback-authorized",
        "blocked-cache-miss",
    ]


def test_reviewed_fka_style_is_attributed_and_render_ready(tmp_path: Path) -> None:
    source = {
        "provider": FKA_PROVIDER,
        "url": "https://www.footballkitarchive.com/stoke-city-2000-01-home-kit/",
        "evidence_sha256": "a" * 64,
        "reviewed_style": {
            "pattern": "vertical_stripes",
            "colors": ["red", "white"],
            "shorts": "white",
            "trim": "blue",
            "stripe_count": 6,
        },
    }
    result = build_catalogue(
        request({"carrier_id": 42, "club_name": "Stoke City", "carrier_status": "continuing", "source": source}),
        cache_dir=tmp_path,
    )
    row = result["rows"][0]
    assert row["status"] == "source-ready"
    assert row["render_contract"]["style"]["pattern"] == "vertical_stripes"
    assert row["source"]["evidence_sha256"] == "a" * 64
    assert "Football Kit Archive" in row["source"]["attribution"]


def test_fka_requires_retained_evidence_hash(tmp_path: Path) -> None:
    source = {
        "provider": FKA_PROVIDER,
        "url": "https://www.footballkitarchive.com/example/",
        "reviewed_style": {"pattern": "solid", "colors": ["red"]},
    }
    with pytest.raises(KitCatalogueError, match="evidence_sha256"):
        build_catalogue(
            request({"carrier_id": 1, "club_name": "Example", "carrier_status": "continuing", "source": source}),
            cache_dir=tmp_path,
        )


def test_fka_style_must_use_existing_pm99_renderer_vocabulary(tmp_path: Path) -> None:
    source = {
        "provider": FKA_PROVIDER,
        "url": "https://www.footballkitarchive.com/example/",
        "evidence_sha256": "a" * 64,
        "reviewed_style": {"pattern": "solid", "colors": ["invisible-ultraviolet"]},
    }
    with pytest.raises(KitCatalogueError, match="renderer colours"):
        build_catalogue(
            request({"carrier_id": 1, "club_name": "Example", "carrier_status": "continuing", "source": source}),
            cache_dir=tmp_path,
        )


def test_clubs_must_be_sorted_for_reproducible_output(tmp_path: Path) -> None:
    with pytest.raises(KitCatalogueError, match="sorted"):
        build_catalogue(
            request(
                {"carrier_id": 2, "club_name": "B", "carrier_status": "continuing", "source": None},
                {"carrier_id": 1, "club_name": "A", "carrier_status": "continuing", "source": None},
            ),
            cache_dir=tmp_path,
        )


def test_omitted_pattern_overlays_default_to_exact_plain_colours() -> None:
    from scripts.season_kit_catalogue_v1 import _parse_wikipedia_home_kit
    parsed = _parse_wikipedia_home_kit("| leftarm1 = FF0000\n| body1 = FFFFFF\n| rightarm1 = FF0000\n| shorts1 = FFFFFF\n| socks1 = FF0000")
    assert parsed["status"] == "home-kit-fields-ready"
    assert parsed["defaulted_empty_pattern_fields"] == ["pattern_b1", "pattern_la1", "pattern_ra1"]


def test_omitted_colour_is_never_inferred() -> None:
    from scripts.season_kit_catalogue_v1 import _parse_wikipedia_home_kit
    parsed = _parse_wikipedia_home_kit("| leftarm1 = FF0000\n| body1 = FFFFFF\n| rightarm1 = FF0000\n| shorts1 = FFFFFF")
    assert parsed["status"] == "missing-home-kit-fields"
    assert "socks1" in parsed["missing_fields"]


def test_unambiguous_css_hex_and_comment_syntax_is_normalised() -> None:
    from scripts.season_kit_catalogue_v1 import _parse_wikipedia_home_kit
    text = "| pattern_la1 = _x\n| pattern_b1 = _x\n| pattern_ra1 = _x\n| leftarm1 = 00c\n| body1 = f4d84d<!--\n| rightarm1 = = BB0000\n| shorts1 = FFFFFFF\n| socks1 = 000000-->"
    parsed = _parse_wikipedia_home_kit(text)
    assert parsed["status"] == "home-kit-fields-ready"
    assert parsed["fields"]["leftarm1"] == "0000cc"
    assert parsed["fields"]["body1"] == "f4d84d"
    assert parsed["fields"]["rightarm1"] == "BB0000"
    assert parsed["fields"]["shorts1"] == "FFFFFF"
