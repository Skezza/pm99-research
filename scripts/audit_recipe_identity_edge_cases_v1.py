#!/usr/bin/env python3
"""Read-only within-club names and season-relative DOB checks for current recipes.

Cross-club ownership has its own pinned-person audit. This complementary report
never merges namesakes, changes birthdays or interprets a preserved native fact
as a sourced literal. Season-start age is a triage anchor, not fixture evidence.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-recipe-within-club-name-and-season-DOB-review-v1'


def inspect(players, clubs, anchor):
    groups = defaultdict(list)
    dates, counts = [], Counter()
    for player in players:
        name = player.get('source_name') or player['name']
        birthday = player['facts'].get('birth_date')
        row = {'carrier_id': player['carrier_id'], 'name': name,
            'native_display_name': player['name'], 'birth_date': birthday,
            'person_id': player.get('person_id'), 'club_id': player['club_id']}
        groups[(player['club_id'], roster.normalise(name))].append(row)
        if not isinstance(birthday, str):
            counts['DOB-not-a-sourced-literal'] += 1
            continue
        try:
            born = date.fromisoformat(birthday)
        except ValueError:
            dates.append(dict(row, status='invalid-calendar-date'))
            counts['invalid-calendar-date'] += 1
            continue
        age = anchor.year - born.year - ((anchor.month, anchor.day) < (born.month, born.day))
        status = 'under-12-or-future-biography-review' if age < 12 else (
            'over-50-biography-review' if age > 50 else 'age-within-broad-triage-range')
        counts[status] += 1
        if status != 'age-within-broad-triage-range':
            dates.append(dict(row, status=status, age_at_anchor=age))
    candidates = []
    for (club_id, full_name_key), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        literal_dates = [row['birth_date'] for row in rows if isinstance(row['birth_date'], str)]
        same_date = len(literal_dates) == len(rows) and len(set(literal_dates)) == 1
        candidates.append({'club_id': club_id, 'club': clubs[club_id]['name'],
            'full_name_key': full_name_key, 'players': rows,
            'classification': 'same-full-name-and-literal-DOB-review' if same_date else
                'same-full-name-different-or-preserved-DOB-review',
            'automatic_merge_authorised': False})
    return {'within_club_name_candidates': candidates, 'DOB_review_candidates': dates,
        'DOB_counts': dict(counts), 'season_age_anchor': anchor.isoformat(),
        'candidate_group_count': len(candidates)}


def run(output):
    if output.exists():
        raise ValueError('identity edge-case audit is immutable')
    sections = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        players, clubs, layers = {}, {}, []
        for label, package, path in planner.package_layers(release):
            players.update({p['carrier_id']: p for p in package['players']})
            clubs.update({c['id']: c for c in package['clubs']})
            layers.append({'label': label, 'path': registry.relative_workspace_path(path),
                'sha256': registry.sha256_file(path)})
        section = inspect(players.values(), clubs, date(int(season[:4]), 8, 1))
        section.update(season=season, release_id=release.release_id,
            package_sha256=registry.sha256_file(release.package_path), layers=layers,
            effective_player_count=len(players))
        sections.append(section)
    # A report describes one coherent installed state, not a moving mixture.
    for section in sections:
        current = registry.load_preferred_release(section['season'])
        if (current.release_id, registry.sha256_file(current.package_path)) != (
                section['release_id'], section['package_sha256']):
            raise ValueError('preferred release changed during edge-case audit')
    result = {'schema_version': SCHEMA, 'utc_time': datetime.now(timezone.utc).isoformat(),
        'policy': 'same-club complete-source-name candidates, including DOB disagreements; never automatic namesake merging',
        'limits': ['August 1 age anchor is triage, not exact opening fixture evidence',
            'preserved DOB needs native readback; absence of a literal is not a wrong fact',
            'cross-club ownership is checked separately; counts must not be added blindly'],
        'candidate_group_count': sum(s['candidate_group_count'] for s in sections),
        'DOB_review_candidate_count': sum(len(s['DOB_review_candidates']) for s in sections),
        'seasons': sections, 'native_writes': 0, 'automatic_changes_authorised': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    print(json.dumps({k: result[k] for k in ('candidate_group_count',
        'DOB_review_candidate_count', 'native_writes', 'automatic_changes_authorised')}))
