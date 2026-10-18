"""Compose a sourced replacement club with retained-person roster repairs.

Pure in-memory preflight only. This is not a publisher or a source-policy
waiver: original source proposals and retained fixture bindings must be
reviewed separately. No factory rebuild or unaffected game write occurs here.
"""
import copy
from datetime import date
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders
from scripts import season_retained_native_transfer_v1 as transfer
from scripts import season_verified_opening_roster_sources_v1 as sources
from scripts import prepare_duplicate_whole_club_native_v1 as whole
from scripts import prepare_duplicate_club_disposition_v1 as allocator
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def original(path, digest):
    path = registry.ROOT / path
    if registry.sha256_file(path) != digest:
        raise ValueError('composition original source changed')
    return path


def original_countries(proposal):
    """Keep frozen old proposals intact; explicitly derive additional country rows."""
    result = copy.deepcopy(proposal)
    enriched = {}
    for person in result['desired_people']:
        evidence = person['raw_evidence']
        path = original(evidence['local_path'], evidence['source_sha256'])
        receipt = pipeline.read_json_file(path.with_name(path.name + '.source.json'))
        pid = int(parse_qs(urlparse(receipt['url']).query)['player_id'][0])
        identity, facts, _ = sources.profile(dict(path=evidence['local_path'],
            sha256=evidence['source_sha256'], url=receipt['url']), pid)
        if (identity['name'], identity['birth_date']) != (
                person['source_player']['name'], person['source_player']['birth_date']):
            raise ValueError('additional country row identifies another person')
        if person['source_player'].get('nationality') is None and facts['nationality'] is not None:
            person['source_player']['nationality'] = facts['nationality']
        enriched[person['source_person']['source_player_id']] = person
    for row in result['allocation']:
        row['replacement'] = copy.deepcopy(enriched[row['replacement']['source_person']['source_player_id']])
    return result


def compile_preflight(base, proposal_path, retained_binding_path, request):
    """Return recipe/JUG/EQ and evidence; do not write or register a game."""
    if (request['season'], request['release_id']) != (base.season, base.release_id):
        raise ValueError('composition request must bind exact registered baseline')
    package = pipeline.read_json_file(base.package_path)
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    if len(package_layers(base)) != 1:
        raise ValueError('composition preflight requires one effective main recipe')
    before = {p['carrier_id']: p for p in package['players']}
    retained = pipeline.read_json_file(retained_binding_path)
    proposal = pipeline.read_json_file(proposal_path)
    if (proposal['season'], proposal['release_id'], proposal['package_sha256']) != (
            base.season, base.release_id, registry.sha256_file(base.package_path)):
        raise ValueError('whole-club source proposal has a different recipe baseline')
    raw = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
            registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI')) != (proposal['jug_sha256'], proposal['eq_sha256']):
        raise ValueError('whole-club native baseline changed')
    fixture = retained['fixture']
    schedule = fixture['date_anchors'][0]
    group = dict(club_name=request['retained_source_club_name'], provider_team_id=request['retained_provider_team_id'],
        competition=request['competition'], expected_opening_game_id=fixture['soccerbase_match_id'],
        schedule=dict(path=schedule['source_path'], sha256=schedule['sha256'], url=schedule['source_url']),
        match=dict(path=fixture['source_path'], sha256=fixture['source_sha256'], url=fixture['source_url']),
        profiles={pid: dict(path=p['profile_path'], sha256=p['profile_sha256'], url=p['profile_url'])
                  for pid, p in retained['provider_profiles'].items()}, reserves=[])
    verified = sources.read(base.season, group)
    people = {p['source_person']['provider_player_id']: p for p in verified['desired']}
    if len(retained['matchday_mapping']) != len(verified['desired']):
        raise ValueError('retained club must account for every original matchday actor')
    mappings = retained['matchday_mapping']
    if [r['soccerbase_player_id'] for r in mappings] != [p['source_person']['provider_player_id'] for p in verified['desired']]:
        raise ValueError('retained mapping differs from literal original XI/bench order')
    moves = []
    new_people = []
    destinations = []
    moved_rows = []
    for row in mappings:
        pid, dest, src = row['soccerbase_player_id'], row['proposed_carrier_id'], row['source_person_carrier_before_plan']
        person = people[pid]
        if src is None:
            new_people.append(person)
            destinations.append(before[dest])
        elif src != dest:
            old = before[src]
            if (sources.fields.normalise(old.get('source_name', old['name'])), old['facts']['birth_date']) != (
                    sources.fields.normalise(person['source_player']['name']), person['source_player']['birth_date']):
                raise ValueError('retained move lacks exact original source identity/DOB')
            moves.append(dict(source_carrier=src, destination_carrier=dest,
                expected_source_display=transfer.read(next(e for e in transfer.IndexedFDIFile.from_bytes(raw).entries
                    if e.record_id == src).decode_payload(raw), src)[0]['name'],
                expected_destination_display=transfer.read(next(e for e in transfer.IndexedFDIFile.from_bytes(raw).entries
                    if e.record_id == dest).decode_payload(raw), dest)[0]['name'],
                recover_destination_capacity=dest in request['recover_move_destinations']))
            moved_rows.append((src, dest))
        else:
            old = before[src]
            if sources.fields.normalise(old.get('source_name', old['name'])) != sources.fields.normalise(person['source_player']['name']):
                raise ValueError('retained matchday source name differs from existing identity')
            if old['facts']['birth_date'] != person['source_player']['birth_date']:
                conflict = dict(carrier_id=src, native_date=old['facts']['birth_date'],
                                source_date=person['source_player']['birth_date'])
                if conflict not in request['preserved_birthday_conflicts']:
                    raise ValueError('undeclared retained birthday conflict')
    # Dated August members fill capacity but never become original matchday actors.
    reserve_rows = retained['proposed_august_reserve_additions']
    for row in reserve_rows:
        evidence = row['source']
        path = original(evidence['path'], evidence['sha256'])
        receipt = pipeline.read_json_file(registry.ROOT / evidence['receipt_path'])
        raw_article = path.read_bytes()
        if receipt.get('url') != evidence['url'] or receipt.get('sha256') != evidence['sha256']:
            raise ValueError('August article URL/hash receipt differs')
        if not (base.season[:4] + '-07-01' <= evidence['published_date'] <= base.season[:4] + '-08-31'):
            raise ValueError('reserve arrival outside agreed July/August window')
        date.fromisoformat(evidence['published_date'])
        if (evidence['published_date'] not in raw_article.decode('utf-8', errors='replace')
                or row['person'] not in BeautifulSoup(raw_article, 'lxml').get_text(' ', strip=True)):
            raise ValueError('August source lacks declared date/person anchors')
    bundle = proposal['capacity_policy_bundle']
    for extra in request.get('additional_moves', []):
        src, dest = extra['source_carrier'], extra['destination_carrier']
        if not any(r['person'] == before[src].get('source_name') and r['proposed_carrier_id'] == dest for r in reserve_rows):
            raise ValueError('additional retained move lacks positive August source')
        person, _, _ = sources.profile(extra['profile_binding'], extra['provider_player_id'])
        if (sources.fields.normalise(before[src].get('source_name', before[src]['name'])), before[src]['facts']['birth_date']) != (
                sources.fields.normalise(person['name']), person['birth_date']):
            raise ValueError('additional August person lacks exact original biography identity')
        moves.append(extra)
        moved_rows.append((src, dest))
    allocation = []
    for destination, person in zip(destinations, new_people):
        allocation.extend(allocator.allocate(raw, [destination], [person], {}, capacity_bundle=bundle))
    declared = {row['soccerbase_player_id']: row['proposed_carrier_id'] for row in mappings}
    if any(declared[a['replacement']['source_person']['provider_player_id']] != a['carrier_id'] for a in allocation):
        raise ValueError('retained new-player allocation differs from approved source mapping')
    result, whole_composition = whole.compile_recipe(package, original_countries(proposal))
    by = {p['carrier_id']: p for p in result['players']}
    for src, dest in moved_rows:
        actor = copy.deepcopy(before[src])
        actor.update({k: before[dest][k] for k in ('id', 'carrier_id', 'carrier_family', 'club_id')})
        by[dest].clear()
        by[dest].update(actor)
    updates = [dict(player_id=a['player_id'], carrier_id=a['carrier_id'], layer='main',
        before=copy.deepcopy(before[a['carrier_id']]), replacement=a['replacement'],
        replacement_opening_evidence=dict(date=fixture['date'])) for a in allocation]
    composition = dict(season=base.season, bindings=dict(snapshot=dict(project_url='https://www.soccerbase.com/')),
        updates=updates, source_title='Source-bound original matchday bench and retained person moves',
        proof_covers=['bounded-native-preflight-only'], retained_sources=binding(retained_binding_path), request=request)
    result = whole.delta.updated_package(result, composition)
    by = {p['carrier_id']: p for p in result['players']}
    for a in allocation:
        by[a['carrier_id']]['name'] = a['display']['display_name']
    country_updates = []
    artifact = next(a for a in result['artifacts'] if a.get('relative_path') == whole.delta.plan_filename(composition))
    for row in mappings:
        dest = row['proposed_carrier_id']
        if dest not in {m['destination_carrier'] for m in moves}:
            continue
        country = people[row['soccerbase_player_id']]['source_player'].get('nationality')
        if country and by[dest]['facts']['nationality'] != country:
            country_updates.append(dict(carrier_id=dest, nationality=country,
                source_person=people[row['soccerbase_player_id']]))
            by[dest]['facts']['nationality'] = country
            by[dest]['fact_fallbacks'] = [f for f in by[dest].get('fact_fallbacks', []) if f['field'] != 'nationality']
            by[dest]['proof'] = dict(artifact_id=artifact['id'], grade='source-receipt')
    prepared = raw
    for row in proposal['allocation'] + allocation:
        if row.get('same_carrier_name_capacity'):
            prepared, claim = transfer.capacity.recover_slot(prepared, row['carrier_id'], bundle)
            if claim != row['same_carrier_name_capacity']:
                raise ValueError('source allocation capacity claim changed')
    ids = {a['player_id'] for a in proposal['allocation'] + allocation}
    countries = whole.delta.compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    jug = whole.delta.compile_players(prepared, result, ids, countries)
    moved, move_proof = transfer.compile_moves(raw, moves, capacity_bundle=bundle)
    index = transfer.IndexedFDIFile.from_bytes(moved)
    move_targets = {m['destination_carrier'] for m in moves}
    jug = whole.delta.compiler._rebuild_indexed(jug, transfer.IndexedFDIFile.from_bytes(jug),
        {e.record_id: e.decode_payload(moved) for e in index.entries if e.record_id in move_targets})
    if country_updates:
        index = transfer.IndexedFDIFile.from_bytes(jug)
        entries = {e.record_id: e for e in index.entries}
        corrected = {}
        for row in country_updates:
            carrier = row['carrier_id']
            payload = bytearray(entries[carrier].decode_payload(jug))
            observed, _ = transfer.read(payload, carrier)
            payload[observed['name_end'] + 8] = whole.delta.compiler._country_code(row['nationality'], countries) ^ 0x61
            corrected[carrier] = bytes(payload)
        jug = whole.delta.compiler._rebuild_indexed(jug, index, corrected)
    owned = [r['proposed_carrier_id'] for r in mappings] + [r['proposed_carrier_id'] for r in reserve_rows]
    club = next(c for c in package['clubs'] if c['carrier_id'] == request['retained_club_carrier_id'])
    if len(owned) != len(set(owned)) or set(owned) != {p['carrier_id'] for p in package['players'] if p['club_id'] == club['id']}:
        raise ValueError('retained source pool does not cover exact owned capacity')
    index = {e.record_id: e for e in transfer.IndexedFDIFile.from_bytes(jug).entries}
    orders = [OrderReplacement(c, read_initial_order(index[c].decode_payload(jug)).name,
        read_initial_order(index[c].decode_payload(jug)).order, i) for i, c in enumerate(owned, 1)]
    jug = patch_owned_mode1_complete_orders(jug, eq, club_record_id=club['carrier_id'], replacements=orders)
    from scripts import season_whole_club_keeper_exchange_v1 as keeper
    from app.player_initial_order import patch_owned_mode1_keeper_exchange
    if proposal.get('startup_order_exchange'):
        new_club = next(c for c in result['clubs'] if c['id'] == proposal['before_club']['id'])
        keeper.validate_scope(result, new_club, proposal)
        jug = patch_owned_mode1_keeper_exchange(jug, eq,
            keeper.bound_native_replacements(jug, proposal['startup_order_exchange']))
    new_club = next(c for c in result['clubs'] if c['id'] == proposal['before_club']['id'])
    players_by_id = {p['id']: p for p in result['players']}
    eq = whole.rewrite_roster(eq, new_club['carrier_id'],
        [players_by_id[id]['carrier_id'] for id in new_club['roster_player_ids']])
    entry = next(e for e in transfer.IndexedFDIFile.from_bytes(eq).entries if e.record_id == new_club['carrier_id'])
    short, full, _ = whole.labels.prefix_parts(entry.decode_payload(eq))
    eq, _ = whole.labels.rewrite_club_labels(eq, [dict(carrier_id=new_club['carrier_id'],
        native_before=short, native_full_before=full,
        native_after=whole.delta.compiler._pm99_text(proposal['new_club'], label='source-bound club'))])
    manager_source = request['manager_source']
    manager_path = original(manager_source['path'], manager_source['sha256'])
    receipt = pipeline.read_json_file(manager_path.with_name(manager_path.name + '.source.json'))
    query = parse_qs(urlparse(receipt['url']).query)
    expected_team = proposal['original_opening']['source_capture']['source_path'].split('/')[2]
    if (receipt.get('sha256') != manager_source['sha256']
            or urlparse(receipt['url']).hostname != 'www.soccerbase.com'
            or urlparse(receipt['url']).path != '/teams/team.sd'
            or query != dict(team_id=[expected_team], teamTabs=['managers'])):
        raise ValueError('manager source is not the exact original team manager history')
    from scripts.prepare_paired_whole_club_native_v1 import dated_manager_identity
    name, manager_person = dated_manager_identity(manager_path.read_bytes(), proposal['original_opening']['fixture']['date'])
    short, _ = whole.manager_display.short_name(name)
    if short is None:
        raise ValueError('manager needs a proven compact display')
    manager = next(m for m in result['managers'] if m['id'] == new_club['manager_id'])
    holdings, _ = whole._manager_graph(eq_path=base.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=base.game_path / 'DBDAT/ENT98030.FDI')
    if [c['carrier_id'] for c in holdings.get(manager['carrier_id'], [])] != [new_club['carrier_id']]:
        raise ValueError('new club does not exclusively own its manager carrier')
    ent = (base.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    index = transfer.IndexedFDIFile.from_bytes(ent)
    entry = next(e for e in index.entries if e.record_id == manager['carrier_id'])
    names = dict(surname=short, display_name=short)
    payload = whole.delta.compiler._patch_ent_name(entry.decode_payload(ent), manager['carrier_id'],
        whole.delta.compiler._pm99_text(name, label='dated club manager'), native_names=names)
    ent = whole.delta.compiler._rebuild_indexed(ent, index, {manager['carrier_id']: payload})
    manager.update(name=name, person_id='manager-soccerbase-' + str(manager_person), policy='write',
        native_names=names, proof=dict(artifact_id=artifact['id'], grade='source-receipt'))
    identity_carriers = {r['carrier_id'] for r in proposal['allocation'] + allocation} | move_targets
    changed_ids = {p['id'] for p in result['players'] if p['carrier_id'] in identity_carriers}
    portraits = result['assets']['portraits']
    portraits[:] = [p for p in portraits if p['player_id'] not in changed_ids]
    portraits.extend(dict(player_id=id, status='native-no-photo',
        proof=dict(artifact_id=artifact['id'], grade='source-receipt'),
        review_reason='Source-bound identity composition; old slot photograph cleared.') for id in sorted(changed_ids))
    portraits.sort(key=lambda row: row['player_id'])
    archive, photo_offsets = whole.delta.no_photo_archive((base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes(), identity_carriers)
    whole.preserve_other_records(raw, jug, identity_carriers | set(owned))
    whole.preserve_other_records((base.game_path / 'DBDAT/EQ98030.FDI').read_bytes(), eq, {new_club['carrier_id']})
    whole.preserve_other_records((base.game_path / 'DBDAT/ENT98030.FDI').read_bytes(), ent, {manager['carrier_id']})
    whole.package_v2.validate_package(result)
    return result, {'JUG98030.FDI': jug, 'EQ98030.FDI': eq, 'ENT98030.FDI': ent, 'MINIFOTO.PKF': archive}, dict(moves=move_proof, new_people=len(allocation),
        compositions=[whole_composition, composition], owned_order=owned,
        explicit_source_country_updates=country_updates,
        changed_identity_carriers=sorted(identity_carriers), photo_offsets=photo_offsets,
        manager=dict(name=name, source_person_id=manager_person, carrier_id=manager['carrier_id']),
        native_files_written=False, publication_approved=False,
        remaining='Ground/kit application, final source/identity audit, runtime and publication not performed.')
