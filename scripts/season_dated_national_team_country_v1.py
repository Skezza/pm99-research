"""One country byte from a dated national squad and an independently bound person.

This supplies a single historical game flag, not exclusive citizenship or a
claim about the player's club. It does not add mutable global source inputs.
The existing source-backed field writer performs the native transaction.
"""
import copy
from datetime import date
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_compatible_primary_role_v1 as identities
from scripts import season_original_country_policy_v2 as countries
from scripts.season_within_club_reserve_repair_v1 import native_facts

KIND = 'dated-national-squad-single-game-country'
SCOPE = 'Only explicitly selected nationality recipe fields/fallbacks and one country byte per player; identities, dates, roles, skills, club ownership, orders, tactics, managers and assets unchanged. Same-starting-year national-squad flag corroborated by an exact-identity canonical biography; not exclusive citizenship or target-club membership.'


def national_row(source, season, name, birthday):
    year = int(season[:4])
    url = urlsplit(source['url'])
    match = re.fullmatch(r'/(?:en/)?competitions/uefa-european-championship/seasons/(\d{4})-[^/]+/teams/([^/]+)/?', url.path)
    if (url.scheme != 'https' or url.hostname != 'datencenter.dfb.de'
            or not match or int(match[1]) != year or source['year'] != year
            or exchange.published_name_key(match[2].replace('-', ' ')) != exchange.published_name_key(source['country_label'])):
        raise ValueError('exact official national competition/country/starting year required')
    page = BeautifulSoup(exchange.original(source).read_bytes(), 'lxml')
    canonical = page.select_one('link[rel="canonical"]')
    if canonical is None or canonical.get('href', '').rstrip('/') != source['url'].rstrip('/'):
        raise ValueError('official national roster canonical origin differs')
    if source['country_label'] not in {h.get_text(' ', strip=True) for h in page.select('h2')}:
        raise ValueError('official national roster country heading differs')
    heading = source['squad_heading']
    if (not heading.startswith(('Squad ', 'Kader ')) or str(year) not in heading
            or heading not in {h.get_text(' ', strip=True) for h in page.select('h3')}):
        raise ValueError('dated national squad heading differs')
    matches = []
    for row in page.select('tr.c-Table-body-row'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != 3:
            continue
        full_name = ' '.join(' '.join(cells[1].find_all(string=True, recursive=False)).split())
        if exchange.published_name_key(full_name) != exchange.published_name_key(name):
            continue
        table = row.find_parent('table')
        context = table.find_previous('h3') if table else None
        if context is None or context.get_text(' ', strip=True) != heading:
            continue
        born = cells[2].get_text(' ', strip=True)
        if date.fromisoformat(born).isoformat() != birthday:
            raise ValueError('national squad has a conflicting full birthday')
        matches.append(row.get_text(' ', strip=True))
    if not matches:
        raise ValueError('exact full-name/DOB national squad person absent')
    # DFB may repeat the same person in historical and tournament tables. That
    # is one person's evidence, not multiple independent witnesses.
    return dict(country_label=source['country_label'], year=year,
                full_name=name, birth_date=birthday, original_rows=sorted(set(matches)))


def prepare(base, path, request):
    from scripts import season_source_verified_player_changes_v1 as changes
    if (request.get('schema') != changes.INPUT_SCHEMA or request.get('kind') != KIND
            or request.get('season') != base.season or request.get('release_id') != base.release_id
            or not request.get('changes')):
        raise ValueError('explicit exact-parent national-country input required')
    package = changes.pipeline.read_json_file(base.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = changes.ownership.native_owners(eq)
    codes = changes.compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    rows, seen = [], set()
    for selected in request['changes']:
        carrier = selected['carrier_id']
        if type(carrier) is not int or carrier in seen or selected.get('field_mask') != ['nationality']:
            raise ValueError('unique country-only native actors required')
        seen.add(carrier)
        actor = players[carrier]
        name = actor.get('source_name') or actor['name']
        birthday = actor['facts']['birth_date']
        pid = identities.historical_provider_id(base, package, actor, selected.get('historical_witness'))
        historical = selected.get('historical_witness', {}).get('historical_identity')
        if historical is None:
            raise ValueError('explicit original preallocation/fixture club witness required')
        allocation = changes.pipeline.read_json_file(exchange.original(historical['preallocation']))
        bound_clubs = [club for club in allocation['source_clubs']
            if any(row.get('source_row_sha256') == historical['source_row_sha256'] for row in club['players'])]
        if len(bound_clubs) != 1:
            raise ValueError('national-country source club witness is ambiguous')
        exchange.verify_match_club(historical['match'], bound_clubs[0]['selector']['club_name'])
        exchange.verify_match_club(historical['match'], clubs[actor['club_id']]['name'])
        if selected['profile']['provider_player_id'] != pid:
            raise ValueError('national-country canonical provider identity differs')
        profile = exchange.read_transfermarkt_profile(selected['profile'], pid)
        period = national_row(selected['national_roster'], base.season, name, birthday)
        country = exchange.SOURCE_COUNTRIES.get(period['country_label'])
        if (country is None or profile['published_nationality_label'] != period['country_label']
                or profile['published_birth_date'] != birthday
                or exchange.published_name_key(profile['published_full_name']) != exchange.published_name_key(name)):
            raise ValueError('dated national flag and exact biography identity/country disagree')
        observed = native_facts(jug, carrier)
        if (selected['before'] != actor or observed['birth_date'] != birthday
                or observed['name'].casefold() != actor['name'].casefold()
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}):
            raise ValueError('national-country native/recipe/owner preimage differs')
        code, label = countries.native_country(country, codes)
        if label == 'XXX':
            raise ValueError('unsupported national flags remain separately documented')
        entry = entries[carrier]
        payload = entry.decode_payload(jug)
        end = changes.native_player(payload, carrier)['name_end']
        offset = entry.payload_offset + end + 8
        if jug[offset] != (payload[end + 8] ^ 0x61) or jug[offset] == code:
            raise ValueError('exact changed nationality-byte preimage required')
        rows.append(dict(carrier_id=carrier, before=copy.deepcopy(actor),
            values=dict(nationality=country), field_mask=['nationality'],
            native_masks=[dict(file='DBDAT/JUG98030.FDI', record_offset=end+8,
                file_offset=offset, before=jug[offset], after=code)],
            evidence=dict(profile=selected['profile'], parsed_profile=profile,
                national_roster=selected['national_roster'], parsed_national_roster=period,
                native_country_label=label), expected_owner=clubs[actor['club_id']]['carrier_id']))
    result = dict(schema=changes.SCHEMA, kind=KIND, season=base.season, release_id=base.release_id,
        source_input=changes.binding(path), package_sha256=changes.registry.sha256_file(base.package_path),
        jug_sha256=changes.digest(jug), eq_sha256=changes.digest(eq), updates=rows, scope=SCOPE,
        source_policy='exact-historical-person-same-year-national-squad-and-matching-biography-country-v1')
    result['transaction_id'] = changes.digest(changes.packages.canonical_json_bytes(result))[:24]
    validate_mask(result)
    return result


def validate_mask(plan):
    from scripts import season_source_verified_player_changes_v1 as changes
    rows = plan.get('updates', [])
    if plan.get('schema') != changes.SCHEMA or plan.get('kind') != KIND or not rows:
        raise ValueError('explicit dated national-country plan required')
    carriers, offsets = set(), set()
    for row in rows:
        if (set(row) != {'carrier_id', 'before', 'values', 'field_mask', 'native_masks', 'evidence', 'expected_owner'}
                or type(row['carrier_id']) is not int or row['carrier_id'] in carriers
                or row['field_mask'] != ['nationality'] or set(row['values']) != {'nationality'}
                or not isinstance(row['values']['nationality'], str) or len(row['values']['nationality']) != 3
                or len(row['native_masks']) != 1):
            raise ValueError('exact country-only actor mask required')
        carriers.add(row['carrier_id'])
        mask = row['native_masks'][0]
        if (set(mask) != {'file', 'record_offset', 'file_offset', 'before', 'after'}
                or mask['file'] != 'DBDAT/JUG98030.FDI'
                or any(type(mask[k]) is not int for k in ('record_offset', 'file_offset', 'before', 'after'))
                or mask['record_offset'] < 0 or mask['file_offset'] < mask['record_offset']
                or not 0 <= mask['before'] <= 255 or not 0 <= mask['after'] <= 255
                or mask['before'] == mask['after'] or mask['file_offset'] in offsets):
            raise ValueError('exact distinct one-byte national-country transaction required')
        offsets.add(mask['file_offset'])
