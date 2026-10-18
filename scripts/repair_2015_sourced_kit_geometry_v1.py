#!/usr/bin/env python3
"""Project captured 2015 shirts onto the proven factory fabric plane.

No guessed pattern classifier: preserve the actual dated source decoration,
factory silhouette/creases, native wrapper and runtime palette. Shorts retain
the existing declared colour because the sources only show shirts.
"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as visual
from scripts import season_kit_render_bindings_v1 as renderer
from scripts.probe_sourced_factory_kit_v1 import checked_pixel_replacement, kit_image


def source_canvas(image):
    """Unwrap the standard 68x98 FIFAIndex shirt, not the empty background."""
    if image.size != (68, 98):
        raise ValueError('unsupported source garment framing')
    rgb = Image.new('RGBA', image.size, 'white')
    rgb.alpha_composite(image.convert('RGBA'))
    rgb = rgb.convert('RGB')
    canvas = Image.new('RGB', (100, 100))
    # Fixed source fabric interiors exclude the source contour and neckline.
    # Separate arms avoid stretching their backdrop into the shirt torso.
    for box, target, size in (((6, 22, 18, 51), (0, 0), (31, 100)),
                              ((18, 19, 50, 86), (31, 0), (38, 100)),
                              ((50, 22, 62, 51), (69, 0), (31, 100))):
        canvas.paste(rgb.crop(box).resize(size, Image.Resampling.NEAREST), target)
    return canvas


def prepare(output):
    if output.exists():
        raise ValueError('use a new output directory')
    release = registry.load_preferred_release('2015-16')
    source_path = ROOT / '.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v5-native-tone-transfer.json'
    findings_path = ROOT / '.local/visual-quality-v1/2015-16/kits-source-audit/visual-findings.json'
    source = json.loads(source_path.read_text())
    findings = json.loads(findings_path.read_text())
    targets = {int(r['carrier_id']) for r in findings['findings']} | {203}
    sources = {int(r['carrier_id']): r for r in source['rows']}
    clubs = {int(c['carrier_id']): c for c in json.loads(release.package_path.read_text())['clubs']}
    palette, _ = renderer._palette(release.game_path / 'DBDAT')
    original = {n: (release.game_path / 'DBDAT' / n).read_bytes() for n in renderer.ARCHIVES}
    changed = {n: bytearray(v) for n, v in original.items()}
    records = {n: renderer._record_index(release.game_path / 'DBDAT' / n) for n in renderer.ARCHIVES}
    templates = {n: renderer._record_index(ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT' / n)[4]
                 for n in renderer.ARCHIVES}
    events, rows, panels = [], [], []
    for carrier in sorted(targets):
        row = sources[carrier]
        if row['source_club_name'] != clubs[carrier]['name']:
            raise ValueError('source club identity changed')
        path = Path(row['source_image']['cache_path'])
        if visual.sha(path) != row['source_image']['sha256']:
            raise ValueError('source pixels changed')
        with Image.open(path) as opened:
            canvas = source_canvas(opened)
            thumb = opened.convert('RGBA')
            backdrop = Image.new('RGBA', thumb.size, 'white'); backdrop.alpha_composite(thumb)
            panel = [backdrop.convert('RGB')]
        for name in renderer.ARCHIVES:
            record = records[name][carrier]
            if renderer.sha256_bytes(record.raw_bitmap) != row['assets'][name]['sha256']:
                raise ValueError('previous source-bound kit bytes changed')
            fields = {'shorts1': bytes(row['render_recipe']['shorts']).hex()}
            payload = renderer._wikipedia_payload(record, {}, fields, palette, template=templates[name],
                                                  canvas_override=canvas.copy())
            checked_pixel_replacement(record, payload)
            start = record.bitmap_offset
            changed[name][start:start + record.bitmap_length] = payload
            events.append({'archive': name, 'carrier_id': carrier, 'club': clubs[carrier]['name'],
                           'before_bitmap_sha256': renderer.sha256_bytes(record.raw_bitmap),
                           'after_bitmap_sha256': renderer.sha256_bytes(payload),
                           'pixel_lane': [start + record.pixel_offset, start + record.pixel_offset + record.width * record.height]})
            if name == 'MINIESC.PKF':
                panel += [kit_image(record, palette), kit_image(replace(record, raw_bitmap=payload), palette)]
        rows.append({'carrier_id': carrier, 'club': clubs[carrier]['name'], 'source': row['source_image'],
                     'scope': 'shirt source projection; inherited shorts colour not independently certified'})
        panels.append((carrier, clubs[carrier]['name'], panel))
    output.mkdir(parents=True)
    plan = {'schema_version': visual.SCHEMA, 'season': '2015-16',
            'inputs': {'release_id': release.release_id, 'package_sha256': visual.sha(release.package_path),
                       'source_materialisation_sha256': visual.sha(source_path), 'findings_sha256': visual.sha(findings_path)},
            'no_photo': [], 'replacements': []}
    visual.save(output / 'plan.json', plan)
    hashes = {}
    for name in renderer.ARCHIVES:
        lanes = [e['pixel_lane'] for e in events if e['archive'] == name]
        if len(original[name]) != len(changed[name]) or any(
                not any(a <= i < b for a, b in lanes) for i, (a, b) in enumerate(zip(original[name], changed[name])) if a != b):
            raise ValueError('non-pixel kit bytes changed')
        path = output / 'patch/DBDAT' / name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(changed[name])
        hashes['DBDAT/' + name] = visual.sha(path)
        index = renderer._record_index(path)
        for event in (e for e in events if e['archive'] == name):
            if renderer.sha256_bytes(index[event['carrier_id']].raw_bitmap) != event['after_bitmap_sha256']:
                raise ValueError('compact archive readback failed')
    sheets = []
    for offset in range(0, len(panels), 12):
        sheet = Image.new('RGB', (1200, 800), '#18212a'); draw = ImageDraw.Draw(sheet)
        for i, (carrier, club, panel) in enumerate(panels[offset:offset + 12]):
            x, y = (i % 3) * 400, (i // 3) * 200
            draw.text((x + 5, y + 4), f'{carrier} {club}', fill='white')
            draw.text((x + 5, y + 24), 'Source         Before         Corrected', fill='#b9d5f0')
            for j, picture in enumerate(panel): sheet.paste(picture, (x + 5 + 125 * j, y + 45))
        path = output / f'kit-source-comparison-{offset // 12 + 1:02d}.png'
        sheet.save(path); sheets.append({'path': str(path), 'sha256': visual.sha(path)})
    receipt = {'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': '2015-16',
               'plan_sha256': visual.sha(output / 'plan.json'),
               'archive_before_sha256': visual.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'),
               'kit_before_sha256s': {'DBDAT/' + n: renderer.sha256_bytes(v) for n, v in original.items()},
               'outputs': hashes, 'events': events, 'clubs': rows, 'sheets': sheets,
               'no_photo_count': 0, 'replacements': [], 'visual_review': 'pending',
               'prior_audit_corrections': {'204': 'Lazio source is solid, not Sampdoria chest band; correct missing band is carrier 203',
                   '851': 'source really has hoops, not one chest band',
                   '866': 'white source rectangle is a sponsor, not a chest band',
                   '867': 'white source rectangle is a sponsor, not a chest band',
                   '1002': 'source has claret body with blue sleeve/side, not equal halves',
                   '1058': 'source has a blue centre panel, not equal halves',
                   '1107': 'source really has vertical stripes, not one centre panel',
                   '1161': 'source has an offset blue vertical panel, not quarters'}}
    visual.save(output / 'patch/receipt.json', receipt)
    return {'clubs': len(rows), 'bitmap_events': len(events), 'sheets': sheets}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output)))
