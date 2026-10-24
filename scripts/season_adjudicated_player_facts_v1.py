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
from scripts import season_annual_row_identity_guard_v1 as annual_identity

KIND = 'adjudicated-source-player-facts'
FIELDS = ['birth_date', 'nationality']
SCOPE = 'Only explicitly adjudicated birthday and nationality facts/fallbacks and their exact native field bytes; historical source retained, all identities, ownership, roles, ratings, tactics, images, kits and other bytes unchanged.'


def checked(value):
    return exchange.original(value)


def verify_historical_identity(witness):
    """Reproduce a retained identity witness; legacy fixture path is unchanged."""
    if witness.get('identity_policy') == 'annual-source-row-person-identity-v1':
        annual_identity.verify(witness)
        return None
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
    links = [a for a in page.select('a[href]')
             if re.search(r'/spieler/' + re.escape(str(historical['provider_player_id'])) + r'(?:/|$)', a['href'])]
    full_names = {a.get('title') for a in links if a.get('title')}
    # Original providers may omit diacritics (Tokić/Tokic). Keep the complete
    # published name, numeric person, exact source row and dated club fixture
    # requirements; this is not permission to match initials or surnames alone.
    wanted = exchange.published_name_key(witness['full_name'])
    if wanted not in {exchange.published_name_key(name) for name in full_names}:
        # Some modern match sheets show only surnames, but publish the complete
        # name in their numeric profile URL. Accept that full slug only when
        # titles are absent, never as a way around a contradictory full title.
        slugs = set()
        if not full_names:
            for link in links:
                target = urlsplit(link['href'])
                if (target.scheme not in ('', 'https')
                        or target.hostname not in (None, 'www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us')):
                    continue
                slug = re.match(r'^/([^/]+)/(?:profil/spieler|leistungsdatendetails/spieler)/'
                    + re.escape(str(historical['provider_player_id'])) + r'(?:/|$)', target.path)
                if slug:
                    slugs.add(exchange.published_name_key(slug[1].replace('-', ' ')))
        if wanted not in slugs:
            raise ValueError('historical fixture does not independently publish the full identity')
    return int(historical['provider_player_id'])


def _adjudicate_official_sources(witness):
    """Reproduce historical identity before admitting independent official facts."""
    verify_historical_identity(witness)
    sources = witness['official_sources']
    if len(sources) < 2 or len({urlsplit(s['url']).hostname for s in sources}) != len(sources):
        raise ValueError('independent published source hosts required')
    birthdays, countries = [], []
    for source in sources:
        body = checked(source)
        receipt = pipeline.read_json_file(checked(source['receipt']))
        if witness.get('identity_policy') == 'annual-source-row-person-identity-v1':
            receipt_rows = [receipt] + (receipt.get('sources', []) if isinstance(receipt, dict) else [])
            if not any(isinstance(item, dict)
                       and (item.get('url') or item.get('final_url')) == source['url']
                       and (item.get('raw_sha256') or item.get('sha256')) == source['sha256']
                       for item in receipt_rows):
                raise ValueError('official source original URL/SHA receipt differs')
        elif receipt.get('url') != source['url'] or receipt.get('raw_sha256') != source['sha256']:
            # Keep legacy receipt semantics byte-for-byte: only the opt-in annual
            # witness accepts the established multi-source receipt envelope.
            raise ValueError('official source original URL/SHA receipt differs')
        if source.get('provider') == 'premier-league-sdp-player-api':
            from scripts.season_premier_league_profile_facts_v1 import parse_player_json
            identity = parse_player_json(body.read_bytes(), url=source['url'],
                provider_player_id=source['provider_player_id'], full_name=witness['full_name'])
            if source['birth_date'] != {'label': 'dates.birth', 'literal': identity['birth_date'], 'format': '%Y-%m-%d'}:
                raise ValueError('Premier League JSON birthday claim differs from its bound record')
            birthdays.append(identity['birth_date'])
            if source.get('nationality'):
                if source['nationality'] != {'label': 'country.country', 'literal': identity['nationality_label'], 'code': identity['nationality']}:
                    raise ValueError('Premier League JSON country claim differs from its bound record')
                countries.append(identity['nationality'])
            continue
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
        birthdays.append(_literal_day_birthday(claim))
        if source.get('nationality'):
            country = source['nationality']
            if (country['label'] != 'Nationality'
                    or country['label'] + ' ' + country['literal'] not in text
                    or NATIONALITY_CODES.get(country['literal']) != country['code']):
                raise ValueError('published nationality label/literal absent; birthplace is not nationality')
            countries.append(country['code'])
    values = witness['values']
    date.fromisoformat(values['birth_date'])
    if (set(values) not in ({'birth_date'}, set(FIELDS))
            or set(birthdays) != {values['birth_date']}
            or ('nationality' in values and set(countries) != {values['nationality']})):
        raise ValueError('independent birthday or explicit nationality claims disagree')
    return copy.deepcopy(values)


def _literal_day_birthday(claim):
    fmt, literal = claim['format'], claim['literal']
    if (not isinstance(fmt, str) or not isinstance(literal, str) or not literal.strip()
            or '%d' not in fmt or '%Y' not in fmt
            or not any(month in fmt for month in ('%m', '%b', '%B'))):
        raise ValueError('birthday source must publish a precise day, month and full year')
    return datetime.strptime(literal, fmt).date().isoformat()


def _subject_birthday_context(page, source, name, context):
    containers = [node for node in page.select('article,section,div,table,dl')
                  if name in node.get_text(' ', strip=True)
                  and context in ' '.join(node.get_text(' ', strip=True).split())]
    minimal = [node for node in containers
               if not any(child is not node and node in child.parents for child in containers)]
    if len(minimal) != 1:
        raise ValueError('birthday needs one profile container with its subject heading or full-name field')
    node = minimal[0]
    headings = [h.get_text(' ', strip=True) for h in node.select('h1,h2,h3,h4,h5,h6')]
    text = ' '.join(node.get_text(' ', strip=True).split())
    label = source.get('subject_label')
    if (any(h != name for h in headings)
            or (not headings and (not isinstance(label, str) or not label.strip()
                                  or label + ' ' + name not in text))):
        raise ValueError('birthday profile container has another subject heading or lacks an exact full-name field')


def adjudicate_independent_sources(witness):
    """Typed alternative: one official bio plus a distinct named reference source."""
    verify_historical_identity(witness)
    sources = witness['independent_sources']
    allowed = {'official_club_or_association_bio', 'independent_named_reference'}
    required = {'official_club_or_association_bio', 'independent_named_reference'}
    if (not isinstance(sources, list) or len(sources) < 2
            or len({urlsplit(s['url']).hostname for s in sources}) != len(sources)
            or not required.issubset({s.get('publisher_class') for s in sources})
            or any(s.get('publisher_class') not in allowed for s in sources)):
        raise ValueError('independent sources require distinct hosts, an official club/association bio, and a named reference')
    birthdays = []
    for source in sources:
        body = checked(source)
        receipt = pipeline.read_json_file(checked(source['receipt']))
        if receipt.get('url') != source['url'] or receipt.get('raw_sha256') != source['sha256']:
            raise ValueError('independent source original URL/SHA receipt differs')
        parsed = urlsplit(source['url'])
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('independent source needs explicit HTTPS origin')
        text = ' '.join(BeautifulSoup(body.read_bytes(), 'lxml').get_text(' ', strip=True).split())
        if witness['full_name'] not in text:
            raise ValueError('independent source does not name the historical person')
        page = BeautifulSoup(body.read_bytes(), 'lxml')
        headings = [h.get_text(' ', strip=True) for h in page.select('title,h1,h2,h3')]
        if not any(re.search(r'(?<!\w)' + re.escape(witness['full_name']) + r'(?!\w)', h) for h in headings):
            raise ValueError('independent biography subject heading does not identify the full person')
        anchors = source.get('identity_anchors')
        if (not isinstance(anchors, list) or not anchors
                or any(not isinstance(a, str) or not a.strip() or a not in text for a in anchors)):
            raise ValueError('independent source lacks reviewed identity-context anchors')
        claim = source['birth_date']
        context = claim.get('context')
        if (not isinstance(context, str) or context not in text
                or not claim.get('label') or not claim.get('literal')
                or claim['label'] not in context or claim['literal'] not in context):
            raise ValueError('independent source verbatim birthday context/label/literal absent')
        _subject_birthday_context(page, source, witness['full_name'], context)
        birthdays.append(_literal_day_birthday(claim))
    values = witness['values']
    date.fromisoformat(values['birth_date'])
    if set(values) != {'birth_date'} or set(birthdays) != {values['birth_date']}:
        raise ValueError('independent source birthday claims disagree or contain unsupported fields')
    return copy.deepcopy(values)


def adjudicate(witness):
    if 'independent_sources' in witness:
        if 'official_sources' in witness:
            raise ValueError('choose one explicit source-adjudication policy')
        return adjudicate_independent_sources(witness)
    return _adjudicate_official_sources(witness)


def verify_annual_request_binding(base, carrier, actor, witness):
    """Bind the opt-in annual witness to this exact selected actor and parent."""
    if witness.get('identity_policy') != 'annual-source-row-person-identity-v1':
        return
    annual = witness.get('annual_identity')
    if not isinstance(annual, dict) or any((
            annual.get('season') != base.season,
            annual.get('release_id') != base.release_id,
            annual.get('carrier_id') != carrier,
            annual.get('club_id') != actor.get('club_id'),
            witness.get('person_id') != actor.get('person_id'))):
        raise ValueError('annual identity witness differs from selected request actor or exact registered parent')


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
        if (type(carrier) is not int or carrier in seen
                or selection.get('field_mask') not in (['birth_date'], FIELDS)):
            raise ValueError('unique literal actors and explicit birthday/country-only mask required')
        seen.add(carrier)
        actor = actors[carrier]
        witness = selection['witness']
        verify_annual_request_binding(base, carrier, actor, witness)
        values = adjudicate(witness)
        if set(values) != set(selection['field_mask']):
            raise ValueError('adjudicated values must exactly match the selected field mask')
        observed = native_facts(jug, carrier)
        entry = entries[carrier]
        raw = entry.decode_payload(jug)
        end = native_player(raw, carrier)['name_end']
        old_country = raw[end + 8] ^ 0x61
        native_before_dob = selection.get('native_before_birth_date')
        actor_dob = actor['facts']['birth_date']
        if actor_dob == {'policy': 'preserve-existing-mode1'}:
            # Narrow branch for an explicitly measured old native birthday. The old value
            # remains a checked preimage, never an identity source.
            if not isinstance(native_before_dob, str) or observed['birth_date'] != native_before_dob:
                raise ValueError('preserved mode1 DOB requires an explicit exact native preimage')
        elif observed['birth_date'] != actor_dob or (native_before_dob is not None and observed['birth_date'] != native_before_dob):
            raise ValueError('adjudicated existing birthday fact differs from native preimage')
        if (actor != selection['before'] or actor['person_id'] != witness['person_id']
                or actor.get('source_name') != witness['full_name']
                or observed['name'].casefold() != actor['name'].casefold()
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}
                or old_country != codes[selection['native_before_country']]):
            raise ValueError('adjudicated actor/native/source identity or exact preimage differs')
        country = compiler._country_code(values['nationality'], codes) if 'nationality' in values else old_country
        if 'nationality' in values and country == codes['XXX']:
            raise ValueError('unsupported country is a documented gap, not an invented mapping')
        birthday = date.fromisoformat(values['birth_date'])
        encoded = [birthday.day, birthday.month, *birthday.year.to_bytes(2, 'little')]
        masks = []
        selected_fields = ([(end + 8, country)] if 'nationality' in values else [])
        selected_fields += [(end + 12 + i, b) for i, b in enumerate(encoded)]
        for offset, after in selected_fields:
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
                            field_mask=selection['field_mask'][:], native_masks=masks, witness=copy.deepcopy(witness),
                            expected_owner=clubs[actor['club_id']]['carrier_id']))
    result = dict(schema=changes.SCHEMA, season=base.season, release_id=base.release_id, kind=KIND,
        source_input=changes.binding(path), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=changes.digest(jug), eq_sha256=changes.digest(eq),
        textos_sha256=registry.sha256_file(base.game_path / 'DBDAT/TEXTOS.PKF'),
        updates=updates, scope=SCOPE, source_policy=(
            'annual-row-source-person-ID-before-official-independent-facts-v1'
            if any(row['witness'].get('identity_policy') == 'annual-source-row-person-identity-v1'
                   for row in request['changes']) else
            ('historical-row-provider-ID-before-official-plus-independent-named-reference-facts-v1'
             if any('independent_sources' in row['witness'] for row in request['changes'])
             else 'historical-row-provider-ID-before-independent-official-facts-v1')))
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
                or row['field_mask'] not in (['birth_date'], FIELDS)
                or set(row['values']) != set(row['field_mask'])
                or row['values'] != row['witness']['values']
                or len(row['native_masks']) != (5 if 'nationality' in row['values'] else 4)):
            raise ValueError('exact unique adjudicated fact rows required')
        carriers.add(row['carrier_id'])
        date.fromisoformat(row['values']['birth_date'])
        masks = row['native_masks']
        origin = masks[0]['record_offset']
        expected = [0, 4, 5, 6, 7] if 'nationality' in row['values'] else [0, 1, 2, 3]
        if [m['record_offset'] - origin for m in masks] != expected:
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
