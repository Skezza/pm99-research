"""Narrow retained-player role corrections, with a dated DFB roster witness.

The dated roster proves the broad role. A matching original biography supplies
a compatible fine role; this is explicitly not an exact-edition FIFA claim.
"""
import copy
from datetime import datetime
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_historical_roster_audit_v1 import native_player
from scripts.season_historical_role_plan_v1 import HTML_ROLES
from scripts.season_exact_fifa_role_delta_v1 import compatible

KIND = 'dated-roster-compatible-profile-roles'
FIELDS = ['primary_position', 'fine_roles']
SECTIONS = {'Tor': 'G', 'Torwart': 'G', 'Abwehr': 'D', 'Mittelfeld': 'M', 'Angriff': 'F', 'Sturm': 'F'}
SCOPE = 'Only selected exact-identity broad position and six fine-role bytes plus matching recipe fields/fallbacks. Names, dates, countries, skills, order, club ownership, tactics, managers and all assets unchanged. Dated DFB broad role; compatible published biography fine role, not exact-edition FIFA.'


def period_row(value, season, name, birthday, club):
    url = urlsplit(value['url'])
    year = int(season[:4])
    if (url.scheme != 'https' or url.hostname != 'datencenter.dfb.de'
            or f'/seasons/{year}-{year+1}/teams/' not in url.path):
        raise ValueError('dated roster origin and exact target season required')
    page = BeautifulSoup(exchange.original(value).read_bytes(), 'lxml')
    headings = {' '.join(h.get_text(' ', strip=True).split()) for h in page.select('h3')}
    if not any(h.startswith('Kader ') and h.endswith(f'{year}/{year+1}') for h in headings):
        raise ValueError('original dated roster heading differs')
    links = [a for a in page.select('a[href]')
             if urlsplit(a['href']).path == '/profil/' + str(value['provider_player_id'])]
    if len(links) != 1:
        raise ValueError('one exact dated roster provider identity required')
    link = links[0]
    identity_url = urlsplit(link['href'])
    context = parse_qs(identity_url.query).get('historize_title', [])
    if (identity_url.scheme != 'https' or identity_url.hostname != 'datencenter.dfb.de'
            or len(context) != 1 or ',' not in context[0]
            or exchange.published_name_key(context[0].split(',')[0]) != exchange.published_name_key(club)
            or not context[0].endswith(f'{year}/{str(year+1)[-2:]}')
            or exchange.published_name_key(link.get_text(' ', strip=True)) != exchange.published_name_key(name)):
        raise ValueError('dated roster person/club/season context differs')
    row = link.find_parent('tr')
    table = link.find_parent('table')
    cells = row.select('td') if row else []
    heading = table.select_one('thead th') if table else None
    if len(cells) != 3 or heading is None:
        raise ValueError('dated roster row/role section absent')
    born = datetime.strptime(cells[-1].get_text(' ', strip=True), '%d.%m.%Y').date().isoformat()
    broad = SECTIONS.get(heading.get_text(' ', strip=True))
    if born != birthday or broad not in ('D', 'M', 'F'):
        raise ValueError('dated full birthday or supported non-goalkeeper role differs')
    return dict(name=link.get_text(' ', strip=True), birth_date=born, primary_position=broad,
                section=heading.get_text(' ', strip=True), provider_player_id=value['provider_player_id'])


def prepare(base, path, request):
    from scripts import season_source_verified_player_changes_v1 as changes
    if (request.get('schema') != changes.INPUT_SCHEMA or request.get('kind') != KIND
            or request.get('season') != base.season or request.get('release_id') != base.release_id
            or not request.get('changes')):
        raise ValueError('dated role correction needs exact parent and explicit actors')
    package = pipeline.read_json_file(base.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    updates, seen = [], set()
    for selection in request['changes']:
        carrier = selection['carrier_id']
        if type(carrier) is not int or carrier in seen or selection.get('field_mask') != FIELDS:
            raise ValueError('unique explicit position-only actors required')
        seen.add(carrier)
        actor = players[carrier]
        club = clubs[actor['club_id']]
        name = actor.get('source_name') or actor['name']
        birthday = actor['facts']['birth_date']
        published = exchange.read_transfermarkt_profile(selection['profile'], selection['profile']['provider_player_id'])
        period = period_row(selection['period_source'], base.season, name, birthday, club['name'])
        observed = native_facts(jug, carrier)
        if (selection['before'] != actor or published['published_birth_date'] != birthday
                or exchange.published_name_key(published['published_full_name']) != exchange.published_name_key(name)
                or observed['birth_date'] != birthday or observed['name'].casefold() != actor['name'].casefold()
                or observed['position'] != actor['facts']['primary_position'] or observed['position'] == 'G'
                or owners.get(carrier) != {club['carrier_id']}):
            raise ValueError('dated role recipe/native/profile identity or exclusive owner differs')
        key = ''.join(c for c in (published['published_profile_position'] or '').casefold() if c.isalpha())
        fine = HTML_ROLES.get(key)
        broad = period['primary_position']
        if fine is None or not compatible(broad, fine):
            raise ValueError('published biography fine role contradicts dated broad role')
        entry = entries[carrier]
        payload = entry.decode_payload(jug)
        end, old_roles = read_indexed_native_roles(payload, carrier)
        if end != native_player(payload, carrier)['name_end']:
            raise ValueError('independent role and biography field boundaries differ')
        masks = []
        for offset, after in [(end+2+i, fine+1 if i == 0 else 0) for i in range(6)] + [(end+11, compiler.POSITION[broad])]:
            absolute = entry.payload_offset + offset
            if jug[absolute] != payload[offset] ^ 0x61:
                raise ValueError('dated role physical byte boundary differs')
            masks.append(dict(file='DBDAT/JUG98030.FDI', record_offset=offset, file_offset=absolute,
                              before=jug[absolute], after=after))
        candidate = bytearray(jug)
        for mask in masks:
            candidate[mask['file_offset']] = mask['after']
        after_facts = native_facts(bytes(candidate), carrier)
        _, after_roles = read_indexed_native_roles(entry.decode_payload(bytes(candidate)), carrier)
        if after_facts != dict(observed, position=broad) or after_roles != [fine, 98, 98, 98, 98, 98]:
            raise ValueError('dated role native post-readback differs')
        updates.append(dict(carrier_id=carrier, before=copy.deepcopy(actor),
            values=dict(primary_position=broad, fine_roles=[fine]), field_mask=FIELDS[:], native_masks=masks,
            evidence=dict(profile=selection['profile'], period_source=selection['period_source'],
                parsed_period=period, parsed_profile=published, previous_native_roles=old_roles),
            expected_owner=club['carrier_id']))
    result = dict(schema=changes.SCHEMA, kind=KIND, season=base.season, release_id=base.release_id,
        source_input=changes.binding(path), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=changes.digest(jug), eq_sha256=changes.digest(eq), updates=updates, scope=SCOPE,
        source_policy='dated-original-DFB-full-name-DOB-club-position-and-compatible-profile-role-v1')
    result['transaction_id'] = changes.digest(packages.canonical_json_bytes(result))[:24]
    validate_mask(result)
    return result


def validate_mask(plan):
    from scripts import season_source_verified_player_changes_v1 as changes
    rows = plan.get('updates', [])
    if plan.get('schema') != changes.SCHEMA or plan.get('kind') != KIND or not rows:
        raise ValueError('explicit dated role fact plan required')
    seen, offsets = set(), set()
    for row in rows:
        if (set(row) != {'carrier_id', 'before', 'values', 'field_mask', 'native_masks', 'evidence', 'expected_owner'}
                or type(row['carrier_id']) is not int or row['carrier_id'] in seen
                or row['field_mask'] != FIELDS or set(row['values']) != set(FIELDS)
                or row['values']['primary_position'] not in ('D', 'M', 'F')
                or len(row['values']['fine_roles']) != 1
                or type(row['values']['fine_roles'][0]) is not int
                or not 0 <= row['values']['fine_roles'][0] <= 17
                or not compatible(row['values']['primary_position'], row['values']['fine_roles'][0])):
            raise ValueError('exact unique dated role rows required')
        seen.add(row['carrier_id'])
        masks = row['native_masks']
        if len(masks) != 7 or [m['record_offset'] - masks[0]['record_offset'] for m in masks] != [0, 1, 2, 3, 4, 5, 9]:
            raise ValueError('only six role bytes and broad-position byte permitted')
        if [m['after'] for m in masks] != [row['values']['fine_roles'][0]+1, 0, 0, 0, 0, 0,
                                        compiler.POSITION[row['values']['primary_position']]]:
            raise ValueError('role native post-mask must encode the exact approved values')
        for mask in masks:
            if (set(mask) != {'file', 'record_offset', 'file_offset', 'before', 'after'}
                    or mask['file'] != 'DBDAT/JUG98030.FDI'
                    or any(type(mask[k]) is not int for k in ('record_offset', 'file_offset', 'before', 'after'))
                    or mask['record_offset'] < 0 or mask['file_offset'] < mask['record_offset']
                    or not 0 <= mask['before'] <= 255 or not 0 <= mask['after'] <= 255
                    or mask['file_offset'] in offsets
                    or mask['file_offset'] - mask['record_offset'] != masks[0]['file_offset'] - masks[0]['record_offset']):
                raise ValueError('exact distinct native role pre/post masks required')
            offsets.add(mask['file_offset'])
