"""Retain original biographies and narrow actual-native birthday candidates.

This is source/native evidence, not permission to merge same-name players or
move rosters. Known actual clubs are explicit; suspicious other-club copies
remain ownership cases, never silently repaired as if ownership were proved.
"""
from datetime import date
from bs4 import BeautifulSoup

from scripts import season_kit_render_bindings_v1  # canonical editor imports
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_italian_period_kits_20261010 import capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts import season_published_person_identity_v1 as identities

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/midson-odubade-birthdays-v1'
SOURCES = {
    'midson': ('https://www.soccerbase.com/players/player.sd?player_id=29353', 'Jack Midson', '12 Sep, 1983', '1983-09-12'),
    'odubade': ('https://www.stevenagefootballarchive.co.uk/player.php?id=131', 'Yemi Odubade', 'July 4th, 1984', '1984-07-04'),
}
TARGETS = (
    ('2006-07', 10805, 'odubade', 'Oxford'),
    ('2007-08', 11282, 'odubade', 'Oxford'),
    ('2008-09', 11255, 'odubade', 'Oxford'),
    ('2009-10', 10906, 'odubade', 'Stevenage'),
    ('2010-11', 32937, 'midson', 'Oxford United'),
    ('2011-12', 10504, 'midson', 'AFC Wimbledon'),
    ('2012-13', 10504, 'midson', 'AFC Wimbledon'),
    ('2013-14', 10511, 'midson', 'AFC Wimbledon'),
    ('2015-16', 10926, 'midson', 'Eastleigh'),
)


def main():
    source_rows = {}
    for key, (url, name, literal, dob) in SOURCES.items():
        if key == 'odubade':
            # Already captured publisher original confirms1984. Reparse its
            # exact URL/SHA response instead of relying on blocked archive HTML.
            document_path = registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json'
            doc = pipeline.read_json_file(document_path)
            identities.merge({}, doc)
            pairs = [(batch, p) for batch in doc['batches'] for p in batch.get('people', [])
                     if p['source_player_id'] == 67231]
            if len(pairs) != 1 or pairs[0][1]['name'] != name or pairs[0][1]['birth_date'] != dob:
                raise ValueError('original stable Odubade person/DOB differs')
            batch, person = pairs[0]
            source_rows[key] = dict(path=registry.relative_workspace_path(document_path),
                sha256=registry.sha256_file(document_path), url=batch['source_url'],
                raw_path=batch['raw_path'], raw_sha256=batch['raw_sha256'],
                source_person_id=67231, source_name=name, birth_date=dob)
            continue
        path = ROOT / 'source-cache' / (key + '-original-birthday.html')
        capture(url, path)
        text = BeautifulSoup(path.read_bytes(), 'html.parser').get_text(' ', strip=True)
        if name not in text or literal not in text:
            raise ValueError('original named biography/date differs')
        source_rows[key] = dict(path=registry.relative_workspace_path(path),
            **pipeline.read_json_file(path.with_name(path.name + '.source.json')),
            source_name=name, birth_date=dob)
    records = []
    for season, carrier, key, expected_club in TARGETS:
        release = registry.load_preferred_release(season)
        package = pipeline.read_json_file(release.package_path)
        player = next(p for p in package['players'] if p['carrier_id'] == carrier)
        club = next(c for c in package['clubs'] if c['id'] == player['club_id'])
        if club['name'] != expected_club or key not in player['name'].lower():
            raise ValueError('explicit actual player/club target changed')
        raw = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        entry = next(e for e in IndexedFDIFile.from_bytes(raw).entries if e.record_id == carrier)
        payload = entry.decode_payload(raw)
        native = roster.native_player(payload, carrier)
        end = native['name_end']
        observed = date(int.from_bytes(bytes(b ^ 0x61 for b in payload[end+14:end+16]), 'little'),
                        payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
        if observed != player['facts']['birth_date']:
            raise ValueError('recipe/native disagreement needs a separate guarded preimage')
        if observed == source_rows[key]['birth_date']:
            raise ValueError('already-correct target must not be rebuilt')
        records.append(dict(season=season, carrier_id=carrier, release_id=release.release_id,
            manifest_sha256=release.manifest_sha256, package_sha256=registry.sha256_file(release.package_path),
            player=player, club=club['name'], native_name=native['name'], before_birth_date=observed,
            original_source=source_rows[key], target_birth_date=source_rows[key]['birth_date'],
            status='source-native-birthday-candidate-awaiting-original-identity-and-opening-admission'))
    retained(ROOT / 'nine-current-native-candidates.json', dict(
        records=records, count=len(records), native_games_modified=0,
        scope='Nine explicit actual club/player candidates; no source-ID, roster ownership or namesake bypass. Other same-name clubs require their own ownership disposition. Additional findings do not reduce/reset original247 date cases.'))
    print(dict(source_biographies=2, actual_native_candidates=len(records), games_modified=0), flush=True)


if __name__ == '__main__':
    main()
