import json
from types import SimpleNamespace

from scripts import pm99_season_qa_v1 as qa


def test_historical_english_input_cannot_override_current_sourced_manager(tmp_path, monkeypatch):
    old = {'carrier_id': 820, 'name': 'Luke Garrard',
        'native_names': {'surname': 'Garrard', 'display_name': 'Garrard'}}
    current = {'carrier_id': 820, 'name': 'Brian Stock',
        'native_names': {'surname': 'Stock', 'display_name': 'Stock'}}
    source = tmp_path / 'english.json'
    source.write_text(json.dumps({'managers': [old]}))
    package = {'managers': [current], 'artifacts': [{'id': 'english-contextual-package-2021-22',
        'relative_path': source.name, 'sha256': qa._sha256(source)}]}
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    (dbdat / 'ENT98030.FDI').write_bytes(b'native')
    monkeypatch.setattr(qa, '_audit_compiled_manager_ownership', lambda *args, **kwargs:
        {'failure_count': 0, 'failures': []})
    monkeypatch.setattr(qa.IndexedFDIFile, 'from_bytes', lambda data: SimpleNamespace(entries=[
        SimpleNamespace(record_id=820, payload_offset=0, payload_length=6)]))
    profile = SimpleNamespace(surname='Stock', display_name='Stock')
    monkeypatch.setattr(qa, 'parse_indexed_ent_manager_profile', lambda *args, **kwargs: profile)
    def run():
        return qa.audit_compiled_managers(package, game=tmp_path, season='2021-22',
            package_path=tmp_path / 'season-package.json')
    report = run()
    assert report['failure_count'] == 0
    assert report['native_alias_checked_count'] == 1
    assert report['historical_input_aliases_not_current_declarations'] == 1
    profile.display_name = 'Wrong'
    assert run()['failure_count'] == 1
    profile.display_name = 'Stock'
    package['managers'] = []
    import pytest
    with pytest.raises(qa.QaError, match='absent from the current recipe'):
        run()
    package['managers'] = [current]
    source.write_text(source.read_text() + ' ')
    with pytest.raises(qa.QaError, match='hash changed'):
        run()


def test_current_2015_english_overlay_is_still_checked(tmp_path, monkeypatch):
    # The active legacy overlay is not an old full-recipe snapshot.
    source = tmp_path / 'english.json'
    source.write_text(json.dumps({'managers': [{'carrier_id': 820, 'name': 'Luke Garrard',
        'native_names': {'surname': 'Garrard', 'display_name': 'Garrard'}}]}))
    package = {'managers': [], 'artifacts': [{'id': 'english-contextual-package-2015-16',
        'relative_path': source.name, 'sha256': qa._sha256(source)}]}
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    (dbdat / 'ENT98030.FDI').write_bytes(b'native')
    monkeypatch.setattr(qa, '_audit_compiled_manager_ownership', lambda *args, **kwargs:
        {'failure_count': 0, 'failures': []})
    monkeypatch.setattr(qa.IndexedFDIFile, 'from_bytes', lambda data: SimpleNamespace(entries=[]))
    report = qa.audit_compiled_managers(package, game=tmp_path, season='2015-16',
        package_path=tmp_path / 'season-package.json')
    assert report['native_alias_failure_count'] == 1
