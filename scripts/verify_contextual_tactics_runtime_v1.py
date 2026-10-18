#!/usr/bin/env python3
"""Verify real runner pixels and the complete independently read live XI grid."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def marker_centres(path, phase):
    pixels = np.asarray(Image.open(path).convert('RGB'))
    red, green, blue = (pixels[125:380, 175:610, i].astype(int) for i in range(3))
    mask = ((red > 75) & (green < 65) & (blue < 105)) if phase == 'defend' else (
        (red < 40) & (green > 60) & (green > blue + 20))
    count, labels, stats, centres = cv2.connectedComponentsWithStats(mask.astype('uint8'), 8)
    return [(float(centres[i][0] + 175), float(centres[i][1] + 125)) for i in range(1, count)
            if 20 <= stats[i, cv2.CC_STAT_AREA] <= 500]


def verify(candidate, run, carrier_id=307, *, header_review=None):
    layer = json.loads((candidate / 'contextual-tactics.json').read_text())
    clubs = [c for c in layer['clubs'] if c['carrier_id'] == carrier_id]
    if len(clubs) != 1:
        raise ValueError('runtime proof needs one explicitly selected candidate club')
    club = clubs[0]
    context = club['context']
    identity_path = run / 'tactics-team-identity.json'
    identity = json.loads(identity_path.read_text()) if identity_path.is_file() else None
    reviewed_identity = None
    if len(layer['clubs']) > 1 or identity is not None:
        if not identity or identity.get('expected') != club.get('name'):
            raise ValueError('actual tactics header does not independently identify the selected club')
        frame = run / 'screens' / Path(identity['screenshot']).name
        if frame.name != next((run / 'screens').glob('*_tactics_matrix_defend_all_players.png')).name:
            raise ValueError('team identity does not bind the checked tactics frame')
        if hashlib.sha256(frame.read_bytes()).hexdigest() != identity['screenshot_sha256']:
            raise ValueError('team identity screenshot hash changed')
        if not identity.get('matched'):
            if header_review is None:
                raise ValueError('actual tactics header does not independently identify the selected club')
            review = json.loads(Path(header_review).read_text())
            if (review.get('schema_version') != 'pm99-runtime-header-visual-review-v1' or
                    review.get('run_tag') != run.name or review.get('carrier_id') != carrier_id or
                    review.get('observed_club') != club.get('name') or
                    review.get('screenshot_sha256') != identity['screenshot_sha256'] or
                    review.get('method') != 'assistant visual inspection of original screenshot'):
                raise ValueError('visual header review does not bind this exact team and screenshot')
            reviewed_identity = {'path': str(header_review), 'sha256': hashlib.sha256(Path(header_review).read_bytes()).hexdigest(),
                                 'review': review, 'scope': 'explicit visual review of an OCR failure, not an automatic OCR pass'}
    proof_path = run / 'tactics-runtime-proof.json'
    proof = json.loads(proof_path.read_text())
    if proof.get('expected_eq_sha256') and proof['expected_eq_sha256'] != hashlib.sha256((candidate / 'DBDAT/EQ98030.FDI').read_bytes()).hexdigest():
        raise ValueError('live proof was compared against another expected database')
    if (not proof['success'] or proof['carrier_id'] != carrier_id or proof['coordinate_values_checked'] != 880 or
            proof['averages_checked'] != 44 or proof['phases'] != ['attack', 'defend']):
        raise ValueError('runner did not independently read every loaded XI state')
    expected_runtime = b''
    for slot in context['slots']:
        states = slot['states']
        expected_runtime += b''.join(struct.pack('<2I', s[3], s[2]) for s in states)
        expected_runtime += b''.join(struct.pack('<2I', s[1], s[0]) for s in states)
        expected_runtime += struct.pack('<4I', *(sum(s[c] for s in states) // 20 for c in (3, 2, 1, 0)))
    if not any(bytes.fromhex(m['readback_hex']) == expected_runtime for m in proof['matches']):
        raise ValueError('live game state bytes differ from the published recipe')
    reports = []
    for phase, lane_index, depth_index in [('attack', 2, 3), ('defend', 0, 1)]:
        screenshot = next((run / 'screens').glob(f'*_tactics_matrix_{phase}_all_players.png'))
        observed = marker_centres(screenshot, phase)
        used = set()
        for slot in context['slots']:
            depth = sum(s[depth_index] for s in slot['states']) // 20
            lane = sum(s[lane_index] for s in slot['states']) // 20
            expected = (188 + depth, 137 + lane)
            candidates = [(np.hypot(x - expected[0], y - expected[1]), i, (x, y))
                          for i, (x, y) in enumerate(observed) if i not in used]
            if not candidates:
                raise ValueError(f'no visible {phase} marker for {slot["native_name"]}')
            error, component_id, centre = min(candidates)
            if error > 6:
                raise ValueError(f'{phase} marker differs from loaded average for {slot["native_name"]}: {error:.1f}px')
            used.add(component_id)
            reports.append({'player': slot['native_name'], 'player_id': slot['native_player_id'], 'role': slot['role'],
                'phase': phase, 'expected_centre': expected, 'observed_centre': centre, 'error_pixels': float(error),
                'screenshot': str(screenshot), 'screenshot_sha256': hashlib.sha256(screenshot.read_bytes()).hexdigest()})
    return {'schema_version': 'pm99-contextual-tactics-visual-proof-v2', 'success': True,
        'carrier_id': carrier_id, 'club': club.get('name'), 'formation': club.get('formation'),
        'named_player_phases_checked': 22, 'runtime_proof_sha256': hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        'tactics_layer_sha256': hashlib.sha256((candidate / 'contextual-tactics.json').read_bytes()).hexdigest(),
        'team_identity': identity,
        'header_visual_review': reviewed_identity,
        'scope': f"{layer['season']} carrier {carrier_id} XI only; live states and on-screen phase averages, not a claim of match behaviour",
        'players': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--carrier-id', type=int, default=307)
    parser.add_argument('--header-review', type=Path)
    args = parser.parse_args()
    report = verify(args.candidate.resolve(), args.run.resolve(), args.carrier_id, header_review=args.header_review)
    # No silent replacement of evidence from another run.
    with args.output.open('x') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({'success': report['success'], 'named_player_phases_checked': report['named_player_phases_checked']}))


if __name__ == '__main__':
    main()
