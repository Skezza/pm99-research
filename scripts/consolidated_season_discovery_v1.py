#!/usr/bin/env python3
"""Pin current releases and refresh compressed independent roster evidence.

Read-only for games/recipes/registrations. Findings are candidates, never
automatic historical corrections. Completed evidence cannot be overwritten.
"""
import argparse
import collections
import gzip
import json
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_historical_roster_audit_v1 as roster


def bindings():
    rows = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        row = {'season': season, 'release_id': release.release_id,
               'package_sha256': registry.sha256_file(release.package_path),
               'manifest_sha256': registry.sha256_file(release.release_manifest_path),
               'inventory_sha256': registry.sha256_file(release.inventory_path),
               'layers': []}
        for label, package, path in layers.package_layers(release):
            row['layers'].append({'label': label, 'path': str(path),
                                 'sha256': registry.sha256_file(path)})
        rows.append(row)
    return rows


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        stream.write('\n')


def run(output):
    snapshot = {'utc': datetime.now(timezone.utc).isoformat(),
                'machine': socket.gethostname(),
                'source_session': '01a0592d-fcd5-7262-a637-743a8253d9b4',
                'catalog_sha256': registry.sha256_file(registry.CATALOG_PATH),
                'rows': bindings()}
    snapshot_path = output / 'snapshot.json'
    if snapshot_path.exists():
        retained = json.loads(snapshot_path.read_text())
        if retained['rows'] != snapshot['rows'] or retained['catalog_sha256'] != snapshot['catalog_sha256']:
            raise ValueError('Cannot resume discovery against changed releases')
        snapshot = retained
    else:
        write_new(snapshot_path, snapshot)
    results = []
    for row in snapshot['rows']:
        # No game copies, downloads, or large uncompressed CSV exports.
        ram = output.resolve().is_relative_to(Path('/run/user'))
        reserve = 128 * 1024**2 if ram else 8 * 1024**3
        if shutil.disk_usage(output).free < reserve:
            raise RuntimeError('Discovery stopped before additional writes: evidence-store reserve breached')
        season = row['season']
        prior = ROOT / '.local/historical-authored-clubs-review-20261005-r1' / season / 'report.json'
        evidence = output / 'rosters' / season / 'report.json.gz'
        if not evidence.exists():
            roster.audit_season(season, output / 'rosters' / season,
                               prior if prior.is_file() else None, compressed=True)
        with gzip.open(evidence, 'rt') as stream:
            report = json.load(stream)
        assert report['bindings']['package_sha256'] == row['package_sha256']
        summary = {'season': season, **report['summary']}
        same_club = collections.defaultdict(list)
        for player in report['players']:
            key = (player['club_id'], roster.normalise(player.get('source_name') or player['name']),
                   player.get('birth_date'))
            if key[1] and isinstance(key[2], str) and key[2]:
                same_club[key].append(player)
        duplicates = [dict(club_id=k[0], identity=list(k[1:]),
                           players=[{'player_id': p['player_id'], 'name': p['name'],
                                     'carrier_id': p['carrier_id']} for p in values])
                      for k, values in sorted(same_club.items()) if len(values)>1]
        summary.update({'within_club_candidate_groups': len(duplicates),
                        'within_club_candidates': duplicates,
                        'evidence_path': str(evidence),
                        'evidence_sha256': registry.sha256_file(evidence)})
        results.append(summary)
        print(season, json.dumps({k:v for k,v in summary.items() if k not in
              ('within_club_candidates', 'evidence_path', 'evidence_sha256')}), flush=True)
    assert bindings() == snapshot['rows'], 'Current release bindings changed during discovery'
    assert registry.sha256_file(registry.CATALOG_PATH) == snapshot['catalog_sha256']
    totals = collections.Counter()
    for row in results:
        totals.update({k:v for k,v in row.items() if type(v) is int})
    write_new(output / 'roster-summary.json', {'rows': results, 'totals': dict(totals),
              'unchanged_release_bindings': True,
              'scope': 'Current native/source joins; whole-season sources do not prove August ownership. '
                       'Source-only conflicts and duplicate groups require adjudication.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
