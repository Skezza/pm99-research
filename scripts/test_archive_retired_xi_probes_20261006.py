import json
from types import SimpleNamespace
import pytest
from scripts import archive_retired_xi_probes_20261006 as cleanup


def setup(tmp_path, monkeypatch):
    source = tmp_path / '.local/probes' / cleanup.NAMES[0]
    source.mkdir(parents=True)
    receipts = tmp_path / 'asset-receipts'
    monkeypatch.setattr(cleanup, 'ROOT', tmp_path)
    monkeypatch.setattr(cleanup.old, 'guard_probe', lambda _: source)
    monkeypatch.setattr(cleanup.old, 'RECEIPTS', receipts)
    monkeypatch.setattr(cleanup.registry, 'supported_seasons', lambda: [])
    for asset in cleanup.old.ASSETS:
        path = receipts / cleanup.NAMES[0] / asset / 'receipt.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'archive_verified': True, 'local_removed': True}))
    return source, receipts


def test_only_exact_retired_xi_children(tmp_path, monkeypatch):
    source, _ = setup(tmp_path, monkeypatch)
    assert cleanup.guard(cleanup.NAMES[0]) == source
    with pytest.raises(ValueError, match='exact retired'):
        cleanup.guard('../current-game')


@pytest.mark.parametrize('issue', ['assets-present', 'unverified-archive', 'not-removed'])
def test_separate_asset_archive_is_required(tmp_path, monkeypatch, issue):
    source, receipts = setup(tmp_path, monkeypatch)
    if issue == 'assets-present':
        (source / 'SFX').mkdir()
    else:
        path = receipts / cleanup.NAMES[0] / 'SFX/receipt.json'
        row = json.loads(path.read_text())
        row['archive_verified' if issue == 'unverified-archive' else 'local_removed'] = False
        path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='completed separate archive'):
        cleanup.guard(cleanup.NAMES[0])


@pytest.mark.parametrize('place', ['locator', 'package', 'manifest', 'compiler', 'build-chain'])
def test_current_rebuild_and_release_references_are_protected(tmp_path, monkeypatch, place):
    source, _ = setup(tmp_path, monkeypatch)
    paths = {}
    for key in ('package', 'manifest', 'compiler', 'build-chain'):
        paths[key] = tmp_path / (key + '.json')
        paths[key].write_text(json.dumps({'nested': {'base': str(source / 'DBDAT/JUG98030.FDI')}}
                                        if key == place else {}))
    release = SimpleNamespace(locator={'nested': str(source)} if place == 'locator' else {},
        package_path=paths['package'], release_manifest_path=paths['manifest'],
        compiler_receipt_path=paths['compiler'], build_chain_path=paths['build-chain'])
    monkeypatch.setattr(cleanup.registry, 'supported_seasons', lambda: ['2004-05'])
    monkeypatch.setattr(cleanup.registry, 'load_preferred_release', lambda _: release)
    with pytest.raises(ValueError, match='current release or rebuild input'):
        cleanup.guard(cleanup.NAMES[0])
