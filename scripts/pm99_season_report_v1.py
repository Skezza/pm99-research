#!/usr/bin/env python3
"""Generate a per-season status view from the live catalogue, locators and the newest delivery checklist.

    ./pm99-season report [--json] [--output DIR] [--release-level]

Nothing here is hand-written per season and no completion percentage is produced. Each fact says where it
comes from: ``declared`` values are copied from the locator/checklist (cached, not re-checked now),
``actual`` checks are run by this command, and ``known_issues`` (confirmed findings) are kept apart from
``unreviewed_candidates`` (automatic scan hits that nobody has confirmed as bugs).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor'), str(ROOT / 'upstream/pm99-skezmod-patcher')]
from scripts import json_storage_io_v1 as storage_io
from scripts import season_amendment_candidates_v1 as candidates  # noqa: E402
from scripts import season_editorial_field_policy_v1 as field_policy  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402

DEFAULT_OUTPUT = ROOT / '.local/season-status-report-v1'
CHECKLIST_GLOB = '.local/consolidated-audit-*/release-delivery-checklist-v*.json'
# Exact finding states seen in checklist v298. Anything else is surfaced as "needs reading", never assumed closed.
CLOSED_STATES = frozenset("""
delivered-native-SOURCE-and-runner-verified repaired-and-runtime-verified delivered-source-native-SOURCE-and-runner-verified
delivered-source-native-SOURCE-and-fresh-startup-verified installed-and-runtime-verified delivered-source-native-SOURCE-and-runtime-verified
delivered-installed-native-SOURCE-runtime-verified closed-delivered-installed-native-SOURCE-and-runtime-verified
label-delivered-original-source-native-SOURCE-and-runner-verified delivered-source-native-SOURCE-and-club-label-runner-verified
delivered-native-SOURCE-and-genuine-runner-verified delivered-original-label-opening18-native-SOURCE-and-targeted-runner-verified
delivered-source-native-SOURCE-and-targeted-runner-verified delivered-native-SOURCE-and-local-runner-verified
delivered-source-native-SOURCE-and-genuine-runner-verified resolved-legitimate-period-secondary-position
""".split())
OPEN_STATES = frozenset(['open-dated-annual-broad-position-conflict', 'confirmed-not-delivered'])


def classify_state(state):
    state = str(state)
    if state in CLOSED_STATES:
        return 'closed'
    if state in OPEN_STATES:
        return 'open'
    return 'needs-reading'      # partial/disputed/new wording: shown verbatim, never counted as closed


LEGEND = {
    'declared': 'copied from the release locator or checklist; cached, NOT re-verified by this report',
    'actual': 'checked by this command when it ran (file presence/hashes, attestation structure)',
    'known_issues': 'confirmed findings from the delivery checklist. The checklist is a CACHED historical snapshot (its own date is shown); '
                    'states are classified only from an explicit vocabulary: closed, open, or needs-reading (shown verbatim, never assumed closed)',
    'unreviewed_candidates': 'automatic scan hits (same-person-at-two-clubs groups); NOT confirmed bugs',
    'no_percentages': 'counts only; the checklist\'s own work-complete flag is quoted, never converted to progress',
}


def newest_checklist():
    def version(path):
        match = re.search(r'-v(\d+)\.json$', path.name)
        return int(match.group(1)) if match else -1
    found = sorted(storage_io.glob(ROOT, CHECKLIST_GLOB), key=version)
    return found[-1] if found else None


def load_checklist():
    path = newest_checklist()
    if path is None:
        return None, {}
    data = json.loads(storage_io.read_text(path, encoding='utf-8'))
    by_season = {}
    for row in data.get('additional_confirmed_findings', []):
        season = row.get('season')
        if isinstance(season, str):
            by_season.setdefault(season, {}).setdefault('findings', []).append(row)
    for row in data.get('cross_club_dispositions', []):
        by_season.setdefault(row.get('season'), {}).setdefault('dispositions', []).append(row)
    for row in data.get('within_club_cases', []):
        by_season.setdefault(row.get('season'), {}).setdefault('within_club', []).append(row)
    for row in data.get('accepted_editorial_exceptions', []):
        by_season.setdefault(row.get('season'), {}).setdefault('exceptions', []).append(row)
    for row in data.get('additional_runtime_review_candidates', []):
        match = re.match(r'(\d{4}-\d{2}):', str(row.get('case_id', '')))
        if match:
            by_season.setdefault(match.group(1), {}).setdefault('runtime_candidates', []).append(row)
    scan_path = ROOT / data.get('cross_club_case_file', '')
    scanned = {}
    if storage_io.is_file(scan_path):
        for row in json.loads(storage_io.read_text(scan_path, encoding='utf-8')).get('seasons', []):
            scanned[row.get('season')] = len(row.get('candidates', []))
    vocabulary = {}
    for row in data.get('additional_confirmed_findings', []):
        vocabulary[str(row.get('state'))] = vocabulary.get(str(row.get('state')), 0) + 1
    meta = dict(state_vocabulary={k: dict(count=v, classified_as=classify_state(k)) for k, v in sorted(vocabulary.items())},
                path=str(path.relative_to(ROOT)), utc=data.get('utc'), schema=data.get('schema'),
                work_complete_flag=data.get('all_required_work_complete'), allowed_gaps=data.get('allowed_gaps', []),
                not_automatically_allowed=data.get('not_automatically_allowed', []),
                baseline_unclassified_candidates=data.get('remaining_cross_club_cases'), scan_counts=scanned)
    return meta, by_season


def recipe_facts(release):
    """Per-field capability counts at recipe level (native agreement is still proven when a build runs)."""
    package = json.loads(storage_io.read_text(release.package_path, encoding='utf-8'))
    players, managers = package['players'], package['managers']
    capable = {}
    for label, kind, field in (('rating', 'player-rating', 'passing'), ('broad_position', 'player-fact', 'primary_position'),
                               ('shirt_number', 'player-fact', 'shirt_number'), ('nationality', 'player-fact', 'nationality'),
                               ('birth_date', 'player-fact', 'birth_date'), ('height_cm', 'player-fact', 'height_cm'),
                               ('weight_kg', 'player-fact', 'weight_kg')):
        capable[label] = sum(1 for p in players if field_policy.record_reason(kind, p, field) is None)
    return dict(players=len(players), managers=len(managers), clubs=len(package['clubs']),
                players_with_field_editable=capable,
                whole_record_preserved_players=sum(1 for p in players if p.get('policy') == 'preserve-existing-mode1'),
                managers_renamable=sum(1 for m in managers if field_policy.record_reason('manager-name', m, 'name') is None),
                note='counts are per field: a player with one unknown fact is still editable in the other fields')


def season_row(season, checklist, *, release_level):
    release = registry.load_preferred_release(season)
    locator = release.locator
    playable = registry.validate_preferred_release(season, level='playable')
    attestation_issues = registry._validate_runtime_attestation(release) if release.attestation_path else ['no runtime attestation registered']
    actual = dict(playable_validation=dict(valid=playable['valid'], missing=playable['missing'], issue_count=len(playable.get('issues', []))),
                  runtime_attestation=dict(registered=release.attestation_path is not None, valid=not attestation_issues, issues=attestation_issues))
    if release_level:
        full = registry.validate_preferred_release(season, level='release')
        actual['release_validation'] = dict(valid=full['valid'], issue_count=len(full.get('issues', [])))
    facts = checklist.get(season, {})
    findings = facts.get('findings', [])
    classed = [(classify_state(f['state']), dict(id=f.get('id') or f.get('name'), state=f['state'])) for f in findings]
    open_findings = [r for c, r in classed if c == 'open']
    needs_reading = [r for c, r in classed if c == 'needs-reading']
    row = dict(season=season, release_id=release.release_id, play_command=f'./pm99-season play {season}',
        edit_command=f'./pm99-season apply-amendments {season} --dry-run',
        declared=dict(technical_status=locator.get('technical_status'), qa_status=locator.get('qa_status', 'not-recorded'),
                      editorial_status=locator.get('editorial_status', 'not-recorded'),
                      editorial_warning_count=locator.get('editorial_warning_count'),
                      import_issue_count=len(locator.get('import_issues') or [])),
        actual=actual, recipe=recipe_facts(release),
        known_issues=dict(confirmed_findings_recorded=len(findings), open=open_findings, needs_reading=needs_reading,
                          closed=sum(1 for c, _ in classed if c == 'closed'),
                          accepted_editorial_exceptions=[e.get('id') for e in facts.get('exceptions', [])],
                          runtime_review_candidates=[c.get('case_id') for c in facts.get('runtime_candidates', [])]),
        unreviewed_candidates=dict(cross_club_groups_in_original_scan=checklist.get('__scan__', {}).get(season),
                                   cross_club_cases_disposed=len(facts.get('dispositions', [])),
                                   within_club_cases_listed=len(facts.get('within_club', []))),
        edited_candidates=[dict(release_id=c['release_id'], parent=c['parent_release_id'], edits=c['change_count'], play_command=c['play_command'])
                           for c in candidates.list_candidates(season)])
    return row


def build_report(seasons, *, release_level=False):
    meta, by_season = load_checklist()
    if meta:
        by_season['__scan__'] = meta['scan_counts']
    rows = [season_row(season, by_season, release_level=release_level) for season in seasons]
    return dict(schema='pm99-season-status-report-v1', generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                legend=LEGEND, checklist=meta, seasons=rows,
                totals=dict(seasons=len(rows), playable_actual=sum(r['actual']['playable_validation']['valid'] for r in rows),
                            runtime_attested_actual=sum(r['actual']['runtime_attestation']['valid'] for r in rows),
                            confirmed_findings_open_or_needing_reading=sum(len(r['known_issues']['open']) + len(r['known_issues']['needs_reading']) for r in rows)))


def markdown(report):
    out = ['# Season status (generated)', '', 'Generated by `./pm99-season report`; nothing here is hand-written. No completion percentages.', '']
    for key, text in report['legend'].items():
        out.append(f'- **{key}**: {text}')
    meta = report['checklist']
    if meta:
        out += ['', f'Checklist: `{meta["path"]}` ({meta["utc"]}); its own all-work-complete flag is **{meta["work_complete_flag"]}**. '
                f'Allowed gaps: {", ".join(meta["allowed_gaps"]) or "none recorded"}.']
    out += ['', '| Season | Release | Playable (checked) | Runtime attestation (checked) | Declared QA | Confirmed findings (cached) | Unreviewed candidate groups | Edited candidates | Play |',
            '|---|---|---|---|---|---|---|---|---|']
    for r in report['seasons']:
        a = r['actual']
        out.append(f'| {r["season"]} | `{r["release_id"]}` | {"yes" if a["playable_validation"]["valid"] else "NO"} | '
                   f'{"valid" if a["runtime_attestation"]["valid"] else "not valid/absent"} | {r["declared"]["qa_status"]} | '
                   f'{len(r["known_issues"]["open"])} open / {len(r["known_issues"]["needs_reading"])} needs reading | {r["unreviewed_candidates"]["cross_club_groups_in_original_scan"] if r["unreviewed_candidates"]["cross_club_groups_in_original_scan"] is not None else "n/a"} | '
                   f'{len(r["edited_candidates"])} | `{r["play_command"]}` |')
    out += ['', '## Known gaps and limits per season', '']
    for r in report['seasons']:
        rec = r['recipe']
        out.append(f'### {r["season"]}')
        cap = rec['players_with_field_editable']
        out.append(f'- Workbook build route, per field (of {rec["players"]} recipe players): ratings {cap["rating"]}, broad position {cap["broad_position"]}, '
                   f'shirt {cap["shirt_number"]}, nationality {cap["nationality"]}, DOB {cap["birth_date"]}, height {cap["height_cm"]}, weight {cap["weight_kg"]}; '
                   f'{rec["managers_renamable"]} of {rec["managers"]} managers renamable. A person with one unknown fact is still editable in their other fields; '
                   f'{rec["whole_record_preserved_players"]} whole-record preserved players are read-only.')
        for issue in r['known_issues']['open']:
            out.append(f'- Confirmed, open: `{issue["id"]}` — {issue["state"]}')
        for issue in r['known_issues']['needs_reading']:
            out.append(f'- Confirmed, state needs reading (not assumed closed): `{issue["id"]}` — {issue["state"]}')
        for case in r['known_issues']['runtime_review_candidates']:
            out.append(f'- Runtime review candidate (unconfirmed): `{case}`')
        if r['actual']['runtime_attestation']['issues']:
            out.append(f'- Attestation: {"; ".join(map(str, r["actual"]["runtime_attestation"]["issues"][:3]))}')
        out.append(f'- Unreviewed automatic candidate groups: {r["unreviewed_candidates"]["cross_club_groups_in_original_scan"]} scanned, '
                   f'{r["unreviewed_candidates"]["cross_club_cases_disposed"]} disposed (not confirmed bugs).')
        for cand in r['edited_candidates']:
            out.append(f'- Edited candidate `{cand["release_id"]}` ({cand["edits"]} edit group(s), parent `{cand["parent"]}`): `{cand["play_command"]}`')
        out.append('')
    return '\n'.join(out) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('season', nargs='?', default='all')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='directory for status.json and status.md')
    parser.add_argument('--no-write', action='store_true')
    parser.add_argument('--release-level', action='store_true', help='also run the (slower) release-level validation per season')
    args = parser.parse_args(argv)
    seasons = registry.supported_seasons() if args.season == 'all' else [pipeline.normalise_season_id(args.season)]
    report = build_report(seasons, release_level=args.release_level)
    if not args.no_write:
        args.output.mkdir(parents=True, exist_ok=True)
        storage_io.write_text(args.output / 'status.json', json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        storage_io.write_text(args.output / 'status.md', markdown(report), encoding='utf-8')
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(markdown(report).split('## Known gaps')[0])
        if not args.no_write:
            print(f'wrote {args.output}/status.md and status.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
