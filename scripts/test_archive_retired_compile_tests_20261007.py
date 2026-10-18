import json
from types import SimpleNamespace
import pytest
from scripts import archive_retired_compile_tests_20261007 as cleanup

@pytest.mark.parametrize('place', ['locator', 'package', 'manifest', 'compiler', 'chain'])
def test_every_current_reference_location_is_protected(tmp_path, monkeypatch, place):
    source = tmp_path / cleanup.NAMES[0]
    paths = {}
    for key in ('package', 'manifest', 'compiler', 'chain'):
        paths[key] = tmp_path / (key + '.json')
        paths[key].write_text(json.dumps({'nested': [str(source / 'DBDAT/JUG98030.FDI')]}
                                        if key == place else {}))
    release = SimpleNamespace(locator={'input': str(source)} if place == 'locator' else {},
        package_path=paths['package'], release_manifest_path=paths['manifest'],
        compiler_receipt_path=paths['compiler'], build_chain_path=paths['chain'])
    monkeypatch.setattr(cleanup.registry, 'supported_seasons', lambda: ['2007-08'])
    monkeypatch.setattr(cleanup.registry, 'load_preferred_release', lambda _: release)
    with pytest.raises(ValueError, match='references this old test'):
        cleanup.check_references(source)

def test_allowlist_excludes_original_2015_and_current_games():
    assert len(cleanup.NAMES) == 5
    assert all(name.startswith(('2007-08-', '2008-09-')) for name in cleanup.NAMES)

def test_changed_document_invalidates_reference_cache(tmp_path):
    path = tmp_path / 'package.json'
    path.write_text('{}')
    stat = path.stat()
    assert cleanup.references(path, stat.st_mtime_ns, stat.st_size) == ()
    path.write_text(json.dumps({'base': 'protected-test-game'}))
    stat = path.stat()
    assert cleanup.references(path, stat.st_mtime_ns, stat.st_size) == ('protected-test-game',)
