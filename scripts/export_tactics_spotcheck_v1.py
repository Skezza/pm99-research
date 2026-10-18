#!/usr/bin/env python3
"""Export genuine, hash-checked tactics samples without launching games.

Each image is an original runner frame, not a rendered recipe diagram. The
existing coverage verifier must bind its sampled grid and named XI to the
final candidate. This does not claim every season/club has been played.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from scripts import season_pipeline_v2 as pipeline
from scripts import season_tactics_formation_runtime_v1 as runtime

SELECTION = ('5-4-1', '4-5-1', '5-2-3', '3-4-3', '4-1-3-2',
             '3-4-1-2', '4-4-2', '4-3-3', '4-2-3-1', '4-1-4-1',
             '5-3-2', '3-5-2', '3-4-2-1', '3-1-4-2', '4-3-2-1')


def checked_frame(proof, phase):
    rows = [p for p in proof['players'] if p['phase'] == phase]
    bindings = {(p['screenshot'], p['screenshot_sha256']) for p in rows}
    if len(rows) != 11 or len(bindings) != 1:
        raise ValueError('sample needs all eleven players on one phase frame')
    path_text, digest = next(iter(bindings))
    path = Path(path_text).resolve()
    if not path.is_relative_to((ROOT / '.local/runlogs/pm99_runner').resolve()):
        raise ValueError('frame is outside the runner artifact tree')
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('runner frame changed since verification')
    return path, digest


def export(root, output):
    if output.exists():
        raise ValueError('output already exists; never overwrite a review pack')
    coverage = runtime.verify_coverage(root, root)
    rows = []
    for number, formation in enumerate(SELECTION, 1):
        proof_path = root / 'formation-runtime-proofs-v2' / (formation + '.json')
        proof = json.loads(proof_path.read_text())
        row = {'number': number, 'club': proof['club'], 'season': proof['season'],
               'formation': formation, 'run_path': proof['run_path'],
               'proof_path': str(proof_path), 'proof_sha256': hashlib.sha256(proof_path.read_bytes()).hexdigest(),
               'frames': {}}
        for phase in ('attack', 'defend'):
            path, digest = checked_frame(proof, phase)
            row['frames'][phase] = {'original_path': str(path), 'sha256': digest,
                                    'file': f'{number:02d}-{proof["season"]}-{formation}-{phase}.png'}
        rows.append(row)
    output.mkdir(parents=True)
    cards = []
    for row in rows:
        for frame in row['frames'].values():
            shutil.copy2(frame['original_path'], output / frame['file'])
        title = f'{row["number"]:02d}. {row["club"]} — {row["season"]} — {row["formation"]}'
        images = ''.join(f'<figure><a href="{html.escape(row["frames"][phase]["file"])}">'
                         f'<img src="{html.escape(row["frames"][phase]["file"])}" '
                         f'alt="{html.escape(title)} {phase}"></a><figcaption>{phase.title()}</figcaption></figure>'
                         for phase in ('attack', 'defend'))
        cards.append(f'<section><h2>{html.escape(title)}</h2><div class="pair">{images}</div></section>')
    document = ('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>15 genuine PM99 tactics examples</title><style>'
        'body{font:16px system-ui;background:#111;color:#eee;margin:24px;max-width:1400px}'
        '.pair{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:320px}'
        'img{width:100%;max-width:640px}section{margin:30px 0}a{color:#8cf}'
        '</style><h1>15 genuine PM99 tactics examples</h1><p>Original runner screenshots. '
        'Click a frame to open it at full size. Attacking and defending positions are shown side by side.</p>'
        '<p>These formation samples are bound to the final rollout’s unchanged named XI and grid. '
        'They are not 15 newly launched published games and do not prove every club has been played. '
        'The rollout changes English playable tactics only; foreign mode-1 tactics are preserved.</p>'
        + ''.join(cards) + '</html>')
    (output / 'index.html').write_text(document, encoding='utf-8')
    manifest = {'schema': 'pm99-tactics-spotcheck-v1', 'sample_count': len(rows),
                'scope': 'genuine sampled formation frames; exact-grid/XI transfer, not all-club gameplay',
                'coverage': coverage, 'examples': rows}
    pipeline.write_canonical_json(output / 'manifest.json', manifest)
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
    for page in range(3):
        sheet = Image.new('RGB', (1280, 5 * 530), '#171b22')
        draw = ImageDraw.Draw(sheet)
        for slot, row in enumerate(rows[page * 5:(page + 1) * 5]):
            y = slot * 530
            draw.text((12, y + 5), f'{row["number"]:02d}  {row["club"]}  {row["season"]}  {row["formation"]}     Attack / Defend',
                      font=font, fill='white')
            for column, phase in enumerate(('attack', 'defend')):
                with Image.open(output / row['frames'][phase]['file']) as frame:
                    if frame.size != (640, 480):
                        raise ValueError('unexpected native screenshot dimensions')
                    sheet.paste(frame.convert('RGB'), (column * 640, y + 40))
        sheet.save(output / f'contact-sheet-{page + 1}.png')
    with zipfile.ZipFile(output / 'tactics-15-examples.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            if path.suffix in ('.png', '.html', '.json'):
                archive.write(path, path.name)
    return {'output': str(output), 'sample_count': len(rows), 'original_frames': len(rows) * 2}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / '.local/contextual-tactics-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.root.resolve(), args.output.resolve())))
