"""Compile one foreign source transaction in memory, never install it.

The native APIs are unchanged. This orchestration independently repeats the
original-source allocation, composes Serbian recipe identities, and verifies
all unrelated native records. Until kit/tactics/runtime/reconstruction are
closed, the result is explicitly private and cannot count as a release.
"""
import copy
import hashlib
import tempfile
from pathlib import Path

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_source_package_builder_v1 as builder
from scripts import season_package_v2 as packages
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _patch_indexed_eq_team_string_payload
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders

SCHEMA = 'pm99-private-source-bound-foreign-native-candidate-v1'


def compose_recipe(package, proposal):
    club, slots = native.validate_allocation(package, proposal)
    copied = copy.deepcopy(package)
    target = next(c for c in copied['clubs'] if c['id'] == club['id'])
    target.update(name=proposal['new_club'], full_name=proposal['new_club'],
        identity_id=builder._source_club_identity_id(proposal['country'], proposal['new_club']))
    day = proposal['first_fixture']['date']
    composition = dict(season=proposal['season'], source_title=proposal.get('source_title', 'Original OFK domestic opening XI and positive dated reserves'),
        bindings={'snapshot': {'project_url': 'https://www.transfermarkt.co.uk/'}},
        foreign_original_source=proposal,
        proof_covers=['original-target-club-first-XI', 'positive-dated-opening-reserves', f'fixed{len(slots)}-source-identities'],
        updates=[dict(player_id=r['player_id'], carrier_id=r['carrier_id'], layer='main',
            before=r['before_recipe'], replacement=r['replacement'],
            replacement_opening_evidence={'date': day}) for r in proposal['allocation']])
    if proposal.get('source_fallback'):
        composition['proof_covers'] = ['published-August-cup-XI-not-first-league-XI',
            'published-August-friendly-additions', f'fixed{len(slots)}-source-identities']
    if proposal.get('schema_version') == 'pm99-private-original-monagas2003-verified-inputs-v1':
        composition['proof_covers'] = ['published-August-cup-XI-not-first-league-XI',
            'positive-adjoining-July31-opening-actors', 'explicit-unpublished-secondary-DOBs',
            f'fixed{len(slots)}-distinct-publisher-identities']
    if proposal.get('schema_version') == 'pm99-private-original-sartid2000-verified-inputs-v1':
        composition['proof_covers'] = ['original-August-round2-XI-not-first-league-XI',
            'original-August-used-substitutes', 'positive-dated-August-reserves',
            'fixed18-distinct-publisher-identities']
    if proposal.get('schema_version') == 'pm99-private-original-estudiantes2000-verified-inputs-v1':
        composition['proof_covers']=['published-August-cup-XI-not-first-league-XI',
            'original-published-used-and-unused-cup-bench',
            'explicit-unresolved-Javier-Gomez-identity-and-native-date-fallback',
            'fixed16-distinct-source-actors']
    if proposal.get('schema_version') == 'pm99-private-original-mladost2001-verified-inputs-v1':
        composition['proof_covers']=['original-August-round2-XI-not-first-league-XI',
            'original-used-substitutes-and-four-positive-dated-reserves',
            'eight-unresolved-published-surname-actors-with-native-date-fallback',
            'fixed18-distinct-source-actors']
    if proposal.get('schema_version') == 'pm99-private-original-monagas2002-verified-inputs-v1':
        composition['proof_covers'] = ['published-August-cup-XI-not-first-league-XI',
            'original-August-used-and-unused-substitutes', 'explicit-unpublished-secondary-DOBs',
            f'fixed{len(slots)}-distinct-publisher-identities']
    if proposal.get('published_surname_fallback'):
        composition['proof_covers']=['original-first-league-XI-and-positive-opening-reserves',
            'explicit-published-surname-actor-first-name-and-DOB-unavailable', f'fixed{len(slots)}-distinct-source-actors']
    result = delta.updated_package(copied, composition)
    from scripts import prepare_borac_2003_verified_inputs_v1 as borac_inputs
    if proposal.get('secondary_fact_review', {}).get('policy') == borac_inputs.STABLE_SKILLS_POLICY:
        if proposal.get('schema_version') != 'pm99-private-original-borac2003-verified-inputs-v1':
            raise ValueError('stable physical defaults require the Borac source adapter')
        rating_composition = copy.deepcopy(composition)
        for row in rating_composition['updates']:
            row['replacement']['source_player']['height_cm'] = None
            row['replacement']['source_player']['weight_kg'] = None
        original_ratings = delta.updated_package(copied, rating_composition)
        original_by_id = {p['id']: p for p in original_ratings['players']}
        for player in result['players']:
            if player['id'] in slots:
                player['ratings']['values'] = copy.deepcopy(original_by_id[player['id']]['ratings']['values'])
    players = {p['id']: p for p in result['players']}
    assigned = {}
    for row in proposal['allocation']:
        players[row['player_id']]['name'] = row['display']['display_name']
        assigned[row['replacement']['source_person']['source_player_id']] = row['player_id']
    target = next(c for c in result['clubs'] if c['id'] == club['id'])
    target['roster_player_ids'] = [assigned[r['source_person']['source_player_id']] for r in proposal['desired_people']]
    artifact = next(a for a in result['artifacts'] if a.get('relative_path') == delta.plan_filename(composition))
    target['proof'] = dict(artifact_id=artifact['id'], grade='source-receipt')
    return result, composition, slots


def compile_files(release, proposal, package, *, original_dated=None):
    result, composition, slots = compose_recipe(package, proposal)
    if original_dated is None:
        raw, report_binding = source.original('ofk-first-fixture-2004-3142214')
        dated = source.dated_manager_ground(raw)
        manager_names = dict(surname='Babic', display_name='Babic')
        artifact = 'ofk-original-manager-ground-2004'
        report_relative = 'ofk-original-opening.html'
        manager_person_id = 'manager-transfermarkt-4219'
    else:
        dated = copy.deepcopy(original_dated['dated'])
        report_binding = original_dated['report_binding']
        manager_names = copy.deepcopy(original_dated['manager_native_names'])
        artifact = original_dated['artifact_id']
        report_relative = original_dated['relative_path']
        manager_person_id = original_dated['manager_person_id']
        if (dated['date'] != proposal['first_fixture']['date']
                or dated['source_club_id'] != proposal['transfermarkt_club_id']
                or registry.sha256_file(registry.ROOT / report_binding['path']) != report_binding['sha256']):
            raise ValueError('foreign dated original input differs from source allocation')
    carrier = proposal['before_club']['carrier_id']
    before = {name: (release.game_path / 'DBDAT' / name).read_bytes()
        for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF')}
    codes = delta.compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
    jug = delta.compile_players(before['JUG98030.FDI'], result, set(slots), codes)
    target = next(c for c in result['clubs'] if c['id'] == proposal['before_club']['id'])
    by_id = {p['id']: p for p in result['players']}
    ordered = [by_id[id]['carrier_id'] for id in target['roster_player_ids']]
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    orders = []
    for n, id in enumerate(ordered, 1):
        field = read_initial_order(entries[id].decode_payload(jug))
        orders.append(OrderReplacement(id, field.name, field.order, n))
    jug = patch_owned_mode1_complete_orders(jug, before['EQ98030.FDI'],
        club_record_id=carrier, replacements=orders)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    if [read_initial_order(entries[id].decode_payload(jug)).order for id in ordered] != list(range(1, len(slots) + 1)):
        raise ValueError('foreign complete source order did not survive native readback')
    eq = native.rewrite_roster(before['EQ98030.FDI'], carrier, ordered)
    index = IndexedFDIFile.from_bytes(eq)
    entry = next(e for e in index.entries if e.record_id == carrier)
    changed, fields = _patch_indexed_eq_team_string_payload(entry.decode_payload(eq),
        short_name=proposal['new_club'], full_club_name=proposal['new_club'], stadium_name=dated['ground'])
    if set(fields) != {'name', 'stadium', 'full_club_name'}:
        raise ValueError('foreign identity changed an unexpected team field')
    eq = delta.compiler._rebuild_indexed(eq, index, {carrier: changed})
    holders, _ = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    manager = next(m for m in result['managers'] if m['id'] == target['manager_id'])
    mid = manager['carrier_id']
    if [c['carrier_id'] for c in holders.get(mid, [])] != [carrier]:
        raise ValueError('target foreign coach does not have exclusive native ownership')
    ent_index = IndexedFDIFile.from_bytes(before['ENT98030.FDI'])
    ent_entry = next(e for e in ent_index.entries if e.record_id == mid)
    patched = delta.compiler._patch_ent_name(ent_entry.decode_payload(before['ENT98030.FDI']), mid,
        dated['manager'], native_names=manager_names)
    ent = delta.compiler._rebuild_indexed(before['ENT98030.FDI'], ent_index, {mid: patched})
    manager.update(name=dated['manager'], policy='write', native_names=manager_names,
        person_id=manager_person_id, proof={'artifact_id': artifact, 'grade': 'source-receipt'})
    target.update(ground_policy='write', ground_name=dated['ground'])
    result['artifacts'].append(dict(id=artifact, kind='season-input', relative_path=report_relative,
        sha256=report_binding['sha256'], media_type=(original_dated or {}).get('media_type','text/html')))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    photo, offsets = delta.no_photo_archive(before['MINIFOTO.PKF'], set(ordered))
    after = dict(zip(('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF'), (jug, eq, ent, photo)))
    for name, allowed in [('JUG98030.FDI', set(ordered)), ('EQ98030.FDI', {carrier}), ('ENT98030.FDI', {mid})]:
        native.preserve_other_records(before[name], after[name], allowed)
    before_index = IndexedFDIFile.from_bytes(before['JUG98030.FDI'])
    after_index = IndexedFDIFile.from_bytes(jug)
    if [(e.record_id, e.payload_offset, e.payload_length) for e in before_index.entries] != [
            (e.record_id, e.payload_offset, e.payload_length) for e in after_index.entries]:
        raise ValueError('foreign player compilation moved fixed native record windows')
    return result, composition, before, after, dict(dated_manager_ground=dated,
        ordered_source_player_ids=[r['source_person']['source_player_id'] for r in proposal['desired_people']],
        ordered_native_carriers=ordered, removed_portrait_carriers=sorted(offsets),
        manager_native_names=manager_names, manager_carrier_id=mid)


def prepare(output, *, proposal_path=None):
    if output.exists(): raise ValueError('foreign native candidate is immutable')
    proposal_path = proposal_path or source.AUDIT / 'ofk-2004-fixed18-private-allocation-v1.json'
    proposal = pipeline.read_json_file(proposal_path)
    with tempfile.TemporaryDirectory(prefix='pm99-ofk-replay-') as temporary:
        replayed = source.prepare(Path(temporary) / 'allocation.json',
            secondary_facts=bool(proposal.get('secondary_fact_review')),
            baseline_release_id=proposal['baseline_release_id'])
        if replayed != proposal: raise ValueError('foreign original allocation cannot be independently replayed')
    release = registry.load_registered_release('2004-05', proposal['baseline_release_id'])
    if release.release_id != proposal['baseline_release_id'] or registry.sha256_file(
            release.package_path) != proposal['baseline_package']['sha256']:
        raise ValueError('foreign source allocation baseline changed')
    if not registry.validate_preferred_release('2004-05', level='playable')['valid']:
        raise ValueError('preferred baseline failed its immutable game checks')
    package = pipeline.read_json_file(release.package_path)
    recipe, composition, before, after, details = compile_files(release, proposal, package)
    # Independent deterministic composition/readback, not output-file copying.
    repeated = compile_files(release, replayed, pipeline.read_json_file(release.package_path))
    if (recipe, composition, before, after, details) != repeated:
        raise ValueError('foreign native transaction is not deterministic')
    if registry.sha256_file(release.package_path) != proposal['baseline_package']['sha256'] or any(
            (release.game_path / 'DBDAT' / n).read_bytes() != raw for n, raw in before.items()):
        raise ValueError('foreign immutable baseline changed during compilation')
    output.mkdir(parents=True)
    for name, data in after.items(): atomic_bytes(output / 'DBDAT' / name, data)
    pipeline.write_canonical_json(output / 'season-package.json', recipe)
    pipeline.write_canonical_json(output / delta.plan_filename(composition), composition)
    proof = dict(schema_version=SCHEMA, season='2004-05', baseline_release_id=release.release_id,
        source_proposal_sha256=registry.sha256_file(proposal_path), fixed_slots=18,
        original_source_allocation_replayed_exactly=True, repeated_native_and_recipe_composition_exact=True,
        unrelated_native_records_byte_identical=True, fixed_player_windows_preserved=True,
        **details, baseline_hashes={n: hashlib.sha256(raw).hexdigest() for n, raw in before.items()},
        native_hashes={n: hashlib.sha256(raw).hexdigest() for n, raw in after.items()},
        registered=False, historical_release=False, publication_authorised=False,
        duplicate_case_closed=False, game_tree_materialized=False,
        remaining=['period kit source/design', 'tactical deployment', 'typed release reconstruction',
            'runtime actual club/player/kit proof', 'fresh normal startup and promotion'])
    pipeline.write_canonical_json(output / 'native-proof.json', proof)
    return proof


if __name__ == '__main__':
    prepare(source.AUDIT / 'ofk-2004-private-native-v1')
