#!/usr/bin/env python3
"""Capture/replay one missing opening plus original full-name/DOB biographies.

This is a bridge review, not an ownership approval or native transaction.
Missing people and the unlinked unused bench remain explicit gaps.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import capture_match_archive_sources_v1 as capture
from scripts import season_11v11_opening_source_v1 as archive
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_person_identity_v1 as persons
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def run(club, season, competition, schedule_url, person_input, cache, output, expected_games=46):
    if output.exists():
        raise ValueError('archive original opening bridge review is immutable')
    schedule = capture.capture(schedule_url, cache)
    schedule_raw = (ROOT / schedule['path']).read_bytes()
    fixture = archive.first_fixture(schedule_raw, club, season, competition, expected_games)
    match = capture.capture(fixture['url'], cache)
    parsed = archive.verify_pair(schedule_raw, (ROOT / match['path']).read_bytes(),
                                 club, season, competition, expected_games)
    people, _, _, snapshot = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    person_sha = registry.sha256_file(person_input)
    people, summary = persons.merge(people, json.loads(person_input.read_text()))
    rows = []
    for player in parsed['starting_xi'] + parsed['published_linked_bench']:
        row = {'archive_player': player}
        try:
            source = capture.capture(player['source_profile_url'], cache)
            row['original_biography'] = source
            row['identity_bridge'] = archive.bridge_person((ROOT / source['path']).read_bytes(), player, people)
            row['status'] = 'original-full-name-DOB-bridge-reparsed'
        except (OSError, ValueError) as exc:
            row.update(status='original-archive-identity-gap', reason=str(exc))
        rows.append(row)
        print(json.dumps({'player': player['name'], 'status': row['status'],
            'reason': row.get('reason')}), flush=True)
    if registry.sha256_file(person_input) != person_sha:
        raise ValueError('bound historical public person input changed during archive capture')
    result = {'schema_version': 'pm99-original-11v11-opening-bridge-review-v1',
        'season': season, 'club': club, 'original_opening': parsed,
        'bindings': {'snapshot': snapshot,
            'person_input': {'path': registry.relative_workspace_path(person_input), 'sha256': person_sha},
            'original_schedule': schedule, 'original_report': match,
            'reader': {'path': registry.relative_workspace_path(Path(archive.__file__)),
                       'sha256': registry.sha256_file(Path(archive.__file__))}},
        'person_input_refusals': summary['refused'], 'players': rows,
        'summary': {'linked_people': len(rows),
            'bridged_people': sum(r['status'] == 'original-full-name-DOB-bridge-reparsed' for r in rows),
            'unlinked_unused_bench': len(parsed['unused_substitute_names'])},
        'approved_for_duplicate_ownership': False, 'native_corrections': 0,
        'remaining_work': ['Bind the club to its original historical squad source and published club ID.',
            'Resolve every first-XI, used and unused bench identity without guessed initials or dates.',
            'Independently replay the typed archive bridge in the planner before any native correction.'],
        'credits': ['11v11 / Association of Football Statisticians', 'Transfermarkt']}
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    print(json.dumps(result['summary']), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--club', required=True)
    parser.add_argument('--season', required=True)
    parser.add_argument('--competition', required=True)
    parser.add_argument('--schedule-url', required=True)
    parser.add_argument('--person-input', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-league-games', type=int, default=46)
    args = parser.parse_args()
    run(args.club, args.season, args.competition, args.schedule_url,
        args.person_input, args.cache, args.output, args.expected_league_games)
