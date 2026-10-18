#!/usr/bin/env python3
"""Independently reread cached first fixtures, managers and duplicate ownership.

No scraping, recipe edits or historical approval occurs here. The schedule
must independently identify the earliest domestic fixture, and its original
match page must identify exactly the requested club. Whole-season membership
and absence from a matchday squad are never treated as ownership proof.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts.reconcile_opening_date_identities_v1 import _club_key, _normalise
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

SCHEMA = 'pm99-independent-opening-roster-review-v1'
HTML_PARSER = 'lxml' if importlib.util.find_spec('lxml') is not None else 'html.parser'


def first_fixture(payload, competition):
    """Separate implementation: date/report/competition read from raw rows."""
    page = BeautifulSoup(payload, HTML_PARSER)
    rows = []
    for tr in page.find_all('tr'):
        reports, codes = set(), set()
        for link in tr.find_all('a', href=True):
            href = link['href']
            report = re.search(r'/spielbericht/index/spielbericht/(\d+)(?:/|$)', href)
            code = re.search(r'/test/spieltag/wettbewerb/([^/?]+)', href)
            if report: reports.add(report.group(1))
            if code: codes.add(code.group(1))
        date = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', tr.get_text(' ', strip=True))
        if competition not in codes or len(reports) != 1 or date is None:
            continue
        parsed = dt.datetime.strptime(date.group(1), '%d/%m/%Y').date().isoformat()
        rows.append((parsed, next(iter(reports))))
    if not rows:
        raise ValueError('original schedule has no unambiguous domestic fixture')
    return min(rows, key=lambda row: (row[0], int(row[1])))


def _players(container):
    result = {}
    for link in container.find_all('a', href=True):
        match = re.search(r'/profil/spieler/(\d+)(?:/|$)', link['href'])
        if match:
            # Full name in title, not the abbreviated surname in a pitch grid.
            name = link.get('title') or link.get_text(' ', strip=True)
            if name.strip(): result[match.group(1)] = name.strip()
    return result


def match_team(payload, club_id, date):
    """Do not call the capture's lineup parser or trust its manager field."""
    page = BeautifulSoup(payload, HTML_PARSER)
    description = page.find('meta', attrs={'name': 'description'})
    dates = re.findall(r'\b(\d{2}/\d{2}/\d{4})\b', description.get('content', '') if description else '')
    metadata_dates = {dt.datetime.strptime(d, '%d/%m/%Y').date().isoformat() for d in dates}
    header_dates = set()
    for header in page.select('.sb-datum'):
        for value in re.findall(r'\b(\d{2}/\d{2}/(?:\d{4}|\d{2}))\b', header.get_text(' ', strip=True)):
            fmt = '%d/%m/%Y' if len(value) == 10 else '%d/%m/%y'
            header_dates.add(dt.datetime.strptime(value, fmt).date().isoformat())
    if header_dates and header_dates != {date}:
        raise ValueError('visible match header date disagrees with earliest schedule fixture')
    date_discrepancy = None
    if metadata_dates and metadata_dates != {date}:
        # Original pages can publish the next day in their SEO description
        # while the visible fixture header and original domestic schedule
        # agree. Do not infer a timezone or silently discard the discrepancy.
        next_day = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
        if header_dates != {date} or metadata_dates != {next_day}:
            raise ValueError('match page date disagrees with earliest schedule fixture')
        date_discrepancy = {'policy': 'exact-visible-header-and-original-schedule-with-next-day-seo-date-v1',
                            'visible_header_date': date, 'metadata_dates': sorted(metadata_dates),
                            'timezone_explanation': 'not-established; original published discrepancy retained'}
    candidates = []
    for box in page.find_all('div'):
        classes = box.get('class', [])
        if 'large-6' not in classes and 'aufstellung-box' not in classes:
            continue
        # Numeric identity must match in full: club 1 cannot match club 14.
        ids = set()
        for a in box.find_all('a', href=True):
            m = re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href'])
            if m: ids.add(int(m.group(1)))
        if ids == {club_id} and (box.find('table') is not None or box.select('.formation-player-container')):
            candidates.append(box)
    if len(candidates) != 1:
        raise ValueError(f'original report has {len(candidates)} exact club lineup boxes')
    box = candidates[0]
    tables = []
    for table in box.find_all('table'):
        # Some competitions publish eleven substitutes. A bench is not a
        # starting XI merely because its table happens to contain 11 IDs.
        if ('ersatzbank' in table.get('class', []) or table.find_parent(
                class_='aufstellung-ersatzbank-box') is not None):
            continue
        players = {}
        for tr in table.find_all('tr'):
            cells = tr.find_all('td', recursive=False)
            if len(cells) < 2: continue
            if cells[0].get_text(' ', strip=True).casefold() in ('manager', 'coach', 'trainer'):
                continue
            players.update(_players(cells[1]))
        if len(players) == 11: tables.append(players)
    grid = {}
    for container in box.select('.formation-player-container'):
        grid.update(_players(container))
    if len(tables) == 1:
        starters = tables[0]
        if grid and set(grid) != set(starters):
            raise ValueError('published pitch and eleven-player table disagree')
    elif len(grid) == 11:
        starters = grid
    else:
        raise ValueError('cannot independently establish eleven starting players')
    managers = {}
    for link in box.find_all('a', href=True):
        m = re.search(r'/profil/trainer/(\d+)(?:/|$)', link['href'])
        if m: managers[m.group(1)] = (link.get('title') or link.get_text(' ', strip=True)).strip()
    if len(managers) > 1: raise ValueError('ambiguous managers in original club box')
    bench = {}
    for container in box.select('.aufstellung-ersatzbank-box'):
        bench.update(_players(container))
    result = {'starting_xi': starters, 'substitutes': bench,
            'manager': next(iter(managers.values()), None),
            'match_page_date_independently_published': bool(metadata_dates or header_dates)}
    if date_discrepancy is not None:
        result['date_publication_discrepancy'] = date_discrepancy
    return result


def verified_page(root, receipts, url):
    matches = [r for r in receipts if r['url'] == url]
    if len(matches) != 1: raise ValueError('original URL lacks one exact cache receipt')
    receipt = matches[0]; relative = Path(receipt['cache_path'])
    if relative.is_absolute() or '..' in relative.parts: raise ValueError('unsafe cache path')
    path = root / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt['sha256']:
        raise ValueError('original source hash changed')
    return raw, {'path': registry.relative_workspace_path(path), **receipt}


def verify_opening(row, capture, cache):
    selector = row['source_selector']
    if 'transfermarkt_club_id' not in selector:
        raise ValueError('non-Transfermarkt original source requires its own independent parser')
    code = row.get('source_competition_code')
    if not code: raise ValueError('domestic competition identity missing')
    schedule, sr = verified_page(cache, capture['source']['cache_files'], row['schedule_url'])
    date, match = first_fixture(schedule, code)
    if (date, match) != (row['first_league_fixture_date'], str(row['source_match_id'])):
        raise ValueError('capture is not the original schedule earliest domestic fixture')
    report, rr = verified_page(cache, capture['source']['cache_files'], row['lineup_source_url'])
    parsed = match_team(report, int(selector['transfermarkt_club_id']), date)
    for field in ('starting_xi', 'substitutes'):
        declared = {str(p['source_player_id']) for p in row[field]}
        if declared != set(parsed[field]): raise ValueError(f'original {field} IDs differ from capture')
    if _normalise(parsed['manager']) != _normalise(row.get('declared_manager')):
        raise ValueError('original manager differs from capture')
    return {'date': date, 'source_club_id': selector['transfermarkt_club_id'],
            'source_url': row['lineup_source_url'], 'schedule_url': row['schedule_url'],
            'raw_sources': [sr, rr], **parsed}


def duplicate_queue(players, clubs, opening):
    groups = collections.defaultdict(list)
    for p in players:
        key = roster.person_identity_key(p)
        if key is not None:
            groups[key].append(p)
    rows = []
    for (name, date), candidates in sorted(groups.items()):
        if len(candidates) < 2 or len({p['carrier_id'] for p in candidates}) < 2: continue
        records = []
        for p in candidates:
            club = clubs[p['club_id']]; evidence = opening.get(p['club_id'])
            names = {_normalise(p.get('source_name')), _normalise(p['name'])} - {''}
            source_names = {_normalise(n) for field in ('starting_xi', 'substitutes')
                            for n in (evidence or {}).get(field, {}).values()}
            hit = bool(names & source_names)
            records.append({'player_id': p['id'], 'carrier_id': p['carrier_id'], 'club_id': club['id'],
                'club': club['name'], 'nationality': p['facts'].get('nationality'),
                'positive_first_fixture_name_match': hit,
                'identity_match_basis': 'exact-full-name-only; DOB not published in match report' if hit else None,
                'fixture_date': evidence['date'] if evidence else None,
                'source_url': evidence['source_url'] if evidence else None})
        hit_clubs = {r['club_id'] for r in records if r['positive_first_fixture_name_match']}
        status = ('one-dated-club-hit-replacement-and-transfer-check-required' if len(hit_clubs) == 1 else
                  'multiple-dated-club-hits-transfer-timing-required' if len(hit_clubs) > 1 else 'dated-owner-unresolved')
        rows.append({'normalised_name': name, 'birth_date': date, 'candidates': records,
                     'status': status, 'automatic_change_authorised': False})
    return rows


def audit(season, opening_root, output_root, reuse_path=None):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy = roster.add_legacy_english(package, season)
    path = opening_root / season / 'opening-lineups.json'
    capture = json.loads(path.read_text()) if path.exists() else None
    binding = {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
               'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
               'ent_sha256': registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'), 'legacy': legacy,
               'opening_capture_path': registry.relative_workspace_path(path) if path.exists() else None,
               'opening_capture_sha256': registry.sha256_file(path) if path.exists() else None}
    reused = {}
    if reuse_path is not None:
        previous = json.loads(reuse_path.read_text())
        if previous['schema_version'] != SCHEMA or previous['season'] != season or previous['bindings'] != binding:
            raise ValueError('opening evidence reuse requires identical recipe, native managers and capture')
        for row in previous['clubs']:
            if row['status'] != 'original-first-fixture-reparsed': continue
            for source in row['evidence']['raw_sources']:
                if registry.sha256_file(ROOT / source['path']) != source['sha256']:
                    raise ValueError('reused original opening source bytes changed')
            reused[row['club_id']] = row['evidence']
    source_clubs = collections.defaultdict(list)
    for row in (capture or {}).get('clubs', []):
        group = roster.source_group(row['source_selector']['country_catalog'])
        source_clubs[(group, _club_key(row['source_selector']['club_name']))].append(row)
    holders, manager_names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    club_managers = {c['carrier_id']: (id, manager_names.get(id), len(owned)) for id, owned in holders.items() for c in owned}
    rows, opening, counts = [], {}, collections.Counter()
    for club in clubs:
        country = roster.club_group(club)
        candidates = source_clubs.get((country, _club_key(club.get('full_name') or club['name'])), [])
        manager_id, manager_name, owners = club_managers.get(club['carrier_id'], (None, None, 0))
        result = {'club_id': club['id'], 'carrier_id': club['carrier_id'], 'club': club['name'],
                  'playable': club['id'].startswith(('english-club-', 'legacy-english-club-')),
                  'native_manager': manager_name, 'native_manager_carrier_id': manager_id,
                  'native_manager_owner_count': owners, 'status': 'opening-source-unavailable',
                  'manager_status': 'not-independently-verified', 'full_opening_roster_verified': False}
        if len(candidates) == 1:
            try:
                evidence = reused.get(club['id']) or verify_opening(candidates[0], capture, opening_root / season / 'cache')
                opening[club['id']] = evidence
                result.update(status='original-first-fixture-reparsed', evidence=evidence)
                result['manager_status'] = ('match' if _normalise(evidence['manager']) == _normalise(result['native_manager']) else 'mismatch') if evidence['manager'] else 'source-manager-unpublished'
                # Positive XI/bench evidence only; never certify unlisted squad members.
                recipe_names = {_normalise(p.get('source_name') or p['name']) for p in players if p['club_id'] == club['id']}
                result['published_matchday_players'] = len(evidence['starting_xi']) + len(evidence['substitutes'])
                result['full_name_matchday_members_in_recipe'] = sum(_normalise(n) in recipe_names for f in ('starting_xi', 'substitutes') for n in evidence[f].values())
            except (OSError, ValueError, KeyError) as exc:
                result.update(status='original-first-fixture-reparse-gap', error=str(exc))
        elif len(candidates) > 1: result['status'] = 'ambiguous-source-club'
        counts[result['status']] += 1; counts['manager:' + result['manager_status']] += 1
        rows.append(result)
    duplicates = duplicate_queue(players, {c['id']: c for c in clubs}, opening)
    for row in duplicates: counts['duplicate:' + row['status']] += 1
    summary = {'season': season, 'clubs': len(clubs), 'duplicate_person_candidates': len(duplicates), **dict(counts)}
    result = {'schema_version': SCHEMA, 'season': season, 'historical_verification_complete': False,
              'limits': ['A matchday list is not a complete August squad.', 'No automatic ownership replacement follows from non-appearance.',
                         'Full-name match is not independent DOB proof.', 'Managers checked at first domestic fixture, not one worldwide August date.',
                         'Sources absent, unsupported or ambiguous remain explicit gaps.'],
              'bindings': binding,
              'summary': summary, 'clubs': rows, 'duplicate_players': duplicates}
    if reuse_path is not None:
        result['reused_original_evidence'] = {'path': registry.relative_workspace_path(reuse_path),
            'sha256': registry.sha256_file(reuse_path), 'clubs': len(reused),
            'original_bytes_rehashed': True, 'scope': 'Completed successful reparses only; gaps reconsidered'}
    dest = output_root / season / 'opening-review.json'; dest.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(dest, result)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--opening-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse-root', type=Path)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=1)
    parser.add_argument('--resume', action='store_true', help='reuse only exactly bound completed reports')
    args = parser.parse_args(); summaries = []
    pending = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        saved = args.output / season / 'opening-review.json'
        if saved.exists():
            if not args.resume: raise ValueError('completed opening review exists; use --resume')
            document = json.loads(saved.read_text()); release = registry.load_preferred_release(season)
            capture = args.opening_root / season / 'opening-lineups.json'
            expected = document['bindings']
            if (document['schema_version'], document['season'], expected['release_id'], expected['package_sha256'],
                    expected['eq_sha256'], expected['ent_sha256'], expected['opening_capture_sha256']) != (
                    SCHEMA, season, release.release_id, registry.sha256_file(release.package_path),
                    registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'), registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'),
                    registry.sha256_file(capture) if capture.exists() else None):
                raise ValueError('completed opening review is stale')
            for club in document['clubs']:
                for source in club.get('evidence', {}).get('raw_sources', []):
                    if registry.sha256_file(ROOT / source['path']) != source['sha256']:
                        raise ValueError('completed original opening evidence changed')
            summaries.append(document['summary']); print(json.dumps({'existing_proof_reused': True, **document['summary']}), flush=True)
            continue
        old = args.reuse_root / season / 'opening-review.json' if args.reuse_root else None
        pending.append((season, old if old and old.exists() else None))
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        work = [pool.submit(audit, season, args.opening_root, args.output, old) for season, old in pending]
        for future in concurrent.futures.as_completed(work):
            summary = future.result(); summaries.append(summary)
            print(json.dumps(summary), flush=True)
    summaries.sort(key=lambda row: row['season'])
    totals = sum((collections.Counter({k: v for k, v in s.items() if k != 'season'}) for s in summaries), collections.Counter())
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': summaries, 'totals': dict(totals), 'historical_verification_complete': False})


if __name__ == '__main__':
    main()
