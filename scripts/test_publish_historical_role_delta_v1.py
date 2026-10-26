import copy
import json
from types import SimpleNamespace

import pytest
from scripts import publish_historical_role_delta_v1 as publish
from scripts.test_season_package_compiler_v2 import _native_package, _dd6361_player_payload, _indexed_fdi, _manager_payload


def plan_for(package):
    player = package['players'][1]
    return {'season': '2014-15', 'updates': [{'player_id': player['id'], 'carrier_id': player['carrier_id'],
        'name': player['name'], 'birth_date': player['facts']['birth_date'], 'fine_roles': [11],
        'provenance': {'method': 'synthetic-dated-role-test'}}], 'unresolved': []}


def test_only_declared_recipe_roles_and_proof_binding_change():
    package = _native_package()
    before = copy.deepcopy(package)
    result = publish.updated_package(package, plan_for(package))
    assert package == before
    assert result['players'][1]['facts']['fine_roles'] == [11]
    result['players'][1]['facts']['fine_roles'] = before['players'][1]['facts']['fine_roles']
    for key in package.keys() - {'artifacts', 'proofs'}:
        assert result[key] == before[key]


def test_role_plan_identity_and_whole_record_preservation_are_enforced():
    package = _native_package()
    plan = plan_for(package)
    plan['updates'][0]['birth_date'] = '2001-01-01'
    with pytest.raises(ValueError, match='identity'):
        publish.updated_package(package, plan)
    plan = plan_for(package)
    package['players'][1]['policy'] = 'preserve-existing-mode1'
    with pytest.raises(ValueError, match='whole-record'):
        publish.updated_package(package, plan)


def test_empty_delta_does_not_replace_the_historical_role_input():
    package=_native_package()
    previous=publish.updated_package(package,plan_for(package))
    empty=plan_for(previous);empty['updates']=[]
    assert publish.updated_package(previous,empty)==previous


def test_derived_keeper_proof_is_labelled_editorial_consistency():
    package = _native_package()
    package['players'][1]['facts']['primary_position'] = 'G'
    plan = plan_for(package)
    plan.update(policy='declared-and-native-G-preserved-fine-role-to-keeper-zero-v1',
                proof_grade='reviewed-editorial')
    plan['updates'][0]['fine_roles'] = [0]
    result = publish.updated_package(package, plan)
    proof = next(p for p in result['proofs'] if p['id']=='proof-historical-roles-2014-15')
    assert proof['grade'] == 'reviewed-editorial'
    assert proof['covers'] == ['declared-native-goalkeeper-position-consistency']


@pytest.mark.parametrize('canonical,surname', [('Luigi Del Neri', 'Del Neri'),
                                              ('Stefano Colantuono', 'Colantuono')])
def test_manager_identity_change_refreshes_existing_native_aliases(canonical, surname):
    package = _native_package()
    manager = package['managers'][0]
    manager['native_names'] = {'surname': manager['name'], 'display_name': manager['name']}
    # An earlier season-wide manager source must survive this one-person update.
    inherited = copy.deepcopy(package['artifacts'][0])
    inherited.update(id='historical-manager-plan-2014-15', relative_path='manager-plan.json')
    package['artifacts'].append(inherited)
    club = next(c for c in package['clubs'] if c['manager_id'] == manager['id'])
    before = copy.deepcopy(package)
    control = {'season': '2014-15', 'updates': []}
    plan = {'updates': [{'club_id': club['id'], 'manager_id': manager['id'],
                        'club_carrier_id': club['carrier_id'], 'carrier_id': manager['carrier_id'],
                        'before': manager['name'], 'before_policy': manager.get('policy'),
                        'after': canonical, 'native_after': surname}]}
    result = publish.updated_package(package, control, manager_plan=plan)
    assert package == before
    assert result['managers'][0]['native_names'] == {'surname': surname, 'display_name': surname}
    assert next(a for a in result['artifacts'] if a['id'] == inherited['id']) == inherited
    new_proof = result['managers'][0]['proof']['artifact_id']
    assert new_proof != inherited['id']
    assert next(a for a in result['artifacts'] if a['id'] == new_proof)['relative_path'].startswith('manager-update-')
    for key in package.keys() - {'managers', 'artifacts', 'proofs'}:
        assert result[key] == package[key]


def test_nationality_update_changes_only_declared_country_and_its_fallback():
    package = _native_package()
    player = package['players'][1]
    # The extra receipt annotation is intentionally retained in the plan.
    player['fact_fallbacks'] = [{'field': 'nationality', 'policy': 'old-default'}, {'field': 'height_cm', 'policy': 'preserve'}]
    plan = plan_for(package); plan['updates'] = []
    change = {'updates': [{'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
        'birth_date': player['facts']['birth_date'], 'before': player['facts']['nationality'], 'after': 'POR'}]}
    before = copy.deepcopy(package)
    # Validate the real recipe without synthetic fallback metadata policies.
    from unittest.mock import patch
    with patch.object(publish.package_v2, 'validate_package'):
        result = publish.updated_package(package, plan, change)
    assert package == before
    assert result['players'][1]['facts']['nationality'] == 'POR'
    assert result['players'][1]['fact_fallbacks'] == [player['fact_fallbacks'][1]]
    result['players'][1]['facts']['nationality'] = player['facts']['nationality']
    result['players'][1]['fact_fallbacks'] = player['fact_fallbacks']
    for key in package.keys() - {'artifacts', 'proofs'}:
        assert result[key] == before[key]


@pytest.mark.parametrize('with_nationality', [False, True])
@pytest.mark.parametrize('with_manager', [False, True])
@pytest.mark.parametrize('with_club', [False, True])
def test_delta_publication_is_immutable_and_honest_about_partial_compile(tmp_path, monkeypatch, with_nationality, with_manager, with_club):
    if with_club and not with_manager: pytest.skip('club rename requires paired coach')
    monkeypatch.setattr(publish, 'ROOT', tmp_path)
    monkeypatch.setattr(publish.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(publish.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    game = tmp_path / 'old-game'
    for name in publish.registry.REQUIRED_GAME_FILES:
        target = game / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'unchanged synthetic content')
    original = _indexed_fdi([(2, '', _dd6361_player_payload(2, role=3))])
    (game / 'DBDAT/JUG98030.FDI').write_bytes(original)
    original_ent = _indexed_fdi([(1, '', _manager_payload() + b'unknown manager tail')])
    if with_manager:
        (game / 'DBDAT/ENT98030.FDI').write_bytes(original_ent)
        def graph(*, eq_path, ent_path):
            data = ent_path.read_bytes()
            entry = publish.IndexedFDIFile.from_bytes(data).entries[0]
            payload = entry.decode_payload(data)
            from scripts.build_2015_english92_release import _read_inner_string
            name, _, _ = _read_inner_string(payload, 7)
            return {1: [{'carrier_id': 307}]}, {1: name}
        monkeypatch.setattr(publish, '_manager_graph', graph)
    package = _native_package()
    original_eq = None
    if with_club:
        from scripts.test_season_historical_club_label_plan_v1 import payload
        from app.editor_actions import _patch_indexed_eq_team_string_payload
        club = package['clubs'][0]
        eq_payload, _ = _patch_indexed_eq_team_string_payload(payload(), short_name=club['name'], full_club_name=club['full_name'])
        original_eq = _indexed_fdi([(307, '', eq_payload)])
        (game / 'DBDAT/EQ98030.FDI').write_bytes(original_eq)
    package_path = tmp_path / 'old-package.json'
    package_path.write_bytes(publish.package_v2.canonical_json_bytes(package))
    inventory = publish.pipeline.build_tree_inventory(game)
    inventory_path = tmp_path / 'old-inventory.json'
    publish.pipeline.write_canonical_json(inventory_path, inventory)
    chain_path, compiler_path = tmp_path / 'old-chain.json', tmp_path / 'old-compiler.json'
    publish.pipeline.write_canonical_json(chain_path, {'historical-test-chain': True})
    publish.pipeline.write_canonical_json(compiler_path, {'historical-test-compiler': True})
    manifest_path = tmp_path / 'old-manifest.json'
    manifest = publish.pipeline.create_release_manifest(season='2014-15',
        verified_base=publish.pipeline.make_verified_base_descriptor(base_id='test-base', tree=game),
        season_document=publish.pipeline.canonical_json_document_descriptor(package_path, document_id='season-package'),
        output_inventory=inventory)
    publish.pipeline.write_canonical_json(manifest_path, manifest)
    release = SimpleNamespace(game_path=game, package_path=package_path, inventory_path=inventory_path,
        build_chain_path=chain_path, compiler_receipt_path=compiler_path, release_manifest_path=manifest_path,
        manifest_sha256=publish.registry.sha256_file(manifest_path), release_id='old',
        locator={'game_inventory_fingerprint': inventory['files_fingerprint'], 'qa_report_path': 'old-qa.json'})
    monkeypatch.setattr(publish.registry, 'load_preferred_release', lambda season: release)
    plan = plan_for(package)
    plan.update(release_id='old', package_sha256=publish.registry.sha256_file(package_path),
                jug_sha256=publish.registry.sha256_file(game / 'DBDAT/JUG98030.FDI'))
    plan_path = tmp_path / 'plan.json'
    publish.pipeline.write_canonical_json(plan_path, plan)
    nationality_path = None
    if with_nationality:
        from scripts import season_package_compiler_v2 as compiler
        monkeypatch.setattr(compiler, '_extract_country_codes_from_textos', lambda path: {'PORTUGAL': 47, 'XXX': 0})
        player = package['players'][1]
        nationality = {'season': '2014-15', 'release_id': 'old',
            'package_sha256': plan['package_sha256'], 'jug_sha256': plan['jug_sha256'],
            'updates': [{'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
                'birth_date': player['facts']['birth_date'], 'before': 'ENG', 'after': 'POR', 'native_country_code': 47}]}
        nationality_path = tmp_path / 'nationality.json'
        publish.pipeline.write_canonical_json(nationality_path, nationality)
    manager_path = None
    if with_manager:
        manager = package['managers'][0]
        manager_plan = {'season': '2014-15', 'release_id': 'old', 'package_sha256': plan['package_sha256'],
            'eq_sha256': publish.registry.sha256_file(game / 'DBDAT/EQ98030.FDI'),
            'ent_sha256': publish.registry.sha256_file(game / 'DBDAT/ENT98030.FDI'),
            'updates': [{'club_id': 'club-307', 'club_carrier_id': 307, 'manager_id': manager['id'], 'carrier_id': 1,
                'before': manager['name'], 'before_policy': manager.get('policy'), 'native_before': 'Old Manager',
                'after': 'Sourced Historical Coach', 'native_after': 'Sourced Historical Coach',
                'evidence': {'raw_sources': []}}]}
        manager_path = tmp_path / 'manager.json'; publish.pipeline.write_canonical_json(manager_path, manager_plan)
    club_path = None
    if with_club:
        from scripts import season_historical_club_label_plan_v1 as labels
        source_path = tmp_path / 'source.json'; publish.pipeline.write_canonical_json(source_path, {'synthetic': True})
        binding = {'release_id': 'old', 'package_sha256': plan['package_sha256'],
            'eq_sha256': manager_plan['eq_sha256'], 'ent_sha256': manager_plan['ent_sha256'],
            'source_row_path': 'source.json', 'source_row_sha256': publish.registry.sha256_file(source_path),
            'original_capture_path': 'source.json', 'original_capture_sha256': publish.registry.sha256_file(source_path)}
        row = {'club_id': club['id'], 'carrier_id': club['carrier_id'], 'before': club['name'],
            'before_full': club['full_name'], 'after': 'Werder Bremen', 'identity_after': 'source-club-werder-bremen',
            'native_before': club['name'], 'native_full_before': club['full_name'], 'native_after': 'Werder Bremen',
            'evidence': {'manager': 'Sourced Historical Coach'}, 'source_selector': {},
            'status': 'source-supported-club-label-mismatch'}
        audit_path = tmp_path / 'audit.json'; publish.pipeline.write_canonical_json(audit_path, {'bindings': binding, 'clubs': [row]})
        club_plan = {**binding, 'schema_version': labels.SCHEMA, 'season': '2014-15', 'source_bindings': binding,
            'audit_path': 'audit.json', 'audit_sha256': publish.registry.sha256_file(audit_path), 'updates': [row]}
        club_path = tmp_path / 'club.json'; publish.pipeline.write_canonical_json(club_path, club_plan)
    result = publish.publish('2014-15', plan_path, release_id='test-role-delta', nationality_plan_path=nationality_path, manager_plan_path=manager_path, club_plan_path=club_path)
    new_game = type(game)(result['game'])
    assert result['changed_players'] == 1
    assert (game / 'DBDAT/JUG98030.FDI').read_bytes() == original
    assert (new_game / 'DBDAT/JUG98030.FDI').stat().st_ino != (game / 'DBDAT/JUG98030.FDI').stat().st_ino
    assert (new_game / 'DBDAT/MINIESC.PKF').stat().st_ino == (game / 'DBDAT/MINIESC.PKF').stat().st_ino
    receipt = json.loads((new_game.parent / 'role-delta-compiler.json').read_text())
    assert receipt['clubs_written'] == int(with_club)
    assert receipt['managers_written'] == int(with_manager)
    assert receipt['compilation_mode'] == ('known-good-baseline-club-and-manager-name-delta' if with_club else ('known-good-baseline-manager-name-delta' if with_manager else ('known-good-baseline-role-and-nationality-delta' if with_nationality else 'known-good-baseline-role-only-delta')))
    if with_manager:
        assert (game / 'DBDAT/ENT98030.FDI').read_bytes() == original_ent
        changed = (new_game / 'DBDAT/ENT98030.FDI').read_bytes()
        entry = publish.IndexedFDIFile.from_bytes(changed).entries[0]
        assert entry.decode_payload(changed).endswith(b'unknown manager tail')
        assert (new_game / 'DBDAT/ENT98030.FDI').stat().st_ino != (game / 'DBDAT/ENT98030.FDI').stat().st_ino
        assert ((new_game / 'DBDAT/EQ98030.FDI').stat().st_ino == (game / 'DBDAT/EQ98030.FDI').stat().st_ino) == (not with_club)
        current = json.loads((new_game.parent / 'season-package.json').read_text())
        assert current['managers'][0]['name'] == 'Sourced Historical Coach'
        if with_club:
            assert current['clubs'][0]['name'] == 'Werder Bremen'
            assert (game / 'DBDAT/EQ98030.FDI').read_bytes() == original_eq
            changed = (new_game / 'DBDAT/EQ98030.FDI').read_bytes()
            entry = publish.IndexedFDIFile.from_bytes(changed).entries[0]
            assert entry.decode_payload(changed).endswith(b'unknown roster manager ratings tail')
    if with_nationality:
        from scripts import season_historical_roster_audit_v1 as audit
        from app.fdi_indexed import IndexedFDIFile
        from app.indexed_jug_roles import read_indexed_native_roles
        new_jug = (new_game / 'DBDAT/JUG98030.FDI').read_bytes()
        payload = IndexedFDIFile.from_bytes(new_jug).entries[0].decode_payload(new_jug)
        end, _ = read_indexed_native_roles(payload, 2)
        assert payload[end + 8] ^ 0x61 == 47
        assert len(receipt['nationality_changes']) == 1
    assert receipt['historical_verification_complete'] is False
    locator = json.loads(publish.registry.locator_path('2014-15', 'test-role-delta').read_text())
    assert locator['attestation_path'] is None
    assert 'qa_report_path' not in locator
