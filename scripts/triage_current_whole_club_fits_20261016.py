"""Check old14 fits against today's recipes; never redo represented clubs."""
from collections import Counter
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/whole-club-current-fit-triage-v1'
SUMMARY = registry.ROOT / '.local/duplicate-ownership-v3/whole-club-fit-scan-r1/summary.json'


def main():
    loaded = {}; rows = []
    for row in pipeline.read_json_file(SUMMARY)['decisions']:
        if row['status'] != 'complete-source-fit':
            continue
        season = row['season']
        if season not in loaded:
            actual = registry.load_preferred_release(season)
            loaded[season] = actual, pipeline.read_json_file(actual.package_path)
        actual, package = loaded[season]
        path = registry.ROOT / row['proposal_path']
        if registry.sha256_file(path) != row['proposal_sha256']:
            raise ValueError('old immutable source-fit proposal changed')
        proposal = pipeline.read_json_file(path)
        club = next(c for c in package['clubs'] if c['carrier_id'] == row['carrier_id'])
        represented = [dict(carrier_id=c['carrier_id'], name=c['name']) for c in package['clubs']
            if normalise(row['target']) in (normalise(c['name']), normalise(c.get('full_name', '')))]
        repeats = [name for name, count in Counter(normalise(p['source_player']['name'])
            for p in proposal['desired_people']).items() if count > 1]
        classification = ('target-already-represented-do-not-create-another-copy' if represented else
            'unrepresented-target-but-proposal-repeats-player-name' if repeats else
            'unrepresented-target-needs-fresh-admission')
        rows.append(dict(season=season, carrier_id=club['carrier_id'], current_club=club['name'],
            old_proposed_target=row['target'], represented_targets=represented,
            repeated_proposed_names=repeats, classification=classification,
            source_proposal=dict(path=row['proposal_path'], sha256=row['proposal_sha256']),
            current_release_id=actual.release_id, current_manifest_sha256=actual.manifest_sha256,
            current_package_sha256=registry.sha256_file(actual.package_path)))
    if len(rows) != 14:
        raise ValueError('original14 source-fit decisions must remain visible')
    ROOT.mkdir(parents=True, exist_ok=True)
    retained(ROOT / 'current-dispositions.json', dict(utc=datetime.now(UTC).isoformat(),
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', machine='joe-Vostro-3350',
        source_summary=dict(path=registry.relative_workspace_path(SUMMARY), sha256=registry.sha256_file(SUMMARY)),
        rows=rows, classes=dict(Counter(r['classification'] for r in rows)),
        native_writes=0, recipe_writes=0, duplicate_cases_closed=0,
        scope='Current recipe target coverage only, not historical/native roster certification. The14 old complete fits are not14 pending club builds.'))
    print(dict(rows=len(rows), classes=dict(Counter(r['classification'] for r in rows)), native_writes=0), flush=True)


if __name__ == '__main__':
    main()
