import pytest
from scripts.repair_registered_player_identities_v1 import declared_repairs


def test_only_recipe_declared_clones_are_repairable():
    package = {'players': [{'carrier_id': 33191, 'append_from_carrier_id': 7952}]}
    declared_repairs(package, [{'record_id': 33191, 'old_native_id': 7952}])
    for row in ({'record_id': 33192, 'old_native_id': 7952},
                {'record_id': 33191, 'old_native_id': 123}):
        with pytest.raises(ValueError, match='undeclared'):
            declared_repairs(package, [row])


def test_publication_keeps_old_bytes_and_artwork_but_clears_stale_attestation(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from scripts import repair_registered_player_identities_v1 as fix
    from scripts.test_season_package_compiler_v2 import _indexed_fdi

    monkeypatch.setattr(fix, 'ROOT', tmp_path)
    monkeypatch.setattr(fix.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(fix.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    game = tmp_path / 'original-game'
    for name in fix.registry.REQUIRED_GAME_FILES:
        target = game / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'unchanged synthetic game data')
    payload = b'\x40\x00\xdd\x63\x61' + bytes(v ^ 0x61 for v in (7952).to_bytes(2, 'little')) + b'opaque tail'
    jug = game / 'DBDAT/JUG98030.FDI'
    original = _indexed_fdi([(7952, '', payload), (33191, '', payload)])
    jug.write_bytes(original)
    inventory = fix.pipeline.build_tree_inventory(game)
    inventory_path = tmp_path / 'inventory.json'
    fix.pipeline.write_canonical_json(inventory_path, inventory)
    package = tmp_path / 'package.json'
    fix.pipeline.write_canonical_json(package, {'players': [
        {'carrier_id': 33191, 'append_from_carrier_id': 7952}]})
    chain_path = tmp_path / 'chain.json'
    fix.pipeline.write_canonical_json(chain_path, {'stages': [
        {'id': 'portrait-old', 'outputs': {'DBDAT/MINIESC.PKF': fix.registry.sha256_file(game / 'DBDAT/MINIESC.PKF')}}]})
    manifest_path = tmp_path / 'manifest.json'
    fix.pipeline.write_canonical_json(manifest_path, fix.pipeline.create_release_manifest(season='2004-05',
        verified_base=fix.pipeline.make_verified_base_descriptor(base_id='test-base', tree=game),
        season_document=fix.pipeline.canonical_json_document_descriptor(package, document_id='season-package'),
        output_inventory=inventory))
    old = SimpleNamespace(game_path=game, package_path=package, inventory_path=inventory_path,
        build_chain_path=chain_path, release_manifest_path=manifest_path,
        manifest_sha256=fix.registry.sha256_file(manifest_path), release_id='old', locator={
            'game_inventory_fingerprint': inventory['files_fingerprint'],
            'package_canonical_sha256': 'a' * 64, 'attestation_path': 'old-attestation.json',
            'qa_report_path': 'old-qa.json', 'qa_report_sha256': 'b' * 64,
            'portrait_patch_application_path': 'retained-photo-proof.json'})
    monkeypatch.setattr(fix.registry, 'load_preferred_release', lambda season: old)
    result = fix.publish('2004-05', release_id='fixed')
    repaired_game = tmp_path / '.local/season-identity-repairs-v1/2004-05/fixed/game'
    assert result['repaired_players'] == 1
    assert jug.read_bytes() == original
    assert (repaired_game / 'DBDAT/JUG98030.FDI').read_bytes() != original
    assert jug.stat().st_ino != (repaired_game / 'DBDAT/JUG98030.FDI').stat().st_ino
    assert (game / 'DBDAT/MINIESC.PKF').stat().st_ino == (repaired_game / 'DBDAT/MINIESC.PKF').stat().st_ino
    destination = fix.registry.locator_path('2004-05', 'fixed').parent
    locator = json.loads((destination / 'locator.json').read_text())
    assert locator['attestation_path'] is None and locator['qa_status'] == 'not-recorded'
    assert 'qa_report_path' not in locator
    assert locator['portrait_patch_application_path'] == 'retained-photo-proof.json'
    assert json.loads((destination / 'build-chain.json').read_text())['stages'][0]['id'] == 'portrait-old'
