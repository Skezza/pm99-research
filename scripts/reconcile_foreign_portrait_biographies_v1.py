#!/usr/bin/env python3
"""Reconcile portrait review flags against cached biographies, without game writes.

An alias is cleared only when target and image-source names identify the SAME
cached biography and its birth date corroborates the recipe. Contradictory CSV
dates are explicitly recorded. Source-only agreement is not enough to approve
a portrait attached to a different target player.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.season_portrait_pipeline_v1 import _normalise_name
from scripts.season_portrait_pipeline_v1 import _name_score

INPUT = ROOT / '.local/visual-qa-20261003/foreign-source-verification/report.json'
OUTPUT = ROOT / '.local/visual-qa-20261003/foreign-biography-review/report.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def name_key(value):
    return _normalise_name(re.sub(r'\s*\([^)]*\)\s*$', '', value))


def biography_index(root):
    from scripts import capture_2015_wikipedia_player_facts_v1 as wiki
    index = defaultdict(dict)
    for path in sorted(root.glob('wikipedia-player-facts*/pages/*.json')):
        doc = json.loads(path.read_text())
        query = doc.get('query', {})
        pages = query.get('pages', [])
        if isinstance(pages, dict):
            pages = pages.values()
        aliases = defaultdict(list)
        for row in query.get('redirects', []):
            aliases[row['to']].append(row['from'])
        for page in pages:
            revisions = page.get('revisions', [])
            if not revisions:
                continue
            revision = revisions[0]
            content = revision.get('slots', {}).get('main', {}).get('content', '')
            if not re.search(r'{{\s*infobox\s+football\s+biography', content, re.I):
                continue
            dob = wiki._facts(content).get('birth_date')
            if not dob:
                continue
            names = [page['title'], *aliases[page['title']]]
            for field in ('name', 'fullname', 'full_name', 'full name'):
                value = wiki._parameter(content, field)
                if value:
                    names.append(wiki.wikipedia._clean_wikitext(value))
            keys = {name_key(value) for value in names if len(name_key(value).split()) >= 2}
            item = {'page_id': page['pageid'], 'title': page['title'], 'birth_date': dob,
                    'source_url': 'https://en.wikipedia.org/w/index.php?oldid=' + str(revision['revid']),
                    'revision_id': revision['revid'], 'revision_timestamp': revision.get('timestamp'),
                    'cache_path': str(path), 'cache_sha256': sha(path), 'name_keys': sorted(keys)}
            for key in keys:
                index[key][page['pageid']] = item
    return {key: list(pages.values()) for key, pages in index.items()}


def verdict(row, index):
    target = name_key(row['name'])
    source = name_key(row.get('dated_source_name', ''))
    # Common one-word football aliases cannot independently identify a person.
    if len(target.split()) < 2 or len(source.split()) < 2:
        return {'result': 'needs-labelled-full-identity-reference', 'cleared_issues': []}
    target_matches = {p['page_id']: p for p in index.get(target, [])}
    source_matches = {p['page_id']: p for p in index.get(source, [])}
    same = target_matches.keys() & source_matches.keys()
    if len(same) != 1:
        return {'result': 'no-unique-shared-biography', 'cleared_issues': []}
    page = target_matches[next(iter(same))]
    reference = {k: v for k, v in page.items() if k != 'name_keys'}
    if page['birth_date'] != row.get('recipe_birth_date'):
        return {'result': 'biography-found-but-birth-date-conflict', 'cleared_issues': [], 'reference': reference}
    cleared = ['source-name-needs-independent-review'] if 'source-name-needs-independent-review' in row['issues'] else []
    if page['birth_date'] != row.get('source_birth_date'):
        # Both labelled full identities point to this biography. Its DOB
        # supports the recipe, not the CSV. Keep the original discrepancy in
        # the input report and record this resolution instead of overwriting
        # the recipe with an erroneous upstream value.
        if 'recipe-and-source-birth-date-disagree-or-missing' in row['issues']:
            cleared.append('recipe-and-source-birth-date-disagree-or-missing')
        return {'result': 'identity-corroborated-upstream-csv-date-conflict',
                'cleared_issues': cleared, 'reference': reference,
                'upstream_conflicting_birth_date': row.get('source_birth_date')}
    return {'result': 'target-and-source-identity-corroborated', 'cleared_issues': cleared,
            'reference': reference}


def official_edition_verdict(row, ea_players, index):
    """Use EA's own edition-specific ID/alias list, with a corroborating DOB.

    Unlike a search-result guess, this binds the actual image URL's ID to an
    explicitly labelled FIFA16 alias. A mononym alone or a conflicting birthday
    cannot clear a warning. It still does not certify the pixels depict the person.
    """
    person = ea_players.get(row.get('fifa_id'))
    if not person or not row.get('source_hash_matches') or row.get('face_count') != 1:
        return {'result': 'official-edition-not-corroborated', 'cleared_issues': []}
    full = ' '.join(str(person.get(k) or '') for k in ('f', 'l')).strip()
    alias = str(person.get('c') or '')
    target = name_key(row['name'])
    labelled = bool(target and (target == name_key(alias) or
                               _name_score(row['name'], full, full)[0] >= 85))
    if not labelled:
        return {'result': 'official-alias-disagrees', 'cleared_issues': []}
    matches = index.get(name_key(full), [])
    reference = matches[0] if len(matches) == 1 else None
    birthday = reference['birth_date'] if reference else row.get('source_birth_date')
    if not birthday or birthday != row.get('recipe_birth_date'):
        return {'result': 'official-identity-birth-date-unresolved', 'cleared_issues': [],
                'official_full_name': full, 'official_alias': alias}
    clearable = {'player-id-not-in-dated-edition', 'source-name-needs-independent-review'}
    if reference and row.get('source_birth_date') != birthday:
        clearable.add('recipe-and-source-birth-date-disagree-or-missing')
    return {'result': 'official-edition-alias-and-birthday-corroborated',
            'cleared_issues': [issue for issue in row['issues'] if issue in clearable],
            'official_full_name': full, 'official_alias': alias,
            'birth_date': birthday, 'birth_date_basis': 'revision-pinned-biography' if reference else 'dated-csv',
            'reference': {k: v for k, v in reference.items() if k != 'name_keys'} if reference else None}


def run(fetch=False):
    report = json.loads(INPUT.read_text())
    cache_root = ROOT / '.local/season-pipeline-v2/source-cache'
    if fetch:
        from scripts import capture_2015_wikipedia_player_facts_v1 as wiki
        titles = sorted({name for row in report['players'] if row['issues']
                         for name in (row['name'], row.get('dated_source_name', ''))
                         if len(name_key(name).split()) >= 2})
        cache = wiki.opening.SnapshotCache(cache_root / 'wikipedia-player-facts-portrait-review-20261003',
                                          offline=False, delay=5)
        # Existing capture helper: exact titles, redirects, pinned revisions,
        # query-keyed immutable cache, and at most ten titles per request.
        for start in range(0, len(titles), 10):
            try:
                wiki._fetch_batches(titles=titles[start:start + 10], cache=cache,
                                    batch_size=10, title_offset=start)
            except HTTPError as exc:
                if exc.code != 429:
                    raise
                # Stop network work on a rate limit, but still reconcile and
                # save all successfully captured evidence below. A later run
                # resumes from immutable cache misses, never repeating hits.
                print(json.dumps({'capture_paused': 'Wikipedia rate limit',
                                  'retry_after': exc.headers.get('Retry-After'),
                                  'captured_titles': start}), flush=True)
                break
            print(json.dumps({'biography_titles_checked': min(start + 10, len(titles)),
                              'total_titles': len(titles)}), flush=True)
    index = biography_index(cache_root)
    ea_path = ROOT / '.local/season-2015-16/fifa16-ea-player-meta.json'
    ea_document = json.loads(ea_path.read_text())
    from scripts.capture_fifa16_player_meta import SOURCE_URL
    if ea_document.get('source_url') != SOURCE_URL:
        raise ValueError('EA metadata is not bound to the official FIFA16 endpoint')
    ea_players = {int(row['id']): row for row in ea_document['players']}
    from scripts.season_release_registry_v1 import load_preferred_release
    package_path = load_preferred_release('2015-16').package_path
    package = json.loads(package_path.read_text())
    package_dates = {int(p['carrier_id']): p.get('facts', {}).get('birth_date') for p in package['players']}
    rows = []
    for row in report['players']:
        checked = verdict(row, index)
        official = official_edition_verdict({**row, 'recipe_birth_date': package_dates.get(row['carrier_id'])}, ea_players, index)
        cleared = set(checked['cleared_issues']) | set(official['cleared_issues'])
        remaining = [issue for issue in row['issues'] if issue not in cleared]
        rows.append({'carrier_id': row['carrier_id'], 'name': row['name'],
                     'original_issues': row['issues'], 'remaining_issues': remaining,
                     'biography_check': checked, 'official_edition_check': official})
    result = {'schema_version': 'pm99-foreign-portrait-biography-review-v1',
              'input_report_sha256': sha(INPUT), 'players_checked': len(rows),
              'official_edition_metadata': {'path': str(ea_path), 'sha256': sha(ea_path),
                                            'source_url': SOURCE_URL},
              'package_sha256': sha(package_path),
              'biography_results': dict(Counter(r['biography_check']['result'] for r in rows)),
              'official_edition_results': dict(Counter(r['official_edition_check']['result'] for r in rows)),
              'fully_cleared_review_rows': sum(bool(r['original_issues']) and not r['remaining_issues'] for r in rows),
              'remaining_review_rows': sum(bool(r['remaining_issues']) for r in rows),
              'scope': 'Cached labelled identities and dates, not face recognition or visual certification.',
              'players': rows}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'players'}))


def english_biography_verdict(row, index):
    target, source = name_key(row['name']), name_key(row.get('dated_source_name') or '')
    if min(len(target.split()), len(source.split())) < 2:
        return {'cleared_issues': [], 'result': 'needs-labelled-full-identity'}
    targets = {p['page_id']: p for p in index.get(target, [])}
    sources = {p['page_id']: p for p in index.get(source, [])}
    shared = targets.keys() & sources.keys()
    if len(shared) != 1:
        return {'cleared_issues': [], 'result': 'no-unique-shared-biography'}
    page = targets[next(iter(shared))]
    if page['birth_date'] not in {row.get('recipe_birth_date'), row.get('source_birth_date')}:
        return {'cleared_issues': [], 'result': 'independent-birthday-conflict'}
    clearable = {'dated-source-person-does-not-match-recipe',
                 'source-and-recipe-birthday-conflict-needs-corroboration'}
    return {'result': 'same-person-corroborated-secondary-date-conflicts-retained',
            'cleared_issues': [i for i in row['issues'] if i in clearable],
            'reference': {k: v for k, v in page.items() if k != 'name_keys'}}


def reconcile_english(input_path, output, fetch=False):
    report = json.loads(input_path.read_text())
    cache_root = ROOT / '.local/season-pipeline-v2/source-cache'
    if fetch:
        from scripts import capture_2015_wikipedia_player_facts_v1 as wiki
        titles = sorted({name for row in report['players'] if row['issues']
                         for name in (row['name'], row.get('dated_source_name') or '')
                         if len(name_key(name).split()) >= 2})
        cache = wiki.opening.SnapshotCache(cache_root / 'wikipedia-player-facts-english-portrait-review-20261003',
                                          offline=False, delay=5)
        for start in range(0, len(titles), 10):
            try:
                wiki._fetch_batches(titles=titles[start:start + 10], cache=cache, batch_size=10, title_offset=start)
            except HTTPError as exc:
                if exc.code != 429:
                    raise
                print(json.dumps({'capture_paused': 'Wikipedia rate limit', 'captured_titles': start}), flush=True)
                break
            print(json.dumps({'english_biography_titles_checked': min(start + 10, len(titles)),
                              'total_titles': len(titles)}), flush=True)
    index = biography_index(cache_root)
    rows = []
    for row in report['players']:
        verdict = english_biography_verdict(row, index) if row['issues'] else {'cleared_issues': [], 'result': 'no-identity-issues'}
        rows.append({**row, 'remaining_issues': [i for i in row['issues'] if i not in verdict['cleared_issues']],
                     'biography_check': verdict})
    result = {'schema_version': 'pm99-english-portrait-biography-review-v1', 'season': '2015-16',
              'release_id': report['release_id'], 'input_report_sha256': sha(input_path),
              'package_sha256': report['package_sha256'], 'minifoto_sha256': report['minifoto_sha256'],
              'players_checked': len(rows), 'remaining_review_rows': sum(bool(r['remaining_issues']) for r in rows),
              'cleared_review_rows': sum(bool(r['issues']) and not r['remaining_issues'] for r in rows),
              'scope': 'Identity/date corroboration, not independent facial certification.', 'players': rows}
    from scripts import season_pipeline_v2 as pipeline
    pipeline.write_canonical_json(output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'players'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-flagged-biographies', action='store_true')
    parser.add_argument('--english-report', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.english_report:
        if not args.output:
            parser.error('English reconciliation requires --output')
        reconcile_english(args.english_report, args.output, args.fetch_flagged_biographies)
    else:
        run(args.fetch_flagged_biographies)
