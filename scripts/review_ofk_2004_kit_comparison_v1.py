"""Generate a palette-correct diagnostic, not new artwork."""
from PIL import Image, ImageDraw
from scripts import season_kit_render_bindings_v1 as render
from scripts import season_release_registry_v1 as registry
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts.probe_sourced_factory_kit_v1 import kit_image


def main():
    target = source.AUDIT / 'ofk-2004-kit-comparison-v1.png'
    if target.exists(): raise ValueError('kit diagnostic already exists; inspect it')
    baseline = registry.load_preferred_release('2004-05')
    palette, _ = render._palette(baseline.game_path / 'DBDAT')
    root = source.AUDIT / 'ofk-2004-private-kits-v1/DBDAT'
    sheet = Image.new('RGB', (620, 740), '#25313a')
    draw = ImageDraw.Draw(sheet)
    draw.text((15, 8), 'Existing Becej / reviewed 2004 OFK - actual game palette', fill='white')
    for i, archive in enumerate(render.ARCHIVES):
        old = render._record_index(baseline.game_path / 'DBDAT' / archive)[706]
        new = render._record_index(root / archive)[706]
        draw.text((15, i * 235 + 35), archive, fill='white')
        for col, record in enumerate((old, new)):
            picture = kit_image(record, palette)
            picture.thumbnail((250, 200), Image.Resampling.NEAREST)
            sheet.paste(picture, (15 + col * 310, i * 235 + 60))
    sheet.save(target)


if __name__ == '__main__': main()
