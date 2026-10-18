#!/usr/bin/env python3
"""Audit all registered club rosters against external source bytes and runtime.

Read-only: no recipe or game writes. A source-list match does not certify an
August squad, a detailed role, or a missing player. Report those separately.
The legacy 2015 English lane is included, not omitted because its world
package contains only foreign clubs.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import gzip
import html
from functools import lru_cache
from html.parser import HTMLParser
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import capture_footballsquads_season as csv_source
from scripts import capture_footballsquads_web_season as web_source
from scripts import capture_ntf_historical_carrier_squads_v1 as ntf_source
from scripts import capture_transfermarkt_historical_squads_v1 as tm_source
from scripts.season_carrier_allocation_v1 import COUNTRY_GROUPS, ENGLISH_NON_LEAGUE_CARRIER_IDS
from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier
from app.editor_actions import _indexed_variable_name_runtime_segments
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_identity import read_indexed_player_id

SCHEMA = 'pm99-historical-roster-audit-v1'
POSITIONS = {0: 'G', 1: 'D', 2: 'M', 3: 'F'}
ROLE_LABELS = (
    'Goalkeeper', 'Right Back', 'Left Back', 'Sweeper', 'Inside Centre Left',
    'Inside Centre Right', 'Right Midfielder', 'Inside Right', 'Centre Forward',
    'Central Midfielder', 'Left Midfielder', 'Right Winger', 'Central Striker',
    'Left Winger', 'Defensive Midfielder', 'Right Forward', 'Left Forward', 'Inside Left',
)


def normalise(value: Any) -> str:
    return ''.join(c.casefold() for c in unicodedata.normalize('NFKD', str(value or ''))
                   if c.isalnum() and not unicodedata.combining(c))


def person_identity_key(player: dict[str, Any]) -> tuple[str, str] | None:
    """Country-independent identity candidate, never a lossy display alias."""
    name = player.get('source_name') or player.get('name')
    date = player.get('facts', {}).get('birth_date')
    if not isinstance(name, str) or not name.strip() or not isinstance(date, str):
        return None
    return normalise(name), date


def role_conflict(position: Any, role: int) -> bool:
    if position not in ('G', 'D', 'M', 'F') or role == 98:
        return False
    return (position == 'G' and role != 0) or (
        position in ('D', 'M', 'F') and role == 0
    ) or (position == 'F' and role in (1, 2, 3, 4, 5)) or (
        position == 'D' and role in (8, 12, 15, 16)
    )


def native_player(payload: bytes, carrier: int) -> dict[str, Any]:
    """Read the actual loader's strings and roles, not the old offset heuristic."""
    if read_indexed_player_id(payload) != carrier:
        raise ValueError('native self-ID differs from directory carrier')
    segments = _indexed_variable_name_runtime_segments(payload)
    # Real indexed records have self-ID + shirt number, then strings at 8.
    if segments['first_len_offset'] != 8:
        raise ValueError('not the native indexed string prefix')
    end = segments['full_name_end']
    if end + 28 > len(payload):
        raise ValueError('native metadata block overruns record')
    name = payload[segments['full_name_start']:end].decode('cp1252')
    roles = [(payload[end + 2 + slot] ^ 0x61) - 1
             if payload[end + 2 + slot] ^ 0x61 else 98 for slot in range(6)]
    if any(role not in (*range(18), 98) for role in roles):
        raise ValueError(f'unsupported role codes: {roles}')
    return {'name': name, 'family': payload[2:5].hex(), 'name_end': end,
            'position': POSITIONS.get(payload[end + 11] ^ 0x61),
            'roles': roles, 'display_role': ROLE_LABELS[roles[0]] if roles[0] != 98 else 'Unassigned'}


def club_group(club: dict[str, Any]) -> str | None:
    if club['division'] != 'preserve-existing-mode1-membership':
        return 'england'
    carrier = int(club['carrier_id'])
    return 'england' if carrier in ENGLISH_NON_LEAGUE_CARRIER_IDS or group_for_carrier(carrier) == 'english-non-league' else group_for_carrier(carrier)


def source_group(value: str) -> str | None:
    return 'england' if value in ('eng', 'england', 'english-non-league') else COUNTRY_GROUPS.get(value)


def club_names(group: str | None, name: str, full_name: str = '') -> set[str]:
    """Only explicit, country-scoped aliases; never fuzzy club matching."""
    groups = {group, 'english-non-league'} if group == 'england' else {group}
    # Keep original table order and country scope. Including actual alias
    # contents in the key also makes edits/fixtures invalidate the cache.
    aliases = tuple((baseline, tuple(variants))
        for table in (ntf_source.ALIASES, ntf_source.HISTORICAL_ALIASES)
        for (country, baseline), variants in table.items() if country in groups)
    return set(_expanded_club_names(name, full_name, aliases))


@lru_cache(maxsize=32)
def _normalised_club_alias_groups(aliases):
    return tuple(frozenset(normalise(n) for n in (baseline, *variants))
                 for baseline, variants in aliases)


@lru_cache(maxsize=8192)
def _expanded_club_names(name, full_name, aliases):
    names = {normalise(n) for n in (name, full_name) if n != ''}
    for group in _normalised_club_alias_groups(aliases):
        if names & group:
            names.update(group)
    return frozenset(names)


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title, self.complete, self.parts = False, False, []

    def handle_starttag(self, tag, attrs):
        if tag == 'title' and not self.complete:
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title' and self.in_title:
            self.in_title, self.complete = False, True

    def handle_data(self, data):
        if self.in_title:
            self.parts.append(data.strip())


def original_html_title(payload):
    # A title check needs only the head, not thousands of player-table nodes.
    parser = _TitleParser()
    parser.feed(payload[:65536].decode('utf-8', errors='replace'))
    return html.unescape(' '.join(parser.parts).strip()) if parser.complete else ''


def historical_html_title(payload: bytes, provider: str, season: str, group: str | None,
                          *, allow_calendar_ending_year=True) -> tuple[str, str]:
    """Bind club AND period to the original document, not a capture's labels."""
    title = original_html_title(payload)
    pattern = (r'(.+?)\s+\((\d{4}(?:/\d{2})?)\)\s*\|\s*National Football Teams' if provider == 'ntf'
               else r'(.+?)\s+-\s+(?:Detailed squad|Squad)\s+(\d{2}/\d{2}|\d{4})(?:\s+\(Detailed view\))?\s*\|\s*Transfermarkt')
    matched = re.fullmatch(pattern, title)
    if matched is None:
        raise ValueError('original HTML title has no supported dated club identity')
    name, period = matched.groups()
    start = int(season[:4])
    accepted = {str(start), season[:4] + '/' + season[-2:], season[2:4] + '/' + season[-2:]}
    if allow_calendar_ending_year and group in ntf_source.CALENDAR_YEAR_COUNTRIES:
        accepted.add(str(start + 1))
    if period not in accepted:
        raise ValueError(f'original title period {period} is outside {season}')
    return name.strip(), period


def add_legacy_english(package: dict[str, Any], season: str) -> tuple[list, list, list]:
    clubs, players = list(package['clubs']), list(package['players'])
    bindings = []
    if season != '2015-16' or any(c['division'] != 'preserve-existing-mode1-membership' for c in clubs):
        return clubs, players, bindings
    path = ROOT / '.local/season-2015-16/english92-2015-16-build36-native-no-photo/2015-16-english92-manifest.json'
    raw = path.read_bytes()
    manifest = json.loads(raw)
    country_table = compiler._extract_country_codes_from_textos(
        registry.load_preferred_release(season).game_path / 'DBDAT/TEXTOS.PKF')
    country_names = {value: name for name, value in country_table.items()}
    bindings.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'purpose': 'legacy-English-declaration-not-independent-source'})
    owned = {}
    for team in manifest['teams']:
        cid = f"legacy-english-club-{team['record_id']}"
        club = {'id': cid, 'carrier_id': team['record_id'], 'name': team['club'],
                'full_name': team.get('full_club_name', team['club']), 'division': team['division'],
                'roster_player_ids': [f'legacy-english-player-{id}' for id in team['roster_player_record_ids']]}
        clubs.append(club)
        for id in team['roster_player_record_ids']:
            owned[id] = cid
    for player in manifest['players']:
        carrier = player['record_id']
        if carrier not in owned:
            continue
        players.append({'id': f'legacy-english-player-{carrier}', 'carrier_id': carrier,
                        'name': player['name'], 'club_id': owned[carrier], 'carrier_family': 'dd6361',
                        'facts': {'birth_date': player.get('birth_date'),
                                  'nationality': country_names.get(player.get('nationality_code')),
                                  'height_cm': player.get('height_cm'),
                                  'weight_kg': player.get('weight_kg'),
                                  'shirt_number': player.get('shirt_number'),
                                  'primary_position': POSITIONS.get(player.get('position_code')),
                                  'fine_roles': player.get('fine_roles')}})
    return clubs, players, bindings


def load_sources(season: str) -> tuple[list[dict], list[dict]]:
    paths = sorted((ROOT / 'seasons' / season / 'sources').glob('*.json'))
    # Independently captured backfills live here, not in the original
    # FootballSquads directory. Only the exact capture schema/season passes.
    paths += sorted((ROOT / '.local' / ('season-' + season)).glob('*.json'))
    if season == '2015-16':
        paths += [ROOT / '.local/season-sources/footballsquads-2015-world-hybrid.json',
                  ROOT / '.local/season-sources/footballsquads-2015-16.json']
    clubs, bindings, seen = [], [], set()
    label = f'{season[:4]}/{season[-2:]}'
    for path in paths:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        document = json.loads(raw)
        if document.get('schema_version') != 'pm99-footballsquads-season-capture-v1':
            continue
        # Composed calendar/split-year captures are accepted only when their
        # explicit season label is the selected season, never by file name.
        if document.get('season', {}).get('label') != label:
            continue
        bindings.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'source': document.get('source')})
        for row in document['clubs']:
            key = (row['country_catalog'], row['club_name'], row['source_path'], row['source_sha256'])
            if key in seen:
                continue
            seen.add(key)
            clubs.append(dict(row))
    return clubs, bindings


class SourceVerifier:
    """Check original hash-bound raw files and independently reparse them."""
    def __init__(self, season: str, previous=None, source_bindings=None):
        self.season = season
        self.roots = [ROOT / '.local/external-sources/cache.footballsquads']
        self.roots += sorted((ROOT / '.local/external-sources/footballsquads-web').glob(season + '-*'))
        self.roots += sorted((ROOT / '.local' / ('season-' + season)).glob('*cache*'))
        self.results = {}
        self.previous = {}
        if previous is not None:
            if (previous['schema_version'] != SCHEMA or previous['season'] != season or
                    previous['bindings']['sources'] != source_bindings):
                raise ValueError('cannot reuse source reparses from changed captures or another season')
            grouped = collections.defaultdict(list); checked = {}
            for row in previous['raw_sources']:
                if row.get('local_path'):
                    path = ROOT / row['local_path']
                    if path not in checked: checked[path] = registry.sha256_file(path)
                    if checked[path] != row['source_sha256']:
                        raise ValueError('original source changed since its completed reparse')
                grouped[(row['source_path'], row['source_sha256'])].append(row)
            for key, rows in grouped.items():
                if all(r == rows[0] for r in rows): self.previous[key] = rows[0]

    def verify(self, row: dict) -> dict:
        key = (row['source_path'], row['source_sha256'], hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
        if key in self.results:
            return self.results[key]
        if key[:2] in self.previous:
            self.results[key] = dict(self.previous[key[:2]])
            return self.results[key]
        relative = Path(key[0])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe source path')
        result = {'status': 'raw-source-unavailable', 'source_path': key[0], 'source_sha256': key[1]}
        for root in self.roots:
            path = root / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != key[1]:
                continue
            result['local_path'] = str(path.relative_to(ROOT))
            try:
                if path.suffix == '.txt':
                    title = next(line for line in path.read_text().splitlines() if line.strip())
                    matched = csv_source._TITLE.fullmatch(title)
                    if matched is None:
                        raise ValueError('not a dated squad title')
                    source_label = matched.group(3)
                    start = int(source_label[:4])
                    accepted = {int(self.season[:4])}
                    if source_group(row['country_catalog']) in ntf_source.CALENDAR_YEAR_COUNTRIES:
                        accepted.add(int(self.season[:4]) + 1)
                    if start not in accepted:
                        raise ValueError('raw source title is outside selected season')
                    parsed = csv_source._read_club_file(path, root=root, season_start=start, season_label=source_label)
                    parsed_name, parsed_players = parsed['club_name'], parsed['players']
                elif 'ntf' in root.name:
                    family = source_group(row['country_catalog'])
                    _, country = ntf_source.SOURCE_COUNTRIES[family]
                    parsed_name, label = historical_html_title(path.read_bytes(), 'ntf', self.season, family)
                    parsed_players = [ntf_source.canonical_player(p) for p in ntf_source.parse_squad_page(
                        path.read_bytes(), country_name=country.replace('_', ' '), season_label=label)]
                elif 'transfermarkt' in root.name:
                    parsed_name, _ = historical_html_title(path.read_bytes(), 'transfermarkt', self.season,
                                                          source_group(row['country_catalog']))
                    parsed_players = [tm_source.canonical_player(p) for p in tm_source.parse_squad(path.read_bytes())]
                else:
                    parsed_name, parsed_players = web_source.parse_club_page(
                        payload=path.read_bytes(), source_year=int(self.season[:4]), label=str(path))
                if normalise(parsed_name) not in club_names(source_group(row['country_catalog']), row['club_name']) or parsed_players != row['players']:
                    result['status'] = 'raw-capture-disagrees'
                else:
                    result['status'] = 'raw-source-reparsed'
            except Exception as exc:
                result.update(status='raw-source-unparseable', error=str(exc))
            break
        self.results[key] = result
        return result


def source_matches(player: dict, candidates: list[dict]) -> tuple[str, list[dict]]:
    names = {normalise(player.get('source_name')), normalise(player['name'])} - {''}
    matches = [row for row in candidates if normalise(row['facts']['name']) in names]
    dob = player.get('facts', {}).get('birth_date')
    if isinstance(dob, str):
        exact = [row for row in matches if row['facts'].get('birth_date') == dob]
        if exact:
            return 'name-and-birth-date', exact
        known = [row for row in matches if row['facts'].get('birth_date')]
        if known:
            return 'birth-date-disagrees', known
    return ('name-only' if matches else 'not-found'), matches


def audit_season(season: str, output: Path, original_audit_path=None, *, compressed=False) -> dict:
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy_bindings = add_legacy_english(package, season)
    by_id = {p['id']: p for p in players}
    sources, source_bindings = load_sources(season)
    prior = json.loads(original_audit_path.read_text()) if original_audit_path else None
    verifier = SourceVerifier(season, prior, source_bindings)
    sources_by_club = collections.defaultdict(list)
    sources_by_name = collections.defaultdict(list)
    for source in sources:
        verified = verifier.verify(source)
        source['_raw_status'] = verified['status']
        key = (source_group(source['country_catalog']), normalise(source['club_name']))
        for facts in source['players']:
            row = {'facts': facts, 'club': source['club_name'], 'country': key[0],
                   'source_path': source['source_path'], 'source_sha256': source['source_sha256'],
                   'raw_status': verified['status']}
            sources_by_club[key].append(row)
            sources_by_name[normalise(facts['name'])].append(row)
    jug_data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq_data = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug_entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    eq_entries = {int(e.record_id): e for e in IndexedFDIFile.from_bytes(eq_data).entries}
    native_cache, club_rows, player_rows = {}, [], []
    for club in clubs:
        carrier = int(club['carrier_id'])
        group = club_group(club)
        candidates = [row for name in club_names(group, club['name'], club.get('full_name', ''))
                      for row in sources_by_club.get((group, name), [])]
        rows_for_club = []
        entry = eq_entries.get(carrier)
        native_club = parse_eq_external_team_roster_payload(
            eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length], {}) if entry else None
        expected = [int(by_id[id]['carrier_id']) for id in club['roster_player_ids'] if id in by_id]
        actual = [row.player_record_id for row in native_club.rows] if native_club else None
        for id in club['roster_player_ids']:
            player = by_id.get(id)
            if player is None:
                rows_for_club.append({'player_id': id, 'membership_status': 'recipe-player-missing'})
                continue
            pid = int(player['carrier_id'])
            if pid not in native_cache:
                try:
                    native_cache[pid] = native_player(jug_entries[pid].decode_payload(jug_data), pid)
                except Exception as exc:
                    native_cache[pid] = {'error': str(exc)}
            native = native_cache[pid]
            match_basis, matches = source_matches(player, candidates)
            elsewhere_candidates = []
            if not matches:
                for name in {normalise(player['name']), normalise(player.get('source_name'))} - {''}:
                    elsewhere_candidates += sources_by_name.get(name, [])
                elsewhere_basis, elsewhere = source_matches(player, elsewhere_candidates)
            else:
                elsewhere_basis, elsewhere = 'not-needed', []
            status = ('source-club-unavailable' if not candidates else 'player-not-in-source-squad')
            if matches:
                status = 'birth-date-conflict' if match_basis == 'birth-date-disagrees' else (
                    'captured-squad-match' if all(m['raw_status'] == 'raw-source-reparsed' for m in matches)
                    else 'unverified-capture-match')
            elif elsewhere and elsewhere_basis == 'name-and-birth-date':
                status = 'captured-at-other-club'
            facts = player.get('facts', {})
            source_positions = sorted({m['facts'].get('position') for m in matches if m['facts'].get('position')})
            requested_position = facts.get('primary_position')
            roles = native.get('roles', [])
            row = {'season': season, 'club_id': club['id'], 'club': club['name'], 'club_carrier': carrier,
                   'playable': club['division'] != 'preserve-existing-mode1-membership',
                   'player_id': id, 'carrier_id': pid, 'name': player['name'],
                   'source_name': player.get('source_name'), 'birth_date': facts.get('birth_date'),
                   'membership_status': status, 'match_basis': match_basis,
                   'source_raw_verified': bool(matches) and all(m['raw_status'] == 'raw-source-reparsed' for m in matches),
                   'other_source_clubs': sorted({m['club'] for m in elsewhere}),
                   'source_positions': source_positions, 'recipe_position': requested_position,
                   'source_position_conflict': isinstance(requested_position, str) and bool(source_positions) and requested_position not in source_positions,
                   'native_name': native.get('name'), 'native_name_matches': normalise(native.get('name')) == normalise(player['name']),
                   'native_position': native.get('position'), 'display_role': native.get('display_role'),
                   'native_role_codes': roles, 'native_error': native.get('error'),
                   'display_role_conflict': bool(roles) and role_conflict(requested_position, roles[0]),
                   'native_position_conflict': isinstance(requested_position, str) and native.get('position') != requested_position,
                   'shared_slot': id in club.get('shared_preserve_player_ids', []),
                   'evidence': [{'path': m['source_path'], 'sha256': m['source_sha256'], 'raw_status': m['raw_status']} for m in matches]}
            rows_for_club.append(row)
            player_rows.append(row)
        club_rows.append({'season': season, 'id': club['id'], 'carrier_id': carrier, 'club': club['name'],
                          'country_group': group, 'playable': club['division'] != 'preserve-existing-mode1-membership',
                          'recipe_roster_count': len(expected), 'native_roster_count': len(actual) if actual is not None else None,
                          'native_roster_matches': actual == expected,
                          'native_club_name': native_club.short_name if native_club else None,
                          'source_available': bool(candidates),
                          'membership_status_counts': dict(collections.Counter(r['membership_status'] for r in rows_for_club)),
                          'missing_recipe_player_ids': [r['player_id'] for r in rows_for_club if r['membership_status'] == 'recipe-player-missing']})
    counts = collections.Counter(row['membership_status'] for row in player_rows)
    counts.update({'club_seasons': len(clubs), 'player_roster_occurrences': len(player_rows),
                   'unique_recipe_players': len(players), 'playable_clubs': sum(c['playable'] for c in club_rows),
                   'non_playable_clubs': sum(not c['playable'] for c in club_rows),
                   'native_roster_mismatches': sum(not c['native_roster_matches'] for c in club_rows),
                   'undeclared_native_clubs': len(set(eq_entries) - {int(c['carrier_id']) for c in clubs}),
                   'source_raw_verified_players': sum(r['source_raw_verified'] for r in player_rows),
                   'source_position_conflicts': sum(r['source_position_conflict'] for r in player_rows),
                   'display_role_conflicts': sum(r['display_role_conflict'] for r in player_rows),
                   'native_read_errors': sum(bool(r['native_error']) for r in player_rows),
                   'native_name_mismatches': sum(not r['native_name_matches'] for r in player_rows)})
    report = {'schema_version': SCHEMA, 'season': season, 'result': 'audit-complete-corrections-pending',
              'scope': 'All 543 native clubs, including separate legacy 2015 English lane',
              'temporal_limit': 'Season squad membership, NOT independently verified August ownership',
              'independence': 'Original external source files rehashed and reparsed; recipes are not their own authority',
              'bindings': {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
                           'jug_sha256': hashlib.sha256(jug_data).hexdigest(), 'eq_sha256': hashlib.sha256(eq_data).hexdigest(),
                           'sources': source_bindings, 'legacy': legacy_bindings},
              'summary': dict(counts), 'raw_sources': list(verifier.results.values()),
              'clubs': club_rows, 'players': player_rows}
    if original_audit_path:
        report['source_reuse'] = {'path': registry.relative_workspace_path(original_audit_path),
            'sha256': registry.sha256_file(original_audit_path),
            'scope': 'Unchanged capture and original bytes rehashed; completed raw reparses reused. Club/player joins and native reads recomputed.',
            'missing_sources_not_researched_again': True}
        report['independence'] = 'Completed independent raw reparses reused under unchanged capture/raw hashes; current club joins recomputed, not inherited'
    output.mkdir(parents=True, exist_ok=True)
    if compressed:
        destination = output / 'report.json.gz'
        # Compact evidence keeps the full individual findings, not just totals.
        # Exclusive creation prevents silently replacing a completed audit.
        with destination.open('xb') as stream:
            with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0, filename='') as archive:
                archive.write(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                         separators=(',', ':')).encode('utf-8'))
        return {'season': season, **dict(counts)}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for name, rows in [('clubs', club_rows), ('players', player_rows)]:
        with (output / (name + '.csv')).open('w', newline='') as handle:
            fields = list(rows[0]) if rows else []
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return {'season': season, **dict(counts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season', choices=['all', *registry.supported_seasons()])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    summaries = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        result = audit_season(season, args.output / season)
        summaries.append(result)
        print(json.dumps(result), flush=True)
    totals = dict(sum((collections.Counter({k: v for k, v in row.items() if k != 'season'}) for row in summaries), collections.Counter()))
    (args.output / 'summary.json').write_text(json.dumps({'schema_version': SCHEMA, 'seasons': summaries, 'totals': totals}, indent=2) + '\n')


if __name__ == '__main__':
    main()
