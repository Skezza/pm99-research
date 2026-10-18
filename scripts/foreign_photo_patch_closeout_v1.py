#!/usr/bin/env python3
"""Export credited samples decoded from installed native BMPs, not candidate previews."""
import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts.pm99_kit_palette_v1 import runtime_kit_palette


def installed_preview(bitmap, palette):
    shape = portraits.validate_minifoto_bitmap(bitmap)
    pixels = bitmap[shape.pixel_offset:shape.pixel_offset + shape.pixel_length]
    if len(pixels) != shape.width * shape.height:
        raise ValueError('unsupported portrait row stride')
    image = Image.frombytes('P', (shape.width, shape.height), pixels)
    image.putpalette([int(channel) for colour in palette for channel in colour])
    return ImageOps.flip(image).convert('RGB')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch-root', type=Path, action='append', required=True,
                        help='repeat in installation order')
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True)
    selected = {}
    for root in args.patch_root:
        for path in sorted(root.glob('*/patch/receipt.json')):
            receipt = json.loads(path.read_text())
            for row in receipt['replacements']:
                selected[(receipt['season'], int(row['carrier_id']))] = row
    rows = []
    samples = []
    wanted = [('2005-06', 'Cristiano Ronaldo'), ('2006-07', 'Lionel Messi'),
              ('2006-07', 'Ronaldinho'), ('2007-08', 'Paolo Maldini'),
              ('2009-10', 'Xavi Hernandez'), ('2011-12', 'Andres Iniesta'),
              ('2012-13', 'Marko Arnautovic'), ('2013-14', 'Robert Lewandowski'),
              ('2016-17', 'Gianluigi Buffon'), ('2019-20', 'Erling Haaland'),
              ('2025-26', 'Kylian Mbappe'), ('2025-26', 'Lamine Yamal')]
    for (season, carrier), row in sorted(selected.items()):
        release = registry.load_preferred_release(season)
        bitmap = release.game_path / 'DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        if art.sha(bitmap) != row['bitmap_sha256']:
            raise ValueError('installed portrait differs from reviewed patch')
        rows.append({'season': season, 'name': row['name'], 'carrier_id': carrier,
                     **{key: row['source'][key] for key in ('title', 'photo_year', 'date_basis', 'date_declaration',
                        'artist', 'licence', 'licence_url', 'source_page')}, 'bitmap_sha256': row['bitmap_sha256']})
        if (season, row['source_name']) not in wanted: continue
        palette, palette_source = runtime_kit_palette(release.game_path / 'DBDAT')
        preview = installed_preview(bitmap.read_bytes(), palette)
        # Verify that the receipt's candidate preview actually matches the
        # currently installed native pixels and runtime palette.
        candidate = Image.open(row['preview_path']).convert('RGB')
        if preview.tobytes() != candidate.tobytes():
            old_palette_path, _ = portraits.discover_riff_palette_resource(release.game_path / 'DBDAT/MINIFOTO.PKF',
                extra_roots=[release.game_path / 'DBDAT', release.game_path])
            old_palette = portraits.load_riff_palette(old_palette_path)
            if ([i for i in range(256) if old_palette[i] != palette[i]] != [111]
                    or installed_preview(bitmap.read_bytes(), old_palette).tobytes() != candidate.tobytes()):
                raise ValueError('native decode and candidate preview differ beyond the known palette slot 111')
        tile = Image.new('RGB', (300, 240), '#202833')
        tile.paste(ImageOps.contain(Image.open(row['crop_path']).convert('RGB'), (140, 140)), (5, 5))
        tile.paste(preview.resize((128, 128), Image.Resampling.NEAREST), (162, 10))
        draw = ImageDraw.Draw(tile)
        for y, label in [(154, season + ' ' + row['source_name']), (174, str(row.get('club') or '')),
                         (194, 'Photographed ' + str(row['source']['photo_year'])), (215, 'Right: installed native BMP')]:
            draw.text((5, y), label, fill='white')
        samples.append(((season, row['source_name']), tile))
    samples.sort(key=lambda item: wanted.index(item[0]))
    canvas = Image.new('RGB', (1200, max(240, ((len(samples) + 3)//4)*240)), '#111820')
    for index, (_, tile) in enumerate(samples):
        canvas.paste(tile, ((index % 4)*300, (index // 4)*240))
    canvas.save(args.output_root / 'installed-photo-samples.png')
    with (args.output_root / 'photo-credits.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    art.save(args.output_root / 'installed-photo-patch-summary.json', {'patched_photos': len(rows),
             'patched_seasons': len({r['season'] for r in rows}), 'samples': len(samples), 'photos': rows})
    print(json.dumps({'patched_photos': len(rows), 'samples': len(samples), 'output': str(args.output_root)}))


if __name__ == '__main__':
    main()
