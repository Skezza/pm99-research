import json
from types import SimpleNamespace

import pytest
from scripts import archive_superseded_review_csvs_20261006 as archive


def setup(tmp_path, monkeypatch, reference=None):
    monkeypatch.setattr(archive, 'ROOT', tmp_path)
    source = tmp_path / 'old-review'
    monkeypatch.setattr(archive, 'SOURCE', source)
    monkeypatch.setattr(archive, 'RECEIPT', tmp_path / 'receipt.json')
    monkeypatch.setattr(archive.registry, 'supported_seasons', lambda: ['2000-01'])
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'artifacts': [reference] if reference else []}))
    monkeypatch.setattr(archive.registry, 'load_preferred_release',
        lambda s: SimpleNamespace(locator={}, package_path=package))
    monkeypatch.setattr(archive.registry, 'relative_workspace_path', lambda p: str(p.relative_to(tmp_path)))
    path = source / '2000-01' / 'players.csv'
    path.parent.mkdir(parents=True)
    path.write_text('regenerable,view\n')
    return path


def test_default_never_removes_exports_or_contacts_pi(tmp_path, monkeypatch):
    path = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(archive.archive, 'remote', lambda *a, **k: pytest.fail('read-only default contacted Pi'))
    row = archive.run()
    assert row['file_count'] == 1 and row['local_removed'] is False
    assert path.is_file() and not archive.RECEIPT.exists()


def test_current_recipe_reference_refuses_archive(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, 'old-review/2000-01/players.csv')
    with pytest.raises(ValueError, match='unreferenced'):
        archive.run()


def test_completed_receipt_is_not_overwritten(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    archive.RECEIPT.write_text('{}')
    with pytest.raises(ValueError, match='already exists'):
        archive.run()


def test_additional_root_is_fixed_not_an_arbitrary_deletion_path(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='fixed regenerable CSV allowlist'):
        archive.run(review_root='../../current-game')


def test_allowlisted_old_review_default_remains_read_only(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    name = archive.ADDITIONAL_REVIEW_ROOTS[0]
    path = tmp_path / '.local' / name / '2000-01/players.csv'
    path.parent.mkdir(parents=True)
    path.write_text('old,view\n')
    row = archive.run(review_root=name)
    assert row['file_count'] == 1 and row['local_removed'] is False
    assert path.is_file()
