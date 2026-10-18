"""Bind original league dates to explicit club identities, never to players.

This discovery layer is not an ownership policy. Current publisher names
identify possible stable IDs only; original dated squad membership and strict
transfer brackets are still mandatory before any roster repair. No XIs,
substitutes, managers, kits or current squads are invented or inherited here.
"""
import json
from scripts import capture_original_public_club_entities_v1 as public
from scripts import season_football_data_opening_dates_v1 as dates
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_release_registry_v1 as registry

POLICY = 'original-results-and-explicit-published-club-name-discovery-date-only-v1'
COMPETITIONS = {'d3': 'E3', 'fltwo': 'E3', 'conf': 'EC'}
# Explicit source-label aliases, not prefix/fuzzy matching. Match exactly one
# label in the selected original season/competition or refuse the ambiguity.
CSV_ALIASES = {
    'Boston United': ('Boston', 'Boston Utd'),
    'Dagenham & Redbridge': ('Dag and Red', 'Dag & Red'),
    'Gravesend & Northfleet': ('Gravesend',),
    'Rushden & Diamonds': ('Rushden & D',),
    'King\'s Lynn Town': ('Kings Lynn',),
    'Braintree Town': ('Braintree', 'Braintree Town'),
}


def read_entities(path):
    document = json.loads(path.read_text())
    if document.get('schema_version') != 'pm99-original-public-club-entity-discovery-v1':
        raise ValueError('unsupported explicit public club discovery')
    result = {}
    for batch in document['batches']:
        raw = registry.ROOT / batch['raw_path']
        if registry.sha256_file(raw) != batch['raw_sha256']:
            raise ValueError('original club entity response changed')
        if batch['source_url'] != public.url(batch['requested_ids']) or json.loads(
                (registry.ROOT / batch['receipt_path']).read_text()) != {
                    'url': batch['source_url'], 'sha256': batch['raw_sha256']}:
            raise ValueError('original club entity URL/SHA receipt differs')
        entities, gaps = public.parse(json.loads(raw.read_text()), batch['requested_ids'])
        if (entities, gaps) != (batch['entities'], batch['missing_ids']):
            raise ValueError('explicit club discovery does not reproduce from original publisher')
        for entity in entities:
            id = entity['source_club_id']
            if id in result and result[id] != entity:
                raise ValueError('original club entities conflict for one stable ID')
            result[id] = entity
    return result


def read_results(row):
    raw = registry.ROOT / row['path']
    receipt = json.loads((registry.ROOT / row['receipt_path']).read_text())
    if (registry.sha256_file(raw) != row['sha256'] or receipt != row['original_urls']
            or receipt['sha256'] != row['sha256']):
        raise ValueError('original league result URL/SHA differs')
    for key in ('requested_url', 'response_url'):
        dates.validate_url(receipt[key], row['season'], row['competition'])
    matches = dates.parse(raw.read_bytes(), row['season'], row['competition'])
    if len(matches) != row['matches'] or len({m['home'] for m in matches}) != row['clubs']:
        raise ValueError('original result summary differs from independently replayed archive')
    return raw.read_bytes()


def bind(capture, entities, raw, season):
    code = COMPETITIONS.get(capture['competition_catalog'])
    if capture['country_catalog'] != 'eng' or code is None:
        raise ValueError('date discovery is restricted to original English mens lower-league captures')
    accepted = roster.club_names('england', capture['club_name'])
    candidates = [e for e in entities.values() if e['country_id'] in (189, 191)
        and e['club_type_id'] == 1 and e['is_national_team'] is False
        and str(e['main_club_id']) == str(e['source_club_id'])
        and any(roster.normalise(n) in accepted for n in e['published_names'])]
    if len(candidates) != 1:
        raise ValueError('dated squad club needs one explicit stable publisher identity; lifecycle/name ambiguity remains a gap')
    entity = candidates[0]
    names = [capture['club_name'], *entity['published_names'], *CSV_ALIASES.get(capture['club_name'], ())]
    wanted = {roster.normalise(n) for n in names}
    matches = dates.parse(raw, season, code)
    labels = {m[k] for m in matches for k in ('home', 'away') if roster.normalise(m[k]) in wanted}
    if len(labels) != 1:
        raise ValueError('dated squad club needs one exact reviewed original CSV label')
    fixture = dates.first_fixture(raw, season, code, next(iter(labels)))
    return {'policy': POLICY, 'source_club_id': entity['source_club_id'],
        'historical_squad_club': capture['club_name'], 'published_identity': entity,
        'original_date_evidence': fixture, 'starting_xi': None, 'substitutes': None,
        'manager': None, 'player_ownership_approved': False, 'native_corrections': 0}
