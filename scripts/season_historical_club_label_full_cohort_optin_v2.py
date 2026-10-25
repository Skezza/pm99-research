#!/usr/bin/env python3
"""Explicit source-bound complete roster identity proof; no opening XI claim."""
from __future__ import annotations
import json
import hashlib
import sys
from pathlib import PurePosixPath
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = next((parent for parent in Path(__file__).resolve().parents if (parent / 'scripts').is_dir()), None)
if ROOT is None:
    raise RuntimeError('cannot locate repository scripts directory')
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_source_package_builder_v1 as builder
from scripts.season_historical_roster_audit_v1 import club_group, club_names, source_group
from scripts.reconcile_opening_date_identities_v1 import _normalise
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _read_eq_inline_string
from app.models import PlayerRecord
from app.indexed_jug_identity import read_indexed_player_id
from scripts.prepare_2015_world_fifa16_carrier_allocation import group_for_carrier

SCHEMA = 'pm99-source-bound-full-roster-club-identity-witness-v2'
ARTIFACT_PREFIX = 'opening-squad-preallocation-'

def _source_rows(preallocation, selector):
    wanted = json.dumps(selector, sort_keys=True, separators=(',', ':'))
    matches = [source for source in preallocation['source_clubs']
        if json.dumps(source['selector'], sort_keys=True, separators=(',', ':')) == wanted]
    if len(matches) != 1:
        raise ValueError(f'exact source selector has {len(matches)} matches in bound preallocation')
    return matches[0]

def _matches(player, row):
    facts = row.get('facts', {})
    names = {_normalise(player.get('name', '')), _normalise(player.get('source_name', ''))}
    if _normalise(facts.get('name', '')) not in names:
        return False
    dob = facts.get('birth_date')
    return not dob or player.get('facts', {}).get('birth_date') == dob

def _selector_identity(selector):
    """Return a namespaced, content-bound selector key; never invent a provider ID."""
    required = ('country_catalog', 'competition_catalog', 'club_name', 'source_path', 'source_sha256')
    if not isinstance(selector, dict) or any(not isinstance(selector.get(k), str) or not selector[k] for k in required):
        raise ValueError('source selector is incomplete')
    if (len(selector['source_sha256']) != 64 or
            any(c not in '0123456789abcdef' for c in selector['source_sha256'])):
        raise ValueError('source selector source SHA-256 is malformed')
    material = json.dumps({k: selector[k] for k in required}, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(material).hexdigest()

def _provider_id(selector):
    """Preserve numeric provider IDs where published; otherwise report no ID."""
    try:
        return int(PurePosixPath(selector['source_path']).stem)
    except (KeyError, TypeError, ValueError):
        return None

def _reparse_soccerbase_august(season, selector, source):
    """Replay one August Soccerbase source cohort from every bound raw body."""
    from scripts.capture_soccerbase_august_squads_v1 import august_games, side_players, player_profile
    from scripts.season_soccerbase_original_opening_v1 import first_fixture
    import re
    match = re.fullmatch(r'soccerbase/team/([1-9][0-9]*)/august', selector['source_path'])
    if match is None or selector.get('competition_catalog') != 'soccerbase-august':
        raise ValueError('unsupported Soccerbase source selector shape')
    team_id = int(match.group(1))
    scope_path = ROOT / 'scripts/data/soccerbase-national-league-august-scope-v1.json'
    scope = json.loads(scope_path.read_text(encoding='utf-8'))
    scope_rows = [r for r in scope['seasons'] if r.get('season') == season]
    if len(scope_rows) != 1:
        raise ValueError('target season has no unique Soccerbase competition-year binding')
    scope_row = scope_rows[0]
    cache = ROOT / '.local' / ('season-' + season) / 'soccerbase-august-cache-v1'
    proof = []
    def original(kind, ident, expected_url):
        body_path = cache / kind / (str(ident) + '.html')
        receipt_path = body_path.with_name(body_path.name + '.source.json')
        raw = body_path.read_bytes()
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        digest = hashlib.sha256(raw).hexdigest()
        if (receipt != {'url': expected_url, 'sha256': digest} or digest != registry.sha256_file(body_path)):
            raise ValueError('Soccerbase body or adjacent original URL receipt changed')
        proof.append({'kind': kind, 'id': ident, 'url': expected_url,
            'path': registry.relative_workspace_path(body_path), 'sha256': digest,
            'receipt_path': registry.relative_workspace_path(receipt_path),
            'receipt_sha256': registry.sha256_file(receipt_path)})
        return raw
    team_url = f"https://www.soccerbase.com/teams/team.sd?season_id={scope_row['season_id']}&team_id={team_id}&teamTabs=results"
    team_raw = original('team', team_id, team_url)
    fixture = first_fixture(team_raw, team_id, season, scope_row['competition'],
        selector['club_name'], team_url)
    club_name, games = august_games(team_raw, competition=scope_row['competition'], start_year=int(season[:4]))
    if club_name != selector['club_name'] or not games or games[0][1] != fixture['game_id']:
        raise ValueError('raw Soccerbase team title/season/first fixture differs from source selector')
    soup = BeautifulSoup(team_raw, 'html.parser')
    ordered = []
    for game_date, game_id, _ in games:
        row = soup.select_one(f'tr#tgc{game_id}')
        home = row.select_one("td.homeTeam a[href*='team_id=']") if row else None
        away = row.select_one("td.awayTeam a[href*='team_id=']") if row else None
        get_id = lambda node: int(__import__('urllib.parse', fromlist=['parse_qs','urlparse']).parse_qs(
            __import__('urllib.parse', fromlist=['urlparse']).urlparse(node.get('href','')).query).get('team_id',['0'])[0]) if node else 0
        if row is None or team_id not in (get_id(home), get_id(away)):
            raise ValueError('raw August schedule row does not identify source club')
        side = 'teamA' if get_id(home) == team_id else 'teamB'
        match_url = f'https://www.soccerbase.com/matches/additional_information.sd?id_game={game_id}'
        match_raw = original('match', game_id, match_url)
        for player_id, label, position, starter in side_players(match_raw, side=side):
            ordered.append((player_id, label, position, starter, game_date, game_id))
    first_game = games[0][1]
    ordered.sort(key=lambda row: (not (row[5] == first_game and row[3]), row[4], row[5]))
    unique = []
    for player_id, label, position, _starter, _date, _game in ordered:
        if not any(row[0] == player_id for row in unique):
            unique.append((player_id, label, position))
    players = []
    for player_id, label, position in unique:
        profile_url = f'https://www.soccerbase.com/players/player.sd?player_id={player_id}'
        profile_raw = original('player', player_id, profile_url)
        players.append(player_profile(profile_raw, fallback_name=label, fallback_position=position))
    source_sha = hashlib.sha256((json.dumps({'games':[r[1] for r in games],
        'players':[r[0] for r in unique], 'team_id':team_id}, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')) + '\n').encode()).hexdigest()
    if source_sha != selector['source_sha256']:
        raise ValueError(f'raw Soccerbase August schedule/player ID digest differs from bound selector (computed {source_sha}, expected {selector["source_sha256"]}, games {len(games)}, players {len(unique)})')
    expected_players = [row['facts'] for row in sorted(source['players'], key=lambda row: row['source_row_index'])]
    if players != expected_players:
        first = next((i for i,(a,b) in enumerate(zip(players,expected_players)) if a!=b),None)
        detail = (players[first], expected_players[first]) if first is not None else None
        raise ValueError(f'raw Soccerbase August profiles differ from bound source cohort (counts {len(players)}/{len(expected_players)}; first mismatch {first}: {detail})')
    return {'method':'soccerbase-august-all-sheets-and-profiles-replayed-v1',
        'season':season, 'team_id':team_id, 'season_id':scope_row['season_id'],
        'competition':scope_row['competition'], 'club_name':club_name,
        'source_selector_sha256':_selector_identity(selector),
        'source_capture_sha256':registry.sha256_file(ROOT / '.local' / ('season-'+season) / 'soccerbase-august-english-nonleague-v1.json'),
        'raw_sources':proof, 'reparsed_player_count':len(players), 'first_fixture':fixture}

def _reparse_source_cohort(season, selector, source):
    if selector.get('competition_catalog') == 'soccerbase-august':
        return _reparse_soccerbase_august(season, selector, source)
    verifier = __import__('scripts.season_historical_roster_audit_v1', fromlist=['SourceVerifier']).SourceVerifier(season)
    # FootballSquads text sources are retained as original bodies in the
    # provider cache, while their source-row selectors live in preallocation.
    # Bind those exact selector fields to the already-adjudicated rows and let
    # the existing verifier reparse title/year/club/players from raw bytes.
    raw_players = [row['facts'] for row in sorted(source['players'], key=lambda row: row['source_row_index'])]
    raw = verifier.verify({**selector, 'players':raw_players})
    if raw.get('status') != 'raw-source-reparsed':
        raise ValueError('dated source body does not reparse for selected season and source club')
    return {'method':'existing-source-verifier-reparsed-v1', 'season':season,
        'source_selector_sha256':_selector_identity(selector), 'raw_source':raw}

def _native_owner_index(eq_bytes):
    indexed = IndexedFDIFile.from_bytes(eq_bytes)
    owners = {}
    for entry in indexed.entries:
        try:
            roster = parse_eq_external_team_roster_payload(
                eq_bytes[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        except Exception:
            roster = None
        if roster is None:
            continue
        for row in roster.rows:
            owners.setdefault(row.player_record_id, []).append(
                {'team_carrier_id': int(entry.record_id), 'flag': row.flag})
    return indexed, owners

def _native_jug_identity_index(jug_bytes, player_ids=None):
    """Decode selected JUG names and verify each selected embedded self ID."""
    indexed = IndexedFDIFile.from_bytes(jug_bytes)
    wanted = None if player_ids is None else {int(player_id) for player_id in player_ids}
    result = {}
    for entry in indexed.entries:
        if wanted is not None and int(entry.record_id) not in wanted:
            continue
        payload = entry.decode_payload(jug_bytes)
        try:
            native_id = read_indexed_player_id(payload)
        except ValueError:
            # Legacy/non-indexed entries cannot establish current JUG identity.
            continue
        if native_id != int(entry.record_id):
            raise ValueError(f'native JUG self ID {native_id} differs from directory ID {entry.record_id}')
        try:
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            name = str(getattr(record, 'name', '') or '').strip()
        except Exception as exc:
            raise ValueError(f'cannot decode native JUG player name for carrier {entry.record_id}') from exc
        if not name or name in ('Unknown Player', 'Parse Error'):
            raise ValueError(f'native JUG player name is unavailable for carrier {entry.record_id}')
        if int(entry.record_id) in result:
            raise ValueError(f'duplicate JUG player directory ID {entry.record_id}')
        result[int(entry.record_id)] = {'name': name, 'self_id': native_id,
            'payload_sha256': hashlib.sha256(payload).hexdigest()}
    if wanted is not None and wanted != set(result):
        raise ValueError(f'JUG directory is missing selected native player IDs: {sorted(wanted - set(result))}')
    return result

def _carrier_country_group(package, carrier_id):
    """Resolve country scope from the package or fixed carrier registry."""
    club = next((row for row in package.get('clubs', [])
        if int(row.get('carrier_id', -1)) == int(carrier_id)), None)
    if club is not None:
        return club_group(club)
    group = group_for_carrier(int(carrier_id))
    return 'england' if group == 'english-non-league' else group

def _bind_cohort(package, club, source, *, require_all, expected_artifact_id, owners,
                 native_players=None):
    players = [p for p in package['players'] if p.get('club_id') == club['id']]
    if not players:
        raise ValueError('package carrier has no roster rows')
    bindings, used = [], set()
    native_ids = set()
    for player in players:
        matches = [r for r in source['players'] if _matches(player, r)]
        if len(matches) > 1 or (require_all and len(matches) != 1):
            raise ValueError(f"actor {player.get('person_id')} has {len(matches)} exact source-row matches")
        if not matches:
            continue
        row = matches[0]
        source_person_id = builder._source_person_id(row)
        source_selector_person_id = builder._source_person_id(row, source_selector=source['selector'])
        if player.get('person_id') != source_person_id:
            raise ValueError(f"actor {player.get('person_id')} differs from exact source identity {source_person_id}")
        if player.get('proof', {}).get('artifact_id') != expected_artifact_id:
            raise ValueError(f"actor {player.get('person_id')} is not tied to the current preallocation artifact")
        native_id = int(player['carrier_id'])
        native_identity = None
        if native_players is not None:
            native_identity = native_players.get(native_id)
            if native_identity is None:
                raise ValueError(f'actor {player.get("person_id")} has no decoded native JUG identity')
            if _normalise(native_identity['name']) != _normalise(player.get('name', '')):
                raise ValueError(f'actor {player.get("person_id")} recipe name differs from decoded native JUG name')
            if native_identity['self_id'] != native_id:
                raise ValueError(f'actor {player.get("person_id")} native JUG self ID is invalid')
        if native_id in native_ids:
            raise ValueError('two source actors resolve to one native player carrier')
        native_ids.add(native_id)
        active = [owner for owner in owners.get(native_id, []) if owner['flag'] == 0]
        if active != [{'team_carrier_id': int(club['carrier_id']), 'flag': 0}]:
            raise ValueError(f'actor {player.get("person_id")} lacks one active native EQ owner at cited carrier')
        row_hash = row.get('source_row_sha256')
        if not row_hash or row_hash in used:
            raise ValueError('source row hash missing or reused by multiple actors')
        used.add(row_hash)
        binding = {'person_id': player['person_id'], 'source_row_index': row['source_row_index'],
            'source_row_sha256': row_hash, 'source_full_name': row['facts']['name'],
            'source_person_id': source_person_id,
            'source_selector_person_id': source_selector_person_id,
            'native_player_carrier_id': native_id,
            'native_active_owner_carrier_id': int(club['carrier_id']),
            'source_birth_date': row['facts'].get('birth_date'), 'package_full_name': player['name'],
            'package_source_name': player.get('source_name'), 'package_birth_date': player.get('facts', {}).get('birth_date')}
        if native_identity is not None:
            binding['native_decoded_name'] = native_identity['name']
            binding['native_self_id'] = native_identity['self_id']
            binding['native_payload_sha256'] = native_identity['payload_sha256']
        bindings.append(binding)
    if require_all and len(bindings) != len(players):
        raise ValueError('not every current roster actor is bound to the same source cohort')
    if require_all and native_ids != {int(str(pid).rsplit('-', 1)[-1]) for pid in club.get('roster_player_ids', [])}:
        raise ValueError('package team roster IDs differ from source-bound actor native IDs')
    if not require_all and not bindings:
        raise ValueError('prior-label selector has no positive identity anchor at cited carrier')
    bindings.sort(key=lambda r: r['person_id'])
    return bindings

def _assert_unique_source_cohort(preallocation, source, target_players, target_group):
    competitors = []
    for candidate in preallocation['source_clubs']:
        if candidate is source:
            continue
        if source_group(candidate.get('selector', {}).get('country_catalog', '')) != target_group:
            continue
        if all(sum(1 for row in candidate['players'] if _matches(player, row)) == 1
               for player in target_players):
            competitors.append(candidate['selector'])
    if competitors:
        raise ValueError('another complete source-cohort candidate also matches target roster actors')
    return []

def create_witness(*, season, source_root, carrier_id, expected_source_selector,
                   prior_label_source_selector=None, collision_carrier_id=None,
                   source_release_id=None):
    """Create a witness only when every current roster row joins exactly."""
    release = (registry.load_registered_release(season, source_release_id)
        if source_release_id is not None else registry.load_preferred_release(season))
    package = json.loads(release.package_path.read_bytes())
    artifact_id = ARTIFACT_PREFIX + season
    descriptor = next((a for a in package.get('artifacts', []) if a.get('id') == artifact_id), None)
    if not descriptor:
        raise ValueError('current package has no bound preallocation artifact')
    pre_path = Path(source_root) / season / 'opening-squad-preallocation.json'
    pre_bytes = pre_path.read_bytes()
    pre_sha = registry.sha256_file(pre_path)
    if pre_sha != descriptor.get('sha256'):
        raise ValueError('preallocation bytes do not match current package descriptor')
    pre = json.loads(pre_bytes)
    source = _source_rows(pre, expected_source_selector)
    if (prior_label_source_selector is None) != (collision_carrier_id is None):
        raise ValueError('old-label carrier and source selector must be supplied together')
    prior_source = (_source_rows(pre, prior_label_source_selector)
        if prior_label_source_selector is not None else None)
    if not source['players']:
        raise ValueError('source cohort is empty')
    by_carrier = {c['carrier_id']: c for c in package['clubs']}
    club, collision = by_carrier.get(carrier_id), by_carrier.get(collision_carrier_id) if collision_carrier_id is not None else None
    if club is None:
        raise ValueError('target carrier must exist')
    if collision_carrier_id is not None and (collision is None or collision_carrier_id == carrier_id):
        raise ValueError('optional old-label comparison carrier must be a distinct existing carrier')
    if collision is not None and club_group(club) != club_group(collision):
        raise ValueError('old-label comparison crosses country groups')
    if source_group(expected_source_selector.get('country_catalog', '')) != club_group(club):
        raise ValueError('target source country does not match target native carrier country')
    if collision is not None and source_group(prior_label_source_selector.get('country_catalog', '')) != club_group(collision):
        raise ValueError('prior-label source country does not match prior native carrier country')
    target_provider_id = _provider_id(expected_source_selector)
    prior_provider_id = (_provider_id(prior_label_source_selector)
        if prior_label_source_selector is not None else None)
    # Keep all existing numeric-ID + explicit collision witnesses byte-stable.
    # The additive identity/reparse fields apply only to the new admission path.
    legacy_numeric_witness = (collision is not None and target_provider_id is not None
        and prior_provider_id is not None)
    target_selector_identity = _selector_identity(expected_source_selector)
    prior_selector_identity = _selector_identity(prior_label_source_selector) if prior_label_source_selector is not None else None
    if legacy_numeric_witness:
        if target_provider_id == prior_provider_id:
            raise ValueError('target and prior-label source selectors share one provider club ID')
    elif target_selector_identity == prior_selector_identity:
        raise ValueError('target and prior-label source selectors are identical')
    if _normalise(club['name']) == _normalise(expected_source_selector['club_name']):
        raise ValueError('target label already matches; no correction needed')
    if collision is not None and _normalise(collision['name']) != _normalise(prior_label_source_selector['club_name']):
        raise ValueError('cited prior-label carrier does not display its bound source selector')
    target_names = club_names(club_group(club), expected_source_selector['club_name'])
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    for _layer_name, layer_package, _layer_path in package_layers(release):
        for other in layer_package.get('clubs', []):
            if other.get('carrier_id') == carrier_id:
                continue
            # The English contextual overlay is England-scoped as a whole and
            # does not carry mode-1 division metadata on each club row.
            other_group = ('england' if _layer_name == 'english' else
                _carrier_country_group(package, other.get('carrier_id', -1)))
            if other_group is None:
                if target_names & club_names(club_group(club), other.get('name', ''), other.get('full_name', '')):
                    raise ValueError('desired source club label has another package-layer carrier with unknown country')
                continue
            if other_group != club_group(club):
                continue
            if target_names & club_names(other_group, other.get('name', ''), other.get('full_name', '')):
                raise ValueError('desired source club label is already represented by another package-layer club')
    eq_path = release.game_path / 'DBDAT/EQ98030.FDI'
    eq_bytes = eq_path.read_bytes()
    eq_index, owners = _native_owner_index(eq_bytes)
    # The desired name must also be free in the complete native EQ directory.
    for entry in eq_index.entries:
        if entry.record_id == carrier_id:
            continue
        payload = entry.decode_payload(eq_bytes)
        marker = payload.find(b'\xdd\x63\x61')
        if marker < 2:
            continue
        native_name, _, _ = _read_eq_inline_string(payload, marker + 4)
        if _normalise(native_name) != _normalise(expected_source_selector['club_name']):
            continue
        other_group = _carrier_country_group(package, entry.record_id)
        if other_group is None:
            raise ValueError(f'native EQ carrier {entry.record_id} country group is unknown for desired-name collision check')
        if other_group == club_group(club):
            raise ValueError('desired source club label is already present on another native EQ carrier')
    # The old numeric collision witness remains byte-identical. The new opt-in
    # path binds authored names to decoded JUG identities and self IDs.
    target_players = [p for p in package['players'] if p.get('club_id') == club['id']]
    native_players = None if legacy_numeric_witness else _native_jug_identity_index(
        (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
        [int(player['carrier_id']) for player in target_players])
    target_bindings = _bind_cohort(package, club, source, require_all=True,
        expected_artifact_id=artifact_id, owners=owners, native_players=native_players)
    prior_bindings = (_bind_cohort(package, collision, prior_source, require_all=False,
        expected_artifact_id=artifact_id, owners=owners)
        if collision is not None else [])
    # A second source selector that also binds the entire roster by exact
    # names/DOBs makes the source-club allocation ambiguous; refuse it.
    _assert_unique_source_cohort(pre, source, target_players, club_group(club))
    raw_source_proof = None if legacy_numeric_witness else _reparse_source_cohort(season, expected_source_selector, source)
    prior_raw_source_proof = (None if legacy_numeric_witness else
        _reparse_source_cohort(season, prior_label_source_selector, prior_source)
        if collision is not None else None)
    witness = {'schema_version': SCHEMA, 'season': season, 'release_id': release.release_id,
        'package_path': registry.relative_workspace_path(release.package_path),
        'package_sha256': registry.sha256_file(release.package_path),
        'eq_path': registry.relative_workspace_path(eq_path), 'eq_sha256': registry.sha256_file(eq_path),
        'native_owner_readback': 'decoded EQ roster rows; each target actor has one active flag-zero owner at cited carrier',
        'preallocation_artifact_id': artifact_id,
        'preallocation_path': registry.relative_workspace_path(pre_path), 'preallocation_sha256': pre_sha,
        'target': {'club_id': club['id'], 'carrier_id': carrier_id, 'before': club['name'],
            'after': expected_source_selector['club_name'], 'country_group': club_group(club)},
        'distinct_old_label_carrier': ({'club_id': collision['id'], 'carrier_id': collision_carrier_id,
            'label': collision['name'], 'source_selector': prior_label_source_selector}
            if collision is not None else None),
        'source_selector': expected_source_selector,
        'target_provider_club_id': target_provider_id,
        'prior_provider_club_id': prior_provider_id,
        'source_fixture_date': source.get('opening_fixture_date'),
        'source_match_id': source.get('opening_source_match_id'),
        'source_roster_rows_total': len(source['players']),
        'target_source_rows_bound': len(target_bindings), 'current_cohort_count': len(target_bindings),
        'roster_bindings': target_bindings,
        'prior_source_roster_rows_total': len(prior_source['players']) if prior_source is not None else 0,
        'prior_source_rows_bound': len(prior_bindings),
        'prior_current_cohort_count': len(prior_bindings), 'prior_roster_bindings': prior_bindings,
        'identity_basis': 'complete_source_bound_roster_cohort',
        'opening_xi_certified': False, 'manager_admission_separate': True,
        'automatic_change_authorized': False}
    if not legacy_numeric_witness:
        witness.update(target_source_selector_identity_sha256=target_selector_identity,
            prior_source_selector_identity_sha256=prior_selector_identity,
            raw_source_reparse=raw_source_proof, prior_raw_source_reparse=prior_raw_source_proof,
            prior_label_collision_present=collision is not None,
            native_jug_identity_readback='decoded JUG player name equals authored package name after canonical normalization; embedded self ID equals directory and recipe carrier ID')
    return witness

def verify_witness(witness, *, source_root):
    if witness.get('schema_version') != SCHEMA:
        raise ValueError('wrong witness schema')
    fresh = create_witness(season=witness['season'], source_root=source_root,
        carrier_id=witness['target']['carrier_id'], expected_source_selector=witness['source_selector'],
        prior_label_source_selector=(witness['distinct_old_label_carrier']['source_selector']
            if witness.get('distinct_old_label_carrier') else None),
        collision_carrier_id=(witness['distinct_old_label_carrier']['carrier_id']
            if witness.get('distinct_old_label_carrier') else None),
        source_release_id=witness['release_id'])
    if witness != fresh:
        raise ValueError('witness is stale or modified')
    return fresh

def proposed_review_row(witness, *, manager_after, manager_carrier_id, manager_owner_count,
                        native_manager_before, manager_source_evidence):
    if not manager_after or manager_owner_count != 1:
        raise ValueError('separate uniquely-owned source-bound manager is required')
    if witness.get('opening_xi_certified') is not False:
        raise ValueError('full-cohort path cannot certify an opening XI')
    if not native_manager_before or not manager_source_evidence:
        raise ValueError('dated manager evidence and native before-name are required')
    for source in manager_source_evidence:
        if not all(source.get(key) for key in ('path', 'sha256', 'source_date', 'url')):
            raise ValueError('manager source evidence lacks dated URL/path/hash')
        path = Path(source['path'])
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or registry.sha256_file(path) != source['sha256']:
            raise ValueError('manager source bytes are absent or changed')
    evidence = {'date': witness.get('source_fixture_date'), 'manager': manager_after,
        'identity_basis': witness['identity_basis'], 'source_match_id': witness.get('source_match_id'),
        'full_cohort_witness': witness, 'manager_source_evidence': manager_source_evidence,
        'raw_sources': [{'path': source['path'], 'sha256': source['sha256']}
            for source in manager_source_evidence]}
    return {'status': 'source-supported-full-cohort-club-label-mismatch',
        'before': witness['target']['before'], 'after': witness['target']['after'],
        'identity_basis': witness['identity_basis'], 'full_cohort_witness': witness,
        'evidence': evidence, 'native_manager': native_manager_before,
        'native_manager_owner_count': manager_owner_count,
        'native_manager_carrier_id': manager_carrier_id,
        'historical_verification_complete': False, 'automatic_change_authorized': False,
        'manager_after': manager_after, 'native_manager_carrier_id': manager_carrier_id,
        'native_manager_owner_count': manager_owner_count}


def verify_manager_sources(row):
    """Check retained named coach/club source context; never certify an XI."""
    from bs4 import BeautifulSoup
    evidence = row.get('evidence', {})
    name = row.get('manager_after')
    club = row.get('after')
    sources = evidence.get('manager_source_evidence')
    if not name or not club or evidence.get('manager') != name or not isinstance(sources, list) or not sources:
        raise ValueError('full-cohort label change requires separate named manager evidence')
    for source in sources:
        if not all(source.get(k) for k in ('path', 'sha256', 'source_date', 'url')):
            raise ValueError('manager source lacks dated URL/path/hash')
        path = Path(source['path'])
        path = path if path.is_absolute() else ROOT / path
        if registry.sha256_file(path) != source['sha256']:
            raise ValueError('manager source bytes changed')
        page = BeautifulSoup(path.read_bytes(), 'lxml')
        for node in page(['script', 'style']):
            node.decompose()
        text = _normalise(page.get_text(' ', strip=True))
        if _normalise(name) not in text or _normalise(club) not in text:
            raise ValueError('manager source does not contain the named coach and target club')
    return True
