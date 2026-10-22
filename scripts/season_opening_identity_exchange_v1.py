"""Data-driven, fixed-carrier opening ownership corrections.

Move represented people without rerating them; admit new people only from an
exact linked match/profile pair. Selected retirements need retained dated
evidence. Reserve exchanges cannot silently replace a starter. No club or
manager is renamed and unrelated records, kits and tactics remain untouched.
"""
import copy
from datetime import date, datetime
import hashlib
import re
from statistics import median
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_rating_calibration_v3 as ratings
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_historical_role_plan_v1 import HTML_ROLES
from scripts.capture_transfermarkt_opening_lineups_v1 import _modern_lineup, _classic_lineup
from scripts.capture_transfermarkt_lineup_person_evidence_v1 import _profile_facts
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.build_woking_owned_opening_20261011 import skills
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order, replace_initial_order
from app.xor import xor_decode

SCHEMA = 'pm99-source-bound-opening-identity-exchange-v1'
INPUT_SCHEMA = SCHEMA + '-input'
PREFIX = 'opening-identity-exchange-'
MODE = 'known-good-baseline-source-bound-opening-identity-exchange-v1'
SCOPE = 'Selected source-bound reserve identities, portraits and explicit complete owned bench ordering only; fixed club membership/counts, starters, tactics, managers, kits and unrelated records preserved.'
SOURCE_COUNTRIES = {**NATIONALITY_CODES, 'Benin': 'BEN'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def original(value):
    path = registry.ROOT / value['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != value['sha256']:
        raise ValueError('opening exchange retained source changed')
    return path


def source_text(value):
    page = BeautifulSoup(original(value).read_bytes(), 'lxml')
    text = ' '.join(page.get_text(' ', strip=True).split())
    if not value.get('anchors') or any(' '.join(a.split()) not in text for a in value['anchors']):
        raise ValueError('opening exchange dated evidence lacks exact reviewed anchors')
    return text


def dated_source(value):
    text = source_text(value)
    anchor = value.get('date_anchor')
    if not isinstance(anchor, str) or anchor not in text:
        raise ValueError('dated exchange evidence needs its literal original date')
    parsed = None
    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%d %B %Y', '%d %b %Y', '%B %d, %Y', '%a %d %b %Y'):
        try:
            parsed = datetime.strptime(anchor, fmt).date().isoformat()
            break
        except ValueError:
            pass
    if parsed != value.get('event_date'):
        raise ValueError('dated exchange source date does not reproduce')
    if value.get('dfb_registration_row'):
        claim = value['dfb_registration_row']
        origin = urlsplit(value['url'])
        page = BeautifulSoup(original(value).read_bytes(), 'lxml')
        if (origin.scheme != 'https' or origin.hostname != 'datencenter.dfb.de'
                or not re.search(r'/(?:seasons/)?' + str(claim['season_start_year']) + '-' +
                    str(claim['season_start_year'] + 1) + r'/(?:teams|mannschaft)/', origin.path)
                or claim['roster_heading'] not in [h.get_text(' ', strip=True) for h in page.select('h3')]
                or claim['club_heading'] not in [h.get_text(' ', strip=True) for h in page.select('h2')]):
            raise ValueError('dated registration source club/season context differs')
        rows = []
        for row in page.select('tr.c-Table-body-row'):
            cells = row.find_all('td', recursive=False)
            if len(cells) != 3:
                continue
            name = ' '.join(' '.join(cells[1].find_all(string=True, recursive=False)).split())
            links = cells[1].find_all('a')
            if links:
                # DFB renders some names as profile links and others as text.
                # Admit only one same-origin person link, never a sidebar or
                # mixed-name cell. Registration dates remain row-bound below.
                link_origin = urlsplit(links[0].get('href', ''))
                if (name or len(links) != 1 or link_origin.scheme != 'https'
                        or link_origin.netloc != 'datencenter.dfb.de'
                        or not re.fullmatch(r'/profil/[0-9]+', link_origin.path)):
                    continue
                name = ' '.join(links[0].get_text(' ', strip=True).split())
            if (name == claim['full_name'] and cells[2].get_text(' ', strip=True) == claim['birthday_literal']):
                rows.append(cells[1])
        kind = claim.get('date_kind', 'ab')
        if (kind not in ('ab', 'bis') or len(rows) != 1 or '(' + kind + ' ' + anchor + ')' not in
                [s.get_text(' ', strip=True) for s in rows[0].select('small')]):
            raise ValueError('dated registration exact person/DOB/entry row differs')
    if value.get('person_row'):
        claim = value['person_row']
        page = BeautifulSoup(original(value).read_bytes(), 'html.parser')
        rows = [row for row in page.select('table.items > tbody > tr') if row.select_one(
            'a[href*="/profil/spieler/' + str(claim['provider_player_id']) + '"]')]
        if len(rows) != 1:
            raise ValueError('dated transfer needs one exact player roster row')
        row = rows[0]
        table = row.find_parent('table', class_='items')
        headers = [' '.join(cell.get_text(' ', strip=True).split()) for cell in table.select('thead th')]
        cells = row.find_all('td', recursive=False)
        if (claim['date_column'] != 'Joined' or headers.count('Joined') != 1
                or headers.count('Signed from') != 1
                or claim['date_literal'] != anchor
                or cells[headers.index(claim['date_column'])].get_text(' ', strip=True) != anchor
                or not cells[headers.index('Signed from')].select_one(
                    'a[href*="/verein/' + str(claim['from_club_id']) + '/"]')):
            raise ValueError('dated player Joined/from-club row does not reproduce')


def verify_first_league_fixture(value):
    """Permit a non-August opener only by replaying its retained league schedule."""
    from types import SimpleNamespace
    from scripts.capture_transfermarkt_opening_lineups_v1 import _first_fixture, TeamRef, SCHEMA as CAPTURE_SCHEMA
    if (value.get('membership_mode') != 'original-published-first-league-fixture-bench'
            and not (value.get('membership_mode') == 'classic-played-substitutes'
                     and value.get('fixture_basis') == 'recorded-first-league-fixture')):
        raise ValueError('non-August membership needs an explicit first league fixture')
    original(value)
    capture = pipeline.read_json_file(original(value['first_league_capture']))
    year = value['season_start_year']
    if (type(year) is not int or capture.get('schema_version') != CAPTURE_SCHEMA
            or capture.get('season_start_year') != year or value['date'][:4] != str(year)):
        raise ValueError('first league fixture capture season differs')
    rows = [row for row in capture['clubs'] if
        row['source_selector'].get('transfermarkt_club_id') == value['provider_club_id']
        and row.get('source_competition_code') == value['competition']]
    if len(rows) != 1:
        raise ValueError('first league fixture needs one exact captured competition club')
    row = rows[0]
    schedule = value['schedule_source']
    raw = original(schedule).read_bytes()
    canonical = BeautifulSoup(raw, 'html.parser').select_one('link[rel="canonical"]')
    canonical_url = urlsplit(canonical.get('href', '') if canonical else '')
    requested_url = urlsplit(schedule['url'])
    # Transfermarkt canonical schedules omit the season suffix. Bind the
    # exact captured seasonal URL separately and the canonical club identity.
    if (schedule['url'] != row['schedule_url'] or canonical is None
            or (canonical_url.scheme, canonical_url.netloc) != ('https', requested_url.netloc)
            or canonical_url.path.rstrip('/') != requested_url.path.split('/saison_id/')[0]):
        raise ValueError('first league fixture original club schedule differs')
    def get(url, key):
        if url != schedule['url'] or key != f'schedule/{year}/{value["provider_club_id"]}.html':
            raise ValueError('first league fixture schedule route differs')
        return raw
    ref = TeamRef(source_club_name=row['source_selector']['club_name'],
        transfermarkt_name=row['source_selector']['transfermarkt_club_name'],
        club_id=value['provider_club_id'], club_path=urlsplit(schedule['url']).path,
        identity_match_method='exact-retained-first-league-capture')
    first = _first_fixture(ref, season_start_year=year, competition_code=value['competition'],
                           cache=SimpleNamespace(get=get))
    if (first['date'] != value['date'] or row['first_league_fixture_date'] != value['date']
            or first['report_url'] != value['url'] or row['lineup_source_url'] != value['url']
            or first['match_id'] != row['source_match_id']):
        raise ValueError('non-August report is not the exact first league fixture')


def match_people(value):
    """Scope links to the exact requested club, not the opponent or page sidebar."""
    page = BeautifulSoup(original(value).read_bytes(), 'html.parser')
    stamp = page.select_one('.sb-datum')
    dates = re.findall(r'\b\d{2}/\d{2}/\d{2}\b', stamp.get_text(' ', strip=True) if stamp else '')
    if len(dates) != 1 or datetime.strptime(dates[0], '%d/%m/%y').date().isoformat() != value['date']:
        raise ValueError('opening exchange original match date differs')
    def matches(box):
        ids = {int(m.group(1)) for a in box.select('a[href]')
               if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href']))}
        return ids == {value['provider_club_id']}
    boxes = [b for b in page.select('.aufstellung-box') if matches(b)]
    if not boxes:
        boxes = [b for b in page.select('.large-6') if matches(b)]
    if len(boxes) != 1:
        raise ValueError('opening exchange match needs one exact club box')
    if value.get('membership_mode') == 'classic-published-starting-XI':
        xi, _ = _classic_lineup(boxes[0])
        return xi, []
    if value.get('membership_mode') == 'classic-played-substitutes':
        xi, _ = _classic_lineup(boxes[0])
        owned = {p['source_player_id'] for p in xi}
        seen = set(owned)
        used = []
        for event in page.select('li.sb-aktion-heim, li.sb-aktion-gast'):
            badge = event.select_one('.sb-aktion-wappen')
            if badge is None:
                continue
            ids = {int(m.group(1)) for a in badge.select('a[href]')
                   if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href']))}
            if ids != {value['provider_club_id']}:
                continue
            entering = event.select('.sb-aktion-wechsel-ein a[href]')
            leaving = event.select('.sb-aktion-wechsel-aus a[href]')
            if not entering and not leaving:
                continue
            if len(entering) != 1 or len(leaving) != 1:
                raise ValueError('classic substitution needs one exact entering and leaving person')
            def person_id(link):
                match = re.search(r'^/([^/]+)/leistungsdatendetails/spieler/(\d+)(?:/|$)', link['href'])
                if match is None:
                    raise ValueError('classic substitution numeric identity absent')
                return match.group(1), match.group(2)
            slug, pid = person_id(entering[0])
            _, out = person_id(leaving[0])
            if out not in owned or pid in seen:
                raise ValueError('classic substitution does not belong to exact club participants')
            owned.remove(out)
            owned.add(pid)
            seen.add(pid)
            used.append(dict(display_name=entering[0].get_text(' ', strip=True), source_player_id=pid,
                source_slug=slug, source_url='https://www.transfermarkt.co.uk/'+slug+'/profil/spieler/'+pid,
                membership_basis='published-used-substitute-not-complete-bench'))
        if not used:
            raise ValueError('classic match has no exact club used-substitute evidence')
        return xi, used
    xi, bench, formation, manager = _modern_lineup(boxes[0])
    return xi, bench


def verify_match_club(value, native_name):
    from scripts.capture_transfermarkt_opening_lineups_v1 import _club_key
    page = BeautifulSoup(original(value).read_bytes(), 'html.parser')
    links = page.select('a[href*="/startseite/verein/' + str(value['provider_club_id']) + '"]')
    labels = {published_name_key(text) for a in links
              for text in (a.get('title', ''), a.get_text(' ', strip=True)) if text}
    # Structural designators such as FC may be absent from the native label;
    # require exact structural equality, never substring/initial matching.
    structural = {_club_key(text) for a in links
                  for text in (a.get('title', ''), a.get_text(' ', strip=True)) if text}
    if (published_name_key(native_name) not in labels
            and (not _club_key(native_name) or _club_key(native_name) not in structural)):
        raise ValueError('published match club does not identify the destination native club')


def read_transfermarkt_profile(profile, pid):
    """Read stable identity and published scalar facts, without season claims."""
    raw = original(profile).read_bytes()
    requested = urlsplit(profile['url'])
    allowed_hosts = {'www.transfermarkt.co.uk', 'www.transfermarkt.us',
                     'www.transfermarkt.com', 'www.transfermarkt.de'}
    if requested.scheme != 'https' or requested.netloc not in allowed_hosts:
        raise ValueError('profile source must use an approved Transfermarkt HTTPS origin')
    if not re.search(r'/spieler/' + str(pid) + r'(?:[/?]|$)', profile['url']):
        raise ValueError('new person profile URL has another provider ID')
    page = BeautifulSoup(raw, 'html.parser')
    # The page must identify itself, not merely contain an unrelated sidebar link.
    canonical = page.select_one('link[rel="canonical"]')
    if canonical is None or not re.search(r'/spieler/' + str(pid) + r'(?:[/?]|$)', canonical.get('href', '')):
        raise ValueError('new person original canonical profile differs')
    declared = urlsplit(canonical['href'])
    if (declared.scheme, declared.netloc) != (requested.scheme, requested.netloc):
        raise ValueError('profile canonical origin differs from retained source')
    parsed = _profile_facts(raw, player=dict(source_player_id=str(pid)))
    birthday = parsed['published_birth_date']
    if birthday is None:
        field = page.select_one('[itemprop="birthDate"]')
        text = field.get_text(' ', strip=True) if field else ''
        match = re.search(r'\b([A-Z][a-z]{2} \d{1,2}, \d{4})\b', text)
        if match:
            birthday = datetime.strptime(match.group(1), '%b %d, %Y').date().isoformat()
    parsed['published_birth_date'] = birthday
    return parsed


def new_person(selection, evidence):
    pid = selection['provider_player_id']
    squad_biography = 'squad_biography' in selection
    if squad_biography:
        if 'profile' in selection or 'native_display_name' in selection or not selection.get('opening_contract'):
            raise ValueError('squad biography needs dated membership, no fabricated profile/family heading')
        from scripts import season_transfermarkt_squad_biography_v1 as biographies
        claim = selection['opening_contract']
        year = date.fromisoformat(claim['opening_date']).year
        profile = evidence[selection['squad_biography']]
        parsed = biographies.read(profile, pid, season=f'{year}-{str(year+1)[-2:]}',
            club_name=claim['club_name'], provider_club_id=claim['provider_club_id'])
    else:
        profile = evidence[selection['profile']]
        parsed = read_transfermarkt_profile(profile, pid)
    birthday = parsed['published_birth_date']
    if (parsed['published_full_name'], birthday) != (selection['name'], selection['birth_date']):
        raise ValueError('new person original name or literal birthday differs')
    if selection['profile_position'] not in (parsed['published_profile_position'] or ''):
        raise ValueError('new person source position differs')
    if squad_biography and selection['profile_position'] != parsed['published_profile_position']:
        raise ValueError('squad biography must use the exact published row position')
    key = re.sub(r'[^a-z]', '', selection['profile_position'].casefold())
    if (key not in HTML_ROLES or selection['fine_roles'] != [HTML_ROLES[key]]
            or not compatible(selection['position'], selection['fine_roles'][0])):
        raise ValueError('new person broad/fine role contradicts source profile')
    if selection['nationality_label'] not in (parsed['published_nationality_label'] or ''):
        raise ValueError('new person source nationality differs')
    if squad_biography and selection['nationality_label'] not in parsed['published_nationality_label'].split(' / '):
        raise ValueError('squad biography requires an exact published nationality label')
    if SOURCE_COUNTRIES.get(selection['nationality_label']) != selection['nationality']:
        raise ValueError('new person source nationality label/code disagree')
    if selection.get('opening_contract'):
        from scripts import season_dated_reserve_membership_v1 as contracts
        contracts.verify(selection, evidence)
        policy = selection['opening_contract']['policy']
        membership = ('original-published-August-Sky-bench-not-played-appearance-claim'
                      if policy == contracts.SKY_POLICY else
                      'original-published-August-Sky-starting-XI-not-opening-match-claim'
                      if policy == contracts.SKY_XI_POLICY else
                      'dated-opening-contract-bracket-not-matchday-claim')
    else:
        fixture = evidence[selection['match']]
        if date.fromisoformat(fixture['date']).month != 8:
            verify_first_league_fixture(fixture)
        _, bench = match_people(fixture)
        people = [row for row in bench if row['source_player_id'] == str(pid)]
        if len(people) != 1:
            raise ValueError('new person is not in the exact club published bench')
        membership = ('original-published-opening-used-substitute' if
            fixture.get('membership_mode') == 'classic-played-substitutes' else 'original-published-opening-bench')
    result = dict(source_person=dict(name=selection['name'], birth_date=birthday,
                    source_player_id=pid, source_provider='transfermarkt',
                    source_profile_url=parsed['linked_profile_url'] if squad_biography else profile['url']),
                source_player=dict(name=selection['name'], birth_date=birthday,
                    position=selection['position'], nationality=selection['nationality'],
                    height_cm=parsed['published_height_cm'] if squad_biography else None,
                    weight_kg=None, shirt_number=parsed['published_shirt_number'] if squad_biography else None),
                raw_evidence=dict(status='raw-source-reparsed', local_path=profile['path'], source_sha256=profile['sha256']),
                membership=membership)
    if squad_biography:
        result['raw_evidence'].update(biography_source_kind=parsed['biography_source_kind'], profile_page_captured=False)
    return result


def identity(player):
    return roster.normalise(player.get('source_name') or player['name']), player['facts']['birth_date']


def published_profile_family_display(selection, evidence):
    """Use an explicitly marked entire family component, never the last token."""
    target = selection['native_display_name']
    profile = evidence[selection['profile']]
    parsed = read_transfermarkt_profile(profile, selection['provider_player_id'])
    page = BeautifulSoup(original(profile).read_bytes(), 'html.parser')
    header = page.select_one('h1.data-header__headline-wrapper')
    if header:
        for number in header.select('.data-header__shirt-number'):
            number.decompose()
    family = header.select('strong') if header else []
    if ((parsed['published_full_name'], parsed['published_birth_date']) != (selection['name'], selection['birth_date'])
            or len(family) != 1 or header.get_text(' ', strip=True) != parsed['published_full_name']
            or family[0].get_text(' ', strip=True) != target
            or not isinstance(target, str) or len(target.split()) != 1):
        raise ValueError('native short display needs the exact published complete single-component family heading')
    return delta.compiler._pm99_text(target, label='published entire family display')


def published_name_key(name):
    # Same full-name spelling policy as the native transliteration boundary;
    # do not split a surname, compare initials or accept substring matches.
    return roster.normalise(name.translate(str.maketrans({'ø': 'o', 'Ø': 'O'})))


def selected_carriers(plan):
    return {row['carrier_id'] for row in plan['decisions']}


def verify_bench_mapping(result, row, evidence):
    resulting = {p['carrier_id']: p for p in result['players']}
    _, bench = match_people(evidence[row['match']])
    mapping = row['bench_mapping']
    if (len(mapping) != len(bench)
            or [str(p['provider_player_id']) for p in mapping] != [p['source_player_id'] for p in bench]):
        raise ValueError('published bench provider IDs differ')
    for mapped, published in zip(mapping, bench):
        actor = resulting[mapped['carrier_id']]
        if published_name_key(actor.get('source_name') or actor['name']) != published_name_key(published['display_name']):
            raise ValueError('published bench provider ID maps to another resulting identity')


def verify_order_only_record(before, after):
    expected = replace_initial_order(before, read_initial_order(after).order, allow_compact=True)
    if after != expected:
        raise ValueError('unselected ordered player changed beyond its startup-order byte')


def filename(plan):
    return PREFIX + plan['transaction_id'] + '.json'


def prepare(base, input_path):
    request = pipeline.read_json_file(input_path)
    if (request.get('schema') != INPUT_SCHEMA or request.get('season') != base.season
            or request.get('release_id') != base.release_id):
        raise ValueError('opening exchange needs an explicit exact-parent request')
    package = pipeline.read_json_file(base.package_path)
    players = {row['carrier_id']: row for row in package['players']}
    clubs = {row['id']: row for row in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    from scripts.season_opening_order_repair_v1 import native_owners
    owners = native_owners(eq)
    evidence = request['evidence']
    for value in evidence.values():
        original(value)
        if value.get('anchors'):
            source_text(value)
    if any('date' in value and value['date'][:4] != base.season[:4] for value in evidence.values()):
        raise ValueError('opening exchange fixture is not in the target starting year')
    complete_mode1 = None
    if 'complete_mode1_opening' in request:
        from scripts import season_complete_mode1_opening_v1 as complete
        complete_mode1 = complete.prepare(base, request, package, jug, eq)
    moves = request['moves']
    targets = [row['destination'] for row in moves] + [row['carrier_id'] for row in request['new_people']]
    order_only = complete_mode1 is not None and complete_mode1['policy'] == complete.ORDER_ONLY_POLICY
    if (not targets and not order_only) or len(set(targets)) != len(targets):
        raise ValueError('opening exchange needs unique complete destinations')
    sources = [row['source'] for row in moves]
    if len(set(sources)) != len(sources) or not set(sources) <= set(targets):
        raise ValueError('every moved original copy must be consumed exactly once')
    for carrier in set(targets):
        actor = players[carrier]
        native = facts.native_facts(jug, carrier)
        if ((native['startup_order'] <= 11 and complete_mode1 is None) or native['birth_date'] != actor['facts']['birth_date']
                or roster.normalise(native['name']) != roster.normalise(actor['name'])
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}
                or skills(jug, carrier) != actor['ratings']['values']):
            raise ValueError('opening exchange requires exact exclusively owned native reserves and matching skills')
    decisions = []
    for row in moves:
        source, target = players[row['source']], players[row['destination']]
        if (source['club_id'], target['club_id']) != (row['from_club'], row['to_club']):
            raise ValueError('opening exchange source or destination club differs')
        if not row.get('evidence') or any(not evidence[key].get('anchors') for key in row['evidence']):
            raise ValueError('each moved owner needs dated reviewed evidence')
        for key in row['evidence']:
            dated_source(evidence[key])
        decision = dict(carrier_id=row['destination'], preserved_source_carrier=row['source'],
                        before=target, moved_before=source)
        if row.get('published_family_person_id') is not None:
            from scripts import season_published_family_component_v1 as families
            from scripts import season_same_carrier_name_capacity_v1 as capacity
            supplement = original(request['published_person_input'])
            person = dict(source_player_id=row['published_family_person_id'], birth_date=source['facts']['birth_date'])
            claim = families.claims(supplement, {person['source_player_id']}).get(person['source_player_id'])
            if claim is None:
                raise ValueError('moved person has no original explicit full-family display claim')
            aliases = families.native_candidates(claim, person)
            if len(aliases) != 1:
                raise ValueError('moved person has ambiguous published family display')
            full_names = {published_name_key(v['original_full_name']) for v in claim['components']}
            if published_name_key(source.get('source_name') or source['name']) not in full_names:
                raise ValueError('published family display belongs to another moved person')
            _, recovery = capacity.recover_slot(jug, row['destination'], request['same_carrier_name_capacity'])
            decision.update(display_name=aliases[0]['name'], published_family_claim=claim,
                            same_carrier_capacity_claim=recovery)
        decisions.append(decision)
    retired = set(targets) - set(sources)
    retirements = request.get('retirements', [])
    if {row['carrier_id'] for row in retirements} != retired or len(retirements) != len(retired):
        raise ValueError('every omitted old identity needs an explicit dated retirement decision')
    for row in retirements:
        actor = players[row['carrier_id']]
        if ((actor.get('source_name') or actor['name'], actor['facts']['birth_date']) != (row['name'], row['birth_date'])
                or not row.get('evidence') or any(not evidence[key].get('anchors') for key in row['evidence'])):
            raise ValueError('retirement identity or dated evidence differs')
        for key in row['evidence']:
            dated_source(evidence[key])
    updates = []
    for row in request['new_people']:
        actor = players[row['carrier_id']]
        if actor['club_id'] != row['club_id']:
            raise ValueError('new person destination club differs')
        if row.get('opening_contract'):
            from scripts import season_dated_reserve_membership_v1 as contracts
            opening_date = contracts.verify(row, evidence, season=base.season, club=clubs[actor['club_id']])
        elif complete_mode1 is not None:
            # Complete original-club/numeric-XI proof above already establishes
            # the explicit native/published club-name bridge.
            opening_date = evidence[row['match']]['date']
        else:
            verify_match_club(evidence[row['match']], clubs[actor['club_id']]['name'])
            opening_date = evidence[row['match']]['date']
        replacement = new_person(row, evidence)
        key = roster.normalise(row['name']), row['birth_date']
        if any(identity(p) == key for p in players.values()):
            raise ValueError('new person already represented; use a retained move')
        updates.append(dict(layer='main', player_id=actor['id'], carrier_id=row['carrier_id'],
            before=actor, replacement=replacement, replacement_opening_evidence=dict(date=opening_date)))
        decision = dict(carrier_id=row['carrier_id'], preserved_source_carrier=None, before=actor,
                        fine_roles=row['fine_roles'])
        if 'native_display_name' in row:
            decision.update(display_name=published_profile_family_display(row, evidence),
                            display_policy='original-profile-explicit-entire-family-heading-v1')
        decisions.append(decision)
    plan = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        source_input=binding(input_path), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=digest(jug), eq_sha256=digest(eq), request=request, updates=updates, decisions=decisions,
        bindings=dict(snapshot=dict(project_url='https://www.transfermarkt.com/')),
        source_title='Dated opening bench identities and August ownership exchanges',
        proof_covers=['bounded-reserve-ownership-and-original-bench-only'], scope=SCOPE)
    if complete_mode1 is not None:
        plan['complete_mode1_opening'] = complete_mode1
        plan['scope'] = 'Selected dated identity replacements plus complete original-XI mode1 startup orders; other actors/facts, roster links, managers, opaque tactics, kits and assets preserved except displaced photos.'
        plan['proof_covers'] = ['original-first-league-XI-and-positive-bench-identities', 'all-other-player-facts-and-opaque-tactics-preserved']
        if order_only:
            plan['scope'] = 'Only complete source-bound mode1 startup orders and recipe roster ordering; every identity, fact, skill, EQ link, tactic, manager, kit and portrait preserved.'
            plan['proof_covers'] = ['original-first-league-XI-order-only', 'all-player-facts-and-EQ-assets-preserved']
    if any(row.get('opening_contract') for row in request['new_people']):
        plan.update(source_title='Dated opening reserve identities and positive ownership brackets',
                    proof_covers=['bounded-reserve-ownership-and-positive-dated-contract-bracket-not-matchday-claims'])
        from scripts import season_dated_reserve_membership_v1 as contracts
        if any(row.get('opening_contract', {}).get('policy') in (contracts.SKY_POLICY, contracts.SKY_XI_POLICY)
               for row in request['new_people']):
            plan.update(source_title='Dated opening reserve identities and source-specific August membership evidence',
                        proof_covers=['bounded-reserve-ownership-and-individually-bound-August-membership-no-unsupported-appearance-claims'])
    for row in request.get('orders', []):
        if evidence[row['match']].get('membership_mode') in ('classic-played-substitutes', 'classic-published-starting-XI'):
            raise ValueError('used substitutes are not a complete published bench; cannot authorise bench order')
        club = next(c for c in package['clubs'] if c['carrier_id'] == row['club_carrier_id'])
        verify_match_club(evidence[row['match']], club['name'])
        owned = {p['carrier_id'] for p in players.values() if p['club_id'] == club['id']}
        order = row['full_order']
        if len(order) != len(set(order)) or set(order) != owned:
            raise ValueError('bench ordering must cover the exact complete owned roster')
        old_order = sorted(owned, key=lambda c: facts.native_facts(jug, c)['startup_order'])
        if order[:11] != old_order[:11]:
            raise ValueError('reserve exchange cannot reorder the starting XI')
        _, bench = match_people(evidence[row['match']])
        mapping = row['bench_mapping']
        if ([str(p['provider_player_id']) for p in mapping] != [p['source_player_id'] for p in bench]
                or [p['carrier_id'] for p in mapping] != order[11:11 + len(bench)]):
            raise ValueError('bench ordering does not match the exact original published bench')
    plan['transaction_id'] = digest(packages.canonical_json_bytes(plan))[:24]
    # Bind exact match IDs to the resulting identities, not independent lists.
    result = bind(package, plan)
    for row in request.get('orders', []):
        verify_bench_mapping(result, row, evidence)
    return plan


def verify(base, plan):
    if plan.get('schema') != SCHEMA or prepare(base, original(plan['source_input'])) != plan:
        raise ValueError('opening exchange original request does not reproduce')


def bind(package, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    if (registry.sha256_file(base.package_path) != plan['package_sha256']
            or pipeline.read_json_file(base.package_path) != package):
        raise ValueError('opening exchange recipe requires its exact baseline')
    if registry.sha256_file(registry.ROOT / plan['source_input']['path']) != plan['source_input']['sha256']:
        raise ValueError('opening exchange request changed')
    result = delta.updated_package(package, plan)
    players = {row['carrier_id']: row for row in result['players']}
    old = {row['carrier_id']: row for row in package['players']}
    aid = PREFIX + plan['transaction_id']
    artifact = next(a for a in result['artifacts'] if a['relative_path'] == delta.plan_filename(plan))
    previous = artifact['id']
    artifact.update(id=aid, relative_path=filename(plan), sha256=digest(packages.canonical_json_bytes(plan)))
    for row in plan['decisions']:
        target = players[row['carrier_id']]
        source = row['preserved_source_carrier']
        if source is not None:
            fixed = {key: target[key] for key in ('id', 'carrier_id', 'carrier_family', 'club_id')}
            target.clear(); target.update(copy.deepcopy(old[source])); target.update(fixed)
            if row.get('display_name'):
                target['name'] = row['display_name']
            target['facts']['shirt_number'] = {'policy': 'preserve-existing-mode1'}
            target['fact_fallbacks'] = [v for v in target.get('fact_fallbacks', []) if v['field'] != 'shirt_number']
            target['fact_fallbacks'].append(dict(field='shirt_number', method='preserve-existing-mode1',
                proof=dict(artifact_id=aid, grade='source-receipt'), value={'policy': 'preserve-existing-mode1'},
                reason='Destination native shirt byte retained; not a sourced number claim.'))
        else:
            if row.get('display_name'):
                target['name'] = row['display_name']
            target['facts']['fine_roles'] = row['fine_roles']
            strength = round(median(p['ratings']['values']['quality'] for p in package['players'] if p['club_id'] == target['club_id']))
            values = ratings.editorial(target, strength, 'opening_squad', date(int(plan['season'][:4]), 8, 1))
            if target['facts']['primary_position'] != 'G':
                values['handling'] = max(1, min(20, values['handling']))
            target['ratings'] = dict(profile='pm99-visible-skills-v1', values=values,
                provenance=dict(method='identity-club-role-age-optional-editorial-calibration-v3',
                    proof_grade='reviewed-editorial', source_ids=[ratings.SOURCE_ID]))
        target['proof'] = dict(artifact_id=aid, grade='source-receipt')
    for collection in ('players', 'sources', 'proofs'):
        for row in result[collection]:
            for key in ('artifact_id', 'evidence_artifact_id'):
                if row.get(key) == previous: row[key] = aid
            for proof in [row.get('proof', {})] + [f.get('proof', {}) for f in row.get('fact_fallbacks', [])]:
                if proof.get('artifact_id') == previous: proof['artifact_id'] = aid
    for row in plan['request'].get('orders', []):
        club = next(c for c in result['clubs'] if c['carrier_id'] == row['club_carrier_id'])
        club['roster_player_ids'] = [players[c]['id'] for c in row['full_order']]
        club['opening']['substitute_player_ids'] = [players[p['carrier_id']]['id'] for p in row['bench_mapping']]
        club['opening']['proof'] = dict(artifact_id=aid, grade='source-receipt')
    if plan.get('complete_mode1_opening') is not None:
        complete = plan['complete_mode1_opening']
        club = next(c for c in result['clubs'] if c['carrier_id'] == complete['club_carrier_id'])
        club['roster_player_ids'] = [players[r['carrier_id']]['id'] for r in complete['orders']]
    selected = {players[c]['id'] for c in selected_carriers(plan)}
    if selected:
        portraits = result['assets']['portraits']
        portraits[:] = [p for p in portraits if p['player_id'] not in selected]
        portraits.extend(dict(player_id=pid, status='native-no-photo', proof=dict(artifact_id=aid, grade='source-receipt'),
            review_reason='Identity moved or replaced; old slot portrait cleared.') for pid in sorted(selected))
        portraits.sort(key=lambda p: p['player_id'])
    keys = [identity(p) for p in result['players'] if p['carrier_id'] in selected_carriers(plan)]
    if len(set(keys)) != len(keys) or any(identity(p) in keys for p in result['players'] if p['carrier_id'] not in selected_carriers(plan)):
        raise ValueError('opening exchange leaves an outside identity copy')
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original_jug), digest(original_eq)) != (plan['jug_sha256'], plan['eq_sha256']):
        raise ValueError('opening exchange immutable baseline changed')
    package = bind(pipeline.read_json_file(base.package_path), plan)
    players = {p['carrier_id']: p for p in package['players']}
    codes = delta.compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    prepared = original_jug
    for row in plan['decisions']:
        if row.get('same_carrier_capacity_claim'):
            from scripts import season_same_carrier_name_capacity_v1 as capacity
            prepared, recovery = capacity.recover_slot(prepared, row['carrier_id'], plan['request']['same_carrier_name_capacity'])
            if recovery != row['same_carrier_capacity_claim']:
                raise ValueError('opening exchange same-carrier name recovery differs')
    selected = selected_carriers(plan)
    if not selected:
        from scripts.season_complete_mode1_opening_v1 import ORDER_ONLY_POLICY
        if plan.get('complete_mode1_opening', {}).get('policy') != ORDER_ONLY_POLICY:
            raise ValueError('empty compilation only allowed for explicit source-bound order-only plan')
        candidate = prepared
    else:
        candidate = delta.compile_players(prepared, package, {players[c]['id'] for c in selected}, codes)
    patched_eq = original_eq
    order_carriers = set()
    if plan.get('complete_mode1_opening') is not None:
        from scripts import season_complete_mode1_opening_v1 as complete
        candidate = complete.apply(candidate, original_eq, plan['complete_mode1_opening'])
        order_carriers.update(r['carrier_id'] for r in plan['complete_mode1_opening']['orders'])
    from scripts import season_opening_order_repair_v1 as ordering
    for row in plan['request'].get('orders', []):
        ix = IndexedFDIFile.from_bytes(candidate)
        entries = {e.record_id: e for e in ix.entries}
        changes = []
        for n, carrier in enumerate(row['full_order'], 1):
            field = read_initial_order(entries[carrier].decode_payload(candidate))
            changes.append(dict(native_player_id=carrier, native_name=field.name, before=field.order, after=n))
        candidate = ordering.apply_layer(original_eq, candidate, dict(schema_version=ordering.SCHEMA,
            clubs=[dict(carrier_id=row['club_carrier_id'], players=changes)]), allow_compact=True)
        ix = IndexedFDIFile.from_bytes(patched_eq)
        entry = next(e for e in ix.entries if e.record_id == row['club_carrier_id'])
        payload = patched_eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
        parsed = delta.compiler.parse_eq_external_team_roster_payload(payload, {})
        if (parsed is None or parsed.mode_byte != 0 or any(r.flag for r in parsed.rows)
                or {r.player_record_id for r in parsed.rows} != set(row['full_order'])):
            raise ValueError('reserve ordering needs an exact fixed-capacity mode0 native roster')
        patched_eq = delta.compiler._rebuild_indexed(patched_eq, ix,
            {row['club_carrier_id']: xor_decode(delta.compiler._rewrite_roster_tail(payload, row['full_order']))})
        order_carriers.update(row['full_order'])
    if eq not in (original_eq, patched_eq) or jug not in (original_jug, candidate):
        raise ValueError('opening exchange accepts only complete exact pre/postimages')
    if (jug == original_jug) != (eq == original_eq) and (original_eq != patched_eq and original_jug != candidate):
        raise ValueError('opening exchange refuses mixed transaction pre/postimages')
    preserve_other_records(original_jug, candidate, selected_carriers(plan) | order_carriers)
    old_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(original_jug).entries}
    new_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(candidate).entries}
    for carrier in order_carriers - selected_carriers(plan):
        before = old_entries[carrier].decode_payload(original_jug)
        after = new_entries[carrier].decode_payload(candidate)
        verify_order_only_record(before, after)
    preserve_other_records(original_eq, patched_eq, {row['club_carrier_id'] for row in plan['request'].get('orders', [])})
    for row in plan['decisions']:
        if row['preserved_source_carrier'] is not None and skills(candidate, row['carrier_id']) != skills(original_jug, row['preserved_source_carrier']):
            raise ValueError('moved person native skills changed')
    return candidate, patched_eq


def reject_factory_recipe(package):
    if any(row['id'].startswith(PREFIX) for row in package.get('artifacts', [])):
        raise ValueError('opening exchange recipe requires exact source reconstruction')


def reconstruction(previous, release_id):
    compiler_path = getattr(previous, 'compiler_receipt_path', None)
    if compiler_path is None:
        return None
    compiler = pipeline.read_json_file(compiler_path)
    if compiler.get('compilation_mode') != MODE:
        return None
    relative = getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path')
    if not relative: return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        raise ValueError('typed opening exchange compiler has a different source schema')
    from scripts import publish_historical_role_delta_v1 as publisher
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited opening exchange recipe cannot be silently reconstructed')
    publisher.publish(previous.season, previous.package_path.parent / 'role-delta-input.json',
        release_id=release_id, source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('opening exchange complete recipe replay differs')
    if not registry.validate_preferred_release(previous.season, level='playable', release_id=release_id)['valid']:
        raise ValueError('opening exchange SOURCE output failed its registered playable gate')
    return dict(season=previous.season, release_id=release_id, complete_game_inventory_identical=True,
                complete_recipe_identical=True, clean_machine_parent_reconstruction=False, compilation_mode=MODE)
