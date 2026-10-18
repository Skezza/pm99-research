"""Narrow factory-identical system-selection scope dispositions; no game writes.

Do not exempt all preserved teams, low-information names or country carriers.
Only the pinned Seleccion America carrier and original placeholder records are
eligible, after whole native record equality. The frozen candidate ledger stays.
"""
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry
from scripts import season_italian_opening_layer_v1 as native
from scripts.season_carrier_allocation_v1 import SYSTEM_SELECTION_IDS
from scripts.finalize_season_release_v1 import DEFAULT_BASE

BASE_HASHES = {
    'JUG98030.FDI': '95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844',
    'EQ98030.FDI': 'e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c',
}


def verify_club(club, players, base_eq_payload, current_eq_payload,
                base_players, current_players):
    if (club.get('carrier_id') != 8801 or 8801 not in SYSTEM_SELECTION_IDS
            or club.get('name') != 'Sel. América' or club.get('full_name') != 'Selección América'
            or club.get('division') != 'preserve-existing-mode1-membership'
            or club.get('opening', {}).get('policy') != 'preserve-existing-mode1'):
        raise ValueError('not the exact declared native system selection')
    ids = set(range(19400, 19411))
    if set(base_players) != ids or set(current_players) != ids or set(players) != ids:
        raise ValueError('system selection roster/carriers differ')
    if base_eq_payload != current_eq_payload or base_players != current_players:
        raise ValueError('system selection native records differ from pinned factory')
    if set(club['roster_player_ids']) != {p['id'] for p in players.values()}:
        raise ValueError('system selection declared roster differs')
    for p in players.values():
        if (p.get('policy') != 'preserve-existing-mode1' or p.get('club_id') != club['id']
                or p.get('source_name') or not isinstance(p.get('facts'), dict)
                or any(v != {'policy': 'preserve-existing-mode1'} for v in p['facts'].values())
                or p.get('proof') != {'artifact_id': 'world-mode1-runtime-contract', 'grade': 'static-contract'}):
            raise ValueError('system selection contains a historical/edited person declaration')


def record(data, carrier):
    entries = [e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError('system-selection native record missing or ambiguous')
    return entries[0].decode_payload(data)


def prepare(root):
    base = {}
    for name, sha in BASE_HASHES.items():
        path = DEFAULT_BASE / 'DBDAT' / name
        if registry.sha256_file(path) != sha:
            raise ValueError('original factory evidence changed')
        base[name] = path.read_bytes()
    original = json.loads((root / 'within-club-adjudication.json').read_text())
    cases = [r for r in original['rows'] if r['club_id'] == 'club-8801']
    if len(cases) != 26 or {r['season'] for r in cases} != set(registry.supported_seasons()):
        raise ValueError('expected the fixed 26 selection cases, not a new denominator')
    base_roster = native.roster_rows(base['EQ98030.FDI'], 8801)[2]
    if base_roster != [(id, 0) for id in range(19400, 19411)]:
        raise ValueError('original selection roster differs')
    base_eq = record(base['EQ98030.FDI'], 8801)
    base_players = {id: record(base['JUG98030.FDI'], id) for id, flag in base_roster}
    rows = []
    for case in cases:
        if sorted(p['carrier_id'] for p in case['players']) != [19403, 19410]:
            raise ValueError('selection candidate identities changed')
        release = registry.load_preferred_release(case['season'])
        package = json.loads(release.package_path.read_text())
        club = next(c for c in package['clubs'] if c['id'] == case['club_id'])
        players = {p['carrier_id']: p for p in package['players'] if p['id'] in club['roster_player_ids']}
        jug_path, eq_path = (release.game_path / 'DBDAT' / n for n in ('JUG98030.FDI', 'EQ98030.FDI'))
        jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
        current_players = {id: record(jug, id) for id in base_players}
        verify_club(club, players, base_eq, record(eq, 8801), base_players, current_players)
        rows.append({'candidate_id': case['id'], 'season': case['season'],
            'release_id': release.release_id, 'club_id': club['id'],
            'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(jug_path), 'eq_sha256': registry.sha256_file(eq_path),
            'classification': 'factory-identical-system-selection-not-a-historical-club-duplicate',
            'scope_exception_proved': True, 'native_changed': False,
            'all_eleven_native_player_records_and_club_identical_to_factory': True,
            'historical_person_identity_approval': False})
    return {'schema': 'pm99-fixed-system-selection-scope-dispositions-v1',
            'factory_hashes': BASE_HASHES, 'rows': rows, 'scope_exception_count': len(rows),
            'native_writes': 0, 'frozen_denominator_changed': False,
            'scope': 'Exactly 26 original untouched native system-selection cases. No real historical club is exempted; no player deleted.'}
