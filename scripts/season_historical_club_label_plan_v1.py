#!/usr/bin/env python3
"""Plan source-row-bound club labels and paired, exclusively owned coaches.

No players, ratings, grounds, kits, membership or carrier selections change.
Ambiguous target-club or coach ownership is left in the review queue.
"""
import argparse
import collections
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from app.editor_actions import _read_eq_inline_string, _patch_indexed_eq_team_string_payload
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_source_package_builder_v1 as builder
from scripts import season_package_compiler_v2 as compiler
from scripts import season_historical_club_label_review_v1 as review
from scripts import season_historical_club_label_full_cohort_optin_v2 as full_cohort_optin
from scripts.season_historical_roster_audit_v1 import club_group
from scripts.build_2015_english92_release import _rebuild_indexed

SCHEMA = 'pm99-historical-club-label-plan-v1'


def prefix_parts(payload):
    marker = payload.find(b'\xdd\x63\x61')
    if marker < 2: raise ValueError('missing indexed club string prefix')
    short, _, end = _read_eq_inline_string(payload, marker + 4)
    stadium, _, ground_end = _read_eq_inline_string(payload, end)
    full, _, full_end = _read_eq_inline_string(payload, ground_end + 2)
    return short, full, (payload[:marker - 2], payload[marker:marker + 4],
        payload[end:ground_end + 2], payload[full_end:])


def rewrite_club_labels(data, updates):
    indexed = IndexedFDIFile.from_bytes(data)
    entries = {e.record_id: e for e in indexed.entries}
    replacements, changes = {}, []
    for row in updates:
        id = row['carrier_id']
        if id in replacements: raise ValueError('duplicate club label carrier')
        old = entries[id].decode_payload(data)
        short, full, preserved = prefix_parts(old)
        if (short, full) != (row['native_before'], row['native_full_before']):
            raise ValueError('club native label before-state changed')
        new, fields = _patch_indexed_eq_team_string_payload(old,
            short_name=row['native_after'], full_club_name=row['native_after'])
        if set(fields) - {'name', 'full_club_name'} or prefix_parts(new)[2] != preserved:
            raise ValueError('club label delta changed ground, control or non-name tail')
        if prefix_parts(new)[:2] != (row['native_after'], row['native_after']):
            raise ValueError('club label native readback failed')
        replacements[id] = new
        if new != old: changes.append({'carrier_id': id, 'before': short, 'full_before': full,
            'after': row['native_after'], 'fields': fields})
    result = _rebuild_indexed(data, indexed, replacements)
    for entry in IndexedFDIFile.from_bytes(result).entries:
        if entry.decode_payload(result) != replacements.get(entry.record_id, entries[entry.record_id].decode_payload(data)):
            raise ValueError('club label delta changed unrelated decoded EQ record')
    return result, changes


def plan(season, audit_path, *, source_release_id=None):
    release = (registry.load_registered_release(season, source_release_id)
        if source_release_id is not None else registry.load_preferred_release(season))
    package = json.loads(release.package_path.read_text()); audit = json.loads(audit_path.read_text())
    binding = audit['bindings']
    if audit['schema_version'] != review.SCHEMA or audit['season'] != season:
        raise ValueError('wrong club label source audit')
    if tuple(binding.get(k) for k in ('release_id', 'package_sha256', 'eq_sha256', 'ent_sha256')) != (
            release.release_id, registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI')):
        raise ValueError('club label audit is stale')
    clubs = {c['id']: c for c in package['clubs']}; managers = {m['id']: m for m in package['managers']}
    candidates = {}
    for row in audit['clubs']:
        if row['status'] == 'source-supported-club-label-mismatch':
            candidates[row['club_id']] = row
        elif row['status'] == 'source-supported-full-cohort-club-label-mismatch':
            full_cohort_optin.verify_manager_sources(row)
            witness = row.get('full_cohort_witness')
            if not isinstance(witness, dict) or row.get('identity_basis') != 'complete_source_bound_roster_cohort':
                raise ValueError('opt-in full-cohort row lacks typed identity witness')
            bound_preallocation = ROOT / witness['preallocation_path']
            source_root = bound_preallocation.parent.parent
            full_cohort_optin.verify_witness(witness, source_root=source_root)
            if (witness['release_id'], witness['package_sha256'], witness['eq_sha256']) != (
                    release.release_id, registry.sha256_file(release.package_path),
                    registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI')):
                raise ValueError('full-cohort witness is stale for selected release')
            if row['club_id'] in candidates:
                raise ValueError('duplicate label review row')
            candidates[row['club_id']] = row
    unresolved = []
    # Reject collisions repeatedly: rejecting one rename restores its original
    # name and can expose a second conflict elsewhere. Never guess a winner.
    while True:
        groups = collections.defaultdict(list)
        for club in package['clubs']:
            target = candidates.get(club['id'], {}).get('after', club['name'])
            groups[(club_group(club), builder._normalise_club_name(target))].append(club['id'])
        rejected = {id for ids in groups.values() if len(ids) > 1 for id in ids if id in candidates}
        for id, row in candidates.items():
            manager = managers.get(clubs[id].get('manager_id'))
            if (not row.get('manager_after') or row['native_manager_owner_count'] != 1 or
                    manager is None or manager['carrier_id'] != row['native_manager_carrier_id']):
                rejected.add(id)
        coach_names = collections.defaultdict(list)
        for club in package['clubs']:
            manager = managers.get(club.get('manager_id'))
            name = candidates.get(club['id'], {}).get('manager_after', manager['name'] if manager else '')
            if name: coach_names[builder._normalise_club_name(name)].append(club['id'])
        rejected |= {id for ids in coach_names.values() if len(ids) > 1 for id in ids if id in candidates}
        if not rejected: break
        for id in sorted(rejected):
            row = candidates.pop(id)
            unresolved.append({'club_id': id, 'before': row['before'], 'after': row['after'],
                'reason': 'ambiguous target club/coach or non-exclusive native manager owner'})
    data = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(data).entries}
    updates, paired = [], []
    for id, row in sorted(candidates.items()):
        club = clubs[id]; manager = managers[club['manager_id']]
        short, full, _ = prefix_parts(entries[club['carrier_id']].decode_payload(data))
        if builder._normalise_club_name(short) != builder._normalise_club_name(compiler._pm99_text(club['name'], label='existing club name')):
            unresolved.append({'club_id': id, 'reason': 'recipe club name differs from native before state',
                'recipe_name': club['name'], 'native_name': short}); continue
        try:
            target = compiler._pm99_text(row['after'], label='sourced club name')
            coach = compiler._pm99_text(row['manager_after'], label='sourced coach name')
            update = {**row, 'before_full': club.get('full_name'),
                'identity_after': builder._source_club_identity_id(club_group(club), row['after']),
                'native_before': short, 'native_full_before': full, 'native_after': target}
            rewrite_club_labels(data, [update])
        except (ValueError, UnicodeError) as exc:
            unresolved.append({'club_id': id, 'reason': str(exc)}); continue
        updates.append(update)
        paired.append({'club_id': id, 'club_carrier_id': club['carrier_id'], 'club': row['after'],
            'manager_id': manager['id'], 'carrier_id': manager['carrier_id'],
            'before': manager['name'], 'before_policy': manager.get('policy'), 'native_before': row['native_manager'],
            'after': row['manager_after'], 'native_after': coach, 'first_fixture_date': row['evidence']['date'],
            'evidence': row['evidence'], 'native_manager_owner_count': 1})
    # A refused string rewrite restores the old label. Recheck collisions
    # against that final state, not just the preliminary candidate set.
    while True:
        targets = {r['club_id']: r['after'] for r in updates}
        groups = collections.defaultdict(list)
        for club in package['clubs']:
            groups[(club_group(club), builder._normalise_club_name(targets.get(club['id'], club['name'])))].append(club['id'])
        rejected = {id for ids in groups.values() if len(ids) > 1 for id in ids if id in targets}
        if not rejected: break
        unresolved.extend({'club_id': id, 'reason': 'target label conflicts after an unsafe rewrite was refused'} for id in sorted(rejected))
        updates = [r for r in updates if r['club_id'] not in rejected]
        paired = [r for r in paired if r['club_id'] not in rejected]
    # Retain valid existing coach evidence, rebased to this exact native recipe.
    prior_path = release.package_path.parent / 'manager-plan.json'
    paired_ids = {r['club_id'] for r in paired}
    if prior_path.exists():
        for old in json.loads(prior_path.read_text())['updates']:
            if old['club_id'] in paired_ids: continue
            manager = managers.get(old['manager_id'])
            if manager is None or manager['name'] != old['after']: continue
            row = copy.deepcopy(old)
            row.update(before=manager['name'], before_policy=manager.get('policy'), native_before=old['native_after'])
            paired.append(row)
    common = {'season': season, **{k: binding[k] for k in ('release_id', 'package_sha256', 'eq_sha256', 'ent_sha256')},
        'audit_path': registry.relative_workspace_path(audit_path), 'audit_sha256': registry.sha256_file(audit_path),
        'historical_verification_complete': False}
    return ({**common, 'schema_version': SCHEMA, 'source_bindings': binding, 'updates': updates, 'unresolved': unresolved},
        {**common, 'schema_version': 'pm99-historical-manager-plan-v1', 'updates': paired, 'unresolved': [],
            'summary': {'source_verified_exclusive_managers': len(paired),
                'native_name_corrections': sum(r['native_before'] != r['native_after'] for r in paired)}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--audit-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        audit = args.audit_root / season / 'club-label-review.json'
        if json.loads(audit.read_text())['summary'].get('source_unavailable'): continue
        binding = json.loads(audit.read_text())['bindings']
        if registry.load_preferred_release(season).release_id != binding['release_id']:
            print(json.dumps({'season': season, 'skipped': 'audit describes a superseded release; do not replay its repairs'}), flush=True)
            continue
        saved = args.output / season / 'club-plan.json'
        if saved.exists():
            existing = json.loads(saved.read_text())
            if (existing['source_bindings'] != binding or existing['audit_sha256'] != registry.sha256_file(audit) or
                    not all((saved.parent / (name + '.json')).exists() for name in ('manager-plan', 'role-plan'))):
                raise ValueError('saved club plan is stale or incomplete')
            print(json.dumps({'season': season, 'existing_plan_reused': True, 'club_names': len(existing['updates'])}), flush=True)
            continue
        clubs, managers = plan(season, audit)
        release = registry.load_preferred_release(season)
        control = {'season': season, 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'updates': [], 'unresolved': []}
        destination = args.output / season; destination.mkdir(parents=True, exist_ok=True)
        for name, document in [('club-plan', clubs), ('manager-plan', managers), ('role-plan', control)]:
            path = destination / (name + '.json')
            if path.exists(): raise ValueError('plan already exists; never overwrite')
            pipeline.write_canonical_json(path, document)
        print(json.dumps({'season': season, 'club_names': len(clubs['updates']),
            'manager_names': managers['summary']['native_name_corrections'], 'unresolved': len(clubs['unresolved'])}), flush=True)


if __name__ == '__main__': main()
