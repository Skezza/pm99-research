import pytest

from scripts import season_visual_patch_v1 as patch
from scripts import season_pipeline_v2 as pipeline
from app.minifoto_bitmap_archive import encode_obfuscated_bitmap_name


def test_no_photo_changes_only_the_active_directory_byte():
    original = bytearray(120)
    original[7] = 2
    original[8:28] = encode_obfuscated_bitmap_name("J9600042.BMP")
    original[50] = 2
    original[51:71] = encode_obfuscated_bitmap_name("J9600043.BMP")
    changed, offsets = patch.patched_archive(bytes(original), [42])
    assert offsets == {42: [7]}
    assert [i for i, (a, b) in enumerate(zip(original, changed)) if a != b] == [7]
    assert changed[50] == 2


def test_missing_expected_photo_is_rejected():
    with pytest.raises(ValueError, match="no longer active"):
        patch.patched_archive(bytes(120), [42])


def test_no_photo_empty_request_preserves_bytes():
    original = bytes(range(120))
    changed, _ = patch.patched_archive(original, [])
    assert changed == original


def test_artwork_only_check_rejects_database_change(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "JUG98030.FDI").write_bytes(b"original")
    before = pipeline.build_tree_inventory(game)
    (game / "JUG98030.FDI").write_bytes(b"changed")
    after = pipeline.build_tree_inventory(game)
    with pytest.raises(ValueError, match="unrelated files"):
        patch.assert_artwork_only_difference(before, after, ["DBDAT/MINIFOTO.PKF"])


def test_artwork_only_check_allows_one_declared_added_bitmap(tmp_path):
    before = pipeline.build_tree_inventory(tmp_path)
    (tmp_path / "J9600042.BMP").write_bytes(b"bitmap")
    after = pipeline.build_tree_inventory(tmp_path)
    assert patch.assert_artwork_only_difference(before, after, ["J9600042.BMP"])["only_right"] == ["J9600042.BMP"]


def test_only_user_runtime_configuration_drift_is_allowed(tmp_path):
    from types import SimpleNamespace
    game = tmp_path / 'game'
    game.mkdir()
    (game / 'manager.ini').write_bytes(b'fullscreen=0')
    (game / 'MANAGPRE.EXE').write_bytes(b'unchanged')
    inventory = tmp_path / 'inventory.json'
    pipeline.write_canonical_json(inventory, pipeline.build_tree_inventory(game))
    release = SimpleNamespace(game_path=game, inventory_path=inventory)
    (game / 'manager.ini').write_bytes(b'fullscreen=1')
    assert patch.source_inventory(release)[1]['changed'][0]['path'] == 'manager.ini'
    (game / 'MANAGPRE.EXE').write_bytes(b'changed')
    with pytest.raises(ValueError, match='unexpected file changes'):
        patch.source_inventory(release)


def test_later_added_unrelated_file_is_not_treated_as_configuration(tmp_path):
    from types import SimpleNamespace
    inventory = tmp_path / 'inventory.json'
    game = tmp_path / 'game'
    game.mkdir()
    pipeline.write_canonical_json(inventory, pipeline.build_tree_inventory(game))
    (game / 'extra.fdi').write_bytes(b'extra')
    with pytest.raises(ValueError, match='unexpected file changes'):
        patch.source_inventory(SimpleNamespace(game_path=game, inventory_path=inventory))


def test_successive_publications_keep_unique_stages_and_allow_replacing_a_blank(tmp_path, monkeypatch):
    import json
    import shutil
    from types import SimpleNamespace

    monkeypatch.setattr(patch, 'ROOT', tmp_path)
    monkeypatch.setattr(patch.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(patch.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    game = tmp_path / 'base-game'
    for name in patch.registry.REQUIRED_GAME_FILES:
        target = game / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'unchanged-native')
    (game / 'manager.ini').write_bytes(b'fullscreen=0')
    inventory = pipeline.build_tree_inventory(game)
    inventory_path = tmp_path / 'inventory.json'
    patch.save(inventory_path, inventory)
    chain_path = tmp_path / 'chain.json'
    patch.save(chain_path, {'stages': []})
    package = tmp_path / 'package.json'
    patch.save(package, {'season': '2014-15'})
    manifest_path = tmp_path / 'manifest.json'
    patch.save(manifest_path, pipeline.create_release_manifest(season='2014-15',
        verified_base=pipeline.make_verified_base_descriptor(base_id='test-base', tree=game),
        season_document=pipeline.canonical_json_document_descriptor(package, document_id='season-package'),
        output_inventory=inventory))
    current = SimpleNamespace(game_path=game, inventory_path=inventory_path,
        build_chain_path=chain_path, release_manifest_path=manifest_path,
        manifest_sha256=patch.sha(manifest_path), locator={'game_inventory_fingerprint': inventory['files_fingerprint'],
        'required_visual_absent_paths': ['DBDAT/MINIFOTO/J9600042.BMP']})
    monkeypatch.setattr(patch.registry, 'load_preferred_release', lambda season: current)
    # Preserve a user setting without declaring manager.ini a visual bitmap.
    (game / 'manager.ini').write_bytes(b'fullscreen=1')
    for index in (1, 2):
        output = tmp_path / f'patch-{index}/game'
        shutil.copytree(current.game_path, output)
        bitmap = output / 'DBDAT/MINIFOTO/J9600042.BMP'
        bitmap.parent.mkdir(parents=True, exist_ok=True)
        bitmap.write_bytes(f'new-face-{index}'.encode())
        base, _ = patch.source_inventory(current)
        after = pipeline.build_tree_inventory(output)
        patch.save(output.parent / 'visual-patch-application.json', {
            'season': '2014-15', 'registered_base_inventory_fingerprint': current.locator['game_inventory_fingerprint'],
            'base_inventory_fingerprint': base['files_fingerprint'], 'output_inventory': after,
            'plan_sha256': str(index) * 64})
        release_id = f'test-{index}'
        assert patch.publish('2014-15', output, release_id)['registered'] is False
        destination = patch.registry.locator_path('2014-15', release_id).parent
        locator = json.loads((destination / 'locator.json').read_text())
        assert not locator['required_visual_absent_paths']
        assert 'manager.ini' not in locator['required_visual_file_hashes']
        current = SimpleNamespace(game_path=output, inventory_path=destination / 'metadata/output.inventory.json',
            build_chain_path=destination / 'build-chain.json',
            release_manifest_path=destination / 'metadata/season-manifest.json',
            manifest_sha256=patch.sha(destination / 'metadata/season-manifest.json'), locator=locator)
    manifest = json.loads(current.release_manifest_path.read_text())
    assert len({row['id'] for row in manifest['stages']}) == 2
    assert len({row['id'] for row in manifest['external_artifacts']}) == 3
