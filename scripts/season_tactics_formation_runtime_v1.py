#!/usr/bin/env python3
"""Resume genuine, per-shape game captures through the leased runner wrapper.

One club per formation is sampled. This never claims every club/season has
been played, and it never edits or publishes a game. Existing passed samples
are reverified without relaunching them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.player_initial_order import read_initial_order
from app.fdi_indexed import IndexedFDIFile
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_contextual_tactics_rollout_v1 as rollout
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.verify_contextual_tactics_runtime_v1 import verify

SAMPLES = [
    ('4-4-2', '2015-16', 301, 'Bournemouth', 'tactics_rollout_bournemouth_2015_16_20261005_h'),
    ('4-3-3', '2015-16', 304, 'Sunderland', 'tactics_rollout_sunderland_2015_16_20261005_i'),
    ('4-2-3-1', '2015-16', 302, 'Liverpool', 'tactics_rollout_liverpool_2015_16_20261005_e'),
    ('4-1-4-1', '2015-16', 307, 'Stoke City', None),
    ('5-4-1', '2000-01', 301, 'Bradford City', None),
    ('5-3-2', '2015-16', 336, 'Huddersfield Town', None),
    ('4-5-1', '2000-01', 303, 'Charlton Athletic', None),
    ('5-2-3', '2000-01', 306, 'Ipswich Town', None),
    ('3-5-2', '2015-16', 353, 'Bristol City', None),
    ('3-4-3', '2001-02', 317, 'Southampton', None),
    ('4-1-3-2', '2005-06', 312, 'Chelsea', None),
    ('4-4-1-1', '2015-16', 303, 'Norwich City', None),
    ('4-3-1-2', '2015-16', 314, 'West Ham United', None),
    ('3-4-1-2', '2007-08', 333, 'Wigan Athletic', None),
    ('3-4-2-1', '2016-17', 302, 'Everton', None),
    ('3-1-4-2', '2017-18', 310, 'Manchester City', None),
    ('4-3-2-1', '2018-19', 316, 'Tottenham Hotspur', None),
    ('4-1-2-1-2', '2015-16', 360, 'Oldham Athletic', None),
]

# A/B stayed on championship setup; C reached a Shield-result modal. D adds
# positively classified modal handling. All failed captures remain retained.
RETRY_TAGS = {'3-4-2-1': 'tactics_shape_3_4_2_1_2016_17_20261005_d',
              '4-3-2-1': 'tactics_shape_4_3_2_1_2018_19_20261005_b'}


def selector(english, club):
    division = club['division']
    buttons = {'Premier League': (77, 302), 'Championship': (77, 337),
               'League One': (559, 302), 'League Two': (559, 337)}
    if division not in buttons:
        raise ValueError('unreviewed native division selector')
    peers = sorted([c for c in english['clubs'] if c['division'] == division], key=lambda c: c['name'].casefold())
    if len(peers) not in (20, 24):
        raise ValueError('unreviewed native club-grid size')
    rank = next(i for i, c in enumerate(peers) if c['carrier_id'] == club['carrier_id'])
    columns, step = (10, 31) if len(peers) == 20 else (12, 26)
    return {'division': buttons[division], 'team': (178 + (rank % columns) * step, 323 if rank < columns else 360),
            'basis': 'alphabetical native division grid; actual header and pitch pixels must still independently pass'}


def sample_one(sample, *, worker, root):
    formation, season, carrier, name, previous_run = sample
    parent = root / season
    if previous_run:
        candidate = parent / 'english-rollout-candidate-v1'
        tag = previous_run
    else:
        candidate = parent / 'english-rollout-candidate-v3'
        if not candidate.exists():
            candidate = parent / 'english-rollout-candidate-v1'
        tag = RETRY_TAGS.get(formation, f"tactics_shape_{formation.replace('-', '_')}_{season.replace('-', '_')}_20261005_a")
    layer = json.loads((candidate / 'contextual-tactics.json').read_text())
    row = next(c for c in layer['clubs'] if c['carrier_id'] == carrier)
    if row['formation'] != formation or row['name'] != name:
        raise ValueError('formation sample identity differs from frozen candidate')
    receipt = json.loads((candidate / 'candidate-receipt.json').read_text())
    english = json.loads((candidate / 'english-season-package.json').read_text())
    club = next(c for c in english['clubs'] if c['carrier_id'] == carrier)
    coords = selector(english, club)
    run = ROOT / '.local/runlogs/pm99_runner' / tag
    proof_path = root / 'formation-runtime-proofs-v2' / (formation + '.json')
    if not (run / 'summary.json').exists():
        if run.exists():
            raise ValueError('incomplete/failed run is retained; investigate rather than blindly relaunch: ' + str(run))
        if previous_run:
            raise ValueError('previous runtime sample is missing')
        command = [str(ROOT / 'scripts/run_pm99_experiment.sh'), 'route-capture', '--worker', worker,
            '--run-tag', tag, '--allow-dirty-runner', '--', '--skip-setup', '--skip-prepare', '--skip-build',
            '--dbdat-dir', str(candidate / 'DBDAT'), '--exe-file', receipt['exe_path'],
            '--manager-name', 'AI', '--team-name', name,
            '--team-select-x', str(coords['team'][0]), '--team-select-y', str(coords['team'][1]),
            '--division-select-x', str(coords['division'][0]), '--division-select-y', str(coords['division'][1]),
            '--profile-count', '0', '--capture-route', 'tactics', '--tactics-advanced-inspect',
            '--tactics-advanced-matrix', '--tactics-native-state-proof', str(carrier),
            '--tactics-advanced-view', 'general', '--skip-screen-classification']
        env = dict(os.environ, PM99_RUNNER_ARCHIVE_COLD_RUNS='0', PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    review = root / 'formation-header-reviews-v1' / (tag + '.json')
    proof = verify(candidate, run, carrier, header_review=review if review.is_file() else None)
    launch = json.loads((run / 'control_launch.json').read_text())['child_command']
    def argument(flag):
        return launch[launch.index(flag) + 1]
    if (Path(argument('--dbdat-dir')).resolve() != (candidate / 'DBDAT').resolve() or
            registry.sha256_file(Path(argument('--exe-file'))) != registry.sha256_file(Path(receipt['exe_path']))):
        raise ValueError('formation proof does not bind the season database and executable')
    proof.update({'candidate_path': str(candidate), 'run_path': str(run),
                  'candidate_eq_sha256': registry.sha256_file(candidate / 'DBDAT/EQ98030.FDI'),
                  'candidate_jug_sha256': registry.sha256_file(candidate / 'DBDAT/JUG98030.FDI'),
                  'season_exe_sha256': registry.sha256_file(Path(receipt['exe_path'])),
                  'selector': coords, 'season': season, 'registered': False})
    if proof_path.exists():
        frozen = json.loads(proof_path.read_text())
        frozen.setdefault('header_visual_review', None)
        if pipeline.canonical_json_bytes(frozen) != pipeline.canonical_json_bytes(proof):
            raise ValueError('frozen formation proof differs on replay')
    else:
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(proof_path, proof)
    return proof


def verify_coverage(root, candidates):
    """Bind sampled shapes to their unchanged named deployment in final inputs.

    A source sample may precede unrelated club/bench repairs. Such transfer is
    permitted only when its exact selected club grid, named XI, recipe context
    and per-player startup values are unchanged; it is explicitly derived, not
    a claim the new whole database was launched in that earlier run.
    """
    proven = {}
    for path in (root / 'formation-runtime-proofs-v2').glob('*.json'):
        stored = json.loads(path.read_text())
        candidate, run = Path(stored['candidate_path']), Path(stored['run_path'])
        review = stored.get('header_visual_review')
        proof = verify(candidate, run, stored['carrier_id'], header_review=Path(review['path']) if review else None)
        if pipeline.canonical_json_bytes(proof) != pipeline.canonical_json_bytes({k: stored.get(k) for k in proof}):
            raise ValueError('formation runtime evidence changed')
        launch = json.loads((run / 'control_launch.json').read_text())['child_command']
        exe = Path(launch[launch.index('--exe-file') + 1])
        if (registry.sha256_file(candidate / 'DBDAT/EQ98030.FDI') != stored['candidate_eq_sha256'] or
                registry.sha256_file(candidate / 'DBDAT/JUG98030.FDI') != stored['candidate_jug_sha256'] or
                registry.sha256_file(exe) != stored['season_exe_sha256']):
            raise ValueError('formation source database changed')
        final = candidates / stored['season'] / 'english-rollout-candidate-v3'
        before_layer = json.loads((candidate / 'contextual-tactics.json').read_text())
        after_layer = json.loads((final / 'contextual-tactics.json').read_text())
        before = next(c for c in before_layer['clubs'] if c['carrier_id'] == stored['carrier_id'])
        after = next(c for c in after_layer['clubs'] if c['carrier_id'] == stored['carrier_id'])
        cid = stored['carrier_id']
        old_eq = tactics.payloads((candidate / 'DBDAT/EQ98030.FDI').read_bytes())[cid]
        new_eq = tactics.payloads((final / 'DBDAT/EQ98030.FDI').read_bytes())[cid]
        if before['context'] != after['context'] or old_eq != new_eq:
            raise ValueError('formation sample deployment changed in final candidate')
        def xi(folder):
            jug = (folder / 'DBDAT/JUG98030.FDI').read_bytes()
            return tactics.native_xi(new_eq, jug)
        expected_xi = [(s['native_player_id'], s['native_name']) for s in after['context']['slots']]
        if xi(candidate) != expected_xi or xi(final) != expected_xi:
            raise ValueError('formation sample native XI changed in final candidate')
        proven[stored['formation']] = {'sample_season': stored['season'], 'carrier_id': cid,
            'club': stored['club'], 'proof_path': str(path), 'proof_sha256': registry.sha256_file(path),
            'transfer': 'exact selected-club/context/XI preservation, not whole-DB runtime replay'}
    needed = set()
    for season in registry.supported_seasons():
        path = candidates / season / 'english-rollout-candidate-v3/contextual-tactics.json'
        needed.update(c['formation'] for c in json.loads(path.read_text())['clubs'])
    if needed - set(proven):
        raise ValueError('unproved formation families: ' + ', '.join(sorted(needed - set(proven))))
    return {'success': True, 'formation_families': sorted(needed), 'samples': proven,
            'scope': 'sampled club per formation; offline exact checks cover all 26 seasons, not gameplay for every club',
            'registered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', default='tiny-m73')
    parser.add_argument('--root', type=Path, default=ROOT / '.local/contextual-tactics-v1')
    parser.add_argument('--only', choices=rollout.FORMATIONS)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    if args.audit:
        report = verify_coverage(args.root.resolve(), args.root.resolve())
        print(json.dumps(report, indent=2))
        return
    for sample in SAMPLES:
        if args.only and sample[0] != args.only:
            continue
        proof = sample_one(sample, worker=args.worker, root=args.root.resolve())
        print(json.dumps({'formation': sample[0], 'season': sample[1], 'club': sample[3],
                          'success': proof['success'], 'named_player_phases_checked': 22}), flush=True)


if __name__ == '__main__':
    main()
