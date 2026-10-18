"""Locate original duplicate people globally, including displaced/reordered slots.

This is a review index, not historical verification or authority to close cases.
English 2015 overlay supersedes matching native carriers in the main recipe.
"""
from collections import Counter
import argparse
from datetime import UTC, datetime
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_duplicate_ownership_plan_v1 import package_layers
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.season_frozen_fixture_reserve_v2 import heading_name


def name_key(name):
    return normalise(heading_name(name))


def observe(case, players, *, name_index=None):
    names = {name_key(p['source_name']) for p in case['players']}
    selected = (list(players) if name_index is None else
        [p for name in sorted(names) for p in name_index.get(name, [])])
    matches = [dict(carrier_id=p['carrier_id'], id=p['id'], club_id=p['club_id'],
        source_name=p.get('source_name') or p['name'],
        birth_date=p.get('facts', {}).get('birth_date')) for p in selected
        if name_key(p.get('source_name') or p['name']) in names]
    return dict(matches=matches, observation=(
        'multiple-current-name-matches' if len(matches) > 1 else
        'single-current-name-match-needs-source-proof' if matches else
        'no-current-name-match-needs-identity-review'))


def main(checklist_path):
    root = registry.ROOT / '.local/consolidated-audit-20261009'
    checklist = pipeline.read_json_file(checklist_path)
    frozen_path = registry.ROOT / checklist['cross_club_case_file']
    frozen = pipeline.read_json_file(frozen_path)
    closed = {row['case_id'] for row in checklist['cross_club_dispositions']}
    rows, bindings = [], []
    for group in frozen['seasons']:
        season = group['season']
        release = registry.load_preferred_release(season)
        layers = package_layers(release)
        hashes = [(path, registry.sha256_file(path)) for _, _, path in layers]
        effective = {}
        for _, package, _ in layers:
            for player in package['players']:
                effective[player['carrier_id']] = player
        name_index = {}
        for player in effective.values():
            name_index.setdefault(name_key(player.get('source_name') or player['name']), []).append(player)
        for case in group['candidates']:
            case_id = pipeline.canonical_json_sha256(dict(season=season, case=case))
            rows.append(dict(case_id=case_id, season=season,
                previously_delivered=case_id in closed,
                original_case=case, **observe(case, effective.values(), name_index=name_index)))
        if any(registry.sha256_file(path) != sha for path, sha in hashes):
            raise ValueError('recipe changed during global observation')
        bindings.append(dict(season=season, release_id=release.release_id,
            manifest_sha256=release.manifest_sha256,
            layers=[dict(path=registry.relative_workspace_path(path), sha256=sha)
                for path, sha in hashes]))
        print(dict(season=season, effective_players=len(effective)), flush=True)
    if len(rows) != 2809 or len({r['case_id'] for r in rows}) != 2809:
        raise ValueError('fixed baseline changed')
    result = dict(utc=datetime.now(UTC).isoformat(),
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        checklist_sha256=registry.sha256_file(checklist_path),
        frozen_cases_sha256=registry.sha256_file(frozen_path), bindings=bindings,
        unresolved_observation_counts=dict(Counter(r['observation'] for r in rows
            if not r['previously_delivered'])), rows=rows,
        native_writes=0, recipe_writes=0, new_case_closures=0,
        observation_policy='explicit-published-shirt-heading-stripped-v2',
        limitations=['Name matching locates review evidence, not conclusive identity.',
            'Corrected birthdays or moved slots must not silently close historical cases.',
            'Published actor aliases may require further source reconciliation.'])
    output = root / 'luna-closeout-20261017/global-current-candidate-presence-v2.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    retained(output, result)
    print(result['unresolved_observation_counts'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checklist', type=Path, required=True)
    args = parser.parse_args()
    main(args.checklist)
