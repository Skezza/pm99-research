"""Repair proven post-1999 source DOBs omitted by the English serializer."""
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_birth_year import rewrite_indexed_native_birth_years
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_opening_order_repair_v1 as order
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline

POLICY = 'original-full-name-DOB-exclusive-mode0-legacy-serializer-year-omission-v1'
PREFIX = 'sourced-birth-year-plan-'
FILENAME = 'sourced-birth-year-plan.json'


def original_person(capture, name, birthday):
    rows = [row for row in capture.get('players', [])
            if audit.normalise(row.get('name', '')) == audit.normalise(name)]
    return rows[0] if len(rows) == 1 and rows[0].get('birth_date') == birthday else None


def prepare(release, report_path):
    sys.path.insert(0, str(registry.ROOT / 'upstream/pm99-skezmod-patcher'))
    from player_birth_year_guard import patch_native_birth_year_guard
    exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    if patch_native_birth_year_guard(exe)[0] != exe:
        raise ValueError('modern birth years require the already verified executable guard')
    report = json.loads(report_path.read_text())
    report_hash = registry.sha256_file(report_path)
    captures, bindings = audit.load_sources(release.season)
    if report['bindings']['sources'] != bindings:
        raise ValueError('cached original birthday sources changed')
    checker = audit.SourceVerifier(release.season, previous=report, source_bindings=bindings)
    package = json.loads(release.package_path.read_text())
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    package_hash = registry.sha256_file(release.package_path)
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(jug).entries}
    owners = order.native_owners(eq)
    clubs = {club['id']: club for club in package['clubs']}
    by_club = {}
    for capture in captures:
        by_club.setdefault((audit.source_group(capture['country_catalog']), audit.normalise(capture['club_name'])), []).append(capture)
    updates, unresolved, evidence = [], [], {}
    for player in package['players']:
        birthday = player['facts'].get('birth_date')
        if player.get('policy') == 'preserve-existing-mode1' or not isinstance(birthday, str):
            continue
        target = date.fromisoformat(birthday)
        if target.year < 2000:
            continue
        club, carrier = clubs[player['club_id']], player['carrier_id']
        if club['division'] == 'preserve-existing-mode1-membership':
            continue
        decoded = entries[carrier].decode_payload(jug)
        native = audit.native_player(decoded, carrier)
        end = native['name_end']
        old = {'year': int.from_bytes(bytes(v ^ 0x61 for v in decoded[end+14:end+16]), 'little'),
               'month': decoded[end+13] ^ 0x61, 'day': decoded[end+12] ^ 0x61}
        if old == {'year': target.year, 'month': target.month, 'day': target.day}:
            continue
        row = {'player_id': player['id'], 'carrier_id': carrier, 'name': player['name'],
               'native_name': native['name'], 'birth_date': birthday, 'before_components': old,
               'club_id': club['id'], 'club_carrier_id': club['carrier_id']}
        if (decoded[2:5] != b'\xdd\x63\x61' or owners.get(carrier) != {club['carrier_id']}
                or audit.normalise(native['name']) != audit.normalise(player['name'])
                or not 1900 <= old['year'] < 2000 or (old['month'], old['day']) != (target.month, target.day)):
            unresolved.append(dict(row, reason='not an exclusive exact-name legacy-year-only omission'))
            continue
        witnesses = []
        for alias in audit.club_names(audit.club_group(club), club['name'], club.get('full_name', '')):
            for capture in by_club.get((audit.club_group(club), alias), []):
                source = original_person(capture, player.get('source_name') or player['name'], birthday)
                if source is None:
                    continue
                proof = checker.verify(capture)
                if proof['status'] != 'raw-source-reparsed':
                    continue
                key = hashlib.sha256(pipeline.canonical_json_bytes(capture)).hexdigest()
                evidence[key] = {'capture': capture, 'raw_proof': proof}
                witnesses.append({'evidence_key': key, 'source_player': source})
        if not witnesses:
            unresolved.append(dict(row, reason='no exact original full-name/DOB witness'))
            continue
        updates.append(dict(row, source_name=player.get('source_name') or player['name'], witnesses=witnesses))
    if (registry.sha256_file(release.package_path) != package_hash
            or registry.sha256_file(report_path) != report_hash
            or registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') != hashlib.sha256(jug).hexdigest()
            or registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI') != hashlib.sha256(eq).hexdigest()
            or audit.load_sources(release.season)[1] != bindings):
        raise ValueError('birthday plan inputs changed during verification')
    for item in evidence.values():
        proof = item['raw_proof']
        if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
            raise ValueError('birthday witness changed during planning')
    return {'schema_version': 'pm99-sourced-legacy-birth-year-repair-v1', 'policy': POLICY,
            'season': release.season, 'release_id': release.release_id,
            'package_sha256': package_hash, 'jug_sha256': hashlib.sha256(jug).hexdigest(),
            'eq_sha256': hashlib.sha256(eq).hexdigest(), 'exe_sha256': hashlib.sha256(exe).hexdigest(),
            'original_reparse_report': {'path': registry.relative_workspace_path(report_path), 'sha256': report_hash},
            'source_bindings': bindings, 'evidence': evidence, 'updates': updates, 'unresolved': unresolved}


def verify(release, plan):
    path = registry.ROOT / plan['original_reparse_report']['path']
    if registry.sha256_file(path) != plan['original_reparse_report']['sha256'] or prepare(release, path) != plan:
        raise ValueError('original birthday source/native plan did not reproduce')


def apply(raw, plan):
    return rewrite_indexed_native_birth_years(raw, {row['carrier_id']: row for row in plan['updates']})


def bind(package, plan):
    result = copy.deepcopy(package)
    identifier = PREFIX + plan['season']
    result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != identifier] + [{
        'id': identifier, 'kind': 'season-input', 'sha256': hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest(),
        'media_type': 'application/json', 'relative_path': FILENAME}], key=lambda a: a['id'])
    return result
