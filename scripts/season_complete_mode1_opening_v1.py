"""Bind a complete mode1 XI to its original fixture without rewriting facts.

Used only as an explicit companion to the existing identity exchange. The
reserve-only lane remains unchanged. Non-XI players retain their relative
native order; this does not claim the original seven-player bench order.
"""
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders
from scripts import season_opening_identity_exchange_v1 as exchange

POLICY = 'original-first-league-mode1-XI-and-positive-bench-replacements-v1'
ORDER_ONLY_POLICY = 'original-first-league-mode1-XI-order-only-v1'


def retained_field_matches(declared, actual):
    # A native-preserve reserve is not a historical fact claim. Its bytes are
    # still protected by the exact record diff, and no new default is written.
    return declared == actual or declared == {'policy': 'preserve-existing-mode1'}


def corrected_birthday(base, request, source, actor):
    """Replay an existing official adjudication, never waive identity checks."""
    from scripts import season_adjudicated_player_facts_v1 as adjudicated
    from scripts import season_source_verified_player_changes_v1 as changes
    claims = request['complete_mode1_opening'].get('retained_fact_adjudications', [])
    found = [c for c in claims if c['carrier_id'] == actor['carrier_id']]
    if len(found) != 1:
        raise ValueError('changed original XI birthday needs one exact prior adjudication')
    document = exchange.pipeline.read_json_file(exchange.original(request['evidence'][found[0]['evidence']]))
    if (document.get('schema') != changes.INPUT_SCHEMA or document.get('kind') != changes.ADJUDICATED_KIND
            or document.get('season') != base.season):
        raise ValueError('retained XI adjudication schema/season differs')
    rows = [r for r in document['changes'] if r['carrier_id'] == actor['carrier_id']]
    if len(rows) != 1:
        raise ValueError('retained XI adjudication actor differs')
    row = rows[0]; witness = row['witness']; historical = witness['historical_identity']
    if ('birth_date' not in row['field_mask'] or row['before']['person_id'] != actor['person_id']
            or row['before']['facts']['birth_date'] != source['facts']['birth_date']
            or witness['person_id'] != actor['person_id']
            or historical['source_row_sha256'] != source['source_row_sha256']
            or str(historical['provider_player_id']) != str(source['opening_source_player_id'])
            or exchange.published_name_key(witness['full_name']) != exchange.published_name_key(actor['source_name'])):
        raise ValueError('retained XI adjudication historical identity/preimage differs')
    values = adjudicated.adjudicate(witness)
    if values['birth_date'] != actor['facts']['birth_date']:
        raise ValueError('retained XI birthday differs from official adjudicated fact')
    return actor['carrier_id']


def prepare(base, request, package, jug, eq):
    claim = request['complete_mode1_opening']
    order_only = claim.get('policy') == ORDER_ONLY_POLICY
    if claim.get('policy') not in (POLICY, ORDER_ONLY_POLICY) or request.get('orders') or request.get('moves'):
        raise ValueError('explicit complete mode1 policy without unrelated moves/orders required')
    if order_only and (request.get('new_people') or request.get('retirements')
            or set(request) - {'schema', 'season', 'release_id', 'evidence', 'moves', 'new_people',
                               'orders', 'retirements', 'complete_mode1_opening'}):
        raise ValueError('explicit order-only policy cannot contain identity or unrelated transactions')
    clubs = [c for c in package['clubs'] if c['carrier_id'] == claim['club_carrier_id']]
    if len(clubs) != 1 or clubs[0]['opening'].get('policy') != 'preserve-existing-mode1':
        raise ValueError('complete mode1 opening needs one retained native club')
    club = clubs[0]
    fixture = request['evidence'][claim['match']]
    exchange.verify_first_league_fixture(fixture)
    capture = exchange.pipeline.read_json_file(exchange.original(fixture['first_league_capture']))
    captured = [c for c in capture['clubs'] if c['source_selector'].get('transfermarkt_club_id') == fixture['provider_club_id']]
    if (len(captured) != 1 or captured[0]['source_selector']['club_name'] != club['name']
            or captured[0]['source_competition_code'] != fixture['competition']):
        raise ValueError('original captured club bridge differs from retained native club')
    exchange.verify_match_club(fixture, captured[0]['source_selector']['transfermarkt_club_name'])
    pre = exchange.pipeline.read_json_file(exchange.original(request['evidence'][claim['preallocation']]))
    groups = [c for c in pre['source_clubs'] if c['selector']['club_name'] == club['name']]
    if (len(groups) != 1 or not groups[0]['opening_xi_complete']
            or groups[0]['opening_fixture_date'] != fixture['date']
            or str(groups[0]['opening_source_match_id']) != str(captured[0]['source_match_id'])):
        raise ValueError('retained original preallocation fixture/XI differs')
    projected = sorted((p for p in groups[0]['players'] if type(p.get('opening_xi_order')) is int),
                       key=lambda p: p['opening_xi_order'])
    xi, bench = exchange.match_people(fixture)
    if (len(xi) != 11 or len(projected) != 11
            or [str(p['opening_source_player_id']) for p in projected] != [p['source_player_id'] for p in xi]
            or [p['opening_xi_order'] for p in projected] != list(range(1, 12))):
        raise ValueError('original numeric XI must reproduce exactly in published order')
    actors = [p for p in package['players'] if p['club_id'] == club['id']]
    players = {p['carrier_id']: p for p in actors}
    if set(club['roster_player_ids']) != {p['id'] for p in actors}:
        raise ValueError('complete mode1 recipe ownership differs')
    owners = exchange.roster  # source normalisation, not inferred membership
    facts = {pid: exchange.facts.native_facts(jug, pid) for pid in players}
    if order_only and any(
            owners.normalise(facts[pid]['name']) != owners.normalise(actor['name'])
            or not retained_field_matches(actor['facts']['birth_date'], facts[pid]['birth_date'])
            or not retained_field_matches(actor['facts']['primary_position'], facts[pid]['position'])
            for pid, actor in players.items()):
        raise ValueError('order-only requires all retained native names/DOBs/positions to match')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(eq).entries}
    entry = entries[club['carrier_id']]
    roster = exchange.delta.compiler.parse_eq_external_team_roster_payload(
        eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
    if (roster is None or roster.mode_byte != 1 or any(r.flag for r in roster.rows)
            or len(roster.rows) != len(players)
            or {r.player_record_id for r in roster.rows} != set(players)):
        raise ValueError('complete mode1 native capacity/flags/ownership differ')
    from scripts.season_opening_order_repair_v1 import native_owners
    ownership = native_owners(eq)
    if any(ownership.get(pid) != {club['carrier_id']} for pid in players):
        raise ValueError('complete mode1 opening refuses shared or absent players')
    native_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    if any(read_initial_order(native_index[pid].decode_payload(jug)).family != 'dd6360' for pid in players):
        raise ValueError('complete mode1 opening is compact-only')
    starting = []
    adjudicated = []
    for source in projected:
        matches = [p for p in actors if p['person_id'] == 'person-source-' + source['source_row_sha256']]
        if len(matches) != 1:
            raise ValueError('original XI assignment does not identify one retained actor')
        actor = matches[0]; actual = facts[actor['carrier_id']]
        if actor['facts']['birth_date'] != source['facts']['birth_date']:
            adjudicated.append(corrected_birthday(base, request, source, actor))
        if (owners.normalise(actor.get('source_name') or actor['name']) != owners.normalise(source['facts']['name'])
                or actual['birth_date'] != actor['facts']['birth_date']
                or owners.normalise(actual['name']) != owners.normalise(actor['name'])):
            raise ValueError('retained original XI name/DOB/native identity differs')
        starting.append(actor['carrier_id'])
    claims = claim.get('retained_fact_adjudications', [])
    if len(claims) != len(adjudicated) or {c['carrier_id'] for c in claims} != set(adjudicated):
        raise ValueError('unused or duplicate retained XI adjudication claims')
    selected = {p['carrier_id'] for p in request['new_people']}
    if ((not selected and not order_only) or not selected <= set(players) or selected & set(starting)
            or any(p.get('match') != claim['match'] or p.get('opening_contract') for p in request['new_people'])
            or any(str(p['provider_player_id']) not in {b['source_player_id'] for b in bench} for p in request['new_people'])):
        raise ValueError('mode1 replacements must be independent positive bench identities, never sourced XI')
    tail = sorted(set(players) - set(starting), key=lambda pid: (facts[pid]['startup_order'], pid))
    ordered = starting + tail
    orders = [dict(carrier_id=pid, native_name=facts[pid]['name'], before=facts[pid]['startup_order'], after=n)
              for n, pid in enumerate(ordered, 1)]
    # Reuse the proven native writer NOW as preflight, not after publication.
    apply(jug, eq, dict(club_carrier_id=club['carrier_id'], orders=orders))
    return dict(policy=claim['policy'], club_carrier_id=club['carrier_id'], club_id=club['id'],
                orders=orders, starting_xi=starting, fixture_date=fixture['date'],
                published_bench_ids=[p['source_player_id'] for p in bench],
                reserve_policy='preserve-relative-native-order-not-published-bench-order',
                opaque_tactics_unchanged=True)


def apply(jug, eq, plan):
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    rows = []
    for row in plan['orders']:
        field = read_initial_order(index[row['carrier_id']].decode_payload(jug))
        # Replaced actors have their new source-bound name; only their order is
        # supplied here. The outer transaction independently proves identities.
        if field.order not in (row['before'], row['after']):
            raise ValueError('mode1 order is outside its exact pre/postimages')
        rows.append(OrderReplacement(row['carrier_id'], field.name, field.order, row['after']))
    return patch_owned_mode1_complete_orders(jug, eq, club_record_id=plan['club_carrier_id'], replacements=rows)
