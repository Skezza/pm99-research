#!/usr/bin/env python3
"""Bind the manager short/full field isolation to an actual trophies frame.

This verifies a screen-field experiment, not a successful complete game run.
The experiment's SHORTQA/FULLQA names must never enter a published recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.fdi_indexed import IndexedFDIFile
from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from scripts import season_pipeline_v2 as pipeline


def verify(candidate, run, frame, *, visual_review=None):
    from PIL import Image
    def ocr(image):
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        result = subprocess.run(['tesseract', 'stdin', 'stdout', '--psm', '7'],
                                input=buffer.getvalue(), capture_output=True, check=True)
        return result.stdout.decode('utf-8').strip()
    receipt = json.loads((candidate / 'candidate-receipt.json').read_text())
    if receipt.get('field_probe') is not True:
        raise ValueError('requires a declared field-isolation probe')
    command = json.loads((run / 'control_launch.json').read_text())['child_command']
    argument = lambda name: command[command.index(name) + 1]
    if Path(argument('--dbdat-dir')).resolve() != (candidate / 'DBDAT').resolve():
        raise ValueError('another native input was launched')
    if Path(argument('--exe-file')).resolve() != Path(receipt['source_exe_path']).resolve():
        raise ValueError('another executable was launched')
    path = (candidate / 'DBDAT/ENT98030.FDI')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != receipt['after_ent_sha256']:
        raise ValueError('field-isolation native input changed')
    for file, field in [('EQ98030.FDI', 'source_eq_sha256'), ('JUG98030.FDI', 'source_jug_sha256')]:
        if hashlib.sha256((candidate / 'DBDAT' / file).read_bytes()).hexdigest() != receipt[field]:
            raise ValueError('field isolation changed a player or tactics input')
    entry = next(e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id == 681)
    profile = parse_indexed_ent_manager_profile(data[entry.payload_offset:entry.payload_offset + entry.payload_length], record_id=681)
    if (profile.format, profile.surname, profile.display_name) != ('full_profile', 'SHORTQA', 'FULLQA'):
        raise ValueError('the isolated short and full fields are not distinct')
    if not frame.resolve().is_relative_to((run / 'screens').resolve()):
        raise ValueError('frame does not belong to this actual run')
    with Image.open(frame) as image:
        if image.size != (640, 480):
            raise ValueError('not a native runner frame')
        if visual_review is None:
            title = ocr(image.crop((180, 9, 615, 43)).resize((870, 68)))
            row = ocr(image.crop((154, 264, 239, 282)).resize((510, 108)))
            method = 'local-tesseract'
        else:
            review = json.loads(visual_review.read_text())
            if (review.get('frame_sha256') != hashlib.sha256(frame.read_bytes()).hexdigest() or
                    review.get('method') != 'assistant-original-image-visual-review'):
                raise ValueError('explicit visual review does not bind this original frame')
            title, row = review['observed_title'], review['observed_chelsea_manager']
            method = review['method']
    if 'TEAMS IN CHAMPIONSHIPS' not in title.upper() or 'SHORTQA' not in row.upper() or 'FULLQA' in row.upper():
        raise ValueError(f'actual screen did not prove the short field: title={title!r}, row={row!r}')
    return {'schema': 'pm99-manager-display-field-runtime-proof-v1',
        'candidate': str(candidate), 'run': str(run), 'frame': str(frame),
        'frame_sha256': hashlib.sha256(frame.read_bytes()).hexdigest(),
        'candidate_receipt_sha256': hashlib.sha256((candidate / 'candidate-receipt.json').read_bytes()).hexdigest(),
        'control_launch_sha256': hashlib.sha256((run / 'control_launch.json').read_bytes()).hexdigest(),
        'title_text': title, 'manager_row_text': row, 'text_verification_method': method, 'record_id': 681,
        'visual_review_sha256': hashlib.sha256(visual_review.read_bytes()).hexdigest() if visual_review else None,
        'native_surname': profile.surname, 'native_display_name': profile.display_name,
        'screen_reads': 'surname', 'complete_game_run_proven': False,
        'scope': 'championships manager text field only; failed later bootstrap remains failed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--frame', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--visual-review', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('proof already exists; never overwrite')
    result = verify(args.candidate.resolve(), args.run.resolve(), args.frame.resolve(), visual_review=args.visual_review)
    pipeline.write_canonical_json(args.output, result)
    print(json.dumps(result))
