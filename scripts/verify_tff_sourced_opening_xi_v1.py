"""Independent native field/byte and whole-game scope checks for the TFF pilot."""
import json
from datetime import date
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_tff_sourced_opening_xi_v1 as source
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


# Loader order, independently enumerated rather than calling the writer.
SKILLS = ('speed', 'stamina', 'aggression', 'quality', 'heading', 'dribbling',
          'passing', 'shooting', 'tackling')


def verify_players(before, after, package, plan, countries):
    old_index = IndexedFDIFile.from_bytes(before)
    new_index = IndexedFDIFile.from_bytes(after)
    old = {e.record_id: e.decode_payload(before) for e in old_index.entries}
    new = {e.record_id: e.decode_payload(after) for e in new_index.entries}
    if len(before)!=len(after) or before[:old_index.index_end_offset]!=after[:new_index.index_end_offset]:
        raise ValueError('bounded TFF pilot changed native container length/header/directory')
    if list(old) != list(new) or len(old) != len(old_index.entries):
        raise ValueError('full-XI repair added, removed or reordered native carriers')
    orders = {r['carrier_id']: r for r in plan['orders']}
    selected = {r['carrier_id']: r for r in plan['replacements']}
    people = {p['carrier_id']: p for p in package['players']}
    changed, changed_orders = [], []
    for carrier, payload in old.items():
        candidate = new[carrier]
        if carrier not in orders:
            if candidate != payload:
                raise ValueError('full-XI repair changed another club/player')
            continue
        native = audit.native_player(candidate, carrier)
        end = native['name_end']
        original_end = audit.native_player(payload, carrier)['name_end']
        if read_initial_order(candidate).order != orders[carrier]['after']:
            raise ValueError('native first-XI/reserve order differs from bound source plan')
        if read_initial_order(payload).order != orders[carrier]['before']:
            raise ValueError('native original order differs from source baseline')
        if payload[5:8] != candidate[5:8] or payload[:8] != candidate[:8]:
            raise ValueError('native carrier/shirt/prefix changed')
        old_tail, tail = payload[original_end:], candidate[end:]
        if len(old_tail) != len(tail):
            raise ValueError('native opaque tail layout changed')
        allowed = {0}
        row = selected.get(carrier)
        if row:
            player = people[carrier]
            if native['name'].casefold() != player['name'].casefold():
                raise ValueError('native repaired display name differs from recipe')
            parts = audit._indexed_variable_name_runtime_segments(candidate)
            surname = candidate[parts['surname_start']:parts['surname_end']].decode('cp1252')
            if surname.casefold() != player['name'].split(' ',1)[-1].casefold():
                raise ValueError('native lineup surname differs from repaired display name')
            if row['kind'] == 'wrong-person-facts':
                facts = player['facts']; born = date.fromisoformat(facts['birth_date'])
                actual_date = date(int.from_bytes(bytes(b ^ 0x61 for b in candidate[end+14:end+16]), 'little'),
                                   candidate[end+13] ^ 0x61, candidate[end+12] ^ 0x61)
                if (native['position'], native['roles'], actual_date,
                    candidate[end+8] ^ 0x61, candidate[end+16] ^ 0x61, candidate[end+17] ^ 0x61) != (
                        'D', [4,98,98,98,98,98], born, countries['BRAZIL'],
                        facts['height_cm'], facts['weight_kg']):
                    raise ValueError('native defender identity/facts differ from original sources')
                for i, field in enumerate(SKILLS):
                    if candidate[end+18+i] ^ 0x61 != player['ratings']['values'][field]:
                        raise ValueError('native defender skill differs from declared editorial model')
                if candidate[end+27] ^ 0x61 != player['ratings']['values']['handling'] or candidate[-7] ^ 0x61 != player['ratings']['values']['handling']:
                    raise ValueError('native defender handling differs from declared outfield rating')
                allowed.update(range(2,9)); allowed.update(range(10,28)); allowed.add(len(tail)-7)
            elif row['kind'] != 'shirt-prefix-display-name':
                raise ValueError('unsupported replacement scope')
        elif payload[:original_end] != candidate[:end]:
            raise ValueError('native unchanged starter/reserve name changed')
        if any(a != b and i not in allowed for i,(a,b) in enumerate(zip(old_tail,tail))):
            raise ValueError('native repair changed opaque bytes or unrelated player facts/skills')
        if payload != candidate: changed.append(carrier)
        if old_tail[0] != tail[0]: changed_orders.append(carrier)
    xi = sorted(orders, key=lambda k: orders[k]['after'])[:11]
    if xi != [p['carrier_id'] for p in plan['starting_xi']]:
        raise ValueError('native first XI differs from eleven federation person identities')
    positions = [audit.native_player(new[k],k)['position'] for k in xi]
    if positions[0] != 'G' or positions.count('G') != 1:
        raise ValueError('native first XI lacks its single order-one goalkeeper')
    allowed_absolute = {i for e in old_index.entries if e.record_id in orders
                        for i in range(e.payload_offset,e.payload_offset+e.payload_length)}
    if any(a!=b and i not in allowed_absolute for i,(a,b) in enumerate(zip(before,after))):
        raise ValueError('native repair changed container padding or undeclared bytes')
    return {'changed_player_records':changed, 'changed_order_records':changed_orders,
            'first_XI_carriers':xi, 'first_XI_positions':positions,
            'unrelated_player_records_identical':True, 'opaque_bytes_preserved':True}


def verify(season, release_id, plan_path, output):
    if output.exists(): raise ValueError('full-XI evidence is immutable')
    plan = json.loads(plan_path.read_text())
    base = registry.load_registered_release(season, plan['source_release_id'])
    release = registry.load_registered_release(season, release_id)
    source.verify(base,plan)
    saved = registry.ROOT / release.locator['sourced_mode1_opening_plan_path']
    if json.loads(saved.read_text()) != plan: raise ValueError('saved original-XI plan differs')
    original_package = json.loads(base.package_path.read_text())
    package = json.loads(release.package_path.read_text())
    if package != source.updated_package(original_package,plan):
        raise ValueError('full-XI repair changed unrelated recipe data')
    before = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    from scripts.season_package_compiler_v2 import _extract_country_codes_from_textos
    countries = _extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    result = verify_players(before,after,package,plan,countries)
    old_inventory = pipeline.build_tree_inventory(base.game_path)
    new_inventory = pipeline.build_tree_inventory(release.game_path)
    diff = pipeline.inventory_difference(old_inventory,new_inventory)
    allowed = {'DBDAT/JUG98030.FDI','DBDAT/MINIFOTO.PKF'}
    wrong_people = {r['carrier_id'] for r in plan['replacements'] if r['kind']=='wrong-person-facts'}
    removed = {f'DBDAT/MINIFOTO/J96{k:05d}.BMP' for k in wrong_people}
    if (diff['only_right'] or not set(diff['only_left']) <= removed
            or not {r['path'] for r in diff['changed']} <= allowed):
        raise ValueError('full-XI delta changed unrelated game/kit/manager/tactics files')
    from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players
    archive = (release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    original_archive = (base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    offsets = _active_offsets_for_players(original_archive,wrong_people)
    allowed_photo_bytes = {i for places in offsets.values() for i in places}
    if len(original_archive)!=len(archive) or any(a!=b and i not in allowed_photo_bytes for i,(a,b) in enumerate(zip(original_archive,archive))):
        raise ValueError('portrait suppression changed other photos or archive bytes')
    if any(_active_offsets_for_players(archive,wrong_people).values()) or any((release.game_path/p).exists() for p in removed):
        raise ValueError('wrong-person photograph remains active')
    eq = (release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(after,eq,package,countries,plan)!=after:
        raise ValueError('source repair is not idempotent')
    replayed, replay_changes = source.replay(after,eq,package,release.package_path,countries)
    if replayed != after or len(replay_changes)!=1:
        raise ValueError('durable source recipe replay differs')
    result.update(schema_version='pm99-original-TFF-independent-native-XI-readback-v1',
        season=season,release_id=release_id,source_release_id=base.release_id,
        source_plan_sha256=registry.sha256_file(saved),package_sha256=registry.sha256_file(release.package_path),
        JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        game_delta=diff, source_game_fingerprint=old_inventory['files_fingerprint'],
        current_game_fingerprint=new_inventory['files_fingerprint'],idempotence=True,durable_recipe_replay=True,
        scope=plan['scope'], secondary_fact_source_conflicts=plan['secondary_fact_source_conflicts'])
    pipeline.write_canonical_json(output,result)
    return result
