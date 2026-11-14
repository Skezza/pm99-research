#!/usr/bin/env python3
"""Replay cached season sources into a complete Native-slot preflight, never a release.

No network, allocations, preferred registration or database writes. Outputs are
immutable and logical-JSON aware. Missing pages become an executable fetch list,
not manual player cases. Annual rows do not establish opening ownership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import json_storage_io_v1 as storage_io
import scripts.json_storage_v1 as storage
from scripts import capture_transfermarkt_historical_squads_v1 as squads
from scripts import transfermarkt_calendar_year_policy_v1 as calendar
from scripts import season_english_fixed_carrier_authoring_v1 as english
from scripts import season_carrier_allocation_v1 as allocation
from scripts.capture_transfermarkt_opening_lineups_v1 import SnapshotCache, CaptureError, _competition_teams, USER_AGENT

SCHEMA = 'pm99-season-recipe-preflight-v1'
VERSION = 1
MAX_PAGE_BYTES = 8 * 1024 ** 2
DEFAULT_SCOPES = (
    ROOT / 'seasons/2000-01/sources/transfermarkt-historical-squad-scope-v1.json',
    ROOT / 'scripts/data/transfermarkt-historical-squad-scope-core-six-v1.json',
)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalise(value):
    # Case and spacing only. No substring, fuzzy, designation or surname match.
    return ' '.join(unicodedata.normalize('NFC', str(value)).casefold().split())


def season_year(value):
    match = re.fullmatch(r'((?:19|20)\d{2})[-/](\d{2})', value)
    if not match or (int(match[1]) + 1) % 100 != int(match[2]):
        raise ValueError('season must be consecutive YYYY-YY')
    return int(match[1])


def inventory_slots(registry):
    if registry.get('schema_version') != 'pm99-world-fixed-carrier-registry-v2':
        raise ValueError('unsupported foreign registry schema')
    rows = []
    for c in registry['carriers']:
        if type(c.get('carrier_id')) is not int or c.get('record_mode') != 1:
            raise ValueError('foreign registry requires mode-1 integer carriers')
        rows.append(dict(carrier_id=c['carrier_id'], lane='foreign', native_name=c['baseline_club']['name'],
            native_country_family=allocation.group_for_carrier(c['carrier_id']), division=None))
    if len(rows) != 451:
        raise ValueError('expected complete 451 foreign carrier registry')
    for division, ids in english.NATIVE_DIVISION_CARRIERS.items():
        rows.extend(dict(carrier_id=c, lane='english', native_name=None,
                         native_country_family='england', division=division) for c in ids)
    if len(rows) != 543 or len({r['carrier_id'] for r in rows}) != 543:
        raise ValueError('expected 543 distinct foreign/English carriers')
    return sorted(rows, key=lambda r: r['carrier_id'])


class VerifiedOfflineCache(SnapshotCache):
    """Existing cache reader, plus title checks for split seasons as well as calendar routes."""
    def __init__(self, directory, target_year):
        super().__init__(directory, offline=True, delay=0)
        self.target_year = target_year
        self.routes = {}
        self.missing = {}
        self.title_checks = {}
        self.rejected = {}

    def get(self, url, key):
        path = self.directory / key
        if not storage_io.is_file(path):
            self.missing[key] = dict(cache_key=key, url=url, reason='missing-cached-page')
            raise CaptureError(f'offline snapshot missing: {key}')
        if storage_io.size(path) > MAX_PAGE_BYTES:
            raise CaptureError(f'cached page exceeds {MAX_PAGE_BYTES} byte bound: {key}')
        payload = super().get(url, key)
        year = int(re.search(r'/saison_id/(\d{4})', url)[1])
        title = calendar._title_text(payload)
        # Provider competition names include retirement dates, e.g. (- 91/92).
        season_title = re.sub(r'\(\s*[-–—]\s*\d{2,4}\s*/\s*\d{2,4}\s*\)', '', title)
        text = re.sub(r'\s*[-–—/]\s*', '/', season_title)
        pairs = re.findall(r'(?<!\d)(\d{4}|\d{2})/(\d{4}|\d{2})(?!\d)', text)
        expected = {(str(year),str(year+1)),(str(year),f'{(year+1)%100:02d}'),
                    (f'{year%100:02d}',f'{(year+1)%100:02d}')}
        good = bool(pairs) and all(pair in expected for pair in pairs)
        if not pairs and year != self.target_year:
            # A bare foundation/anniversary year is not a calendar squad season.
            good = bool(re.search(rf'\b(?:squad|kader|season|saison|table|teams)\s+(?:season\s+)?{self.target_year}(?!\d)', text, re.I))
        self.title_checks[key] = dict(title=title, provider_year=year, matched=good)
        if not good:
            self.rejected[key] = dict(cache_key=key, reason='source-year-title-mismatch', title=title)
            raise CaptureError(f'source year/title mismatch: {key}: {title}')
        return payload


def replay_sources(year, scopes, cache):
    clubs, competitions, gaps = [], [], []
    for scope in sorted(scopes, key=lambda r: (r['country_catalog'], r['competition_catalog'], r['source_competition_code'])):
        configured = scope['source_competition_code']
        try:
            route = calendar.route_provider_year(year, configured, scope['country_catalog'])
        except calendar.RoutingError as exc:
            gaps.append(dict(scope=scope, reason='calendar-route-quarantined', detail=str(exc)))
            continue
        teams = None
        errors = []
        missing_before = set(cache.missing)
        for code in squads.competition_code_candidates(configured, year):
            try:
                teams = _competition_teams(season_start_year=route.provider_season_id,
                    target_season_start_year=year, competition_code=code, cache=cache)
                break
            except CaptureError as exc:
                errors.append(str(exc))
        if not teams:
            gaps.append(dict(scope=scope, reason='no-usable-cached-competition', details=errors))
            continue
        # Failed aliases are not work requests once this competition resolved.
        for key in set(cache.missing) - missing_before:
            cache.missing.pop(key)
        competitions.append(dict(scope=scope, effective_code=code, provider_year=route.provider_season_id,
            routing=route.document(), published_clubs=len(teams)))
        for team in sorted(teams, key=lambda t: (t.club_id, t.transfermarkt_name)):
            key = calendar.cache_key(kind='squad', target_year=year, provider_year=route.provider_season_id,
                                      code=code, club_id=team.club_id)
            slug = team.club_path.strip('/').split('/')[0]
            url = f'{squads.BASE_URL}/{slug}/kader/verein/{team.club_id}/saison_id/{route.provider_season_id}'
            row = dict(country_catalog=scope['country_catalog'], competition_catalog=scope['competition_catalog'],
                source_competition_code=code, club_name=team.transfermarkt_name,
                provider_club_id=str(team.club_id), source_path=key, source_url=url,
                provider_year=route.provider_season_id, target_year=year,
                evidence_kind='annual-squad-not-opening-ownership', players=[], status='missing-source')
            try:
                payload = cache.get(url, key)
                row['players'] = [squads.canonical_player(p) for p in squads.parse_squad_with_dom_fallback(payload)]
                if not row['players']:
                    raise CaptureError('no supported player rows')
                row.update(status='parsed-year-checked-annual-source', source_sha256=digest(payload),
                           title=cache.title_checks[key]['title'])
            except (CaptureError, ValueError) as exc:
                row.update(reason='unusable-or-missing-squad', detail=str(exc))
            clubs.append(row)
    return sorted(clubs, key=club_key), competitions, gaps


def club_key(c):
    return (c['country_catalog'], c['competition_catalog'], c['provider_club_id'])


def classify_slots(slots, clubs):
    rows = [dict(r) for r in slots]
    foreign = defaultdict(list)
    eng = defaultdict(list)
    for club in clubs:
        if club['country_catalog'] == 'eng':
            division = english.COMPETITION_DIVISION.get(club['competition_catalog'])
            if division:
                eng[division].append(club)
        else:
            family = allocation.COUNTRY_GROUPS.get(club['country_catalog'])
            if family is not None:
                foreign[(family, normalise(club['club_name']))].append(club)
    eng_slots = defaultdict(list)
    for row in rows:
        if row['lane'] == 'english':
            eng_slots[row['division']].append(row)
            continue
        candidates = foreign.get((row['native_country_family'], normalise(row['native_name'])), []) if row['native_country_family'] is not None else []
        if len(candidates) == 1:
            bind_candidate(row, candidates[0], 'exact-name-and-native-country-family-candidate')
        else:
            row.update(status='ambiguous-name-candidates' if candidates else 'no-exact-source-candidate',
                candidate_count=len(candidates), historical_identity_verified=False, opening_ownership_verified=False)
    overflow = []
    for division, targets in eng_slots.items():
        sources = sorted(eng.get(division, []), key=lambda c: (normalise(c['club_name']), c['provider_club_id']))
        # A capacity proposal, NOT a historical identity/ownership decision.
        for row, club in zip(sorted(targets, key=lambda r: r['carrier_id']), sources):
            bind_candidate(row, club, 'division-capacity-proposal-not-authoring')
            row['status'] = 'division-capacity-proposal' if club['players'] else 'division-capacity-proposal-source-unusable'
        for row in sorted(targets, key=lambda r: r['carrier_id'])[len(sources):]:
            row.update(status='no-source-for-division-slot', historical_identity_verified=False, opening_ownership_verified=False)
        overflow.extend(dict(source_club=club_key(c), reason='source-division-exceeds-native-capacity') for c in sources[len(targets):])
    return sorted(rows, key=lambda r: r['carrier_id']), sorted(overflow, key=lambda r: r['source_club'])


def bind_candidate(row, source, method):
    row.update(status='annual-source-candidate' if source['status'] == 'parsed-year-checked-annual-source' else 'candidate-page-missing-or-unusable',
        candidate=dict(source_club_key=club_key(source), club_name=source['club_name'], provider_club_id=source['provider_club_id'],
                       source_path=source['source_path'], source_sha256=source.get('source_sha256')),
        match_method=method, historical_identity_verified=False, opening_ownership_verified=False)


def assemble_report(season, registry, clubs, competitions, source_gaps, cache, inputs):
    slots, overflow = classify_slots(inventory_slots(registry), clubs)
    unique_pages = {}
    for c in clubs:
        unique_pages.setdefault(c['source_path'], c)
    players = [p for c in unique_pages.values() for p in c['players']]
    bound_keys = {tuple(r['candidate']['source_club_key']) for r in slots if r.get('candidate')}
    unmatched = [dict(source_club_key=club_key(c), club_name=c['club_name'],
        reason='no-slot-proposal-or-unmapped-country') for c in clubs if club_key(c) not in bound_keys]
    ids = Counter((p['source_identity']['provider'], p['source_identity']['player_id'])
                  for p in players if p.get('source_identity'))
    claims = defaultdict(set)
    unknown_names = defaultdict(list)
    for c in clubs:
        c['identity_metrics'] = dict(rows=len(c['players']), rows_with_provider_id=sum(bool(p.get('source_identity'))for p in c['players']),
            rows_missing_dob=sum(not p.get('birth_date')for p in c['players']))
        for p in c['players']:
            if not p.get('source_identity'):
                unknown_names[normalise(p.get('name',''))].append(dict(club_key=club_key(c),birth_date=p.get('birth_date')))
    for club in clubs:
        for p in club['players']:
            if p.get('source_identity'):
                ident = p['source_identity']; claims[(ident['provider'], ident['player_id'])].add(club['provider_club_id'])
    snapshots = sorted(cache.used.values(), key=lambda r: r['cache_path'])
    result = dict(schema_version=SCHEMA, version=VERSION, season=season,
        state='preflight-partial-not-generator-completion', full_d1_complete=False,
        expected_slots=543, slots=slots, scope_observations=competitions, source_gaps=source_gaps,
        source_clubs=clubs, source_capacity_omissions=overflow, source_clubs_without_slot=unmatched,
        coverage=dict(foreign_slots=451, english_slots=92, parsed_squad_pages=sum(bool(c['players']) for c in unique_pages.values()),
            source_club_observations=len(clubs), unique_source_pages=len(unique_pages),
            division_capacity_proposals=sum(r['status']=='division-capacity-proposal' for r in slots),
            parsed_player_rows=len(players), rows_with_provider_id=sum(ids.values()), unique_provider_ids=len(ids),
            candidate_slots_with_annual_source=sum(r['status'] == 'annual-source-candidate' for r in slots),
            slot_status_counts=dict(sorted(Counter(r['status'] for r in slots).items())),
            club_identity_verified=0, opening_owner_verified=0,
            managers='not-evaluated', opening_xi='not-evaluated', transfer_dates='not-evaluated'),
        same_name_unidentified_candidates=[dict(name=k,observations=v)for k,v in sorted(unknown_names.items())if k and len(v)>1],
        cross_club_identity_claims=[dict(provider=k[0], player_id=k[1], provider_club_ids=sorted(v))
                                   for k,v in sorted(claims.items()) if len(v)>1],
        input_lock=dict(schema_version='pm99-season-preflight-input-lock-v1', season=season,
            environment=dict(python=list(sys.version_info[:3]),unicode=unicodedata.unidata_version,beautifulsoup=__import__('bs4').__version__),
            inputs=inputs, snapshots=snapshots),
        source_validation=dict(title_checks=dict(sorted(cache.title_checks.items())), rejected=list(cache.rejected.values())),
        fetch_requests=[cache.missing[k] for k in sorted(cache.missing)],
        next_required_measurements=['dated arrivals/departures/loans', 'manager at roster cutoff',
            'reference fixture XI/bench', 'historical club continuity/replacement', 'country-era source routing'])
    return result


class BoundedProbeCache(SnapshotCache):
    """Only explicitly requested probes may fetch, each at most 8 MiB/20 seconds."""
    def get(self, url, key):
        path = self.directory/key
        if storage_io.is_file(path) or self.offline:
            if storage_io.is_file(path) and storage_io.size(path)>MAX_PAGE_BYTES:
                raise CaptureError('cached probe page exceeds size bound')
            return super().get(url,key)
        with urlopen(Request(url,headers={'User-Agent':USER_AGENT,'Accept-Language':'en-GB,en;q=0.9'}),timeout=20) as response:
            expected_id = re.search(r'/verein/(\d+)',url)[1]
            if not re.search(rf'/verein/{expected_id}(?:/|$)',urlsplit(response.geturl()).path):
                raise CaptureError('source redirected away from the requested club identity')
            payload = response.read(MAX_PAGE_BYTES+1)
        if len(payload)>MAX_PAGE_BYTES:
            raise CaptureError('probe response exceeds size bound')
        self.validator(payload,url)
        path.parent.mkdir(parents=True,exist_ok=True)
        with storage_io.open_file(path,'xb') as handle:
            handle.write(payload)
        self.used[key]=dict(cache_path=key,sha256=digest(payload),url=url)
        return payload


def probe_managers(clubs, count, snapshot, directory, *, offline):
    """Bounded provider-availability measurement, not a Native manager assignment."""
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError('manager probe must be between 1 and 4 country samples')
    on = date.fromisoformat(snapshot)
    from scripts.capture_opening_manager_history_supplements_v1 import manager_at_date, ManagerHistoryError
    cache = BoundedProbeCache(directory, offline=offline, delay=0)
    chosen = {}
    for c in sorted(clubs, key=club_key):
        if c['players']:
            chosen.setdefault(c['country_catalog'], c)
    observations, snapshots = [], []
    for country, c in sorted(chosen.items())[:count]:
        slug = c['source_url'].split('/')[3]
        url = f"{squads.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{c['provider_club_id']}"
        key = f"manager-history/{c['provider_club_id']}.html"
        error_path = directory/'probe-errors'/f"{c['provider_club_id']}-{on.isoformat()}.json"
        row = dict(country_catalog=country, source_club=c['club_name'], provider_club_id=c['provider_club_id'],
                   snapshot_date=on.isoformat(), url=url)
        if storage_io.is_file(error_path):
            event = storage.read_json(error_path)
            if event.get('url') != url or event.get('schema_version') != 'pm99-source-probe-failure-v1':
                raise ValueError('saved probe failure does not match the requested source')
            row.update(status='source-request-failed', failure=event)
            snapshots.append(dict(cache_path=f"probe-errors/{error_path.name}",sha256=storage.sha256_file(error_path),url=url))
        else:
            try:
                payload = cache.get(url,key)
                try:
                    name, manager_id = manager_at_date(payload,on)
                    row.update(status='dated-manager-parsed',manager_name=name,provider_manager_id=manager_id)
                except ManagerHistoryError as exc:
                    row.update(status='manager-history-not-uniquely-parsed',detail=str(exc))
            except (URLError, TimeoutError, CaptureError) as exc:
                if offline:
                    raise ValueError(f'locked probe source missing or unusable: {key}: {exc}') from exc
                event = dict(schema_version='pm99-source-probe-failure-v1',url=url,
                    reason=type(exc).__name__,http_status=getattr(exc,'code',None),detail=str(exc))
                error_path.parent.mkdir(parents=True,exist_ok=True)
                storage.write_bytes(error_path,canonical(event),compressed=False,overwrite=False)
                row.update(status='source-request-failed',failure=event)
                snapshots.append(dict(cache_path=f"probe-errors/{error_path.name}",sha256=storage.sha256_file(error_path),url=url))
            finally:
                if not offline:
                    time.sleep(1)
        observations.append(row)
    snapshots += sorted(cache.used.values(),key=lambda r:r['cache_path'])
    return observations, sorted(snapshots,key=lambda r:r['cache_path'])


def snapshot_coverage(database, receipt_path, year, player_ids):
    """Measure a hash-pinned local dataset with read-only, bounded SQL; no ownership inference."""
    receipt = storage.read_json(receipt_path)
    actual = storage_io.physical_sha256_file(database)
    if actual != receipt['source']['database_sha256']:
        raise ValueError('local transfer snapshot differs from pinned receipt')
    import duckdb
    connection = duckdb.connect(str(database),read_only=True)
    try:
        connection.execute("SET memory_limit='128MB'")
        connection.execute('SET threads=1')
        if connection.execute('SELECT * FROM version').fetchall() != [(receipt['source']['database_version'],)]:
            raise ValueError('pinned dataset version differs')
        rows = []
        for y in range(year-1,year+2):
            count,people = connection.execute(
                'SELECT count(*),count(DISTINCT player_id) FROM transfers WHERE transfer_date>=? AND transfer_date<?',
                [date(y,1,1),date(y+1,1,1)]).fetchone()
            rows.append(dict(year=y,transfer_rows=count,unique_players=people))
        matching = connection.execute(
            'SELECT count(DISTINCT player_id) FROM transfers WHERE player_id IN (SELECT unnest(?)) AND transfer_date>=? AND transfer_date<?',
            [sorted(set(int(x)for x in player_ids)),date(year-1,1,1),date(year+2,1,1)]).fetchone()[0]
        games = connection.execute('SELECT count(*) FROM games WHERE season=?',[year]).fetchone()[0]
    finally:
        connection.close()
    if storage_io.physical_sha256_file(database) != actual:
        raise ValueError('read-only source snapshot unexpectedly changed')
    return dict(database_sha256=actual,receipt_sha256=storage.sha256_file(receipt_path),duckdb_version=duckdb.__version__,
                transfer_rows_by_year=rows,captured_people_with_period_transfer_rows=matching,
                captured_unique_people=len(set(player_ids)),games_in_target_season=games,
                dated_ownership_verified=False,limit='Counts measure this pinned dataset only; no row means no evidence here, not no transfer.')


def run(season, registry_path, scope_paths, cache_root, *, manager_probe=0, snapshot_date=None, probe_cache=None, probe_offline=True, database=None, receipt_path=None):
    year = season_year(season)
    season = f'{year}-{(year+1)%100:02d}'
    registry = storage.read_json(registry_path)
    scopes, seen = [], set()
    dependency_paths = [Path(__file__), Path(squads.__file__), Path(english.__file__), Path(allocation.__file__), Path(calendar.__file__),
        ROOT/'scripts/capture_transfermarkt_opening_lineups_v1.py',
        ROOT/'scripts/supplement_2015_ntf_with_transfermarkt.py',ROOT/'scripts/season_player_identity_v1.py',
        ROOT/'scripts/capture_2015_source_tail_squads_v1.py',ROOT/'scripts/prepare_2015_world_fifa16_carrier_allocation.py',
        ROOT/'scripts/capture_opening_manager_history_supplements_v1.py',ROOT/'scripts/json_storage_v1.py',ROOT/'scripts/json_storage_io_v1.py',ROOT/'scripts/json_storage_policy_v2.py']
    inputs = [dict(role='foreign-registry', sha256=storage.sha256_file(registry_path))]
    inputs += [dict(role='code:'+str(path.relative_to(ROOT)),sha256=digest(storage_io.read_bytes(path)))for path in dependency_paths]
    for path in scope_paths:
        rows, sha = squads.load_scope(path)
        inputs.append(dict(role='scope', sha256=sha))
        for r in rows:
            key = (r['country_catalog'], r['competition_catalog'])
            if key in seen:
                raise ValueError(f'duplicate scope selector: {key}')
            seen.add(key); scopes.append(r)
    cache = VerifiedOfflineCache(cache_root, year)
    clubs, competitions, gaps = replay_sources(year, scopes, cache)
    report = assemble_report(season, registry, clubs, competitions, gaps, cache,
                           sorted(inputs, key=lambda r: (r['role'],r['sha256'])))
    if manager_probe:
        if not snapshot_date or date.fromisoformat(snapshot_date).year != year or probe_cache is None:
            raise ValueError('manager probing requires explicit --snapshot-date in season start year and --probe-cache-root')
        samples, snapshots = probe_managers(clubs,manager_probe,snapshot_date,probe_cache,offline=probe_offline)
        report['manager_source_probe'] = samples
        report['input_lock']['manager_probe'] = dict(count=manager_probe,snapshot_date=snapshot_date,snapshots=snapshots)
        report['coverage']['managers'] = dict(sampled=len(samples),dated_source_parsed=sum(x['status']=='dated-manager-parsed'for x in samples))
    if database is not None or receipt_path is not None:
        if database is None or receipt_path is None:
            raise ValueError('snapshot measurement requires both --database and --pinned-receipt')
        ids=[p['source_identity']['player_id']for c in clubs for p in c['players']if p.get('source_identity')]
        observed=snapshot_coverage(database,receipt_path,year,ids)
        report['local_transfer_snapshot']=observed
        report['input_lock']['local_transfer_snapshot']=observed
    return report


def write_outputs(directory, report):
    if storage_io.exists(directory):
        raise ValueError('output directory must be new; evidence is never overwritten')
    directory.mkdir(parents=True)
    outputs = {'preflight.json': report, 'source-capture.json': dict(schema_version='pm99-preflight-source-observations-v1',
                season=report['season'], clubs=report['source_clubs']),
               'input-lock.json': dict(report['input_lock'], expected_report_sha256=digest(canonical(report))), 'fetch-requests.json': report['fetch_requests']}
    for name, value in outputs.items():
        storage.write_bytes(directory / name, canonical(value), compressed=False, overwrite=False)
    return {k:digest(canonical(v)) for k,v in outputs.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--registry', type=Path, default=ROOT/'seasons/2000-01/fixed-carrier-registry.json')
    parser.add_argument('--scope', action='append', type=Path)
    parser.add_argument('--cache-root', type=Path, default=ROOT/'.local/source-cache/transfermarkt-season-v1')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--lock', type=Path, help='require exact input and report replay from a saved logical JSON lock')
    parser.add_argument('--database',type=Path,help='optional pinned local DuckDB source, opened read-only')
    parser.add_argument('--pinned-receipt',type=Path,help='existing source snapshot receipt for --database')
    parser.add_argument('--probe-managers',type=int,default=0,help='explicit online manager-history availability sample, max4 countries')
    parser.add_argument('--snapshot-date',help='explicit query date for optional manager source sample (not a game roster decision)')
    parser.add_argument('--probe-cache-root',type=Path,help='separate immutable raw source/failure cache for optional probes')
    args = parser.parse_args(argv)
    try:
        report = run(args.season, args.registry, args.scope or DEFAULT_SCOPES, args.cache_root,
            manager_probe=args.probe_managers,snapshot_date=args.snapshot_date,probe_cache=args.probe_cache_root,probe_offline=bool(args.lock),database=args.database,receipt_path=args.pinned_receipt)
        if args.lock:
            lock = storage.read_json(args.lock)
            expected = lock.pop('expected_report_sha256', None)
            if lock != report['input_lock'] or expected != digest(canonical(report)):
                raise ValueError('locked replay differs: source inputs, parser or measured output changed')
        outputs = write_outputs(args.output_dir, report)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f'preflight failed: {exc}\n')
    print(json.dumps(dict(state=report['state'],coverage=report['coverage'],expected_slots=543,
                          pending_fetches=len(report['fetch_requests']),output_sha256=outputs),sort_keys=True))
    return 0 if report['full_d1_complete'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
