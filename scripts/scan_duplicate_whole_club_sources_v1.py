#!/usr/bin/env python3
"""Find complete source-only whole-club fits, without network/game writes.

Reuse the pinned people/history snapshot within this process, rehash it at
completion, and retain every rejection. No diagnostic may publish natively.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import inventory_duplicate_club_dispositions_v1 as inventory
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_same_carrier_name_capacity_v1 as capacity


def source_gap_scope(reason, fixed_capacity):
    """Reuse only failures proved independent of which old carrier is chosen."""
    if reason == 'Soccerbase club identity lacks two consistent dated starter ownership brackets':
        return ('club-original-identity',)
    if reason.startswith('fixed capacity lacks ') and reason.endswith(' positively dated opening reserves'):
        return ('opening-reserve-evidence', fixed_capacity)
    return None


def explicit_matchday_route(enabled,fit_reserve_pool=False):
    if fit_reserve_pool and not enabled:
        raise ValueError('reserve-pool exploration requires explicit matchday/career authority')
    return (dict(allow_original_matchday_only_club_identity=True,
        allow_original_provider_career_reserves=True,fit_verified_reserve_pool=fit_reserve_pool) if enabled else {})


def complete_without_outside_copies(decision):
    return decision.get('status')=='complete-source-fit' and decision.get('outside_collisions')==[]


class BoundSnapshotCache:
    def __init__(self):
        self.loaded = {}
        self.public = {}
        self.public_files = {}

    def load(self, database, receipt):
        key = (database.resolve(), receipt.resolve())
        if key not in self.loaded:
            self.loaded[key] = context.load_snapshot(database, receipt)
        return self.loaded[key]

    def verify(self):
        for (database, receipt), (_, _, binding) in self.loaded.items():
            if (whole.registry.sha256_file(database), whole.registry.sha256_file(receipt)) != (
                    binding['sha256'], binding['pinned_receipt_sha256']):
                raise ValueError('source-only scan snapshot changed during cached decisions')
        for path, digest in self.public_files.items():
            if whole.registry.sha256_file(path) != digest:
                raise ValueError('source-only scan public original changed during cached decisions')

    def merge_public(self, people, events, bindings):
        key = (id(people), id(events), json.dumps(bindings, sort_keys=True))
        if key not in self.public:
            # The ordinary reader independently reparses every original before
            # caching. Freeze each original and URL receipt for final rehash.
            documents = []
            for label in ('published_person_supplement', 'published_transfer_supplement'):
                item = bindings[label]
                path = ROOT / item['path']
                if whole.registry.sha256_file(path) != item['sha256']:
                    raise ValueError('cached public supplement differs from its binding')
                self.public_files[path] = item['sha256']
                documents.append(json.loads(path.read_text()))
            for document in documents:
                for row in document.get('batches', document.get('players', [])):
                    if 'raw_sha256' not in row:
                        continue
                    path = ROOT / row['raw_path']
                    self.public_files[path] = row['raw_sha256']
                    path = ROOT / row['source_receipt_path']
                    self.public_files[path] = whole.registry.sha256_file(path)
            self.public[key] = whole.public.merge_bound(people, events, bindings)
        return self.public[key]


def scan(prior_root, capacity_root, output, seasons, capacity_fallback_plan=None, *,
         matchday_career_route=False, first_fit_per_target=False,fit_verified_reserve_pool=False):
    if (output / 'summary.json').exists():
        raise ValueError('completed source scan must not be repeated')
    output.mkdir(parents=True,exist_ok=True)
    route=explicit_matchday_route(matchday_career_route,fit_verified_reserve_pool)
    scan_policy=dict(route=route,first_fit_per_target=first_fit_per_target)
    cache = BoundSnapshotCache()
    outcomes = []
    for season in seasons:
        if season == '2015-16':
            continue  # Original legacy/English overlay has a separate route.
        release = whole.registry.load_preferred_release(season)
        layers = whole.planner.package_layers(release)
        captures, _ = whole.roster.load_sources(season)
        duplicates, targets = inventory.candidates([c for _, p, _ in layers for c in p['clubs']], captures)
        if matchday_career_route:
            duplicates=sorted(duplicates,key=lambda c:(c['fixed_capacity'],c['carrier_id']))
        prior_path = prior_root / season / 'ownership-plan.json'
        prior = json.loads(prior_path.read_text())
        bindings = prior['bindings']
        cap_path = capacity_root / season / 'ownership-plan.json'
        bundle = json.loads(cap_path.read_text())['bindings'].get('same_carrier_name_capacity')
        if bundle is None:
            if capacity_fallback_plan is None:
                raise ValueError('explicit capacity fallback plan required for a zero-update season')
            cap_path = capacity_fallback_plan
            bundle = json.loads(cap_path.read_text())['bindings']['same_carrier_name_capacity']
        capacity.verify_bundle(bundle)
        for target in targets:
            shared_gaps = {}
            for duplicate in duplicates:
                if shutil.disk_usage(ROOT).free < 8 * 1024 ** 3:
                    raise ValueError('8-GiB source scan reserve reached; completed decisions retained')
                carrier = duplicate['carrier_id']
                target_key = whole.roster.normalise(target['club'])
                path = output / season / f'{carrier}-{target_key}.json'
                decision = path.with_name(path.stem + '-decision.json')
                if decision.exists():
                    saved = json.loads(decision.read_text())
                    if (matchday_career_route or first_fit_per_target) and saved.get('source_scan_policy')!=scan_policy:
                        raise ValueError('saved source scan used another explicit route; preserve it')
                    if (saved['baseline_package_sha256'] != whole.registry.sha256_file(release.package_path)
                            or saved['prior_plan_sha256'] != whole.registry.sha256_file(prior_path)
                            or saved['capacity_plan_sha256'] != whole.registry.sha256_file(cap_path)):
                        raise ValueError('saved source-scan decision has a changed baseline')
                    if saved.get('proposal_path') and whole.registry.sha256_file(ROOT / saved['proposal_path']) != saved['proposal_sha256']:
                        raise ValueError('saved source-scan proposal changed')
                    outcomes.append(saved)
                    scope = source_gap_scope(saved.get('reason') or '', duplicate['fixed_capacity'])
                    if saved['status'] == 'source-gap' and scope:
                        shared_gaps[scope] = (saved, decision)
                    if first_fit_per_target and complete_without_outside_copies(saved):
                        break
                    continue
                result = {'season': season, 'carrier_id': carrier, 'target': target['club'],
                    'baseline_release_id': release.release_id,
                    'baseline_package_sha256': whole.registry.sha256_file(release.package_path),
                    'prior_plan_path': whole.registry.relative_workspace_path(prior_path),
                    'prior_plan_sha256': whole.registry.sha256_file(prior_path),
                    'capacity_plan_path': whole.registry.relative_workspace_path(cap_path),
                    'capacity_plan_sha256': whole.registry.sha256_file(cap_path),
                    'native_writes': 0, 'publication_authorised': False}
                if matchday_career_route or first_fit_per_target:
                    result['source_scan_policy']=scan_policy
                reuse = next((shared_gaps[key] for key in (
                    ('club-original-identity',), ('opening-reserve-evidence', duplicate['fixed_capacity']))
                    if key in shared_gaps), None)
                if reuse:
                    saved, source = reuse
                    result.update(status='source-gap', reason=saved['reason'],
                        same_target_source_gap_not_reparsed={'path': whole.registry.relative_workspace_path(source),
                            'sha256': whole.registry.sha256_file(source)})
                    whole.pipeline.write_canonical_json(decision, result)
                    outcomes.append(result)
                    continue
                try:
                    if not path.exists():
                        whole.prepare(season, carrier, target['club'],
                            ROOT / bindings['published_person_supplement']['path'],
                            ROOT / bindings['published_transfer_supplement']['path'],
                            ROOT / bindings['soccerbase_opening_sources']['club_entities']['path'], path,
                            capacity_bundle=bundle, baseline_release_id=release.release_id,
                            inspect_collisions=True, snapshot_binding=bindings['snapshot'],
                            allow_keeper_order_exchange=True, snapshot_loader=cache.load,
                            public_loader=cache.merge_public,**route)
                    proposal = json.loads(path.read_text())
                    if (proposal['schema_version'] != 'pm99-whole-club-collision-diagnostic-only-v1'
                            or proposal['release_id'] != release.release_id
                            or proposal['package_sha256'] != result['baseline_package_sha256']
                            or proposal['new_club'] != target['club']
                            or proposal['before_club']['carrier_id'] != carrier
                            or proposal.get('capacity_policy_bundle') != bundle):
                        raise ValueError('completed diagnostic has a changed whole-club scan binding')
                    result.update(status='allocation-gap' if proposal['allocation_gap'] else 'complete-source-fit',
                        reason=proposal['allocation_gap'],
                        outside_collisions=proposal['outside_collisions'],
                        proposal_path=whole.registry.relative_workspace_path(path),
                        proposal_sha256=whole.registry.sha256_file(path))
                except (ValueError, OSError) as exc:
                    result.update(status='source-gap', reason=str(exc))
                whole.pipeline.write_canonical_json(decision, result)
                outcomes.append(result)
                scope = source_gap_scope(result.get('reason') or '', duplicate['fixed_capacity'])
                if result['status'] == 'source-gap' and scope:
                    shared_gaps[scope] = (result, decision)
                print(json.dumps({k: result[k] for k in ('season', 'carrier_id', 'target', 'status', 'reason')}), flush=True)
                if first_fit_per_target and complete_without_outside_copies(result):
                    break
    cache.verify()
    summary = {'schema_version': 'pm99-source-only-whole-club-fit-scan-v1',
        'native_writes': 0, 'network_requests': 0, 'publication_authorised': False,
        'scope': 'complete original XI/dated reserves and owned mode1 keeper exchange; NOT playable delivery',
        'outcome_counts': dict(Counter(r['status'] for r in outcomes)), 'decisions': outcomes}
    if matchday_career_route or first_fit_per_target:
        summary['source_scan_policy']=scan_policy
    whole.pipeline.write_canonical_json(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prior-root', 'capacity-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seasons', nargs='+', default=whole.registry.supported_seasons())
    parser.add_argument('--capacity-fallback-plan', type=Path,
        help='Explicit factory/runtime-proved capacity policy for zero-update seasons')
    parser.add_argument('--matchday-career-route',action='store_true',
        help='Use existing positive complete-matchday identity and dated-career-reserve policies; never infer membership')
    parser.add_argument('--first-fit-per-target',action='store_true',
        help='Stop exploring alternative carriers only after a complete fit with zero outside collisions')
    parser.add_argument('--fit-verified-reserve-pool',action='store_true',
        help='Explicit alternative-pool exploration; not required for an already capacity-fitting matchday roster')
    args = parser.parse_args()
    scan(args.prior_root, args.capacity_root, args.output, args.seasons, args.capacity_fallback_plan,
         matchday_career_route=args.matchday_career_route,first_fit_per_target=args.first_fit_per_target,
         fit_verified_reserve_pool=args.fit_verified_reserve_pool)
