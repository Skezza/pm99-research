"""Original TFF first-round sheet plus exact shirt/DOB annual-row identity.

Only a fully exclusive compact native club is supported. Past Players rows
are eligible ONLY with a positive original first-match appearance and a TFF
person-ID/profile/DOB binding; an end-season roster is not an August roster.
No nickname expansion or same-name deduplication is performed.
"""
import copy
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders, read_initial_order
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as annual, season_package_compiler_v2 as compiler
from scripts import season_football_data_opening_dates_v1 as dates
from scripts import capture_footballsquads_season as raw_annual
from scripts import season_within_club_reserve_repair_v1 as roster
from scripts.season_art_transaction_v1 import atomic_bytes

SCHEMA = 'pm99-original-TFF-first-round-complete-exclusive-mode1-XI-v1'
PREFIX = 'sourced-tff-opening-xi-'
FILENAME = 'sourced-tff-opening-xi.json'
BROAD_ROLE_POLICY = 'original-TFF-first-XI-broad-position-conservative-compatible-role-v1'
MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
          'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def capture(url, cache):
    parsed = urlparse(url)
    args = parse_qs(parsed.query)
    if (parsed.scheme != 'https' or parsed.netloc != 'www.tff.org'
            or parsed.path.lower() != '/default.aspx' or parsed.fragment
            or len(args) != 2 or not all(len(v) == 1 and v[0].isdigit() for v in args.values())
            or {k.lower() for k in args} not in ({'pageid', 'kisiid'}, {'pageid', 'macid'}, {'pageid', 'ftxtid'})):
        raise ValueError('only exact original TFF match/person/news URLs supported')
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path, receipt = cache / (key + '.html'), cache / (key + '.source.json')
    if path.exists():
        if json.loads(receipt.read_text()) != {'url': url, 'sha256': registry.sha256_file(path)}:
            raise ValueError('original TFF receipt changed')
    else:
        if receipt.exists():
            raise ValueError('TFF original missing beneath receipt')
        with urlopen(Request(url, headers={'User-Agent': 'PM99 historical football research'}), timeout=30) as response:
            if response.geturl() != url:
                raise ValueError('TFF source redirected')
            raw = response.read(2 * 1024 * 1024 + 1)
        if not 1000 <= len(raw) <= 2 * 1024 * 1024:
            raise ValueError('TFF source truncated or oversized')
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, {'url': url, 'sha256': registry.sha256_file(path)})
        time.sleep(1)
    return {'url': url, 'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)}


def original(binding):
    path = registry.ROOT / binding['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('TFF opening original source bytes changed')
    return path.read_bytes()


def require_tff_binding(binding, page, key, identity):
    parsed = urlparse(binding.get('url', ''))
    args = parse_qs(parsed.query)
    normal = {k.lower(): v for k, v in args.items()}
    if (parsed.scheme != 'https' or parsed.netloc != 'www.tff.org'
            or parsed.path.lower() != '/default.aspx' or parsed.fragment
            or len(args) != 2 or normal != {'pageid': [str(page)], key: [str(identity)]}):
        raise ValueError('original TFF binding has a different page/person/match identity')


def one(page, suffix):
    rows = page.select('[id$="' + suffix + '"]')
    if len(rows) != 1:
        raise ValueError('missing or ambiguous original TFF field: ' + suffix)
    return rows[0].get_text(' ', strip=True)


def sheet(raw, day, home, away):
    page = BeautifulSoup(raw.decode('cp1254'), 'lxml')
    if one(page, '_lblTarih').split(' - ')[0] != datetime.fromisoformat(day).strftime('%d.%m.%Y').lstrip('0'):
        raise ValueError('TFF fixture date differs')
    if 'Turkcell Süper Lig' not in one(page, '_lblOrganizasyonAdi'):
        raise ValueError('TFF fixture is not the target league')
    # Link labels are provider-native, never approximated club aliases.
    titles = page.select('head > title')
    if len(titles) != 1 or not titles[0].get_text(' ', strip=True).startswith(home + ' ' + away + ' -'):
        raise ValueError('TFF fixture club pair differs')
    result = []
    for link in page.select('a[id*="grdTakim1_rptKadrolar_"][id$="_lnkOyuncu"]'):
        q = parse_qs(urlparse(link['href']).query)
        if set(q) != {'pageId', 'kisiId'} or q['pageId'] != ['30'] or len(q['kisiId']) != 1 or not q['kisiId'][0].isdigit():
            raise ValueError('TFF starter has no exact person identity')
        number = one(page, link['id'].replace('_lnkOyuncu', '_formaNo'))
        result.append({'tff_id': int(q['kisiId'][0]), 'registered_name': link.get_text(' ', strip=True),
                       'shirt_number': int(number.rstrip('.'))})
    if len(result) != 11 or len({p['tff_id'] for p in result}) != 11 or len({p['shirt_number'] for p in result}) != 11:
        raise ValueError('TFF sheet must publish eleven distinct starters/IDs/shirts')
    return result


def profile(raw, registered_name):
    page = BeautifulSoup(raw.decode('cp1254'), 'lxml')
    prefix = '_OyuncuDisplay1_oyuncuBilgileri_'
    if one(page, prefix + 'lblAdi') != registered_name:
        raise ValueError('TFF profile belongs to another registered person')
    if one(page, prefix + 'Label10') != 'Doğum Tarihi':
        raise ValueError('TFF birthday label differs')
    day, month, year = one(page, prefix + 'Label2').split()
    birth = datetime(int(year), MONTHS.index(month) + 1, int(day)).date().isoformat()
    return {'registered_name': registered_name, 'birth_date': birth,
            'nationality': {'TC':'TUR'}.get(one(page, prefix + 'Label3'), one(page, prefix + 'Label3'))}


def biography_alias(raw, source, registered_name):
    page = BeautifulSoup(raw, 'lxml')
    boxes = page.select('table.infobox')
    if len(boxes) != 1:
        raise ValueError('nickname bridge needs one original biography infobox')
    box = boxes[0]
    full = []
    for row in box.select('tr'):
        cells = row.find_all(['th','td'], recursive=False)
        if len(cells) == 2 and cells[0].get_text(' ',strip=True) == 'Full name':
            full.append(cells[1].get_text(' ',strip=True))
    birthdays = box.select('.bday')
    if (len(full) != 1 or annual.normalise(full[0]) != annual.normalise(registered_name)
            or len(birthdays) != 1 or birthdays[0].get_text(strip=True) != source['birth_date']
            or not page.select('h1') or not page.select('h1')[0].get_text(' ',strip=True).startswith(source['name'] + ' (')):
        raise ValueError('nickname bridge lacks literal sporting/full names and annual DOB')
    return {'full_name':full[0],'sporting_name':source['name'],'birth_date':source['birth_date']}


def annual_rows(raw, season, club):
    lines = raw.decode('utf-8-sig').splitlines()
    if lines[0] != '=  ' + club + ' - Turkish Süper Lig ' + season[:4] + '/' + season[-2:]:
        raise ValueError('original annual club/season header differs')
    sections, section, past = [], [], False
    for line in lines[1:]:
        if line.startswith('=='):
            if section: sections.append((past, section)); section = []
            if line != '== Past Players':
                raise ValueError('unknown annual roster section')
            past = True
        elif line.strip():
            section.append(line)
    if section: sections.append((past, section))
    rows = []
    for past, section in sections:
        for row in csv.DictReader(section, skipinitialspace=True):
            born = raw_annual._birth_date(row['Date of Birth'], season_start=int(season[:4]), label=row['Name'])
            datetime.fromisoformat(born)
            rows.append({'name': row['Name'], 'birth_date': born, 'position': row['Pos'],
                         'nationality': row['Nat'], 'shirt_number': int(row['Number']),
                         'height_cm': raw_annual._height_cm(row['Height'], label=row['Name']) if row['Height'] else None,
                         'weight_kg': raw_annual._weight_kg(row['Weight'], label=row['Name']) if row['Weight'] else None,
                         'past_player': past})
    return rows


def prepare(release, bindings, *, club_carrier_id=1006, mistaken_carrier=14506, retained_carrier=14497):
    package = json.loads(release.package_path.read_text())
    club = next(c for c in package['clubs'] if c['carrier_id'] == club_carrier_id)
    if club['name'] != 'Gaziantepspor' or release.season != '2009-10':
        raise ValueError('initial TFF repair policy is pinned to the verified 2009 Gaziantepspor pilot')
    if mistaken_carrier == retained_carrier:
        raise ValueError('two distinct original people require two distinct carriers')
    require_tff_binding(bindings['match'], 397, 'macid', 79502)
    require_tff_binding(bindings['first_round_news'], 201, 'ftxtid', 7635)
    receipt = json.loads(original(bindings['results_receipt']))
    for key in ('requested_url', 'response_url'):
        dates.validate_url(receipt[key], release.season, 'T1')
    results = original(bindings['results'])
    if hashlib.sha256(results).hexdigest() != receipt['sha256']:
        raise ValueError('results receipt differs')
    first = dates.first_fixture(results, release.season, 'T1', club['name'])
    if first['fixture'] != {'date': '2009-08-09', 'home': club['name'], 'away': 'Galatasaray', 'competition_code': 'T1'}:
        raise ValueError('Gaziantepspor first played fixture differs')
    news = BeautifulSoup(original(bindings['first_round_news']).decode('cp1254'), 'lxml').get_text(' ', strip=True)
    if not all(s in news for s in ('Turkcell Süper Lig 1. hafta karşılaşmasında', 'Gaziantepspor', 'Galatasaray', '9.08.2009')):
        raise ValueError('incomplete results require independent original federation first-round proof')
    xi = sheet(original(bindings['match']), '2009-08-09', 'GAZİANTEPSPOR', 'GALATASARAY A.Ş.')
    sources = annual_rows(original(bindings['annual']), release.season, club['name'])
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    by_id = {p['carrier_id']: p for p in package['players'] if p['id'] in club['roster_player_ids']}
    members = {p['carrier_id']: roster.native_facts(jug, p['carrier_id']) for p in by_id.values()}
    before, kept = members[mistaken_carrier], members[retained_carrier]
    if (annual.normalise(before['name']), before['birth_date'], before['position']) != (annual.normalise(kept['name']), kept['birth_date'], kept['position']):
        raise ValueError('mistaken slot is not an exact native duplicate of the retained forward')
    bound, replacements, conflicts = [], [], []
    for person in xi:
        require_tff_binding(bindings['profiles'][str(person['tff_id'])], 30, 'kisiid', person['tff_id'])
        fact = profile(original(bindings['profiles'][str(person['tff_id'])]), person['registered_name'])
        matches = [p for p in sources if (p['shirt_number'], p['nationality']) ==
                   (person['shirt_number'], fact['nationality'])]
        if len(matches) != 1:
            raise ValueError('original annual row needs one exact dated-club/shirt/nationality match')
        source = matches[0]
        bridge = None
        if source['birth_date'] != fact['birth_date']:
            if annual.normalise(source['name']) != annual.normalise(fact['registered_name']):
                bridge = biography_alias(original(bindings['biographies'][str(person['tff_id'])]), source, fact['registered_name'])
            conflicts.append({'tff_id':person['tff_id'],'name':source['name'],
                'annual_birth_date':source['birth_date'],'TFF_registered_birth_date':fact['birth_date'],
                'disposition':'existing annual/native birthday retained; conflict logged, not guessed',
                'independent_full_name_bridge':bridge})
        # Two original views tie the same dated club/shirt/birthday to the
        # official full registration and the published sporting name. Both
        # names remain recorded; no initial or guessed nickname expansion.
        candidates = [p for p in by_id.values() if annual.normalise(re.sub(r'^#\d{1,3}\s+', '', p.get('source_name') or p['name'])) == annual.normalise(source['name'])
                      and p['facts'].get('birth_date') == source['birth_date']]
        if person['tff_id'] == 1224041:
            if source['position'] != 'D' or source['birth_date'] != '1978-11-17' or candidates:
                raise ValueError('mistaken defender requires the original matching annual/registered identity')
            carrier = mistaken_carrier
            replacements.append({'carrier_id': carrier, 'kind': 'wrong-person-facts', 'source': source, 'tff_person': fact, 'tff_id': person['tff_id']})
        else:
            if person['tff_id'] == 1252986:
                candidates = [p for p in candidates if p['carrier_id'] == retained_carrier]
            if len(candidates) != 1:
                raise ValueError('starter recipe identity is absent or ambiguous')
            carrier = candidates[0]['carrier_id']
            if (members[carrier]['birth_date'], members[carrier]['position']) != (source['birth_date'], source['position']):
                raise ValueError('starter native DOB/position differs from the annual row')
            if (candidates[0].get('source_name') or '').startswith('#'):
                replacements.append({'carrier_id': carrier, 'kind': 'shirt-prefix-display-name', 'source': source, 'tff_person': fact, 'tff_id': person['tff_id']})
        bound.append({**person, 'carrier_id': carrier, 'source': source, 'tff_person': fact})
    if len({p['carrier_id'] for p in bound}) != 11:
        raise ValueError('first XI maps multiple real people into one carrier')
    keeper = [p for p in bound if p['source']['position'] == 'G']
    if len(keeper) != 1:
        raise ValueError('sourced first XI must have exactly one keeper')
    ranked = sorted(bound, key=lambda p: ('GDMF'.index(p['source']['position']), members[p['carrier_id']]['startup_order'], p['carrier_id']))
    reserves = sorted(set(members) - {p['carrier_id'] for p in ranked}, key=lambda id: (members[id]['startup_order'], id))
    orders = [{'carrier_id': id, 'player_id': by_id[id]['id'], 'before': members[id]['startup_order'], 'after': i + 1}
              for i, id in enumerate([p['carrier_id'] for p in ranked] + reserves)]
    plan = {'schema_version': SCHEMA, 'season': release.season, 'source_release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path), 'jug_sha256': registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
            'eq_sha256': registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'), 'bindings': bindings,
            'club_id': club['id'], 'club_carrier_id': club['carrier_id'], 'first_fixture': first,
            'starting_xi': ranked, 'orders': orders, 'replacements': replacements,
            'secondary_fact_source_conflicts': conflicts,
            'birth_date_policy': 'TFF registered date 17 November 1978 agrees with original annual row; other biographies reporting 18 November remain an explicit source conflict',
            'scope': 'complete first-XI membership and keeper/order controls; reserve membership, tactical formation and all other clubs not historically cleared'}
    return plan


def updated_package(package, plan):
    result = copy.deepcopy(package)
    identity = PREFIX + plan['season']
    proof = {'artifact_id': identity, 'grade': 'source-receipt'}
    people = {p['carrier_id']: p for p in result['players']}
    for row in plan['replacements']:
        player, source = people[row['carrier_id']], row['source']
        if row['kind'] == 'shirt-prefix-display-name':
            player['name'], player['source_name'] = 'R. Tabata', source['name']
        else:
            player['source_name'] = row['tff_person']['registered_name']
            player['person_id'] = 'person-tff-' + str(row['tff_id'])
            player['facts'].update(birth_date=source['birth_date'], primary_position=source['position'],
                                   nationality=source['nationality'], height_cm=source['height_cm'],
                                   weight_kg=source['weight_kg'], fine_roles=[4])
            from scripts import season_editorial_ratings_v1 as ratings
            rating = ratings.build_rating_output({'schema_version': ratings.INPUT_SCHEMA, 'snapshot_date': '2009-08-09',
                'hierarchy': {'schema_version': ratings.HIERARCHY_SCHEMA, 'snapshot_date': '2009-08-09',
                    'clubs': [{'club_id': player['club_id'], 'strength': 65, 'source_ids': ['tff-opening-source-' + plan['season']]}]},
                'players': [{'player_id': player['id'], 'person_id': player['person_id'], 'club_id': player['club_id'],
                    'position': 'D', 'birth_date': source['birth_date'], 'height_cm': source['height_cm'], 'squad_status': 'starting_xi'}]})
            player['ratings'] = rating['player_ratings'][0]['ratings']
            player['ratings']['provenance'] = {k: player['ratings']['provenance'][k] for k in ('method','proof_grade','source_ids')}
            player['fact_fallbacks'] = [p for p in player.get('fact_fallbacks', []) if p['field'] == 'shirt_number']
            portraits = result['assets']['portraits']
            portraits[:] = [p for p in portraits if p['player_id'] != player['id']]
            portraits.append({'player_id': player['id'], 'status': 'native-no-photo', 'proof': proof,
                             'review_reason': 'Wrong-person face removed; defender photograph not sourced.'})
            portraits.sort(key=lambda p: p['player_id'])
        player['proof'] = proof
    result['artifacts'].append({'id': identity, 'kind': 'season-input', 'relative_path': FILENAME,
        'sha256': hashlib.sha256(pipeline.canonical_json_bytes(plan)+b'\n').hexdigest(), 'media_type': 'application/json'})
    result['artifacts'].sort(key=lambda x: x['id'])
    result['sources'].append({'id': 'tff-opening-source-' + plan['season'], 'title': 'Original TFF first-round sheet and registered player facts',
        'uri': plan['bindings']['match']['url'], 'proof_grade': 'source-receipt', 'evidence_artifact_id': identity})
    result['sources'].sort(key=lambda x: x['id'])
    club = next(c for c in result['clubs'] if c['id'] == plan['club_id'])
    # The existing mode1 schema intentionally has no inferred formation.
    # Its proof now binds the explicit XI/order artifact; do not add unchecked
    # extra opening properties or relabel factory tactics as sourced tactics.
    club['opening']['proof'] = proof
    from scripts.season_package_v2 import validate_package
    validate_package(result)
    return result


def apply(jug, eq, package, country_codes, plan):
    if plan.get('schema_version') != SCHEMA:
        raise ValueError('unsupported original TFF full-XI plan')
    selected = {r['carrier_id'] for r in plan['replacements']}
    subset = {'players': [copy.deepcopy(p) for p in package['players'] if p['carrier_id'] in selected],
              'clubs': copy.deepcopy(package['clubs'])}
    for club in subset['clubs']:
        club['roster_player_ids'] = [p['id'] for p in subset['players'] if p['club_id'] == club['id']]
        # A private two-record core view, never a publishable season recipe.
        # No English startup/tactics selection is recomputed from this view.
        club['opening'] = {'policy':'preserve-existing-mode1'}
    replacements, handling, *_ = compiler._player_replacements(package=subset, jug_data=jug,
        country_codes=country_codes, club_modes={c['id']:1 for c in package['clubs']})
    candidate = compiler._rebuild_indexed(jug, IndexedFDIFile.from_bytes(jug), replacements)
    entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    tails = {}
    for row in handling:
        payload = bytearray(entries[row['record_id']].decode_payload(candidate))
        payload[-7] = row['visible_skills']['handling'] ^ 0x61
        tails[row['record_id']] = bytes(payload)
    if tails: candidate = compiler._rebuild_indexed(candidate, IndexedFDIFile.from_bytes(candidate), tails)
    entries = {e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    orders = [OrderReplacement(r['carrier_id'], read_initial_order(entries[r['carrier_id']].decode_payload(candidate)).name,
                               r['before'], r['after']) for r in plan['orders']]
    candidate = patch_owned_mode1_complete_orders(candidate, eq, club_record_id=plan['club_carrier_id'], replacements=orders)
    return candidate


def verify(release, plan):
    if prepare(release, plan['bindings']) != plan:
        raise ValueError('original full-XI plan does not reproduce from its bound baseline')


def conservative_role(position,role):
    if position=='G' and role!=0:return 0
    if position=='D' and role in (0,8,12,15,16):return 4
    if position=='M' and role in (0,1,2,3,4,5,8,12,15,16):return 9
    if position=='F' and role in (0,1,2,3,4,5,9,14):return 8
    return None


def prepare_broad_roles(release):
    opening_path = registry.ROOT/release.locator['sourced_mode1_opening_plan_path']
    opening = json.loads(opening_path.read_text())
    verify(registry.load_registered_release(release.season,opening['source_release_id']),opening)
    package=json.loads(release.package_path.read_text())
    people={p['carrier_id']:p for p in package['players']}
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    countries=compiler._extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    if apply(jug,eq,package,countries,opening)!=jug:
        raise ValueError('source XI is not installed before broad-role correction')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates=[]
    # Keep compatible roles; central fallbacks are editorial, not exact-role sources.
    for row in opening['starting_xi']:
        carrier=row['carrier_id'];p=people[carrier]
        native=annual.native_player(entries[carrier].decode_payload(jug),carrier)
        position=row['source']['position'];role=native['roles'][0]
        if native['position']!=position or p['facts']['primary_position']!=position:
            raise ValueError('first-XI broad position differs from its original annual row')
        target=conservative_role(position,role)
        if target is None:continue
        updates.append({'player_id':p['id'],'carrier_id':carrier,'name':p['name'],
            'birth_date':p['facts']['birth_date'],'fine_roles':[target],
            'native_before_roles':native['roles'],'original_tff_person_id':row['tff_id'],
            'sourced_broad_position':position,
            'disposition':'contradictory inherited label replaced by conservative central editorial role; not a sourced precise tactical role'})
    return {'policy':BROAD_ROLE_POLICY,'season':release.season,'release_id':release.release_id,
        'package_sha256':registry.sha256_file(release.package_path),
        'jug_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        'opening_plan_path':registry.relative_workspace_path(opening_path),
        'opening_plan_sha256':registry.sha256_file(opening_path),'updates':updates,'unresolved':[]}


def verify_broad_roles(release,plan):
    if prepare_broad_roles(release)!=plan:
        raise ValueError('source-bound broad-role plan does not reproduce')


def replay(jug, eq, package, package_path, countries):
    changes = []
    for artifact in package['artifacts']:
        if not artifact['id'].startswith(PREFIX): continue
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('unsafe full-XI artifact')
        path = package_path.parent / relative
        if registry.sha256_file(path) != artifact['sha256']: raise ValueError('full-XI source plan hash changed')
        plan = json.loads(path.read_text())
        if plan['season'] != f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}":
            raise ValueError('full-XI source plan belongs to another season')
        verify(registry.load_registered_release(plan['season'], plan['source_release_id']), plan)
        # Check durable current facts/proof, not a copied order plan alone.
        original_package = json.loads(registry.load_registered_release(plan['season'], plan['source_release_id']).package_path.read_text())
        wanted = updated_package(original_package, plan)
        ids = {r['carrier_id'] for r in plan['replacements']}
        def identity_without_roles(p):
            result=copy.deepcopy(p);result['facts'].pop('fine_roles',None);return result
        if ([identity_without_roles(p) for p in package['players'] if p['carrier_id'] in ids]
                != [identity_without_roles(p) for p in wanted['players'] if p['carrier_id'] in ids]):
            raise ValueError('full-XI recipe facts changed without a new source plan')
        current_club = next(c for c in package['clubs'] if c['id'] == plan['club_id'])
        wanted_club = next(c for c in wanted['clubs'] if c['id'] == plan['club_id'])
        if current_club != wanted_club:
            raise ValueError('full-XI club roster/opening proof changed without a new source plan')
        jug = apply(jug, eq, package, countries, plan)
        changes.append({'club_carrier_id':plan['club_carrier_id'],'starting_xi':plan['starting_xi']})
    return jug, changes
