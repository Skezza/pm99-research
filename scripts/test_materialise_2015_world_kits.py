from __future__ import annotations

from pathlib import Path

from scripts.materialise_2015_world_kits import _search_match, materialise_kits, parse_home_fields, render_candidate


MINIFOTO = Path(".local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT/MINIESC.PKF")


def test_strict_title_binding_accepts_expanded_club_name() -> None:
    assert _search_match("2015–16 FC Barcelona season", "Barcelona")
    assert _search_match("2015–16 Godoy Cruz season", "Godoy Cruz (Mendoza)")
    assert not _search_match("2015–16 Athletic Bilbao season", "Barcelona")


def test_home_template_requires_all_fields() -> None:
    text = """{{Football kit\n| pattern_la1 = _exampleh\n| pattern_b1 = _exampleh\n| pattern_ra1 = _exampleh\n| leftarm1 = 112233\n| body1 = 112233\n| rightarm1 = 112233\n| shorts1 = 445566\n| socks1 = 778899\n}}"""
    parsed = parse_home_fields(text)
    assert parsed["status"] == "home-kit-fields-ready"
    assert parsed["fields"]["body1"] == "112233"
    assert parse_home_fields(text.replace("| socks1 = 778899", "| socks1 ="))["status"] == "missing-home-kit-fields"


def test_invalid_colour_is_blocked() -> None:
    text = "\n".join(f"| {field} = {'_pattern' if field.startswith('pattern') else 'not-a-colour'}" for field in ("pattern_la1", "pattern_b1", "pattern_ra1", "leftarm1", "body1", "rightarm1", "shorts1", "socks1"))
    assert parse_home_fields(text)["status"] == "invalid-home-kit-colours"


def test_colour_candidate_preserves_native_shading_and_never_makes_a_visible_pixel_transparent() -> None:
    record = type("Record", (), {"width": 6, "height": 6, "pixel_offset": 4, "raw_bitmap": b"head" + bytes([2, 10, 20, 30, 40, 50] * 6) + b"tail"})()
    palette = [(0, 0, 0), *[(value, 0, 0) for value in range(5, 256, 5)]]
    fields = {field: "cc0000" for field in ("leftarm1", "body1", "rightarm1", "shorts1", "socks1")}
    fields.update({field: "" for field in ("pattern_la1", "pattern_b1", "pattern_ra1")})

    payload = render_candidate(record, fields, palette)

    pixels = payload[record.pixel_offset : record.pixel_offset + record.width * record.height]
    assert payload[: record.pixel_offset] == record.raw_bitmap[: record.pixel_offset]
    assert payload[-4:] == record.raw_bitmap[-4:]
    assert all(index != 0 for index in pixels)
    assert len(set(pixels)) >= 3


def test_page_found_wikitext_reaches_render_stage(tmp_path: Path, monkeypatch) -> None:
    fields = "\n".join(f"| {field} = {'_vneck' if field.startswith('pattern') else '112233'}" for field in ("pattern_la1", "pattern_b1", "pattern_ra1", "leftarm1", "body1", "rightarm1", "shorts1", "socks1"))
    wikitext = "{{Football kit\n" + fields + "\n}}"
    monkeypatch.setattr("scripts.materialise_2015_world_kits._search_page", lambda club: {"status": "page-found", "page_title": "2015–16 Example season", "wikitext": wikitext})
    monkeypatch.setattr("scripts.materialise_2015_world_kits._fetch_pattern_layers", lambda tokens, cache: {"status": "missing", "reason": "test"})
    manifest = {"schema_version": "pm99-world-2015-asset-candidate-manifest-v1", "clubs": [{"carrier_id": 1, "source_status": "source-squad-ready", "source_country_catalog": "test", "source_club_name": "Example", "players": []}]}
    result = materialise_kits(manifest, dbdat=MINIFOTO.parent, cache_dir=tmp_path / "cache", output_dir=tmp_path / "out", workers=1)
    assert result["coverage"]["release_eligible_exact_geometry_candidate_count"] == 1
    assert result["rows"][0]["status"] == "release-eligible-exact-geometry-candidate"
