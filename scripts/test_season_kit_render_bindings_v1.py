import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from scripts import season_kit_render_bindings_v1 as renderer
from scripts.season_kit_render_bindings_v1 import ARCHIVES, catalogue_from_english_compiler_input, render_catalogue


def _record(carrier: int = 600) -> SimpleNamespace:
    return SimpleNamespace(width=4, height=4, pixel_offset=0, raw_bitmap=bytes([1] * 16), file_name=f"EQ96{carrier:04d}.BMP")


def _records(_path: Path) -> dict[int, SimpleNamespace]:
    # Carrier 2 is V5's vertical-stripe factory template; 600 is the target.
    return {2: _record(2), 600: _record(600)}


def _catalogue(status: str = "source-ready") -> dict:
    row = {"carrier_id": 600, "carrier_status": "continuing", "club_name": "Example Town", "status": status}
    if status == "source-ready":
        row["render_contract"] = {"kind": "reviewed-pm99-style", "style": {"pattern": "vertical_stripes", "colors": ["red", "white"], "shorts": "black", "stripe_count": 4}}
    return {"schema_version": "pm99-season-kit-catalogue-v1", "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"}, "rows": [row]}


def _palette(_path: Path):
    return ([(index, index, index) for index in range(256)], {"path": "fixture", "source": "fixture", "sha256": "fixture"})


def test_reviewed_source_ready_row_produces_three_hash_bound_artifacts(tmp_path: Path) -> None:
    binding, receipt = render_catalogue(_catalogue(), dbdat=tmp_path, output_dir=tmp_path / "out", pattern_cache_dir=tmp_path / "cache", record_loader=_records, palette_loader=_palette)
    assert binding["kit_catalogue_sha256"] == receipt["kit_catalogue_sha256"]
    assert len(binding["clubs"]) == 1
    assert len(binding["clubs"][0]["artifacts"]) == len(ARCHIVES)
    assert receipt["coverage"]["artifact_count"] == 3
    assert receipt["policy"]["reviewed_style_renderer"] == renderer.factory_tone_renderer.RENDERER_ID
    assert receipt["rows"][0]["renderer"] == renderer.factory_tone_renderer.RENDERER_ID
    assert all((tmp_path / "out" / row["relative_path"]).is_file() for row in binding["clubs"][0]["artifacts"])


def test_catalogue_gap_never_creates_artifact_or_binding(tmp_path: Path) -> None:
    binding, receipt = render_catalogue(_catalogue("blocked-no-target-season-source"), dbdat=tmp_path, output_dir=tmp_path / "out", pattern_cache_dir=tmp_path / "cache", record_loader=_records, palette_loader=_palette)
    assert binding["clubs"] == []
    assert receipt["coverage"]["artifact_count"] == 0
    assert receipt["rows"][0]["status"] == "not-rendered-catalogue-gap"


def test_shorts_overlay_is_never_silently_replaced_with_flat_colour(tmp_path):
    catalogue = _catalogue()
    catalogue['rows'][0]['render_contract'] = {
        'kind': 'wikipedia-template-fields', 'fields': {'shorts1': 'EE7537', 'pattern_sh1': '_am1415h'}}
    binding, receipt = render_catalogue(catalogue, dbdat=tmp_path, output_dir=tmp_path / 'out',
        pattern_cache_dir=tmp_path / 'cache', record_loader=_records, palette_loader=_palette)
    assert binding['clubs'] == []
    assert receipt['rows'][0]['status'] == 'not-rendered-unsupported-shorts-overlay'


def test_wikipedia_source_requires_exact_layers(tmp_path: Path) -> None:
    catalogue = _catalogue()
    catalogue["rows"][0]["render_contract"] = {"kind": "wikipedia-template-fields", "fields": {"pattern_b1": "_x", "pattern_la1": "_x", "pattern_ra1": "_x"}}
    binding, receipt = render_catalogue(catalogue, dbdat=tmp_path, output_dir=tmp_path / "out", pattern_cache_dir=tmp_path / "cache", record_loader=_records, palette_loader=_palette, layer_resolver=lambda _tokens, _cache, _network: {"status": "missing", "reason": "fixture-miss"})
    assert binding["clubs"] == []
    assert receipt["rows"][0]["status"] == "not-rendered-exact-pattern-unavailable"


def test_mixed_default_and_exact_patterns_fetch_only_declared_layer(tmp_path: Path, monkeypatch) -> None:
    payload = io.BytesIO()
    Image.new("RGB", (38, 100), "red").save(payload, format="PNG")
    calls = []

    def get(url, **_kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, content=payload.getvalue())

    monkeypatch.setattr(renderer.legacy_renderer.requests, "get", get)
    result = renderer.resolve_wikipedia_layers(
        {"body": "_exact", "left_arm": "", "right_arm": ""},
        tmp_path / "cache",
        allow_network=True,
    )
    assert result["status"] == "ready"
    assert set(result["layers"]) == {"body"}
    assert result["defaulted_empty_parts"] == ["left_arm", "right_arm"]
    assert len(calls) == 1


def test_english_compiler_projection_uses_final_mode0_carrier() -> None:
    source = {"schema_version": "pm99-english-mode0-compiler-input-v1", "season": "2000/01", "clubs": [{"carrier_id": 341, "club": "Stoke City", "kit": {"status": "source-ready", "policy": "historical-target-season", "source_url": "https://example.test", "home": {"kind": "reviewed-pm99-style", "style": {"pattern": "vertical_stripes"}}}}]}
    catalogue = catalogue_from_english_compiler_input(source)
    assert catalogue["rows"][0]["carrier_id"] == 341
    assert catalogue["rows"][0]["render_contract"]["kind"] == "reviewed-pm99-style"


def test_transparent_pattern_uses_fabric_colour_not_hidden_black(tmp_path):
    path = tmp_path / 'body.png'
    Image.new('RGBA', (38, 59), (0, 0, 0, 0)).save(path)
    canvas = renderer._wikipedia_canvas({'layers': {'body': {'path': str(path)}}},
        {'body1': 'FF0000', 'leftarm1': 'FF0000', 'rightarm1': 'FF0000'})
    assert canvas.getpixel((50, 10)) == (255, 0, 0)
    assert canvas.getpixel((50, 99)) == (255, 0, 0)


def test_short_opaque_pattern_covers_the_entire_shirt(tmp_path):
    path = tmp_path / 'body.png'
    Image.new('RGB', (38, 59), 'blue').save(path)
    canvas = renderer._wikipedia_canvas({'layers': {'body': {'path': str(path)}}},
        {'body1': 'FF0000', 'leftarm1': 'FF0000', 'rightarm1': 'FF0000'})
    assert canvas.getpixel((50, 99)) == (0, 0, 255)
    assert canvas.getpixel((10, 99)) == (255, 0, 0)


def test_opaque_white_diagram_backdrop_is_not_painted_as_fabric(tmp_path):
    from PIL import ImageDraw
    source = Image.new('RGB', (31, 59), 'white')
    ImageDraw.Draw(source).polygon([(15, 14), (30, 2), (30, 45)], fill='red', outline='black')
    path = tmp_path / 'arm.png'
    source.save(path)
    texture = renderer._pattern_texture(path, (255, 0, 0), (31, 100))
    assert texture.getpixel((15, 50)) == (255, 0, 0)
    assert sum(pixel == (255, 255, 255) for pixel in texture.getdata()) == 0


def test_open_white_torso_keeps_fabric_not_only_coloured_piping(tmp_path):
    from PIL import ImageDraw
    source = Image.new('RGB', (38, 59), 'white')
    draw = ImageDraw.Draw(source)
    draw.line([(2, 8), (2, 58)], fill='red', width=2)
    draw.line([(35, 8), (35, 58)], fill='red', width=2)
    path = tmp_path / 'white-body.png'
    source.save(path)
    texture = renderer._pattern_texture(path, (255, 255, 255), (38, 100), 'body')
    assert texture.getpixel((19, 50)) == (255, 255, 255)
    assert sum(p == (255, 255, 255) for p in texture.getdata()) > 3000


def test_straight_body_stripes_remain_straight_in_source_texture(tmp_path):
    from PIL import ImageDraw
    source = Image.new('RGB', (38, 59), 'white')
    ImageDraw.Draw(source).rectangle((12, 0, 25, 58), fill='red')
    path = tmp_path / 'striped-body.png'
    source.save(path)
    texture = renderer._pattern_texture(path, (255, 255, 255), (38, 100), 'body')
    assert list(texture.crop((0, 20, 38, 21)).getdata()) == list(texture.crop((0, 80, 38, 81)).getdata())


def test_open_white_sleeve_does_not_inflate_coloured_cuff(tmp_path):
    from PIL import ImageDraw
    source = Image.new('RGBA', (31, 59), (255, 255, 255, 0))
    draw = ImageDraw.Draw(source)
    draw.line([(30, 5), (13, 22), (25, 34)], fill='black', width=1)
    draw.line([(14, 22), (25, 33)], fill='yellow', width=1)
    path = tmp_path / 'sleeve.png'
    source.save(path)
    texture = renderer._pattern_texture(path, (255, 255, 255), (31, 100), 'left_arm')
    assert sum(p == (255, 255, 255) for p in texture.getdata()) > 2400
