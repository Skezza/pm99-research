#!/usr/bin/env python3
"""Revisit only failed source decisions with explicit two-provider DOB reviews.

Source-only: no network, native writes, publication or waivers. Reparse original
fixtures/annual biographies and bind the explicit review before allocation.
Already represented target clubs are excluded rather than built a second time.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import derive_provider_identity_resolutions_v1 as derivation
from scripts import scan_duplicate_whole_club_sources_v1 as scanner

whole = scanner.whole


def selected_decisions(prior):
    """No successful source fits or unchanged capacity failures are repeated."""
    return [row for row in prior['decisions'] if row.get('status') == 'source-gap'
        and ('birthday conflicts' in (row.get('reason') or '')
             or 'eleven identified players' in (row.get('reason') or ''))]


def represented(name, clubs):
    return any(whole.club_keys(name) & whole.club_keys(c['name'], c.get('full_name', ''))
               for c in clubs)


def original_decision(row):
    """Forward receipts retain their predecessors; find the original bindings."""
    while 'old_decision' in row:
        row = row['old_decision']
    return row


def original_review(season, club, bindings, cache, destination, *, exclude_unpublished_bench_birth_dates=False):
    snap = bindings['snapshot']
    people, events, actual_pin = cache.load(ROOT / snap['path'], ROOT / snap['pinned_receipt_path'])
    if actual_pin != snap:
        raise ValueError('original snapshot binding differs')
    people, events, _ = cache.merge_public(people, events, bindings)
    captures, _ = whole.roster.load_sources(season)
    keys = whole.club_keys(club)
    opening = [c for c in captures if c['source_path'].startswith('soccerbase/team/')
               and keys & whole.club_keys(c['club_name'])]
    annual = [c for c in captures if c['source_path'].endswith('.txt')
              and whole.roster.source_group(c['country_catalog']) == 'england'
              and keys & whole.club_keys(c['club_name'])]
    if len(opening) != 1 or len(annual) > 1:
        raise ValueError('explicit review requires unique original fixture/annual captures')
    actual = whole.replay.replay_club(season, opening[0], people, True, allow_missing_birth_date=True)
    facts = annual[0] if annual else {'players': []}
    raw = whole.roster.SourceVerifier(season).verify(facts) if annual else None
    if annual and raw['status'] != 'raw-source-reparsed':
        raise ValueError('annual facts do not independently reparse')
    document, gaps = derivation.derive(season, club, actual, facts, people,
        exclude_unpublished_bench_birth_dates=exclude_unpublished_bench_birth_dates)
    if gaps:
        raise ValueError('unresolved independent identity review: ' + json.dumps(gaps, sort_keys=True))
    destination.parent.mkdir(parents=True, exist_ok=True)
    whole.pipeline.write_canonical_json(destination, document)
    whole.pipeline.write_canonical_json(destination.with_name(destination.stem + '-receipt.json'), {
        'policy': derivation.POLICY, 'review_sha256': whole.registry.sha256_file(destination),
        'snapshot': snap, 'public_bindings': {k: bindings[k] for k in
            ('published_person_supplement', 'published_transfer_supplement')},
        'opening_capture': opening[0], 'annual_capture': annual[0] if annual else None,
        'annual_raw': raw, 'native_writes': 0, 'publication_authorised': False})
    return destination


def review(prior_path, output):
    if output.exists():
        raise ValueError('forward review output is immutable; do not rerun a completed review')
    output.mkdir(parents=True)
    prior = json.loads(prior_path.read_text())
    cache = scanner.BoundSnapshotCache()
    grouped = {}
    for row in selected_decisions(prior):
        grouped.setdefault((row['season'], row['target']), []).append(row)
    decisions = []
    for (season, club), attempts in grouped.items():
        release = whole.registry.load_preferred_release(season)
        clubs = [c for _, pkg, _ in whole.planner.package_layers(release) for c in pkg['clubs']]
        seed = original_decision(attempts[0])
        parent = json.loads((ROOT / seed['prior_plan_path']).read_text())
        if whole.registry.sha256_file(ROOT / seed['prior_plan_path']) != seed['prior_plan_sha256']:
            raise ValueError('prior source plan changed')
        bindings = parent['bindings']
        review_path = output / season / (whole.roster.normalise(club) + '-identity-review.json')
        error = None
        if represented(club, clubs):
            error = 'target club is already represented; no duplicate target build'
        else:
            try:
                original_review(season, club, bindings, cache, review_path)
            except (ValueError, OSError) as exc:
                error = str(exc)
        shared_source_gaps = {}
        for attempt in attempts:
            if shutil.disk_usage(ROOT).free < 8 * 1024**3:
                raise ValueError('8-GiB reserve reached; completed source decisions retained')
            old = original_decision(attempt)
            row = {'season': season, 'target': club, 'carrier_id': attempt['carrier_id'],
                'baseline_release_id': release.release_id,
                'baseline_package_sha256': whole.registry.sha256_file(release.package_path),
                'old_decision': attempt, 'native_writes': 0, 'publication_authorised': False}
            path = output / season / f'{attempt["carrier_id"]}-{whole.roster.normalise(club)}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            fixed_capacity = len(next(c for c in clubs if c['carrier_id']==attempt['carrier_id'])['roster_player_ids'])
            if error is not None:
                row.update(status='source-gap', reason=error)
            elif fixed_capacity in shared_source_gaps:
                saved, saved_path = shared_source_gaps[fixed_capacity]
                row.update(status='source-gap', reason=saved['reason'],
                    same_target_capacity_source_gap_not_reparsed={
                        'path':whole.registry.relative_workspace_path(saved_path),
                        'sha256':whole.registry.sha256_file(saved_path)})
            else:
                cap_path = ROOT / old['capacity_plan_path']
                if whole.registry.sha256_file(cap_path) != old['capacity_plan_sha256']:
                    raise ValueError('capacity source plan changed')
                bundle = json.loads(cap_path.read_text())['bindings']['same_carrier_name_capacity']
                try:
                    whole.prepare(season, attempt['carrier_id'], club,
                        ROOT / bindings['published_person_supplement']['path'],
                        ROOT / bindings['published_transfer_supplement']['path'],
                        ROOT / bindings['soccerbase_opening_sources']['club_entities']['path'], path,
                        capacity_bundle=bundle, baseline_release_id=release.release_id,
                        inspect_collisions=True, snapshot_binding=bindings['snapshot'],
                        allow_keeper_order_exchange=True, snapshot_loader=cache.load,
                        public_loader=cache.merge_public, identity_review_path=review_path,
                        allow_original_matchday_only_club_identity=True)
                    proposal = json.loads(path.read_text())
                    row.update(status='allocation-gap' if proposal['allocation_gap'] else 'complete-source-fit',
                        reason=proposal['allocation_gap'], outside_collisions=proposal['outside_collisions'],
                        proposal_path=whole.registry.relative_workspace_path(path),
                        proposal_sha256=whole.registry.sha256_file(path))
                except (ValueError, OSError) as exc:
                    row.update(status='source-gap', reason=str(exc))
            decisions.append(row)
            whole.pipeline.write_canonical_json(path.with_name(path.stem + '-decision.json'), row)
            if row['status']=='source-gap' and ((row['reason'] or '').startswith('fixed capacity lacks ')
                    or row['reason']=='matchday-only complete source lacks enough published opening bench places; dated reserves need a separate club bridge'):
                shared_source_gaps[fixed_capacity]=(row,path.with_name(path.stem+'-decision.json'))
            print(json.dumps({k: row[k] for k in ('season', 'target', 'carrier_id', 'status', 'reason')}), flush=True)
    cache.verify()
    result = {'schema_version': 'pm99-forward-failed-whole-club-source-review-v1',
        'prior_summary': {'path': whole.registry.relative_workspace_path(prior_path),
            'sha256': whole.registry.sha256_file(prior_path)},
        'policy': derivation.POLICY, 'network_requests': 0, 'native_writes': 0,
        'publication_authorised': False, 'distinct_club_years': len(grouped),
        'outcome_counts': dict(Counter(r['status'] for r in decisions)), 'decisions': decisions}
    whole.pipeline.write_canonical_json(output / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-summary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.prior_summary, args.output)
