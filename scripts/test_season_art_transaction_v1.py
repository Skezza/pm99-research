import json
from types import SimpleNamespace

import pytest

from scripts import season_art_transaction_v1 as txn
from scripts import season_visual_patch_v1 as art
from scripts import season_pipeline_v2 as pipeline


def fixture(tmp_path, monkeypatch):
    # Unit tests must not depend on the workstation's current free space.
    # The low-disk negative control overrides this explicitly below.
    monkeypatch.setattr(txn.shutil, 'disk_usage', lambda path: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(txn, 'ROOT', tmp_path)
    monkeypatch.setattr(art, 'ROOT', tmp_path)
    monkeypatch.setattr(art.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(art.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    monkeypatch.setattr(art.registry, 'CATALOG_PATH', tmp_path / 'catalog.json')
    original_load = art.registry.load_catalog
    monkeypatch.setattr(art.registry, 'load_catalog', lambda: original_load(art.registry.CATALOG_PATH))
    game = tmp_path / 'game'
    for name in (*art.registry.REQUIRED_GAME_FILES, 'DBDAT/MINIFOTO.PKF'):
        target = game / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'original-native')
    old = game / 'DBDAT/MINIFOTO/J9600042.BMP'
    old.parent.mkdir()
    old.write_bytes(b'old-face')
    inventory = pipeline.build_tree_inventory(game)
    inventory_path = tmp_path / 'inventory.json'
    art.save(inventory_path, inventory)
    chain = tmp_path / 'chain.json'
    art.save(chain, {'stages': []})
    package = tmp_path / 'package.json'
    art.save(package, {'season': '2014-15'})
    manifest = tmp_path / 'manifest.json'
    art.save(manifest, pipeline.create_release_manifest(season='2014-15',
        verified_base=pipeline.make_verified_base_descriptor(base_id='base', tree=game),
        season_document=pipeline.canonical_json_document_descriptor(package, document_id='season-package'),
        output_inventory=inventory))
    locator = {'release_id': 'old', 'game_inventory_fingerprint': inventory['files_fingerprint']}
    old_locator = art.registry.locator_path('2014-15', 'old')
    old_locator.parent.mkdir(parents=True)
    art.save(old_locator, locator)
    current = SimpleNamespace(game_path=game, inventory_path=inventory_path,
        build_chain_path=chain, release_manifest_path=manifest, release_id='old',
        package_path=package, manifest_sha256=art.sha(manifest), locator=locator)
    monkeypatch.setattr(art.registry, 'load_preferred_release', lambda season: current)
    art.save(art.registry.CATALOG_PATH, {'schema_version': art.registry.CATALOG_SCHEMA,
        'seasons': [{'season': '2014-15', 'release_id': 'old', 'release_manifest_sha256': art.sha(manifest)}]})
    root = tmp_path / 'candidate'
    root.mkdir()
    plan = root / 'plan.json'
    art.save(plan, {'season': '2014-15', 'inputs': {'release_id': 'old', 'package_sha256': art.sha(package)},
                   'no_photo': [{'carrier_id': 42}], 'replacements': []})
    patch = root / 'patch'
    bitmap = patch / 'DBDAT/MINIFOTO/J9600043.BMP'
    bitmap.parent.mkdir(parents=True)
    bitmap.write_bytes(b'new-face')
    art.save(patch / 'receipt.json', {'plan_sha256': art.sha(plan),
        'archive_before_sha256': art.sha(game / 'DBDAT/MINIFOTO.PKF'),
        'outputs': {'DBDAT/MINIFOTO/J9600043.BMP': art.sha(bitmap)}})
    return current, plan, patch


def test_install_has_no_full_game_copy_and_restore_is_exact(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'transaction'
    result = txn.install(plan, patch, root, 'new')
    assert result['registered']
    assert not (root / 'originals/MANAGPRE.EXE').exists()
    assert not (current.game_path / 'DBDAT/MINIFOTO/J9600042.BMP').exists()
    new_locator = json.loads(art.registry.locator_path('2014-15', 'new').read_text())
    assert new_locator['attestation_path'] is None
    assert new_locator['qa_status'] == 'not-recorded'
    txn.restore(root)
    pipeline.assert_tree_matches_inventory(current.game_path, json.loads(current.inventory_path.read_text()))
    assert art.registry.load_catalog()['2014-15']['release_id'] == 'old'


def test_publish_failure_restores_bytes_and_catalog(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise RuntimeError('injected failure')
    monkeypatch.setattr(art, 'publish', fail)
    with pytest.raises(RuntimeError, match='injected failure'):
        txn.install(plan, patch, tmp_path / 'transaction', 'new')
    pipeline.assert_tree_matches_inventory(current.game_path, json.loads(current.inventory_path.read_text()))
    assert art.registry.load_catalog()['2014-15']['release_id'] == 'old'


def test_recovery_rejects_unrelated_changes_and_later_portraits(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'transaction'
    txn.install(plan, patch, root, 'new')
    face = current.game_path / 'DBDAT/MINIFOTO/J9600043.BMP'
    face.write_bytes(b'later-face')
    with pytest.raises(ValueError, match='later artwork'):
        txn.restore(root)
    face.write_bytes(b'new-face')
    (current.game_path / 'MANAGPRE.EXE').write_bytes(b'unrelated-change')
    with pytest.raises(ValueError, match='unrelated game'):
        txn.restore(root)


def test_restore_respects_the_same_season_lock_as_install(tmp_path, monkeypatch):
    import fcntl
    current, plan, patch = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'transaction'
    txn.install(plan, patch, root, 'new')
    lock = tmp_path / '.local/season-art-transactions-v1/locks/2014-15.lock'
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            txn.restore(root)
    assert (current.game_path / 'DBDAT/MINIFOTO/J9600043.BMP').read_bytes() == b'new-face'


def test_restore_refuses_a_running_game(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    root = tmp_path / 'transaction'
    txn.install(plan, patch, root, 'new')
    monkeypatch.setattr(txn, '_active_game', lambda game: True)
    with pytest.raises(ValueError, match='close the game'):
        txn.restore(root)
    assert (current.game_path / 'DBDAT/MINIFOTO/J9600043.BMP').read_bytes() == b'new-face'


def test_low_disk_reserve_stops_before_any_game_mutation(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(txn.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0))
    root = tmp_path / 'transaction'
    with pytest.raises(ValueError, match='disk reserve'):
        txn.install(plan, patch, root, 'new')
    assert not root.exists()
    pipeline.assert_tree_matches_inventory(current.game_path, json.loads(current.inventory_path.read_text()))


def test_artwork_transaction_cannot_replace_executable(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    exe = patch / 'MANAGPRE.EXE'
    exe.write_bytes(b'not-artwork')
    receipt = json.loads((patch / 'receipt.json').read_text())
    receipt['outputs']['MANAGPRE.EXE'] = art.sha(exe)
    txn.atomic_bytes(patch / 'receipt.json', pipeline.canonical_json_bytes(receipt))
    with pytest.raises(ValueError, match='invalid artwork'):
        txn.install(plan, patch, tmp_path / 'transaction', 'new')
    pipeline.assert_tree_matches_inventory(current.game_path, json.loads(current.inventory_path.read_text()))


def test_interrupted_transaction_requires_recovery_before_install(tmp_path, monkeypatch):
    current, plan, patch = fixture(tmp_path, monkeypatch)
    journal = tmp_path / '.local/season-art-transactions-v1/interrupted/2014-15/journal.json'
    journal.parent.mkdir(parents=True)
    art.save(journal, {'state': 'prepared'})
    with pytest.raises(ValueError, match='interrupted'):
        txn.install(plan, patch, tmp_path / 'transaction', 'new')
    pipeline.assert_tree_matches_inventory(current.game_path, json.loads(current.inventory_path.read_text()))
