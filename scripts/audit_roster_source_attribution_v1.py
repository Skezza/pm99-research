#!/usr/bin/env python3
"""Find mislabeled clubs from large, unique raw-source roster name cohorts.

Read-only candidate audit, not authority to rename a club or choose its manager.
DOB policies do not make real roster names disappear. Require eleven distinct
full-source-name matches and a unique best same-country source club identity.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def name(value):
    return transfer._normalise(re.sub(r'^#\d{1,2}\s+', '', value.strip()))


def attribution(club, players, sources, verifier):
    actual = {name(p.get('source_name') or p['name']) for p in players}
    group = roster.club_group(club)
    labels = roster.club_names(group, club['name'], club.get('full_name', ''))
    candidates = []
    for source in sources:
        if roster.source_group(source['country_catalog']) != group:
            continue
        captured = {name(p['name']) for p in source['players']}
        shared = actual & captured
        if len(shared) < 11:
            continue
        proof = verifier.verify(source)
        if proof['status'] != 'raw-source-reparsed':
            continue
        candidates.append({'source_club': source['club_name'], 'matched_full_names': len(shared),
            'matches': sorted(shared), 'raw_source': proof,
            'label_agrees': roster.normalise(source['club_name']) in labels})
    if not candidates:
        return {'status': 'no-eleven-name-independent-source-cohort', 'matches': []}
    maximum = max(c['matched_full_names'] for c in candidates)
    best = [c for c in candidates if c['matched_full_names'] == maximum]
    identities = {roster.normalise(c['source_club']) for c in best}
    if len(identities) != 1:
        status = 'ambiguous-best-source-club'
    elif any(c['label_agrees'] for c in best):
        status = 'large-raw-roster-cohort-agrees-with-club-label'
    else:
        status = 'mislabeled-club-candidate-needs-opening-and-manager-proof'
    return {'status': status, 'matches': best, 'roster_count': len(players),
            'unique_full_names': len(actual), 'game_change_authorised_by_audit': False}


def run(seasons, source_root, output):
    if output.exists():
        raise ValueError('attribution audit is immutable')
    results = []
    for season in seasons:
        release = registry.load_preferred_release(season)
        clubs, players, layers = {}, {}, []
        for label, package, path in planner.package_layers(release):
            clubs.update({c['id']: c for c in package['clubs']})
            players.update({p['carrier_id']: p for p in package['players']})
            layers.append({'layer': label, 'path': registry.relative_workspace_path(path),
                           'sha256': registry.sha256_file(path)})
        grouped = collections.defaultdict(list)
        for p in players.values():
            grouped[p['club_id']].append(p)
        captures, bindings = roster.load_sources(season)
        path = source_root / 'reviews' / season / 'report.json'
        if not path.exists():
            path = source_root / 'reviews' / season / 'roster-audit.json'
        verifier = roster.SourceVerifier(season, json.loads(path.read_text()), bindings)
        rows = [dict(attribution(c, grouped[c['id']], captures, verifier),
            club_id=c['id'], carrier_id=c['carrier_id'], club=c['name'],
            playable=c['id'].startswith(('english-club-', 'legacy-english-club-')))
            for c in clubs.values() if grouped[c['id']]]
        summary = dict(collections.Counter(r['status'] for r in rows))
        result = {'season': season, 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path), 'layers': layers,
            'source_bindings': bindings, 'review_path': registry.relative_workspace_path(path),
            'review_sha256': registry.sha256_file(path), 'summary': summary, 'clubs': rows}
        results.append(result)
        print(json.dumps(dict(summary, season=season)), flush=True)
    pipeline.write_canonical_json(output, {'schema_version': 'pm99-raw-roster-source-attribution-v1',
        'scope': 'same-country eleven-full-name candidate cohort, not independent DOB/ownership or manager clearance',
        'seasons': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(registry.supported_seasons() if args.season == 'all' else [args.season], args.source_root, args.output)
