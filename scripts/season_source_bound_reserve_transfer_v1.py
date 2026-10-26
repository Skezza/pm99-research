"""Move a sourced existing reserve without replacing identities or either XI.

Admission requires an original completed transfer chronology and independent
Sky identity/transfer row. Native encoding delegates to existing checked writers.
"""
from pathlib import Path
from datetime import date, datetime
import copy
import hashlib
import re
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from scripts import season_pipeline_v2 as p, season_release_registry_v1 as r
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_source_bound_fixture_membership_v1 as fixture
from scripts import season_published_transfer_history_v1 as history
from scripts import season_batth_wolves_opening_transfer_v1 as native
from scripts.season_roster_membership_payload_core_v1 import reassign_memberships, _read_rosters
from scripts.capture_transfermarkt_opening_lineups_v1 import _club_key

SCHEMA = 'pm99-source-bound-dated-reserve-transfer-v1'
MODE = 'known-good-source-bound-dated-reserve-transfer-v1'
PREFIX = 'source-bound-dated-reserve-transfer-'
_CACHE = {}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def filename(plan):
    return PREFIX + plan['request_sha256'][:16] + '.json'


def artifact_id(plan):
    return PREFIX + plan['request_sha256'][:16]


def _original(row, expected_url):
    if row['url'] != expected_url:
        raise ValueError('original source URL differs')
    path = fixture._source_path(row['path'])
    if r.sha256_file(path) != row['sha256']:
        raise ValueError('original source bytes changed')
    return path


def verify_chronology(request, actor, clubs):
    """Reparse original chronology and independent full identity/transfer row."""
    pid = request['provider_player_id']
    if type(pid) is not int or pid <= 0:
        raise ValueError('positive stable provider identity required')
    anchor = date.fromisoformat(request['opening_date'])
    if anchor.month != 8 or anchor.year != int(request['season'][:4]):
        raise ValueError('target August ownership required')
    raw = _original(request['history'], history.BASE + str(pid))
    document = p.read_json_file(raw)
    events = history.parse(document, pid)
    before = [e for e in events if e['date'] <= anchor.isoformat()]
    after = [e for e in events if e['date'] > anchor.isoformat()]
    if not before or not after:
        raise ValueError('positive entry and exit must bracket the opening date')
    entry, exit = before[-1], after[0]
    source, target = request['from_club_carrier_id'], request['to_club_carrier_id']
    if (entry['from_club_id'] != request['from_provider_club_id']
            or entry['to_club_id'] != request['to_provider_club_id']
            or exit['from_club_id'] != request['to_provider_club_id']):
        raise ValueError('dated source and destination ownership disagree')
    # Every same-day edge must agree; a sorted tie must not select an owner.
    if sum(e['date'] == entry['date'] for e in events) != 1:
        raise ValueError('same-day ownership ambiguity')
    rows = document['data']['history']['terminated']
    names = {row['relativeUrl'].split('/')[1] for row in rows}
    key = lambda s: re.sub('[^a-z0-9]', '', str(s).casefold())
    if {key(x) for x in names} != {key(actor['name'])}:
        raise ValueError('published history identity differs from full recipe name')
    sky = request['identity']
    if not re.fullmatch(r'https://www\.skysports\.com/football/player/[1-9][0-9]*/[a-z0-9-]+', sky['url']):
        raise ValueError('original Sky player profile required')
    page = BeautifulSoup(_original(sky, sky['url']).read_bytes(), 'lxml')
    if not page.title or page.title.get_text().split(' - ')[0] != actor['name']:
        raise ValueError('independent full identity differs')
    dob = datetime.strptime(actor['facts']['birth_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
    if dob not in page.get_text(' ', strip=True):
        raise ValueError('independent birth date differs')
    # One established publisher abbreviation; no fuzzy club matching.
    aliases = {'QPR': 'Queens Park Rangers'}
    matching = []
    for row in page.select('tr'):
        cells = [c.get_text(' ', strip=True) for c in row.select('td')]
        if len(cells) < 3:
            continue
        if (_club_key(aliases.get(cells[0], cells[0])) != _club_key(clubs[source]['name'])
                or _club_key(aliases.get(cells[1], cells[1])) != _club_key(clubs[target]['name'])):
            continue
        try:
            announced = datetime.strptime(cells[2], '%d %b %Y').date()
        except ValueError:
            continue
        if announced <= anchor and abs((date.fromisoformat(entry['date']) - announced).days) <= 7:
            matching.append(cells)
    if len(matching) != 1:
        raise ValueError('independent dated transfer row does not bind both native clubs')
    return {'entry': entry, 'exit': exit, 'independent_transfer_row': matching[0]}


def _layer(package, request):
    out = copy.deepcopy(package)
    players = {a['carrier_id']: a for a in out['players']}
    clubs = {c['carrier_id']: c for c in out['clubs']}
    actor = players[request['carrier_id']]
    source, target = (clubs[request[k]] for k in ('from_club_carrier_id', 'to_club_carrier_id'))
    if (actor['name'] != request['name'] or actor['facts']['birth_date'] != request['birth_date']
            or actor['club_id'] != source['id'] or source['roster_player_ids'].count(actor['id']) != 1
            or actor['id'] in target['roster_player_ids']
            or actor['id'] in source['opening']['starting_xi_player_ids']):
        raise ValueError('reserve identity or owner preimage differs; starters cannot move')
    source['roster_player_ids'].remove(actor['id'])
    target['roster_player_ids'].append(actor['id'])
    actor['club_id'] = target['id']
    source['opening']['substitute_player_ids'] = [x for x in source['opening']['substitute_player_ids'] if x != actor['id']]
    if not 16 <= len(source['roster_player_ids']) <= 25 or not 16 <= len(target['roster_player_ids']) <= 25:
        raise ValueError('reserve transfer violates capacity-fitting roster limits')
    if fixture._package_validation_state(out) != fixture._package_validation_state(package):
        raise ValueError('transfer changed strict recipe validation state')
    return out


def _reconstruct(base, request):
    parent = dict(season=base.season, release_id=base.release_id,
                  manifest_sha256=base.manifest_sha256, **native._parent_files(base))
    if request['parent'] != parent or request['season'] != base.season:
        raise ValueError('immutable parent binding differs')
    main = p.read_json_file(base.package_path)
    clubs = {c['carrier_id']: c for c in main['clubs']}
    actor = next(a for a in main['players'] if a['carrier_id'] == request['carrier_id'])
    source_proof = verify_chronology(request, actor, clubs)
    overlay = fixture._layer_path(main, base.package_path, 'english-season-package.json')
    english = p.read_json_file(overlay)
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    facts = native._native_facts(jug, request['carrier_id'])
    if (fixture._identity_key(facts['name']) != fixture._identity_key(request['name'])
            or facts['birth_date'] != request['birth_date']):
        raise ValueError('native name/birthday differ from independent source identity')
    key = digest(packages.canonical_json_bytes(request))
    cache_key = (key, digest(eq), digest(jug), r.sha256_file(overlay), r.sha256_file(Path(__file__)))
    if cache_key in _CACHE:
        return copy.deepcopy(_CACHE[cache_key])
    rows = _read_rosters(eq)[2]
    selected = {request['from_club_carrier_id'], request['to_club_carrier_id']}
    fixture._verify_selected_package_owners(main, selected, {c: [x.player_record_id for x in rows[c].rows] for c in selected})
    fixture._verify_selected_package_owners(english, selected, {c: [x.player_record_id for x in rows[c].rows] for c in selected})
    after, english_after = _layer(main, request), _layer(english, request)
    neweq, receipt = reassign_memberships(eq, [dict(player_record_id=request['carrier_id'],
        from_club_carrier_id=request['from_club_carrier_id'], to_club_carrier_id=request['to_club_carrier_id'])])
    for a in after['artifacts']:
        if str(a.get('relative_path', '')).endswith('english-season-package.json'):
            a['sha256'] = digest(packages.canonical_json_bytes(english_after))
    desired = compiler._club_player_orders(after)
    ix = IndexedFDIFile.from_bytes(jug)
    entries = {e.record_id: e for e in ix.entries}
    actors = {a['id']: a for a in after['players']}
    changes = []
    for c in selected:
        for player in next(z for z in after['clubs'] if z['carrier_id'] == c)['roster_player_ids']:
            carrier = actors[player]['carrier_id']
            field = read_initial_order(entries[carrier].decode_payload(jug))
            if field.order != desired[player]:
                changes.append(OrderReplacement(record_id=carrier, expected_name=field.name, before=field.order, after=desired[player]))
    newjug = patch_initial_orders(jug, changes, allow_compact=True)
    newer = {e.record_id: e for e in IndexedFDIFile.from_bytes(newjug).entries}
    for cid in entries:
        old, new = entries[cid].decode_payload(jug), newer[cid].decode_payload(newjug)
        if old != new:
            from scripts.season_opening_identity_exchange_v1 import verify_order_only_record
            verify_order_only_record(old, new)
    # Full source/target XI and tactic payloads are preserved, not re-inferred.
    for cid in selected:
        old_entry = next(e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == cid)
        new_entry = next(e for e in IndexedFDIFile.from_bytes(neweq).entries if e.record_id == cid)
        oldraw = eq[old_entry.payload_offset:old_entry.payload_offset + old_entry.payload_length]
        newraw = neweq[new_entry.payload_offset:new_entry.payload_offset + new_entry.payload_length]
        if fixture.order_repair.tactics.native_xi(oldraw, jug) != fixture.order_repair.tactics.native_xi(newraw, newjug):
            raise ValueError('reserve move changed a native starting XI')
    result = dict(main=after, english=english_after, jug=newjug, eq=neweq,
                  chronology=source_proof, roster_receipt=receipt,
                  changed_order_carriers=[z.record_id for z in changes])
    _CACHE.clear()
    _CACHE[cache_key] = copy.deepcopy(result)
    return result


def prepare(base, input_path):
    path = fixture._source_path(r.relative_workspace_path(Path(input_path).resolve()))
    request = p.read_json_file(path)
    if request.get('schema') != SCHEMA + '-input':
        raise ValueError('typed dated reserve input required')
    _reconstruct(base, request)
    return dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        source_input={'path': r.relative_workspace_path(path), 'sha256': r.sha256_file(path)},
        request_sha256=digest(packages.canonical_json_bytes(request)),
        package_sha256=r.sha256_file(base.package_path), jug_sha256=r.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        scope='One source-proven existing mode0 reserve owner and required startup orders; main/English rosters aligned; both XIs, facts, ratings, tactics, managers and assets preserved.')


def _outputs(plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('unsupported reserve transfer plan')
    path = fixture._source_path(plan['source_input']['path'])
    if r.sha256_file(path) != plan['source_input']['sha256']:
        raise ValueError('original reserve request changed')
    base = r.load_registered_release(plan['season'], plan['release_id'])
    if prepare(base, path) != plan:
        raise ValueError('reserve transfer plan does not reproduce')
    return _reconstruct(base, p.read_json_file(path))


def verify(base, plan):
    if base.season != plan['season'] or base.release_id != plan['release_id']:
        raise ValueError('reserve plan belongs to another parent')
    _outputs(plan)


def bind(package, plan):
    if digest(packages.canonical_json_bytes(package)) != plan['package_sha256']:
        raise ValueError('recipe preimage differs')
    result = copy.deepcopy(_outputs(plan)['main'])
    result['artifacts'].append(dict(id=artifact_id(plan), kind='season-input',
        relative_path=filename(plan), sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def updated_english(plan):
    return copy.deepcopy(_outputs(plan)['english'])


def apply(jug, eq, plan):
    base = r.load_registered_release(plan['season'], plan['release_id'])
    result = _outputs(plan)
    before = ((base.game_path / 'DBDAT/JUG98030.FDI').read_bytes(), (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    after = result['jug'], result['eq']
    if (jug, eq) not in (before, after):
        raise ValueError('reserve writer requires complete preimage or complete postimage')
    return after


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('dated reserve transfer requires source-bound reconstruction')


def reconstruction(previous, release_id, *, minimum_free_bytes=8*1024**3):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = r.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = p.read_json_file(path)
    base = r.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('reserve SOURCE plan must be child-owned')
    receipt = p.read_json_file(previous.compiler_receipt_path)
    if r.sha256_file(path) != receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('reserve SOURCE plan hash differs')
    publisher.publish(base.season, previous.package_path.parent / 'role-delta-input.json',
        release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path, minimum_free_bytes=minimum_free_bytes)
    rebuilt = r.load_registered_release(base.season, release_id)
    p.assert_tree_matches_inventory(rebuilt.game_path, p.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('reserve SOURCE recipe differs')
    return dict(complete_recipe_identical=True, complete_game_inventory_identical=True)
