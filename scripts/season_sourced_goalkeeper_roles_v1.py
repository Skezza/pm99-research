"""Correct copied outfield role labels for independently sourced goalkeepers.

A literal G source maps to PM99 role zero; no outfield side inference. Reuse
completed raw reparses only when every capture binding and raw hash still
matches. Skip shared carriers and preserved/uncertain identities.
"""
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_opening_order_repair_v1 as order

POLICY = 'original-target-squad-full-name-DOB-literal-G-to-PM99-role-zero-v1'


def original_keeper(capture, name, birthday):
    rows = [p for p in capture['players'] if audit.normalise(p['name']) == audit.normalise(name)]
    if len(rows) != 1 or (rows[0]['birth_date'], rows[0]['position']) != (birthday, 'G'):
        return None
    return rows[0]


def prepare(release, reparse_report):
    report_raw = reparse_report.read_bytes()
    report_hash = hashlib.sha256(report_raw).hexdigest()
    report = json.loads(report_raw)
    captures, bindings = audit.load_sources(release.season)
    checker = audit.SourceVerifier(release.season, previous=report, source_bindings=bindings)
    by_club = defaultdict(list)
    for capture in captures:
        by_club[(audit.source_group(capture['country_catalog']), audit.normalise(capture['club_name']))].append(capture)
    package_raw = release.package_path.read_bytes()
    package_hash = hashlib.sha256(package_raw).hexdigest()
    package = json.loads(package_raw)
    clubs = {c['id']: c for c in package['clubs']}
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = order.native_owners(eq)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates, unresolved = [], []
    for player in package['players']:
        if (player.get('policy') == 'preserve-existing-mode1'
                or player['facts']['primary_position'] != 'G'
                or not isinstance(player['facts'].get('birth_date'), str)):
            continue
        carrier, club = player['carrier_id'], clubs[player['club_id']]
        name, birthday = player.get('source_name') or player['name'], player['facts']['birth_date']
        evidence = []
        for alias in audit.club_names(audit.club_group(club), club['name'], club.get('full_name', '')):
            for capture in by_club.get((audit.club_group(club), alias), []):
                source = original_keeper(capture, name, birthday)
                if source is None:
                    continue
                proof = checker.verify(capture)
                if proof['status'] == 'raw-source-reparsed':
                    evidence.append({'capture': capture, 'raw_proof': proof, 'source_player': source})
        if not evidence:
            continue
        if owners.get(carrier) != {club['carrier_id']}:
            unresolved.append({'carrier_id': carrier, 'name': name, 'reason': 'shared or mismatched actual native ownership'})
            continue
        try:
            decoded = index[carrier].decode_payload(jug)
            native = audit.native_player(decoded, carrier)
            end, before = read_indexed_native_roles(decoded, carrier)
            born = date(int.from_bytes(bytes(v ^ 0x61 for v in decoded[end+14:end+16]), 'little'),
                        decoded[end+13] ^ 0x61, decoded[end+12] ^ 0x61).isoformat()
        except (KeyError, ValueError) as exc:
            unresolved.append({'carrier_id': carrier, 'name': name,
                               'reason': 'native identity/role/date unreadable; no write', 'detail': str(exc)})
            continue
        if (audit.normalise(native['name']) != audit.normalise(player['name'])
                or native['position'] != 'G' or born != birthday):
            unresolved.append({'carrier_id': carrier, 'name': name, 'reason': 'native full display/DOB/primary position disagreement'})
            continue
        if before[0] == 0:
            continue
        updates.append({'player_id': player['id'], 'carrier_id': carrier, 'name': player['name'],
                        'birth_date': birthday, 'fine_roles': [0],
                        'provenance': {'method': POLICY, 'source_name': name,
                                       'source_position': 'G', 'native_before_roles': before,
                                       'club_id': club['id'], 'club_carrier_id': club['carrier_id'],
                                       'evidence': evidence,
                                       'limit': 'literal goalkeeper role only; no new ownership/first-XI/ability/photo claim'}})
    # Recheck the exact bytes consumed, not hashes taken only after the reads.
    if (registry.sha256_file(release.package_path) != package_hash
            or registry.sha256_file(reparse_report) != report_hash
            or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != hashlib.sha256(jug).hexdigest()
            or registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI') != hashlib.sha256(eq).hexdigest()
            or audit.load_sources(release.season)[1] != bindings):
        raise ValueError('source or native inputs changed during keeper role planning')
    for row in updates:
        for evidence in row['provenance']['evidence']:
            proof = evidence['raw_proof']
            if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
                raise ValueError('used original keeper source changed during planning')
    return {'schema_version': 'pm99-historical-role-plan-v1', 'season': release.season,
            'release_id': release.release_id, 'package_sha256': package_hash,
            'jug_sha256': hashlib.sha256(jug).hexdigest(),
            'eq_sha256': hashlib.sha256(eq).hexdigest(),
            'policy': POLICY, 'original_reparse_report': {'path': registry.relative_workspace_path(reparse_report),
                                                       'sha256': report_hash},
            'source_bindings': bindings, 'updates': updates, 'unresolved': unresolved,
            'summary': {'goalkeeper_role_corrections': len(updates), 'shared_or_native_conflicts': len(unresolved)}}


def verify(release, plan):
    binding = plan['original_reparse_report']
    path = registry.ROOT / binding['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != binding['sha256'] or prepare(release, path) != plan:
        raise ValueError('sourced goalkeeper role plan does not independently reproduce')
