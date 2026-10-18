"""Observe fixed duplicate candidates against current recipes, without dispositions.

Changed or missing identities require review; neither observation proves a repair.
"""
from collections import Counter
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    root = registry.ROOT / '.local/consolidated-audit-20261009'
    checklist_path = root / 'release-delivery-checklist-v107.json'
    checklist = pipeline.read_json_file(checklist_path)
    cases_path = registry.ROOT / checklist['cross_club_case_file']
    frozen = pipeline.read_json_file(cases_path)
    closed = {row['case_id'] for row in checklist['cross_club_dispositions']}
    rows = []
    bindings = []
    for season_row in frozen['seasons']:
        season = season_row['season']
        release = registry.load_preferred_release(season)
        package_hash = registry.sha256_file(release.package_path)
        package = pipeline.read_json_file(release.package_path)
        players = {p['id']: p for p in package['players']}
        bindings.append(dict(season=season, release_id=release.release_id,
            package_sha256=package_hash, manifest_sha256=release.manifest_sha256))
        for case in season_row['candidates']:
            case_id = pipeline.canonical_json_sha256(dict(season=season, case=case))
            observations = []
            for old in case['players']:
                current = players.get(old['player_id'])
                observations.append(dict(player_id=old['player_id'],
                    original=old, current=current,
                    observation='record-absent' if current is None else 'record-present'))
            rows.append(dict(case_id=case_id, season=season,
                disposition='previously-delivered' if case_id in closed else 'unreviewed',
                observations=observations))
        if registry.sha256_file(release.package_path) != package_hash:
            raise ValueError('recipe changed during observation')
    identifiers = [row['case_id'] for row in rows]
    if len(identifiers) != 2809 or len(set(identifiers)) != len(identifiers):
        raise ValueError('fixed baseline must contain exactly 2809 unique cases')
    if not closed.issubset(identifiers):
        raise ValueError('published dispositions do not map to fixed cases')
    result = dict(utc=datetime.now(UTC).isoformat(),
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        checklist_sha256=registry.sha256_file(checklist_path),
        frozen_cases_sha256=registry.sha256_file(cases_path), bindings=bindings,
        counts=dict(Counter(row['disposition'] for row in rows)), rows=rows,
        native_writes=0, recipe_writes=0, new_case_closures=0,
        policy='Observation only. Changed, absent or matching recipe records are not historical dispositions.')
    output = root / 'luna-closeout-20261017/fixed-current-candidate-inventory.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    retained(output, result)
    print(result['counts'], flush=True)


if __name__ == '__main__':
    main()
