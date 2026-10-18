#!/usr/bin/env python3
"""Freeze additional original-source reviews without overwriting old evidence."""
import argparse
import collections
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_targeted_soccerbase_opening_replay_v1 as targeted
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import prepare_duplicate_club_disposition_v1 as whole


def extend(plan_path, capture_root, output):
    if output.exists(): raise ValueError('source review is immutable; use a new output')
    plan = json.loads(plan_path.read_text()); bindings = plan['bindings']; pin = bindings['snapshot']
    people, events, actual_pin = context.load_snapshot(ROOT/pin['path'], ROOT/pin['pinned_receipt_path'])
    if actual_pin != pin: raise ValueError('original person snapshot binding changed')
    people, events, _ = public.merge_bound(people, events, bindings)
    previous = bindings['soccerbase_opening_sources']['review']
    path = ROOT/previous['path']
    if registry.sha256_file(path) != previous['sha256']: raise ValueError('original source review changed')
    document = copy.deepcopy(json.loads(path.read_text()))
    if (document['snapshot_binding'] != pin
            or document['published_person_binding'] != bindings['published_person_supplement']):
        raise ValueError('original review uses different person inputs')
    by_season = {s['season']: s for s in document['seasons']}
    clubs_by_season = {}; added = []; refused = []
    # Snapshot completed files now: later collector writes do not alter this review.
    selected = sorted(capture_root.glob('*/*/capture.json'))
    for path in selected:
        binding = {'path': registry.relative_workspace_path(path),
            'sha256': registry.sha256_file(path), 'policy': targeted.POLICY}
        saved = targeted.read_capture(binding); season = saved['target']['season']
        section = by_season[season]
        previous_rows = [r for r in section['clubs'] if whole.club_keys(r['club']) & whole.club_keys(saved['target']['club'])]
        complete = [r for r in previous_rows if r.get('status') == 'original-first-fixture-reparsed'
            and all(len(r.get('identity_bridges', {}).get(field, [])) == len(r.get('original_match', {}).get(field, []))
                for field in ('starting_xi', 'published_bench'))
            and len(r.get('identity_bridges', {}).get('starting_xi', [])) == 11]
        if complete: continue  # Retain the exact already-complete historical source.
        try:
            row = targeted.replay_capture(binding, season, people)
            if season not in clubs_by_season:
                release = registry.load_preferred_release(season)
                clubs_by_season[season] = {c['id']: c for _, package, _ in planner.package_layers(release) for c in package['clubs']}
            represented = []
            for id in saved['target']['native_club_ids']:
                club = clubs_by_season[season][id]
                if not whole.club_keys(club['name'], club.get('full_name', '')) & whole.club_keys(saved['target']['club']):
                    raise ValueError('targeted source no longer matches current native carrier identity')
                represented.append({'club_id': id, 'carrier_id': club['carrier_id'], 'club': club['name']})
            row['represented_native_clubs'] = represented
            section['clubs'] = [r for r in section['clubs'] if r not in previous_rows] + [row]
            added.append({'season': season, 'club': row['club'], 'binding': binding,
                'source_provider_bridges': sum(p['transfermarkt_person'] is not None for ps in row['identity_bridges'].values() for p in ps)})
            print(json.dumps({'source_review_added': season, 'club': row['club']}), flush=True)
        except (ValueError, OSError, KeyError) as exc:
            refused.append({'path': str(path), 'reason': str(exc)})
    if not added: raise ValueError('no stronger missing original sources to publish')
    counts = collections.Counter()
    for section in document['seasons']:
        for row in section['clubs']:
            counts[row['status']] += 1
            if row['status'] == 'original-first-fixture-reparsed':
                counts['published-XI-people'] += len(row['original_match']['starting_xi'])
                counts['independently-identified-XI-people'] += len(row['identity_bridges']['starting_xi'])
                counts['unique-provider-identity-bridges'] += sum(p['transfermarkt_person'] is not None
                    for ps in row['identity_bridges'].values() for p in ps)
                counts['identity-gaps'] += len(row['identity_gaps'])
    document['summary'] = dict(counts)
    document['targeted_original_extension'] = {'policy': targeted.POLICY,
        'previous_review': previous, 'selected_capture_count': len(selected), 'added': added, 'refused': refused,
        'native_writes': 0, 'recipes_modified': 0, 'historical_ownership_approved': False}
    pipeline.write_canonical_json(output, document)
    print(json.dumps({'added_original_club_seasons': len(added), 'refused': len(refused), 'output': str(output)}), flush=True)
    return document


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--capture-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); extend(a.plan, a.capture_root, a.output)
