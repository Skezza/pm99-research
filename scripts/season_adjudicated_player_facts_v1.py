"""Known-wrong facts: historical identity first, independently published facts second.

This deliberately does not loosen the missing-country or adult-height identity
guards. The old birthday is a checked preimage, never evidence of identity.
"""
import copy
from datetime import datetime, date
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_source_package_builder_v1 as builder
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_historical_roster_audit_v1 import native_player
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES

KIND = 'adjudicated-source-player-facts'
FIELDS = ['birth_date', 'nationality']
SCOPE = 'Only explicitly adjudicated birthday and nationality facts/fallbacks and their exact native field bytes; historical source retained, all identities, ownership, roles, ratings, tactics, images, kits and other bytes unchanged.'


def checked(value):
    return exchange.original(value)


def verify_historical_identity(witness):
    """Reproduce the exact original row -> dated fixture -> provider identity."""
    historical = witness['historical_identity']
    allocation = pipeline.read_json_file(checked(historical['preallocation']))
    candidates = [(club, row) for club in allocation['source_clubs'] for row in club['players']
                  if row.get('source_row_sha256') == historical['source_row_sha256']]
    if len(candidates) != 1:
        raise ValueError('historical identity needs one original source row')
    club, row = candidates[0]
    if (builder._source_person_id(row) != witness['person_id']
            or row['facts']['name'] != witness['full_name']
            or str(row.get('opening_source_player_id')) != str(historical['provider_player_id'])
            or club['opening_source_match_id'] != str(historical['match_id'])
            or club['opening_fixture_date'] != historical['match']['date']):
        raise ValueError('historical source row/provider/date identity differs')
    match = historical['match']
    parsed = urlsplit(match['url'])
    if (parsed.scheme != 'https' or parsed.hostname not in ('www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us')
            or not re.search(r'/spielbericht/' + re.escape(str(historical['match_id'])) + r'(?:/|$)', parsed.path)):
        raise ValueError('historical fixture URL/ID differs')
    xi, bench = exchange.match_people(match)
    participants = [p for p in xi + bench if str(p['source_player_id']) == str(historical['provider_player_id'])]
    if len(participants) != 1:
        raise ValueError('historical provider person absent or ambiguous in exact club')
    page = BeautifulSoup(checked(match).read_bytes(), 'lxml')
    full_names = {a.get('title') for a in page.select('a[href]')
                  if re.search(r'/spieler/' + re.escape(str(historical['provider_player_id'])) + r'(?:/|$)', a['href'])}
    # Original providers may omit diacritics (Tokić/Tokic). Keep the complete
    # published name, numeric person, exact source row and dated club fixture
    # requirements; this is not permission to match initials or surnames alone.
    if exchange.published_name_key(witness['full_name']) not in {
            exchange.published_name_key(name) for name in full_names if name}:
        raise ValueError('historical fixture does not independently publish the full identity')
    return int(historical['provider_player_id'])


def adjudicate(witness):
    """Reproduce historical identity before admitting independent official facts."""
    verify_historical_identity(witness)
    sources = witness['official_sources']
    if len(sources) < 2 or len({urlsplit(s['url']).hostname for s in sources}) != len(sources):
        raise ValueError('independent published source hosts required')
    birthdays, countries = [], []
    for source in sources:
        body = checked(source)
        receipt = pipeline.read_json_file(checked(source['receipt']))
        if receipt.get('url') != source['url'] or receipt.get('raw_sha256') != source['sha256']:
            raise ValueError('official source original URL/SHA receipt differs')
        parsed = urlsplit(source['url'])
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('official source needs an explicit HTTPS origin')
        text = ' '.join(BeautifulSoup(body.read_bytes(), 'lxml').get_text(' ', strip=True).split())
        if witness['full_name'] not in text:
            raise ValueError('official biography does not name the historical person')
        claim = source['birth_date']
        literal = claim['label'] + ' ' + claim['literal']
        if literal not in text:
            raise ValueError('published birthday label/literal absent')
        birthdays.append(datetime.strptime(claim['literal'], claim['format']).date().isoformat())
        if source.get('nationality'):
            country = source['nationality']
            if (country['label'] != 'Nationality'
                    or country['label'] + ' ' + country['literal'] not in text
                    or NATIONALITY_CODES.get(country['literal']) != country['code']):
                raise ValueError('published nationality label/literal absent; birthplace is not nationality')
            countries.append(country['code'])
    values = witness['values']
    date.fromisoformat(values['birth_date'])
    if set(values) != set(FIELDS) or set(birthdays) != {values['birth_date']} or set(countries) != {values['nationality']}:
        raise ValueError('independent birthday or explicit nationality claims disagree')
    return copy.deepcopy(values)


def prepare(base, path, request):
    from scripts import season_source_verified_player_changes_v1 as changes
    if (request.get('schema') != changes.INPUT_SCHEMA or request.get('season') != base.season
            or request.get('release_id') != base.release_id or not request.get('changes')):
        raise ValueError('adjudicated facts require an exact registered parent')
    package = pipeline.read_json_file(base.package_path)
    actors = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    updates, seen = [], set()
    for selection in request['changes']:
        carrier = selection['carrier_id']
        if type(carrier) is not int or carrier in seen or selection.get('field_mask') != FIELDS:
            raise ValueError('unique literal actors and explicit birthday/country-only mask required')
        seen.add(carrier)
        actor = actors[carrier]
        witness = selection['witness']
        values = adjudicate(witness)
        observed = native_facts(jug, carrier)
        entry = entries[carrier]
        raw = entry.decode_payload(jug)
        end = native_player(raw, carrier)['name_end']
        old_country = raw[end + 8] ^ 0x61
        if (actor != selection['before'] or actor['person_id'] != witness['person_id']
                or actor.get('source_name') != witness['full_name']
                or observed['name'].casefold() != actor['name'].casefold()
                or observed['birth_date'] != actor['facts']['birth_date']
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}
                or old_country != codes[selection['native_before_country']]):
            raise ValueError('adjudicated actor/native/source identity or exact preimage differs')
        country = compiler._country_code(values['nationality'], codes)
        if country == codes['XXX']:
            raise ValueError('unsupported country is a documented gap, not an invented mapping')
        birthday = date.fromisoformat(values['birth_date'])
        encoded = [birthday.day, birthday.month, *birthday.year.to_bytes(2, 'little')]
        masks = []
        for offset, after in [(end + 8, country), *[(end + 12 + i, b) for i, b in enumerate(encoded)]]:
            absolute = entry.payload_offset + offset
            if jug[absolute] != raw[offset] ^ 0x61:
                raise ValueError('native physical field boundary differs')
            masks.append(dict(file='DBDAT/JUG98030.FDI', record_offset=offset,
                              file_offset=absolute, before=jug[absolute], after=after))
        # Indexed payload decoding leaves the inner field XOR in place. The
        # physical fact bytes above are plain values because both XORs cancel.
        # Prove the result through the independent native fact reader as well.
        postimage = bytearray(jug)
        for mask in masks:
            postimage[mask['file_offset']] = mask['after']
        postfacts = native_facts(bytes(postimage), carrier)
        postpayload = entry.decode_payload(bytes(postimage))
        if (postfacts != dict(observed, birth_date=values['birth_date'])
                or postpayload[end + 8] ^ 0x61 != country):
            raise ValueError('adjudicated native birthday/country post-readback differs')
        updates.append(dict(carrier_id=carrier, before=copy.deepcopy(actor), values=values,
                            field_mask=FIELDS[:], native_masks=masks, witness=copy.deepcopy(witness),
                            expected_owner=clubs[actor['club_id']]['carrier_id']))
    result = dict(schema=changes.SCHEMA, season=base.season, release_id=base.release_id, kind=KIND,
        source_input=changes.binding(path), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=changes.digest(jug), eq_sha256=changes.digest(eq),
        textos_sha256=registry.sha256_file(base.game_path / 'DBDAT/TEXTOS.PKF'),
        updates=updates, scope=SCOPE, source_policy='historical-row-provider-ID-before-independent-official-facts-v1')
    result['transaction_id'] = changes.digest(packages.canonical_json_bytes(result))[:24]
    validate_mask(result)
    return result


def validate_mask(plan):
    from scripts import season_source_verified_player_changes_v1 as changes
    rows = plan.get('updates', [])
    if plan.get('schema') != changes.SCHEMA or plan.get('kind') != KIND or not rows:
        raise ValueError('explicit adjudicated fact plan required')
    carriers, offsets = set(), set()
    for row in rows:
        if (set(row) != {'carrier_id', 'before', 'values', 'field_mask', 'native_masks', 'witness', 'expected_owner'}
                or type(row['carrier_id']) is not int or row['carrier_id'] in carriers
                or row['field_mask'] != FIELDS or set(row['values']) != set(FIELDS)
                or row['values'] != row['witness']['values'] or len(row['native_masks']) != 5):
            raise ValueError('exact unique adjudicated fact rows required')
        carriers.add(row['carrier_id'])
        date.fromisoformat(row['values']['birth_date'])
        masks = row['native_masks']
        origin = masks[0]['record_offset']
        if [m['record_offset'] - origin for m in masks] != [0, 4, 5, 6, 7]:
            raise ValueError('only native country and complete four-byte birthday fields permitted')
        for mask in masks:
            if (set(mask) != {'file', 'record_offset', 'file_offset', 'before', 'after'}
                    or mask['file'] != 'DBDAT/JUG98030.FDI'
                    or any(type(mask[k]) is not int for k in ('record_offset', 'file_offset', 'before', 'after'))
                    or mask['record_offset'] < 0 or mask['file_offset'] < mask['record_offset']
                    or not 0 <= mask['before'] <= 255 or not 0 <= mask['after'] <= 255
                    or mask['file_offset'] in offsets
                    or mask['file_offset'] - mask['record_offset'] != masks[0]['file_offset'] - origin):
                raise ValueError('exact distinct native fact pre/post boundaries required')
            offsets.add(mask['file_offset'])
