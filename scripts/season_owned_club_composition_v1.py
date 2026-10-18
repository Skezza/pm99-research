"""Compose a sourced replacement club with retained-person roster repairs.

Includes bounded materialisation and exact registered SOURCE reconstruction.
This is not a source-policy waiver: original proposals and retained fixture
bindings must be reviewed separately. Unaffected releases are not rebuilt.
"""
import copy
from datetime import date
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
from scripts import season_retained_native_transfer_v1 as transfer
from app.player_initial_order import OrderReplacement, read_initial_order, patch_owned_mode1_complete_orders
from scripts import season_verified_opening_roster_sources_v1 as sources
from scripts import prepare_duplicate_whole_club_native_v1 as whole
from scripts import prepare_duplicate_club_disposition_v1 as allocator
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline

PRIVATE_SCHEMA = 'pm99-private-retained-club-composition-candidate-v1'
PREFIX = 'retained-club-composition-'
REGISTERED_SCHEMA = 'pm99-native-retained-club-composition-delta-v1'
MODE = 'known-good-baseline-retained-club-composition-and-period-assets-v1'


def reject_factory_recipe(package):
    if any(row.get('id', '').startswith(PREFIX) for row in package.get('artifacts', [])):
        raise ValueError('retained-club recipe requires exact source reconstruction, not factory compilation')


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def original(path, digest):
    path = registry.ROOT / path
    if registry.sha256_file(path) != digest:
        raise ValueError('composition original source changed')
    return path


def bind_owned_order(package, club_id, owned):
    """Record the exact sourced order without adding/removing fixed carriers."""
    club = next(c for c in package['clubs'] if c['id'] == club_id)
    players = {p['carrier_id']: p for p in package['players'] if p['club_id'] == club_id}
    if (len(owned) != len(set(owned)) or set(owned) != set(players)
            or set(club['roster_player_ids']) != {p['id'] for p in players.values()}):
        raise ValueError('retained recipe order must cover exact owned roster')
    club['roster_player_ids'] = [players[carrier]['id'] for carrier in owned]


def sourced_keeper_role(payload, carrier, source_position):
    """Correct a proved keeper's inherited outfield role, and no other bytes."""
    if source_position != 'G':
        raise ValueError('keeper role correction requires a sourced goalkeeper')
    native, fields = transfer.read(payload, carrier)
    if fields['visible_position_code'] != whole.delta.compiler.POSITION['G']:
        raise ValueError('keeper role correction requires matching native broad position')
    if fields['fine_role_codes'] == [0, 98, 98, 98, 98, 98]:
        return bytes(payload), None
    end = native['name_end']
    result = bytearray(payload)
    result[end + 2:end + 8] = bytes((code + 1 if code != 98 else 0) ^ 0x61
                                  for code in [0, 98, 98, 98, 98, 98])
    _, observed = transfer.read(bytes(result), carrier)
    expected = dict(fields, fine_role_codes=[0, 98, 98, 98, 98, 98],
                    first_fine_role_code=0, primary_role_code=0)
    if observed != expected or result[:end + 2] != payload[:end + 2] or result[end + 8:] != payload[end + 8:]:
        raise ValueError('sourced keeper correction changed unrelated native fields')
    return bytes(result), dict(carrier_id=carrier, before_codes=fields['fine_role_codes'],
                              after_codes=observed['fine_role_codes'])


def materialise_private(base, proposal_path, retained_binding_path, request, output, *, input_overrides=None):
    """Save the existing bounded compilation, never register or promote it.

    Retain the complete transaction as a recipe artifact, including moved
    people, uncertainties and source bindings. This is an inspectable actual
    game candidate, NOT source clearance or a complete SOURCE reconstruction.
    All new game writes replace hardlinks atomically; the parent stays intact.
    """
    from scripts.season_art_transaction_v1 import atomic_bytes
    from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact

    output = Path(output)
    if output.is_symlink() or output.exists():
        raise ValueError('private composition output must be new and immutable')
    if not output.resolve().is_relative_to((registry.ROOT / '.local').resolve()):
        raise ValueError('private composition output must remain inside local workspace')
    if not output.resolve().is_relative_to(registry.ROOT.resolve()):
        raise ValueError('private composition output escaped workspace')
    if (output.resolve().is_relative_to(base.game_path.resolve())
            or base.game_path.resolve().is_relative_to(output.resolve())
            or output.resolve().is_relative_to(base.package_path.parent.resolve())):
        raise ValueError('private composition output overlaps protected parent')
    parent_inventory = pipeline.read_json_file(base.inventory_path)
    pipeline.assert_tree_matches_inventory(base.game_path, parent_inventory)
    package, files, proof = compile_preflight(base, proposal_path, retained_binding_path, request)
    if set(files) != {'JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF'}:
        raise ValueError('private composition has unexpected native write scope')
    generated = {}
    for composition in proof['compositions']:
        relative = whole.delta.plan_filename(composition)
        payload = pipeline.canonical_json_bytes(composition) + b'\n'
        if relative in generated and generated[relative] != payload:
            raise ValueError('conflicting generated composition artifacts')
        generated[relative] = payload
    transaction = dict(schema_version=PRIVATE_SCHEMA, season=base.season,
        parent_release_id=base.release_id,
        parent_package=binding(base.package_path), parent_manifest_sha256=base.manifest_sha256,
        whole_club_source=binding(proposal_path), retained_sources=binding(retained_binding_path),
        request=copy.deepcopy(request), retained_source_document=pipeline.read_json_file(retained_binding_path),
        whole_club_proposal=pipeline.read_json_file(proposal_path), compilation=proof,
        native_sha256={name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
        source_clearance=False, publication_approved=False,
        remaining=['independent source/identity review', 'ground and kit context',
                   'complete SOURCE replay', 'genuine runtime validation', 'release publication'])
    payload = pipeline.canonical_json_bytes(transaction) + b'\n'
    relative = PREFIX + hashlib.sha256(payload).hexdigest()[:24] + '.json'
    generated[relative] = payload
    package = copy.deepcopy(package)
    package['artifacts'].append(dict(id=relative[:-5], kind='season-input',
        sha256=hashlib.sha256(payload).hexdigest(), media_type='application/json', relative_path=relative))
    package['artifacts'].sort(key=lambda row: row['id'])
    whole.package_v2.validate_package(package)

    # Resolve every exact artifact before making any new directory. No broad
    # cache search and no acceptance of a same-name file from a newer delta.
    overrides = input_overrides or {}
    inputs = {}
    used = set()
    for artifact in package['artifacts']:
        name = artifact.get('relative_path')
        if not name:
            continue
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ValueError('unsafe private composition recipe artifact')
        if path.parts[0] in {'game', 'season-package.json', 'candidate-receipt.json'}:
            raise ValueError('recipe artifact overlaps private candidate output')
        if name in generated:
            if hashlib.sha256(generated[name]).hexdigest() != artifact['sha256']:
                raise ValueError('generated recipe artifact differs from declared hash')
            continue
        source = Path(overrides.get(name, base.package_path.parent / path))
        verify_recipe_artifact(source, artifact['sha256'])
        inputs[name] = (source, artifact['sha256'])
        if name in overrides:
            used.add(name)
    if set(overrides) != used:
        raise ValueError('unused private composition recipe override')
    predicted = sum(len(data) for data in files.values()) + sum(map(len, generated.values())) + 32 * 1024**2
    if shutil.disk_usage(base.game_path).free - predicted < 8 * 1024**3:
        raise ValueError('private composition would cross the 8-GiB reserve')
    parent_hashes = {name: registry.sha256_file(base.game_path / 'DBDAT' / name) for name in files}
    output.mkdir(parents=True)
    shutil.copytree(base.game_path, output / 'game', copy_function=os.link)
    for name, data in files.items():
        atomic_bytes(output / 'game/DBDAT' / name, data)
        if registry.sha256_file(output / 'game/DBDAT' / name) != transaction['native_sha256'][name]:
            raise ValueError('materialised native file differs from compiled candidate')
    for carrier in proof['changed_identity_carriers']:
        photo = output / 'game/DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        if photo.exists():
            photo.unlink()  # Only the new candidate's directory entry.
    pipeline.write_canonical_json(output / 'season-package.json', package)
    for name, data in generated.items():
        atomic_bytes(output / name, data)
    for name, (source, digest) in inputs.items():
        verify_recipe_artifact(source, digest)
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
    for artifact in package['artifacts']:
        if artifact.get('relative_path'):
            verify_recipe_artifact(output / artifact['relative_path'], artifact['sha256'])
    if any(registry.sha256_file(base.game_path / 'DBDAT' / name) != digest
           for name, digest in parent_hashes.items()):
        raise ValueError('parent changed during private composition materialisation')
    pipeline.assert_tree_matches_inventory(base.game_path, parent_inventory)
    receipt = dict(schema_version=PRIVATE_SCHEMA, season=base.season,
        source_release_id=base.release_id, parent_manifest_sha256=base.manifest_sha256,
        parent_inventory=binding(base.inventory_path), parent_inventory_verified=True,
        transaction_artifact=relative, transaction_sha256=hashlib.sha256(payload).hexdigest(),
        package_sha256=registry.sha256_file(output / 'season-package.json'),
        native_hashes=transaction['native_sha256'],
        changed_identity_carriers=proof['changed_identity_carriers'],
        native_files_written=True, registered=False, publication_authorised=False,
        runtime_verified=False, complete_SOURCE_replay_verified=False,
        remaining=transaction['remaining'])
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    return receipt


def verify_materialised(base, candidate):
    """Read actual files independently of the writer; never approve history."""
    from app.player_initial_order import read_initial_order
    from scripts import season_historical_roster_audit_v1 as audit
    from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact

    candidate = Path(candidate)
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    if (receipt.get('schema_version') != PRIVATE_SCHEMA or receipt.get('registered') is not False
            or receipt.get('publication_authorised') is not False
            or (receipt['season'], receipt['source_release_id'], receipt['parent_manifest_sha256'])
            != (base.season, base.release_id, base.manifest_sha256)):
        raise ValueError('private composition verification requires exact unpromoted parent')
    transaction_path = candidate / receipt['transaction_artifact']
    if registry.sha256_file(transaction_path) != receipt['transaction_sha256']:
        raise ValueError('private composition transaction changed')
    transaction = pipeline.read_json_file(transaction_path)
    package_path = candidate / 'season-package.json'
    if registry.sha256_file(package_path) != receipt['package_sha256']:
        raise ValueError('private composition recipe changed')
    package = pipeline.read_json_file(package_path)
    before = pipeline.read_json_file(base.package_path)
    for artifact in package['artifacts']:
        if artifact.get('relative_path'):
            verify_recipe_artifact(candidate / artifact['relative_path'], artifact['sha256'])
    for name, digest in receipt['native_hashes'].items():
        if registry.sha256_file(candidate / 'game/DBDAT' / name) != digest:
            raise ValueError('private composition native bytes changed')
    pipeline.assert_tree_matches_inventory(base.game_path, pipeline.read_json_file(base.inventory_path))
    difference = pipeline.inventory_difference(pipeline.read_json_file(base.inventory_path),
                                               pipeline.build_tree_inventory(candidate / 'game'))
    selected = set(receipt['changed_identity_carriers'])
    allowed_files = {'DBDAT/' + name for name in receipt['native_hashes']}
    removed = {f'DBDAT/MINIFOTO/J96{carrier:05d}.BMP' for carrier in selected}
    if (difference['only_right'] or set(difference['only_left']) - removed
            or any(row['path'] not in allowed_files for row in difference['changed'])):
        raise ValueError('private composition changed unrelated game files')
    proof = transaction['compilation']
    owned = proof['owned_order']
    proposal = transaction['whole_club_proposal']
    new_club_id = proposal['before_club']['id']
    retained_carrier = transaction['request']['retained_club_carrier_id']
    retained_id = next(c['id'] for c in before['clubs'] if c['carrier_id'] == retained_carrier)
    allowed_clubs = {new_club_id, retained_id}
    manager_id = next(c['manager_id'] for c in before['clubs'] if c['id'] == new_club_id)
    for collection, key, permitted in [('players', 'carrier_id', selected), ('clubs', 'id', allowed_clubs),
                                        ('managers', 'id', {manager_id})]:
        actual = {row[key]: row for row in package[collection]}
        if set(actual) != {row[key] for row in before[collection]} or any(
                actual[row[key]] != row for row in before[collection] if row[key] not in permitted):
            raise ValueError('private composition changed unrelated recipe ' + collection)
    raw = (candidate / 'game/DBDAT/JUG98030.FDI').read_bytes()
    eq = (candidate / 'game/DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in transfer.IndexedFDIFile.from_bytes(raw).entries}
    players = {p['carrier_id']: p for p in package['players']}
    countries = whole.delta.compiler._extract_country_codes_from_textos(candidate / 'game/DBDAT/TEXTOS.PKF')
    observations = []
    for carrier in sorted(selected):
        actor = players[carrier]
        native, fields = transfer.read(entries[carrier].decode_payload(raw), carrier)
        facts = actor['facts']
        birthday = date(fields['birth_year'], fields['birth_month'], fields['birth_day']).isoformat()
        expected_name = whole.delta.compiler._pm99_text(actor['name'], label='private native identity')
        if (audit.normalise(native['name']) != audit.normalise(expected_name)
                or birthday != facts['birth_date']
                or native['position'] != facts['primary_position']):
            raise ValueError('private native name/birthday/position differs from recipe: ' + str(carrier))
        for key in ('height_cm', 'weight_kg'):
            if isinstance(facts.get(key), int) and fields[key] != facts[key]:
                raise ValueError('private native body fact differs from recipe: ' + str(carrier))
        if isinstance(facts.get('nationality'), str) and fields['visible_nationality_code'] != whole.delta.compiler._country_code(facts['nationality'], countries):
            raise ValueError('private native nationality differs from recipe: ' + str(carrier))
        expected_skills = actor['ratings']['values']
        if dict(zip(whole.delta.compiler.SKILLS, fields['skills']), handling=fields['handling']) != expected_skills:
            raise ValueError('private native ten skills differ from recipe: ' + str(carrier))
        fine = facts.get('fine_roles')
        if isinstance(fine, list) and fields['fine_role_codes'] != fine + [98] * (6 - len(fine)):
            raise ValueError('private native explicit fine roles differ from recipe: ' + str(carrier))
        if any(audit.role_conflict(facts['primary_position'], code) for code in fields['fine_role_codes']):
            raise ValueError('private native broad/fine role conflict: ' + str(carrier))
        observations.append(dict(carrier_id=carrier, name=native['name'], birth_date=birthday,
                                 position=native['position'], fine_roles=fields['fine_role_codes'],
                                 ten_skills_match_recipe=True))
    retained = next(c for c in package['clubs'] if c['id'] == retained_id)
    if retained['roster_player_ids'] != [players[c]['id'] for c in owned] or any(
            read_initial_order(entries[c].decode_payload(raw)).order != order for order, c in enumerate(owned, 1)):
        raise ValueError('retained recipe/native opening order differs')
    old_retained = copy.deepcopy(next(c for c in before['clubs'] if c['id'] == retained_id))
    old_retained['roster_player_ids'] = retained['roster_player_ids']
    if retained != old_retained:
        raise ValueError('retained club changed beyond exact opening order')
    new_club = next(c for c in package['clubs'] if c['id'] == new_club_id)
    old_new_club = next(c for c in before['clubs'] if c['id'] == new_club_id)
    new_club_fields = {'name', 'full_name', 'identity_id', 'roster_player_ids', 'proof'}
    allocation = {row['replacement']['source_person']['source_player_id']: row['player_id']
                  for row in proposal['allocation']}
    expected_roster = [allocation[row['source_person']['source_player_id']] for row in proposal['desired_people']]
    if (new_club['name'] != proposal['new_club'] or new_club['full_name'] != proposal['new_club']
            or new_club['identity_id'] != whole.builder._source_club_identity_id('england', proposal['new_club'])
            or new_club['roster_player_ids'] != expected_roster
            or {k: v for k, v in new_club.items() if k not in new_club_fields}
            != {k: v for k, v in old_new_club.items() if k not in new_club_fields}):
        raise ValueError('replacement club recipe differs from complete source allocation')
    eq_index = {e.record_id: e for e in transfer.IndexedFDIFile.from_bytes(eq).entries}
    by_id = {p['id']: p for p in package['players']}
    for club in (retained, new_club):
        entry = eq_index[club['carrier_id']]
        roster = whole.parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        expected = [by_id[id]['carrier_id'] for id in club['roster_player_ids']]
        if (roster is None or roster.mode_byte != 1 or len(roster.rows) != len(expected)
                or {r.player_record_id for r in roster.rows} != set(expected)
                or roster.short_name != club['name'] or roster.full_club_name != club['full_name']):
            raise ValueError('actual native club identity/owned roster differs from recipe')
        if club['id'] == new_club_id and [r.player_record_id for r in roster.rows] != expected:
            raise ValueError('replacement native roster order differs from source')
    manager = next(m for m in package['managers'] if m['id'] == manager_id)
    old_manager = next(m for m in before['managers'] if m['id'] == manager_id)
    manager_proof = proof['manager']
    short, _ = whole.manager_display.short_name(manager_proof['name'])
    native_names = dict(surname=short, display_name=short)
    manager_fields = {'name', 'person_id', 'policy', 'native_names', 'proof'}
    if (manager['name'] != manager_proof['name']
            or manager['person_id'] != 'manager-soccerbase-' + str(manager_proof['source_person_id'])
            or manager['carrier_id'] != manager_proof['carrier_id'] or manager['policy'] != 'write'
            or manager['native_names'] != native_names or short is None
            or {k: v for k, v in manager.items() if k not in manager_fields}
            != {k: v for k, v in old_manager.items() if k not in manager_fields}):
        raise ValueError('replacement manager recipe differs from dated source')
    holders, displays = whole._manager_graph(eq_path=candidate / 'game/DBDAT/EQ98030.FDI',
                                            ent_path=candidate / 'game/DBDAT/ENT98030.FDI')
    if (displays.get(manager['carrier_id']) != short
            or [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])] != [new_club['carrier_id']]):
        raise ValueError('replacement native manager display/sole owner differs from source')
    whole.preserve_other_records((base.game_path / 'DBDAT/JUG98030.FDI').read_bytes(), raw, selected | set(owned))
    whole.preserve_other_records((base.game_path / 'DBDAT/EQ98030.FDI').read_bytes(), eq, {proposal['before_club']['carrier_id']})
    whole.preserve_other_records((base.game_path / 'DBDAT/ENT98030.FDI').read_bytes(),
        (candidate / 'game/DBDAT/ENT98030.FDI').read_bytes(), {proof['manager']['carrier_id']})
    archive = (candidate / 'game/DBDAT/MINIFOTO.PKF').read_bytes()
    cleared, _ = whole.delta.no_photo_archive(archive, selected)
    if cleared != archive or any((candidate / 'game/DBDAT/MINIFOTO' / f'J96{c:05d}.BMP').exists() for c in selected):
        raise ValueError('private composition retains a stale identity portrait')
    return dict(schema_version=PRIVATE_SCHEMA + '-native-readback', season=base.season,
        candidate_receipt=binding(candidate / 'candidate-receipt.json'), observations=observations,
        clubs=[dict(carrier_id=c['carrier_id'], name=c['name'], roster_count=len(c['roster_player_ids']))
               for c in (retained, new_club)], manager=manager_proof,
        retained_order=owned, exact_parent_inventory_verified=True,
        unrelated_recipe_rows_and_native_records_preserved=True, unrelated_game_files_preserved=True,
        stale_portraits_cleared=True, source_clearance=False, runtime_verified=False,
        complete_SOURCE_replay_verified=False, publication_approved=False)


def replay_materialised(base, candidate):
    """Recompile the saved transaction against its exact immutable parent.

    No second game tree or release is created. This proves the bounded recipe
    and native delta, not a clean-machine reconstruction of its parent chain.
    """
    candidate = Path(candidate)
    verified = verify_materialised(base, candidate)
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    transaction = pipeline.read_json_file(candidate / receipt['transaction_artifact'])
    proposal_path = original(transaction['whole_club_source']['path'], transaction['whole_club_source']['sha256'])
    retained_path = original(transaction['retained_sources']['path'], transaction['retained_sources']['sha256'])
    if (pipeline.read_json_file(proposal_path) != transaction['whole_club_proposal']
            or pipeline.read_json_file(retained_path) != transaction['retained_source_document']
            or binding(base.package_path) != transaction['parent_package']):
        raise ValueError('saved composition source document/parent differs')
    expected, files, proof = compile_preflight(base, proposal_path, retained_path, transaction['request'])
    actual = pipeline.read_json_file(candidate / 'season-package.json')
    descriptors = [a for a in actual['artifacts'] if a.get('relative_path') == receipt['transaction_artifact']]
    if len(descriptors) != 1:
        raise ValueError('saved composition transaction descriptor is missing/ambiguous')
    actual['artifacts'].remove(descriptors[0])
    if (pipeline.canonical_json_bytes(actual) != pipeline.canonical_json_bytes(expected)
            or pipeline.canonical_json_bytes(proof) != pipeline.canonical_json_bytes(transaction['compilation'])):
        raise ValueError('saved composition recipe/proof does not exactly replay')
    if set(files) != set(receipt['native_hashes']) or any(
            payload != (candidate / 'game/DBDAT' / name).read_bytes() for name, payload in files.items()):
        raise ValueError('saved composition actual native files do not exactly replay')
    return dict(schema_version=PRIVATE_SCHEMA + '-incremental-replay', season=base.season,
        candidate_receipt=binding(candidate / 'candidate-receipt.json'),
        parent_manifest_sha256=base.manifest_sha256,
        saved_transaction_recipe_identical=True, saved_transaction_native_files_identical=True,
        native_file_sha256=receipt['native_hashes'], changed_identity_count=len(verified['observations']),
        writes_performed=False, clean_machine_parent_reconstruction=False,
        complete_SOURCE_replay_verified=False, runtime_verified=False, publication_approved=False)


def replay_asset_materialised(base, candidate):
    """Replay saved native operations and offline artwork without promotion."""
    from scripts import prepare_paired_club_assets_v1 as assets
    from scripts.season_paired_whole_club_reconstruction_v1 import replay_assets

    candidate = Path(candidate)
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    if receipt.get('schema_version') != PRIVATE_SCHEMA or not receipt.get('paired_asset_stage'):
        raise ValueError('retained artwork replay requires a bound asset stage')
    source = original(receipt['source_native_candidate']['path'] + '/candidate-receipt.json',
                      receipt['source_native_candidate']['sha256']).parent
    native_proof = replay_materialised(base, source)
    for name, digest in receipt['native_hashes'].items():
        if registry.sha256_file(candidate / 'game/DBDAT' / name) != digest:
            raise ValueError('asset candidate native content changed')
    with tempfile.TemporaryDirectory(prefix='retained-assets-replay-', dir=registry.ROOT / '.local') as temporary:
        root = Path(temporary)
        specs = replay_assets(source, receipt, candidate, root / 'assets')
        replayed = root / 'complete'
        assets.prepare(source, root / 'assets', replayed, ground_specs=specs)
        expected = pipeline.build_tree_inventory(candidate / 'game')
        pipeline.assert_tree_matches_inventory(replayed / 'game', expected)
        if (pipeline.canonical_json_bytes(pipeline.read_json_file(replayed / 'season-package.json'))
                != pipeline.canonical_json_bytes(pipeline.read_json_file(candidate / 'season-package.json'))):
            raise ValueError('retained artwork replay changed the recipe')
    return dict(schema_version=PRIVATE_SCHEMA + '-native-and-artwork-replay', season=base.season,
        candidate_receipt=binding(candidate / 'candidate-receipt.json'), native_transaction=native_proof,
        offline_kit_rerender=True, exact_ground_row_replayed=True,
        complete_candidate_game_inventory_identical=True, complete_candidate_recipe_identical=True,
        clean_machine_parent_reconstruction=False, complete_SOURCE_replay_verified=False,
        runtime_verified=False, publication_approved=False)


def verify_identity_difference(base, candidate):
    """Use the existing pinned cross-club key, never invent a new denominator."""
    from scripts import verify_paired_club_identity_v1 as identities
    from scripts import season_whole_club_keeper_exchange_v1 as keeper

    candidate = Path(candidate)
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    if receipt.get('schema_version') != PRIVATE_SCHEMA:
        raise ValueError('identity review requires a retained composition receipt')
    transaction_path = candidate / receipt['transaction_artifact']
    if registry.sha256_file(transaction_path) != receipt['transaction_sha256']:
        raise ValueError('identity review has a changed retained transaction')
    transaction = pipeline.read_json_file(transaction_path)
    if (receipt['season'], receipt['source_release_id'], receipt['parent_manifest_sha256']) != (
            base.season, base.release_id, base.manifest_sha256):
        raise ValueError('identity review must use the exact retained parent')
    if binding(base.package_path) != transaction['parent_package']:
        raise ValueError('identity review parent recipe changed')
    supplement = transaction['whole_club_proposal']['bindings']['published_person_supplement']
    person_path = original(supplement['path'], supplement['sha256'])
    people, snapshot = identities.identities.load_identity_snapshot()
    people, _ = identities.public.merge(people, pipeline.read_json_file(person_path))
    before = pipeline.read_json_file(base.package_path)
    after = pipeline.read_json_file(candidate / 'season-package.json')
    if registry.sha256_file(candidate / 'season-package.json') != receipt['package_sha256']:
        raise ValueError('identity review recipe changed')
    old, new = identities.groups(before, people), identities.groups(after, people)
    selected = set(receipt['changed_identity_carriers'])
    if new.keys() - old.keys():
        raise ValueError('retained composition introduced cross-club identity candidates')
    if any(any(carrier in selected for carrier, _ in rows) for rows in new.values()):
        raise ValueError('retained composition replacement still has an outside copy')
    by = {p['carrier_id']: p for p in after['players']}
    if set(by) != {p['carrier_id'] for p in before['players']} or any(
            by[p['carrier_id']] != p for p in before['players'] if p['carrier_id'] not in selected):
        raise ValueError('identity review found unrelated recipe player changes')
    jug = (candidate / 'game/DBDAT/JUG98030.FDI').read_bytes()
    eq = (candidate / 'game/DBDAT/EQ98030.FDI').read_bytes()
    replayed, _ = keeper.replay(jug, eq, after, candidate / 'season-package.json')
    if replayed != jug:
        raise ValueError('retained candidate keeper-order recipe replay is not idempotent')
    archive = (candidate / 'game/DBDAT/MINIFOTO.PKF').read_bytes()
    cleared, _ = whole.delta.no_photo_archive(archive, selected)
    if cleared != archive or any((candidate / 'game/DBDAT/MINIFOTO' / f'J96{c:05d}.BMP').exists() for c in selected):
        raise ValueError('retained identity review found a stale portrait')
    return dict(schema_version=PRIVATE_SCHEMA + '-identity-difference', season=base.season,
        candidate_receipt_sha256=registry.sha256_file(candidate / 'candidate-receipt.json'),
        package_sha256=registry.sha256_file(candidate / 'season-package.json'),
        identity_snapshot=snapshot, person_input=binding(person_path),
        before_cross_club_candidate_groups=len(old), after_cross_club_candidate_groups=len(new),
        removed_candidate_groups=len(old.keys() - new.keys()), introduced_candidate_groups=0,
        replacement_cross_club_candidates=0, unselected_recipe_players_identical=True,
        corrected_slots=sorted(selected), keeper_recipe_replay_idempotent=True,
        stale_portraits_cleared=True,
        frozen_baseline_changed=False, registered=False, publication_approved=False)


def reconstruction(previous, release_id):
    """Registered SOURCE entry point for this typed, complete transaction."""
    from scripts import prepare_paired_club_assets_v1 as assets
    from scripts.season_paired_whole_club_reconstruction_v1 import replay_assets
    from scripts import publish_paired_whole_club_delta_v1 as publisher

    if getattr(previous, 'compiler_receipt_path', None) is None:
        return None
    compiler = pipeline.read_json_file(previous.compiler_receipt_path)
    if compiler.get('schema') != REGISTERED_SCHEMA or compiler.get('compilation_mode') != MODE:
        return None
    if registry.canonical_document_sha256(previous.package_path) != compiler['season_package_sha256']:
        raise ValueError('edited retained recipe cannot use exact SOURCE reconstruction; no edits discarded')
    path = original(previous.locator['retained_club_composition_candidate_receipt_path'],
                    previous.locator['retained_club_composition_candidate_receipt_sha256'])
    if registry.sha256_file(path) != compiler['candidate_receipt_sha256']:
        raise ValueError('registered retained SOURCE receipt changed')
    receipt = pipeline.read_json_file(path)
    transaction_path = original(registry.relative_workspace_path(path.parent / receipt['transaction_artifact']),
                                receipt['transaction_sha256'])
    transaction = pipeline.read_json_file(transaction_path)
    base = registry.load_registered_release(previous.season, receipt['source_release_id'])
    if base.manifest_sha256 != receipt['parent_manifest_sha256']:
        raise ValueError('registered retained SOURCE parent manifest changed')
    proposal_path = original(transaction['whole_club_source']['path'], transaction['whole_club_source']['sha256'])
    retained_path = original(transaction['retained_sources']['path'], transaction['retained_sources']['sha256'])
    source_replay = original(compiler['original_source_replay']['path'], compiler['original_source_replay']['sha256'])
    root = registry.ROOT / '.local/retained-club-replays-v1' / previous.season / release_id
    if root.exists() or registry.locator_path(previous.season, release_id).parent.exists():
        raise ValueError('retained SOURCE reconstruction output already exists')
    pipeline.assert_tree_matches_inventory(previous.game_path, pipeline.read_json_file(previous.inventory_path))
    materialise_private(base, proposal_path, retained_path, transaction['request'], root / 'native')
    specs = replay_assets(root / 'native', receipt, path.parent, root / 'assets')
    completed = root / 'complete'
    assets.prepare(root / 'native', root / 'assets', completed, ground_specs=specs)
    pipeline.assert_tree_matches_inventory(completed / 'game', pipeline.read_json_file(previous.inventory_path))
    if (pipeline.canonical_json_bytes(pipeline.read_json_file(completed / 'season-package.json'))
            != pipeline.canonical_json_bytes(pipeline.read_json_file(previous.package_path))):
        raise ValueError('retained SOURCE reconstruction recipe differs')
    native_proof = root / 'native-and-assets-proof.json'
    identity_proof = root / 'identity-proof.json'
    pipeline.write_canonical_json(native_proof, replay_asset_materialised(base, completed))
    pipeline.write_canonical_json(identity_proof, verify_identity_difference(base, completed))
    publisher.publish(completed, native_proof, identity_proof, release_id,
                      source_release_id=base.release_id, retained_source_replay_path=source_replay)
    return dict(season=previous.season, release_id=release_id, source_release_id=base.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode=MODE, clean_machine_parent_reconstruction=False)


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
    # Identity preservation must not bless an already-wrong outfield role on
    # a source-proved goalkeeper. Keep this explicit and separate from moves.
    fine_role_corrections = []
    keeper_patches = {}
    entries = {e.record_id: e for e in transfer.IndexedFDIFile.from_bytes(jug).entries}
    for extra in request.get('additional_moves', []):
        _, source_facts, _ = sources.profile(extra['profile_binding'], extra['provider_player_id'])
        dest = extra['destination_carrier']
        if source_facts.get('position') != 'G' or by[dest]['facts']['primary_position'] != 'G':
            continue
        payload, correction = sourced_keeper_role(entries[dest].decode_payload(jug), dest, 'G')
        if correction is not None:
            correction['source_profile'] = extra['profile_binding']
            correction['provider_player_id'] = extra['provider_player_id']
            fine_role_corrections.append(correction)
            keeper_patches[dest] = payload
            by[dest]['facts']['fine_roles'] = [0]
            by[dest]['fact_fallbacks'] = [f for f in by[dest].get('fact_fallbacks', []) if f['field'] != 'fine_roles']
    if keeper_patches:
        jug = whole.delta.compiler._rebuild_indexed(jug, transfer.IndexedFDIFile.from_bytes(jug), keeper_patches)
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
    bind_owned_order(result, club['id'], owned)
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
        sourced_keeper_fine_role_corrections=fine_role_corrections,
        changed_identity_carriers=sorted(identity_carriers), photo_offsets=photo_offsets,
        manager=dict(name=name, source_person_id=manager_person, carrier_id=manager['carrier_id']),
        native_files_written=False, publication_approved=False,
        remaining='Ground/kit application, final source/identity audit, runtime and publication not performed.')
