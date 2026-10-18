"""Explicit original-identity/date disagreements, never namesake merging."""
import copy
from datetime import date
from pathlib import Path

from scripts import season_kit_render_bindings_v1  # canonical editor path
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_soccerbase_august_squads_v1 as profiles
from scripts import season_original_soccerbase_reserves_v1 as careers
from scripts import season_published_person_identity_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_original_person_birth_years_v1 as original
from scripts.inspect_midson_odubade_birthdays_20261016 import ROOT, TARGETS


def original_profile(path, person_id):
    receipt_path = path.with_name(path.name + '.source.json')
    receipt = pipeline.read_json_file(receipt_path)
    expected = f'https://www.soccerbase.com/players/player.sd?player_id={person_id}'
    if receipt != dict(url=expected, sha256=registry.sha256_file(path)):
        raise ValueError('original profile URL/SHA differs')
    return path.read_bytes(), dict(path=registry.relative_workspace_path(path), **receipt)


def admit(base):
    selected = [r for r in TARGETS if r[0] == base.season]
    if len(selected) != 1:
        raise ValueError('only one explicitly reviewed player in each selected season')
    season, carrier, key, club_name = selected[0]
    candidates_path = ROOT / 'nine-current-native-candidates.json'
    candidates = pipeline.read_json_file(candidates_path)
    rows = [r for r in candidates['records'] if r['season'] == season and r['carrier_id'] == carrier]
    if candidates['count'] != 9 or len(rows) != 1:
        raise ValueError('original nine-candidate scope changed')
    candidate = rows[0]
    if (candidate['release_id'] != base.release_id or candidate['manifest_sha256'] != base.manifest_sha256
            or candidate['package_sha256'] != registry.sha256_file(base.package_path)):
        raise ValueError('original candidate baseline changed')
    package = pipeline.read_json_file(base.package_path)
    player = next(p for p in package['players'] if p['carrier_id'] == carrier)
    club = next(c for c in package['clubs'] if c['id'] == player['club_id'])
    full_name = 'Jack Midson' if key == 'midson' else 'Yemi Odubade'
    wanted = '1983-09-12' if key == 'midson' else '1984-07-04'
    rejected = '1983-07-21' if key == 'midson' else '1987-07-04'
    if (player != candidate['player'] or player.get('source_name') != full_name
            or player['facts']['birth_date'] != rejected or club['name'] != club_name
            or player.get('policy') == 'preserve-existing-mode1'):
        raise ValueError('exact original full identity/club/wrong-date preimage differs')
    path = (ROOT / 'source-cache/midson-original-birthday.html' if key == 'midson' else
            registry.ROOT / f'.local/season-{season}/soccerbase-august-cache-v1/player/39723.html')
    raw, source = original_profile(path, 29353 if key == 'midson' else 39723)
    person = profiles.player_profile(raw, fallback_name='', fallback_position='?')
    if person['name'] != full_name or person['position'] != 'F':
        raise ValueError('original numeric player biography identifies another actor')
    team_id = {'Oxford': 1964, 'Oxford United': 1964, 'Stevenage': 2499,
               'AFC Wimbledon': 4194, 'Eastleigh': 4252}[club_name]
    interval = careers.career_interval(raw, team_id, season[:4] + '-08-01')
    corroboration = None
    if key == 'midson':
        if person['birth_date'] != wanted:
            raise ValueError('original numeric Midson profile no longer supplies the exact birthday')
    else:
        # Soccerbase's1987 year is the very error being corrected. The stable
        # publisher67231 agrees with independent period annuals on1984; no
        # current club/role/country/rating/portrait is consumed from the API.
        doc_path = registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json'
        doc = pipeline.read_json_file(doc_path)
        matches = [(b, p) for b in doc['batches'] for p in b.get('people', [])
                   if p['source_player_id'] == 67231]
        if len(matches) != 1 or matches[0][1]['name'] != full_name or matches[0][1]['birth_date'] != wanted:
            raise ValueError('published original Odubade identity/date differs')
        batch, accepted = matches[0]
        # Reparse the complete original response batch that actually contains
        # this person, not thousands of unrelated source responses. All URL,
        # requested-ID, raw SHA, receipt and parsed-field guards are retained.
        identities.merge({}, dict(doc, batches=[batch]))
        if person['birth_date'] != rejected:
            raise ValueError('explicit rejected provider date changed; review the disagreement again')
        corroboration = dict(path=registry.relative_workspace_path(doc_path), sha256=registry.sha256_file(doc_path),
            raw_path=batch['raw_path'], raw_sha256=batch['raw_sha256'], source_url=batch['source_url'],
            accepted_person=accepted, rejected_other_provider_birth_date=person['birth_date'])
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if original.order.native_owners(eq).get(carrier) != {club['carrier_id']}:
        raise ValueError('birthday target is not exclusively owned by the exact expected club')
    entry = next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id == carrier)
    payload = entry.decode_payload(jug)
    native = roster.native_player(payload, carrier)
    end = native['name_end']
    actual = date(int.from_bytes(bytes(b ^ 0x61 for b in payload[end+14:end+16]), 'little'),
                  payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
    if actual != rejected or native['name'] != candidate['native_name']:
        raise ValueError('independently read literal native birthday/name differs')
    return dict(carrier_id=carrier, native_name=native['name'], before_birth_date=rejected,
        birth_date=wanted, before_player=copy.deepcopy(player), expected_club=club_name,
        original_numeric_profile=source, original_full_name=full_name,
        original_numeric_club_id=team_id, original_start_of_season_career=interval,
        independent_date_resolution=corroboration,
        source_candidate_binding=dict(path=registry.relative_workspace_path(candidates_path),
            sha256=registry.sha256_file(candidates_path)))
