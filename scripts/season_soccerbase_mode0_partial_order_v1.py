"""Source-bound partial Plymouth opening selection adapter.

The adapter admits one Soccerbase-documented substitute replacement and
delegates all startup-order bytes to the established mode-0 order repair
writer. It intentionally does not claim a complete matchday bench.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as order_writer
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as soccerbase
from scripts import season_within_club_reserve_repair_v1 as native
from scripts.season_historical_roster_audit_v1 import normalise

ROOT = registry.ROOT
KIND = 'typed-soccerbase-mode0-partial-substitute-order-only-v1'
SEASON = '2000-01'
CLUB_ID = 'english-club-385'
CLUB_CARRIER = 385
REMOVE_ID = 'english-player-33121'
ADD_ID = 'english-player-33129'
ADAMS_PROVIDER_ID = 15645
EVERS_PROVIDER_ID = 8915
FIXTURE = {
    'date': '2000-08-12', 'game_id': 286672, 'team_id': 2036,
    'team_name': 'Plymouth', 'opponent_id': 1537,
    'opponent_name': 'Leyton Orient', 'competition': 'Football League Div 3',
    'score': [0, 1],
    'expected_starting_xi_source_ids': [
        'soccerbase:7225', 'soccerbase:5952', 'soccerbase:9840',
        'soccerbase:9634', 'soccerbase:6203', 'soccerbase:407',
        'soccerbase:2552', 'soccerbase:8701', 'soccerbase:3137',
        'soccerbase:4998', 'soccerbase:16895'],
    'expected_published_bench_source_ids': [
        'soccerbase:14901', 'soccerbase:15645', 'soccerbase:6333',
        'soccerbase:9841', 'soccerbase:15079']}
SOURCE_BINDINGS = {
    'soccerbase_schedule': {
        'path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/plymouth-results-2036.html',
        'sha256': '2f56a48ab2565f47a16a6512403639e70eb90a5fe8b6ff9193756850833e71df',
        'receipt_path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/plymouth-results-2036.html.source.json',
        'receipt_sha256': 'd99cfa35ae4a3161c5143ebf7c7e70f031d0f846693d592b730777dcc643805b',
        'url': 'https://www.soccerbase.com/teams/team.sd?season_id=130&team_id=2036&teamTabs=results'},
    'soccerbase_match_sheet': {
        'path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/match-286672.html',
        'sha256': '878680ababeb4d785fff4be732bb702da6c853f84e89d2e6c797296a4dbd7078',
        'receipt_path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/match-286672.html.source.json',
        'receipt_sha256': 'bbb0e98a1a021642667200938da15d00ea5f979f31467a118a272718106616a9',
        'url': 'https://www.soccerbase.com/matches/additional_information.sd?id_game=286672'},
    'adams_profile': {
        'path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/adams-15645.html',
        'sha256': '832c673e9a892c8cc16a362810e1f6c5fb97bd71eb62f3d766b84a4f942723b0',
        'receipt_path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/adams-15645.html.source.json',
        'receipt_sha256': '129ad4505df849a6a7589f322269910770f1485af6a227ba125b8392612f0e4f',
        'url': 'https://www.soccerbase.com/players/player.sd?player_id=15645'},
    'evers_profile': {
        'path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/evers-8915.html',
        'sha256': '66cb94ead4c9ff5a088a05d9161e74ec3643bbd3e34793dafcc1855bec0b14f1',
        'receipt_path': '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-adams-source-v1/evers-8915.html.source.json',
        'receipt_sha256': 'bda2b09f56793637ec7d1ef1d8fcdc868a62e2129bbffa8ffeeb8c5b725adcbd',
        'url': 'https://www.soccerbase.com/players/player.sd?player_id=8915'}}
BEFORE = ['english-player-33118', 'english-player-33119', 'english-player-33120',
          REMOVE_ID, 'english-player-33122', 'english-player-33124', 'english-player-33125']
AFTER = ['english-player-33118', 'english-player-33119', 'english-player-33120',
         ADD_ID, 'english-player-33122', 'english-player-33124', 'english-player-33125']
EXCLUDED = ['player identity or name edits', 'birth date edits', 'primary-position edits',
            'skills edits', 'ownership or EQ edits', 'tactics', 'manager', 'kit',
            'assets', 'claim that the seven-person recipe bench is complete']
SOURCE_ORDER_POLICY = ('Original dated Soccerbase first league fixture schedule and exact match sheet; '
                       'bind all eleven starters and all five published substitutes by numeric IDs.')
RESERVE_POLICY = 'preserve-relative-native-order-of-nonselected-actors; not-published-bench-order'
SCOPE = ('Plymouth opening substitute selection: replace Sean Evers with existing Plymouth '
         'roster actor Steve Adams; derive startup order with existing writer. Preserve all facts, '
         'skills, ownership, EQ, XI, tactics, managers, kits, assets and other selections.')
_EMPTY = {'moves': [], 'new_people': [], 'orders': [], 'retirements': []}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(binding):
    path = ROOT / binding['path']
    receipt_path = ROOT / binding['receipt_path']
    if _sha(path) != binding['sha256'] or _sha(receipt_path) != binding['receipt_sha256']:
        raise ValueError('bound SoccerBase original or receipt hash changed')
    receipt = pipeline.read_json_file(receipt_path)
    if receipt != {'url': binding['url'], 'sha256': binding['sha256']}:
        raise ValueError('SoccerBase receipt URL/body binding differs')
    return path.read_bytes()


def _validate_request(base, request):
    expected_keys = {
        'schema', 'proposal_kind', 'season', 'release_id',
        'expected_package_sha256', 'expected_jug_sha256', 'expected_eq_sha256',
        'club', 'fixture', 'source_bindings', 'actors',
        'opening_substitutes_before', 'opening_substitutes_after', 'policies'}
    if set(request) != expected_keys or request.get('schema') != exchange.INPUT_SCHEMA:
        raise ValueError('typed Plymouth request has unknown/missing fields or wrong exchange schema')
    if request.get('proposal_kind') != KIND or request.get('season') != SEASON:
        raise ValueError('typed Plymouth request kind/season differs')
    if request.get('release_id') != base.release_id or request.get('season') != base.season:
        raise ValueError('typed Plymouth request exact parent differs')
    if request.get('club') != {'carrier_id': CLUB_CARRIER, 'recipe_club_id': CLUB_ID,
                               'name': 'Plymouth Argyle', 'roster_size': 25}:
        raise ValueError('typed Plymouth club binding differs')
    if request.get('fixture') != FIXTURE or request.get('opening_substitutes_before') != BEFORE \
            or request.get('opening_substitutes_after') != AFTER:
        raise ValueError('typed Plymouth fixture or selection contract differs')
    actors = request.get('actors')
    if actors != {
        'remove': {'player_id': REMOVE_ID, 'carrier_id': 33121, 'full_name': 'Sean Evers',
                   'birth_date': '1977-10-10', 'provider_player_id': EVERS_PROVIDER_ID},
        'add': {'player_id': ADD_ID, 'carrier_id': 33129, 'full_name': 'Steve Adams',
                'birth_date': '1980-09-25', 'provider_player_id': ADAMS_PROVIDER_ID,
                'native_primary_position': 'D', 'dated_match_position': 'M'}}:
        raise ValueError('typed Plymouth actor identities or explicit preserved position differ')
    if request.get('policies') != {
        'source': SOURCE_ORDER_POLICY,
        'order': 'Only use scripts.season_opening_order_repair_v1.repair_club/apply_layer to derive complete 25-person startup order. Preserve relative nonselected tail; no claimed published bench order.',
        'scope': SCOPE, 'excluded': EXCLUDED}:
        raise ValueError('typed Plymouth policy/scope differs')
    bindings = request.get('source_bindings')
    if bindings != SOURCE_BINDINGS:
        raise ValueError('typed Plymouth source body/receipt URLs and hashes differ from reviewed originals')
    if request.get('expected_package_sha256') != registry.sha256_file(base.package_path):
        raise ValueError('typed Plymouth package parent pin differs')
    if request.get('expected_jug_sha256') != registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'):
        raise ValueError('typed Plymouth JUG parent pin differs')
    if request.get('expected_eq_sha256') != registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI'):
        raise ValueError('typed Plymouth EQ parent pin differs')


def _source_proof(request):
    bindings = request['source_bindings']
    schedule_binding = bindings['soccerbase_schedule']
    fixture = soccerbase.first_fixture(
        _read(schedule_binding), 2036, SEASON, FIXTURE['competition'],
        FIXTURE['team_name'], schedule_binding['url'])
    expected_fixture = {key: FIXTURE[key] for key in ('date', 'game_id', 'score')}
    expected_fixture.update(sides=[{'team_id': 2036, 'name': 'Plymouth'},
                                   {'team_id': 1537, 'name': 'Leyton Orient'}])
    if fixture != expected_fixture:
        raise ValueError('original SoccerBase schedule does not reproduce exact Plymouth opener')
    match_binding = bindings['soccerbase_match_sheet']
    match = soccerbase.match(_read(match_binding), fixture, 2036, match_binding['url'])
    xi_ids = [p['source_player_id'] for p in match['starting_xi']]
    bench_ids = [p['source_player_id'] for p in match['published_bench']]
    if xi_ids != FIXTURE['expected_starting_xi_source_ids'] \
            or bench_ids != FIXTURE['expected_published_bench_source_ids']:
        raise ValueError('original dated Plymouth XI or complete five-person published bench differs')
    profiles = {}
    for key, provider_id in (('adams_profile', ADAMS_PROVIDER_ID), ('evers_profile', EVERS_PROVIDER_ID)):
        binding = bindings[key]
        url = f'https://www.soccerbase.com/players/player.sd?player_id={provider_id}'
        if binding.get('url') != url:
            raise ValueError('SoccerBase identity profile URL/provider ID differs')
        source_person = {'source_player_id': f'soccerbase:{provider_id}',
                         'provider_player_id': provider_id}
        profiles[key] = soccerbase.profile(_read(binding), source_person, url)
    adams = profiles['adams_profile']; evers = profiles['evers_profile']
    if (adams['name'], adams['birth_date']) != ('Steve Adams', '1980-09-25') \
            or (evers['name'], evers['birth_date']) != ('Sean Evers', '1977-10-10'):
        raise ValueError('source profile full name/DOB identity differs')
    bench_adams = [p for p in match['published_bench'] if p['provider_player_id'] == ADAMS_PROVIDER_ID]
    if len(bench_adams) != 1 or bench_adams[0]['position'] != 'M' \
            or bench_adams[0]['published_match_name'] != 'S Adams':
        raise ValueError('dated source does not positively bind Adams as a named Plymouth substitute')
    all_ids = {p['provider_player_id'] for p in match['starting_xi'] + match['published_bench']}
    if EVERS_PROVIDER_ID in all_ids:
        raise ValueError('dated source includes Evers in the XI or published substitutes')
    return fixture, match, profiles


def _actor_rows(package, jug, eq, request):
    club_rows = [c for c in package['clubs'] if c.get('carrier_id') == CLUB_CARRIER]
    if len(club_rows) != 1:
        raise ValueError('Plymouth carrier 385 must map to exactly one recipe club')
    club = club_rows[0]
    if club.get('id') != CLUB_ID or club.get('name') != 'Plymouth Argyle':
        raise ValueError('Plymouth recipe club identity differs')
    actors = {p['id']: p for p in package['players']}
    if club.get('opening', {}).get('substitute_player_ids') != BEFORE:
        raise ValueError('current Plymouth opening selection differs from exact preimage')
    if len(club.get('roster_player_ids', [])) != 25 or len(set(club['roster_player_ids'])) != 25:
        raise ValueError('Plymouth recipe roster is not the exact 25-person preimage')
    if not set(BEFORE + [ADD_ID]) <= set(club['roster_player_ids']):
        raise ValueError('Evers and Adams must both be current Plymouth roster members')
    by_id = {REMOVE_ID: actors.get(REMOVE_ID), ADD_ID: actors.get(ADD_ID)}
    for player_id, source_name, dob, carrier in (
            (REMOVE_ID, 'Sean Evers', '1977-10-10', 33121),
            (ADD_ID, 'Steve Adams', '1980-09-25', 33129)):
        actor = by_id[player_id]
        if actor is None or actor.get('carrier_id') != carrier or actor.get('club_id') != CLUB_ID:
            raise ValueError('exact Evers/Adams recipe actors differ')
        if normalise(actor.get('source_name') or actor['name']) != normalise(source_name) \
                or actor['facts'].get('birth_date') != dob:
            raise ValueError('exact source full name/DOB does not map to expected recipe actor')
        nf = native.native_facts(jug, carrier)
        if normalise(nf['name']) != normalise(source_name) or nf['birth_date'] != dob:
            raise ValueError('native full name/DOB actor preimage differs')
        if nf['position'] != actor['facts'].get('primary_position'):
            raise ValueError('native/recipe primary position preimage differs')
    adams = by_id[ADD_ID]
    if adams['facts'].get('primary_position') != 'D':
        raise ValueError('Adams native D preimage changed; this request cannot adjudicate position')
    owners = order_writer.native_owners(eq)
    if owners.get(33121) != {CLUB_CARRIER} or owners.get(33129) != {CLUB_CARRIER}:
        raise ValueError('Evers and Adams must remain exclusively owned by Plymouth carrier 385')
    return club, actors, by_id, owners


def prepare(base, input_path, request=None):
    request_path = Path(input_path)
    if not request_path.is_absolute():
        request_path = ROOT / request_path
    source_request = pipeline.read_json_file(request_path)
    if request is not None and request != source_request:
        raise ValueError('typed Plymouth request differs from bound source input')
    request = source_request
    _validate_request(base, request)
    fixture, match, profiles = _source_proof(request)
    package = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    club, players, player_rows, owner_sets = _actor_rows(package, jug, eq, request)

    # The stable provider IDs join source to the exact native-owned recipe
    # actors. Names and DOBs are rechecked above; no biography field is written.
    adams_bench = next(p for p in match['published_bench'] if p['provider_player_id'] == ADAMS_PROVIDER_ID)
    if adams_bench['provider_player_id'] != profiles['adams_profile']['provider_player_id']:
        raise ValueError('match-sheet Adams link and biography provider ID differ')
    edited = copy.deepcopy(club)
    edited['opening']['substitute_player_ids'] = list(AFTER)
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    layer_club = order_writer.repair_club(edited, players, index, jug)
    layer = {'schema_version': order_writer.SCHEMA, 'season': SEASON, 'clubs': [layer_club]}
    proposed_jug = order_writer.apply_layer(eq, jug, layer, allow_compact=False)
    if order_writer.apply_layer(eq, proposed_jug, layer, allow_compact=False) != proposed_jug:
        raise ValueError('existing startup-order writer is not idempotent')
    offsets = [i for i, (a, b) in enumerate(zip(jug, proposed_jug)) if a != b]
    jug_entries = {e.record_id: e for e in index.values()}
    allowed = []
    before_orders = []
    for row in layer_club['players']:
        entry = jug_entries[row['native_player_id']]
        field = read_initial_order(entry.decode_payload(jug))
        if field.order != row['before'] or field.family != 'dd6361':
            raise ValueError('startup order writer plan does not bind exact noncompact preimage')
        if row['before'] != row['after']:
            allowed.append(entry.payload_offset + field.offset)
            before_orders.append({'carrier_id': row['native_player_id'], 'native_name': field.name,
                                  'before': row['before'], 'after': row['after']})
    if len(offsets) != 5 or sorted(offsets) != sorted(allowed):
        raise ValueError('Evers/Adams proposal must change exactly the five derived startup-order bytes')
    if any(r['before'] != r['after'] for r in layer_club['players'][:11]):
        raise ValueError('original Plymouth XI order must remain unchanged')

    plan = {
        'schema': exchange.SCHEMA, 'season': base.season, 'release_id': base.release_id,
        'source_input': exchange.binding(request_path),
        'package_sha256': request['expected_package_sha256'],
        'jug_sha256': request['expected_jug_sha256'], 'eq_sha256': request['expected_eq_sha256'],
        'request': request, 'updates': [], 'decisions': [],
        'bindings': {'snapshot': {'project_url': 'https://www.soccerbase.com/'}},
        'source_title': 'SoccerBase Plymouth dated original opening substitute selection correction',
        'proof_covers': ['dated-original-Plymouth-XI-and-five-published-substitutes',
                         'one-source-bound-existing-roster-substitute-selection-change',
                         'only-derived-native-startup-order-bytes'],
        'scope': SCOPE,
        'typed_partial_order': {
            'kind': KIND, 'club_carrier_id': CLUB_CARRIER, 'club_id': CLUB_ID,
            'fixture': fixture, 'starting_xi_source_ids': FIXTURE['expected_starting_xi_source_ids'],
            'published_bench_source_ids': FIXTURE['expected_published_bench_source_ids'],
            'adams_source_person': profiles['adams_profile'], 'evers_source_person': profiles['evers_profile'],
            'selection_before': BEFORE, 'selection_after': AFTER,
            'order_layer': layer, 'changed_order_rows': before_orders,
            'changed_jug_offsets': offsets, 'eq_unchanged': True,
            'native_owner_sets': {str(cid): sorted(owner_sets[cid]) for cid in (33121, 33129)},
            'preserved_actor_facts': {pid: copy.deepcopy(player_rows[pid]['facts']) for pid in (REMOVE_ID, ADD_ID)},
            'scope_limit': 'The exact dated source lists five substitutes while the native recipe retains seven selected slots; this is a one-for-one correction, not a complete-bench claim.'}}
    plan['transaction_id'] = exchange.digest(packages.canonical_json_bytes(plan))[:24]
    # Exercise the standard exchange-shaped plan construction/validation path.
    if plan['request'].get('proposal_kind') != KIND:
        raise ValueError('typed proposal kind was lost during construction')
    return plan


def verify(base, plan):
    if plan.get('schema') != exchange.SCHEMA or prepare(base, plan['source_input']['path']) != plan:
        raise ValueError('typed SoccerBase partial order plan does not independently reproduce')


def bind(package, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    if registry.sha256_file(base.package_path) != plan['package_sha256']:
        raise ValueError('exact package parent changed')
    result = delta.updated_package(package, plan)
    artifact = next(a for a in result['artifacts'] if a['relative_path'] == delta.plan_filename(plan))
    previous = artifact['id']
    aid = exchange.PREFIX + plan['transaction_id']
    artifact.update(id=aid, relative_path=exchange.filename(plan),
                    sha256=exchange.digest(packages.canonical_json_bytes(plan)))
    for collection in ('players', 'sources', 'proofs'):
        for row in result[collection]:
            for key in ('artifact_id', 'evidence_artifact_id'):
                if row.get(key) == previous:
                    row[key] = aid
            proofs = [row.get('proof', {})] + [f.get('proof', {}) for f in row.get('fact_fallbacks', [])]
            for proof in proofs:
                if proof.get('artifact_id') == previous:
                    proof['artifact_id'] = aid
    clubs = [c for c in result['clubs'] if c.get('carrier_id') == CLUB_CARRIER]
    if len(clubs) != 1:
        raise ValueError('bound package lost unique Plymouth target')
    club = clubs[0]
    actor_by_carrier = {p['carrier_id']: p for p in result['players']}
    order_rows = plan['typed_partial_order']['order_layer']['clubs'][0]['players']
    club['roster_player_ids'] = [actor_by_carrier[row['native_player_id']]['id'] for row in order_rows]
    club['opening']['substitute_player_ids'] = list(AFTER)
    club['opening']['proof'] = {'artifact_id': aid, 'grade': 'source-receipt'}
    # Only the targeted club's order/selection/proof and the evidence artifact
    # may differ. All player rows, facts, assets, and every other club stay exact.
    old_players = {p['id']: p for p in package['players']}
    new_players = {p['id']: p for p in result['players']}
    if old_players != new_players or result['assets'] != package['assets']:
        raise ValueError('selection-only package binding changed player facts or assets')
    for old, new in zip(package['clubs'], result['clubs']):
        if old['carrier_id'] == CLUB_CARRIER:
            for key in old:
                if key not in ('roster_player_ids', 'opening') and old[key] != new[key]:
                    raise ValueError('selection-only package binding changed another Plymouth field')
        elif old != new:
            raise ValueError('selection-only package binding changed another club')
    if club['opening']['starting_xi_player_ids'] != next(
            c for c in package['clubs'] if c['carrier_id'] == CLUB_CARRIER)['opening']['starting_xi_player_ids']:
        raise ValueError('Plymouth starting XI changed')
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    original_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (exchange.digest(original_jug), exchange.digest(original_eq)) != (plan['jug_sha256'], plan['eq_sha256']):
        raise ValueError('opening order parent JUG/EQ pins changed')
    if eq != original_eq:
        raise ValueError('typed partial order accepts only the exact original EQ input')
    layer = plan['typed_partial_order']['order_layer']
    proposed = order_writer.apply_layer(original_eq, original_jug, layer, allow_compact=False)
    if order_writer.apply_layer(original_eq, proposed, layer, allow_compact=False) != proposed:
        raise ValueError('typed partial order native output is not idempotent')
    allowed = set(plan['typed_partial_order']['changed_jug_offsets'])
    changed = {i for i, (a, b) in enumerate(zip(original_jug, proposed)) if a != b}
    if changed != allowed or len(changed) != 5 or proposed == original_jug:
        raise ValueError('typed partial order changed bytes outside the five exact order masks')
    if jug not in (original_jug, proposed):
        raise ValueError('typed partial order JUG is neither exact preimage nor postimage')
    return proposed, original_eq


def filename(plan):
    return exchange.filename(plan)


def artifact_id(plan):
    return exchange.PREFIX + plan['transaction_id']


def reject_factory_recipe(package):
    return exchange.reject_factory_recipe(package)


def reconstruction(previous, release_id):
    # The standard exchange reconstruction path performs typed prepare/verify,
    # package binding, native apply and whole-SOURCE inventory comparison.
    return exchange.reconstruction(previous, release_id)
